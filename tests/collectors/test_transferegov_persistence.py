from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands.collect_transferegov_parcerias import (
    TransferegovCollectionSummary,
    _fetch_all_pages,
    execute_controlled_transferegov,
)
from barreiras_collectors.connectors.transferegov import (
    TransferegovError,
    fetch_partnerships_page,
    fetch_proposals_page,
    fetch_resource_distributions_page,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.persistence.models import ArtifactIntegrityError
from barreiras_collectors.persistence.service import (
    TransferegovPersistenceService,
)
from barreiras_collectors.resilience import RetryPolicy


class OneShotTransport:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        return HttpResponse(
            status=200,
            headers={"Content-Type": "application/json", "ETag": '"evidence"'},
            body=self.body,
            final_url=url,
        )


class FakeObjectStore:
    def __init__(self, *, tamper: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.tamper = tamper

    def put_if_absent(self, *, object_key, body, content_type, expected_sha256):
        del content_type
        created = object_key not in self.objects
        self.objects.setdefault(object_key, body)
        return SimpleNamespace(
            sha256=expected_sha256,
            byte_size=len(body),
            created=created,
        )

    def read(self, object_key):
        body = self.objects[object_key]
        return body + b"tampered" if self.tamper else body


class FakeRepository:
    def __init__(self) -> None:
        self.batches = []

    def persist(self, batch):
        self.batches.append(batch)
        return SimpleNamespace(
            collection_run_id="run",
            raw_artifact_id="artifact",
            inserted_records=len(batch.records),
            existing_records=0,
        )


def _body(items: list[dict]) -> bytes:
    return json.dumps(
        {
            "data": items,
            "total_pages": 1,
            "total_items": len(items),
            "page_number": 1,
            "page_size": len(items),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()


def proposal_page():
    return fetch_proposals_page(
        page=1,
        transport=OneShotTransport(
            _body(
                [
                    {
                        "id_proposta": 9274,
                        "cd_ibge_recebedor": 2903201,
                        "nm_municipio_recebedor": "BARREIRAS",
                        "ds_objeto": "Custeio de servicos publicos",
                    }
                ]
            )
        ),
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )


def distribution_page():
    return fetch_resource_distributions_page(
        proposal_id=9274,
        validated_proposal_ids=frozenset({9274}),
        page=1,
        transport=OneShotTransport(
            _body(
                [
                    {
                        "id_distribuicao_recurso_proposta": 14886,
                        "id_proposta": 9274,
                        "in_tipo_distribuicao": "Emenda",
                        "valor_emenda": 250000.0,
                    }
                ]
            )
        ),
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )


def partnership_page():
    return fetch_partnerships_page(
        proposal_id=9274,
        validated_proposal_ids=frozenset({9274}),
        page=1,
        transport=OneShotTransport(
            _body(
                [
                    {
                        "id_parceria": 30785,
                        "id_proposta": 9274,
                        "in_situacao_parceria": "Aprovada",
                    }
                ]
            )
        ),
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )


class TransferegovPersistenceTests(unittest.TestCase):
    def test_persists_each_resource_with_distinct_raw_record_contract(self) -> None:
        repository = FakeRepository()
        service = TransferegovPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        )

        pages = (proposal_page(), distribution_page(), partnership_page())
        for page in pages:
            service.persist(page)

        records = [batch.records[0] for batch in repository.batches]
        self.assertEqual(
            [record.record_type for record in records],
            [
                "transferegov_proposta",
                "transferegov_distribuicao_recurso",
                "transferegov_parceria",
            ],
        )
        self.assertEqual(
            [record.source_record_key for record in records],
            [
                "transferegov:proposta:9274",
                "transferegov:distribuicao:14886",
                "transferegov:parceria:30785",
            ],
        )
        self.assertTrue(
            all(
                batch.object_key.startswith("transferegov/parcerias/")
                for batch in repository.batches
            )
        )

    def test_replay_has_stable_artifact_and_record_idempotency_keys(self) -> None:
        repository = FakeRepository()
        service = TransferegovPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        )
        page = proposal_page()

        service.persist(page)
        service.persist(page)

        first, second = repository.batches
        self.assertEqual(first.object_key, second.object_key)
        self.assertEqual(
            first.artifact_idempotency_key,
            second.artifact_idempotency_key,
        )
        self.assertEqual(
            first.records[0].idempotency_key,
            second.records[0].idempotency_key,
        )

    def test_detects_tampered_storage_before_database_write(self) -> None:
        repository = FakeRepository()
        service = TransferegovPersistenceService(
            object_store=FakeObjectStore(tamper=True),
            repository=repository,
        )

        with self.assertRaises(ArtifactIntegrityError):
            service.persist(proposal_page())
        self.assertEqual(repository.batches, [])

    def test_raw_body_must_still_contain_the_validated_items(self) -> None:
        repository = FakeRepository()
        service = TransferegovPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        )
        page = proposal_page()
        object.__setattr__(page, "items", ({"id_proposta": 9999},))

        with self.assertRaises(ArtifactIntegrityError):
            service.persist(page)
        self.assertEqual(repository.batches, [])


class ControlledTransferegovTests(unittest.TestCase):
    def test_pagination_visits_every_declared_page_and_never_truncates(self) -> None:
        requested: list[int] = []

        def fetch(number: int):
            requested.append(number)
            return SimpleNamespace(total_pages=3)

        pages = tuple(
            _fetch_all_pages(  # type: ignore[arg-type]
                fetch=fetch,
                max_pages=3,
                resource="propostas",
            )
        )

        self.assertEqual(requested, [1, 2, 3])
        self.assertEqual(len(pages), 3)

        with self.assertRaisesRegex(TransferegovError, "limite seguro"):
            tuple(
                _fetch_all_pages(  # type: ignore[arg-type]
                    fetch=lambda _number: SimpleNamespace(total_pages=3),
                    max_pages=2,
                    resource="propostas",
                )
            )

    def test_control_starts_before_authentication_or_external_fetch(self) -> None:
        events: list[str] = []

        class ControlProbe:
            def __enter__(self):
                events.append("started")
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                del exc_type, exc_value, traceback
                events.append("closed")
                return False

            def complete(self, **values):
                events.append(f"completed:{values['outcome'].value}")

        def operation() -> TransferegovCollectionSummary:
            self.assertEqual(events, ["started"])
            events.append("external-setup")
            return TransferegovCollectionSummary(
                proposal_records=1,
                related_records=2,
                preserved_pages=3,
                inserted_records=3,
                existing_records=0,
            )

        execute_controlled_transferegov(
            control=ControlProbe(),  # type: ignore[arg-type]
            operation=operation,
        )

        self.assertEqual(
            events,
            ["started", "external-setup", "completed:complete", "closed"],
        )

    def test_empty_proposal_page_is_explicit_empty_coverage(self) -> None:
        summary = TransferegovCollectionSummary(
            proposal_records=0,
            related_records=0,
            preserved_pages=1,
            inserted_records=0,
            existing_records=0,
        )

        self.assertEqual(summary.outcome, CollectionOutcome.EMPTY)


if __name__ == "__main__":
    unittest.main()
