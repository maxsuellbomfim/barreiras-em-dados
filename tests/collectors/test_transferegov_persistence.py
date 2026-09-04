from __future__ import annotations

import inspect
import json
import logging
import unittest
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands import collect_transferegov_parcerias as command
from barreiras_collectors.commands.collect_transferegov_parcerias import (
    TransferegovCollectionSummary,
    _collect_snapshot,
    _fetch_all_pages,
    build_transferegov_snapshot_fingerprint,
    execute_controlled_transferegov,
)
from barreiras_collectors.connectors.transferegov import (
    TransferegovError,
    fetch_commitments_page,
    fetch_partnerships_page,
    fetch_payable_documents_page,
    fetch_payment_orders_page,
    fetch_proposals_page,
    fetch_resource_distributions_page,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.persistence.models import (
    ArtifactIntegrityError,
    RawRecordEvidence,
)
from barreiras_collectors.persistence.postgres import PostgresCollectionRepository
from barreiras_collectors.persistence.service import (
    TransferegovPersistenceService,
)
from barreiras_collectors.resilience import RetryPolicy

EMPTY_SNAPSHOT_FINGERPRINT = sha256(b"").hexdigest()


def snapshot_records(count: int, namespace: str) -> tuple[RawRecordEvidence, ...]:
    return tuple(
        RawRecordEvidence(
            record_type="transferegov_proposta",
            source_record_key=f"transferegov:proposta:{namespace}-{index}",
            payload_sha256=sha256(f"{namespace}-{index}".encode()).hexdigest(),
        )
        for index in range(count)
    )


def snapshot_fingerprint(records: tuple[RawRecordEvidence, ...]) -> str:
    return build_transferegov_snapshot_fingerprint(
        tuple(
            (row.record_type, row.source_record_key, row.payload_sha256)
            for row in records
        )
    )


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


def commitment_page():
    return fetch_commitments_page(
        partnership_id=30785,
        validated_partnership_ids=frozenset({30785}),
        page=1,
        transport=OneShotTransport(
            _body(
                [
                    {
                        "id_empenho_parceria": 11245,
                        "id_parceria": 30785,
                        "nr_empenho": 2025_493599,
                        "valor_empenho": 5000000.0,
                    }
                ]
            )
        ),
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )


def payable_document_page():
    return fetch_payable_documents_page(
        partnership_id=30785,
        validated_partnership_ids=frozenset({30785}),
        page=1,
        transport=OneShotTransport(
            _body(
                [
                    {
                        "id_documento_habil": 5941,
                        "id_parceria": 30785,
                        "nr_documento_habil": "2025TF860130",
                        "vl_documento_habil": 5000000.0,
                    }
                ]
            )
        ),
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
    )


def payment_order_page():
    return fetch_payment_orders_page(
        document_id=5941,
        validated_document_ids=frozenset({5941}),
        page=1,
        transport=OneShotTransport(
            _body(
                [
                    {
                        "id_op": 5932,
                        "id_documento_habil": 5941,
                        "nr_ordem_pagamento": "2025OP053944",
                        "in_situacao_op": "Paga",
                        "nr_ordem_bancaria": "2025OB055607",
                        "dt_emissao_ordem_bancaria": "2025-10-24",
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

    def test_payment_order_emits_independent_bank_order_from_same_evidence(
        self,
    ) -> None:
        repository = FakeRepository()
        service = TransferegovPersistenceService(
            object_store=FakeObjectStore(),
            repository=repository,
        )

        results = []
        for page in (
            commitment_page(),
            payable_document_page(),
            payment_order_page(),
        ):
            results.append(service.persist(page))

        records = [record for batch in repository.batches for record in batch.records]
        self.assertEqual(
            [record.record_type for record in records],
            [
                "transferegov_empenho",
                "transferegov_documento_habil",
                "transferegov_ordem_pagamento",
                "transferegov_ordem_bancaria",
            ],
        )
        self.assertEqual(
            [record.source_record_key for record in records],
            [
                "transferegov:empenho:11245",
                "transferegov:documento-habil:5941",
                "transferegov:ordem-pagamento:5932",
                "transferegov:ordem-bancaria:2025OB055607",
            ],
        )
        self.assertIs(
            records[-2].payload,
            records[-1].payload,
        )
        self.assertEqual(
            [
                (
                    evidence.record_type,
                    evidence.source_record_key,
                    evidence.payload_sha256,
                )
                for evidence in results[-1].record_evidence
            ],
            [
                (
                    "transferegov_ordem_pagamento",
                    "transferegov:ordem-pagamento:5932",
                    records[-2].payload_sha256,
                ),
                (
                    "transferegov_ordem_bancaria",
                    "transferegov:ordem-bancaria:2025OB055607",
                    records[-1].payload_sha256,
                ),
            ],
        )
        self.assertEqual(
            repository.batches[-1].object_key,
            "transferegov/parcerias/ordens-pagamento-documento/sha256/"
            f"{payment_order_page().body_sha256[:2]}/"
            f"{payment_order_page().body_sha256}.json",
        )

    def test_snapshot_fingerprint_is_order_independent_and_exact(self) -> None:
        rows = (
            ("tipo-b", "chave-2", "b" * 64),
            ("tipo-a", "chave-1", "a" * 64),
        )
        expected = sha256(
            (
                "tipo-a\x1fchave-1\x1f"
                + "a" * 64
                + "\n"
                + "tipo-b\x1fchave-2\x1f"
                + "b" * 64
            ).encode("utf-8")
        ).hexdigest()

        self.assertEqual(
            build_transferegov_snapshot_fingerprint(rows),
            expected,
        )
        self.assertEqual(
            build_transferegov_snapshot_fingerprint(tuple(reversed(rows))),
            expected,
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
    def test_repository_stages_only_minimal_snapshot_evidence(self) -> None:
        calls: list[tuple[str, tuple[object, ...] | None]] = []

        class Result:
            @staticmethod
            def fetchone():
                return {"snapshot_id": "00000000-0000-0000-0000-000000000099"}

        class Connection:
            closed = False

            def transaction(self):
                return self

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                del exc_type, exc_value, traceback
                return False

            def execute(self, query, params=None):
                calls.append((query, params))
                return Result()

            def close(self):
                self.closed = True

        connection = Connection()
        records = snapshot_records(2, "repository")
        fingerprint = snapshot_fingerprint(records)

        snapshot_id = PostgresCollectionRepository(
            lambda: connection  # type: ignore[arg-type]
        ).stage_transferegov_snapshot(
            run_id="00000000-0000-0000-0000-000000000001",
            fiscal_year=2025,
            records=records,
            snapshot_fingerprint=fingerprint,
        )

        self.assertEqual(snapshot_id, "00000000-0000-0000-0000-000000000099")
        stage_call = next(
            (query, params)
            for query, params in calls
            if "source.stage_transferegov_snapshot" in query
        )
        serialized = json.loads(stage_call[1][2])
        self.assertEqual(
            set(serialized[0]),
            {"record_type", "source_record_key", "payload_sha256"},
        )
        self.assertEqual(stage_call[1][3], fingerprint)
        self.assertTrue(connection.closed)

    def test_fiscal_year_range_is_bounded_and_inclusive(self) -> None:
        self.assertTrue(hasattr(command, "validate_fiscal_year_range"))
        validate = command.validate_fiscal_year_range

        self.assertEqual(
            validate(2021, 2026, current_year=2026),
            tuple(range(2021, 2027)),
        )
        for values in ((2020, 2026), (2025, 2024), (2021, 2027)):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    validate(*values, current_year=2026)

    def test_yearly_backfill_attempts_remaining_years_before_reporting_failure(
        self,
    ) -> None:
        self.assertTrue(hasattr(command, "execute_yearly_backfill"))
        attempted: list[int] = []
        related_control_years: list[int] = []

        class ControlProbe:
            run_id = "00000000-0000-0000-0000-000000000001"

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                del exc_type, exc_value, traceback
                return False

            def complete(self, **_values):
                return None

        def operation_factory(year: int):
            def operation() -> TransferegovCollectionSummary:
                attempted.append(year)
                if year == 2022:
                    raise RuntimeError("indisponivel")
                return TransferegovCollectionSummary(
                    proposal_records=0,
                    related_records=0,
                    preserved_pages=1,
                    inserted_records=0,
                    existing_records=0,
                    manifest_records=0,
                    snapshot_fingerprint=EMPTY_SNAPSHOT_FINGERPRINT,
                    snapshot_records=(),
                )

            return operation

        with self.assertRaisesRegex(TransferegovError, "2022"):
            staged_years: list[int] = []
            command.execute_yearly_backfill(
                fiscal_years=(2021, 2022, 2023),
                control_factory=lambda _year: ControlProbe(),
                operation_factory=operation_factory,
                logger=logging.getLogger("test-transferegov-backfill"),
                related_control_factory=lambda year: (
                    related_control_years.append(year) or {}
                ),
                snapshot_stager=lambda _run_id, year, _records, _fingerprint: (
                    staged_years.append(year)
                ),
            )

        self.assertEqual(attempted, [2021, 2022, 2023])
        self.assertEqual(related_control_years, [2021, 2022, 2023])
        self.assertEqual(staged_years, [2021, 2023])

    def test_snapshot_walks_from_partnership_to_bank_order_without_skipping_stage(
        self,
    ) -> None:
        self.assertIn("fiscal_year", inspect.signature(_collect_snapshot).parameters)

        def page(endpoint: str, items: list[dict]):
            return SimpleNamespace(
                endpoint_code=endpoint,
                items=tuple(items),
                total_pages=1,
                cursor={"page": 1},
                body_sha256=f"{len(endpoint):064x}",
            )

        class ServiceProbe:
            def __init__(self) -> None:
                self.endpoints: list[str] = []

            def persist(self, collected_page):
                self.endpoints.append(collected_page.endpoint_code)
                inserted = len(collected_page.items)
                contracts = {
                    "propostas-barreiras": (
                        "transferegov_proposta",
                        "id_proposta",
                        "proposta",
                    ),
                    "distribuicoes-proposta": (
                        "transferegov_distribuicao_recurso",
                        "id_distribuicao_recurso_proposta",
                        "distribuicao",
                    ),
                    "parcerias-proposta": (
                        "transferegov_parceria",
                        "id_parceria",
                        "parceria",
                    ),
                    "empenhos-parceria": (
                        "transferegov_empenho",
                        "id_empenho_parceria",
                        "empenho",
                    ),
                    "documentos-habeis-parceria": (
                        "transferegov_documento_habil",
                        "id_documento_habil",
                        "documento-habil",
                    ),
                    "ordens-pagamento-documento": (
                        "transferegov_ordem_pagamento",
                        "id_op",
                        "ordem-pagamento",
                    ),
                }
                record_type, identifier_field, key_label = contracts[
                    collected_page.endpoint_code
                ]
                evidence = [
                    SimpleNamespace(
                        record_type=record_type,
                        source_record_key=(
                            f"transferegov:{key_label}:{item[identifier_field]}"
                        ),
                        payload_sha256=sha256(
                            json.dumps(item, sort_keys=True).encode("utf-8")
                        ).hexdigest(),
                    )
                    for item in collected_page.items
                ]
                if collected_page.endpoint_code == "ordens-pagamento-documento":
                    inserted += sum(
                        bool(item.get("nr_ordem_bancaria"))
                        for item in collected_page.items
                    )
                    evidence.extend(
                        SimpleNamespace(
                            record_type="transferegov_ordem_bancaria",
                            source_record_key=(
                                "transferegov:ordem-bancaria:"
                                f"{item['nr_ordem_bancaria']}"
                            ),
                            payload_sha256=sha256(
                                json.dumps(item, sort_keys=True).encode("utf-8")
                            ).hexdigest(),
                        )
                        for item in collected_page.items
                        if item.get("nr_ordem_bancaria")
                    )
                return SimpleNamespace(
                    inserted_records=inserted,
                    existing_records=0,
                    record_evidence=tuple(evidence),
                )

        service = ServiceProbe()
        with (
            patch(
                "barreiras_collectors.commands.collect_transferegov_parcerias."
                "fetch_proposals_page",
                return_value=page(
                    "propostas-barreiras",
                    [{"id_proposta": 30854}],
                ),
            ) as proposals,
            patch(
                "barreiras_collectors.commands.collect_transferegov_parcerias."
                "fetch_resource_distributions_page",
                return_value=page(
                    "distribuicoes-proposta",
                    [{"id_distribuicao_recurso_proposta": 43389}],
                ),
            ),
            patch(
                "barreiras_collectors.commands.collect_transferegov_parcerias."
                "fetch_partnerships_page",
                return_value=page(
                    "parcerias-proposta",
                    [{"id_parceria": 30785}],
                ),
            ),
            patch(
                "barreiras_collectors.commands.collect_transferegov_parcerias."
                "fetch_commitments_page",
                return_value=page(
                    "empenhos-parceria",
                    [{"id_empenho_parceria": 11245}],
                ),
            ) as commitments,
            patch(
                "barreiras_collectors.commands.collect_transferegov_parcerias."
                "fetch_payable_documents_page",
                return_value=page(
                    "documentos-habeis-parceria",
                    [{"id_documento_habil": 5941}],
                ),
            ) as documents,
            patch(
                "barreiras_collectors.commands.collect_transferegov_parcerias."
                "fetch_payment_orders_page",
                return_value=page(
                    "ordens-pagamento-documento",
                    [
                        {
                            "id_op": 5932,
                            "nr_ordem_bancaria": "2025OB055607",
                        }
                    ],
                ),
            ) as payment_orders,
        ):
            summary = _collect_snapshot(
                service=service,  # type: ignore[arg-type]
                fiscal_year=2025,
                page_size=500,
                max_pages=3,
                logger=logging.getLogger("test-transferegov-stages"),
            )

        self.assertEqual(
            service.endpoints,
            [
                "propostas-barreiras",
                "distribuicoes-proposta",
                "parcerias-proposta",
                "empenhos-parceria",
                "documentos-habeis-parceria",
                "ordens-pagamento-documento",
            ],
        )
        self.assertEqual(summary.observed_records, 7)
        self.assertEqual(summary.distribution_records, 1)
        self.assertEqual(summary.partnership_records, 1)
        self.assertEqual(summary.commitment_records, 1)
        self.assertEqual(summary.payable_document_records, 1)
        self.assertEqual(summary.payment_order_records, 1)
        self.assertEqual(summary.bank_order_records, 1)
        self.assertEqual(proposals.call_args.kwargs["page_size"], 500)
        self.assertEqual(proposals.call_args.kwargs["fiscal_year"], 2025)
        self.assertEqual(commitments.call_args.kwargs["page_size"], 200)
        self.assertEqual(documents.call_args.kwargs["page_size"], 200)
        self.assertEqual(payment_orders.call_args.kwargs["page_size"], 200)
        self.assertEqual(commitments.call_args.kwargs["partnership_id"], 30785)
        self.assertEqual(documents.call_args.kwargs["partnership_id"], 30785)
        self.assertEqual(payment_orders.call_args.kwargs["document_id"], 5941)

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
        self.assertIn(
            "fiscal_year",
            inspect.signature(execute_controlled_transferegov).parameters,
        )
        events: list[str] = []
        completion: dict[str, object] = {}

        class ControlProbe:
            run_id = "00000000-0000-0000-0000-000000000001"

            def __enter__(self):
                events.append("started")
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                del exc_type, exc_value, traceback
                events.append("closed")
                return False

            def complete(self, **values):
                completion.update(values)
                events.append(f"completed:{values['outcome'].value}")

        def operation() -> TransferegovCollectionSummary:
            self.assertEqual(events, ["started"])
            events.append("external-setup")
            records = snapshot_records(3, "control")
            return TransferegovCollectionSummary(
                proposal_records=1,
                related_records=2,
                preserved_pages=3,
                inserted_records=3,
                existing_records=0,
                manifest_records=3,
                snapshot_fingerprint=snapshot_fingerprint(records),
                snapshot_records=records,
            )

        execute_controlled_transferegov(
            control=ControlProbe(),  # type: ignore[arg-type]
            fiscal_year=2025,
            operation=operation,
            snapshot_stager=lambda run_id, year, records, fingerprint: (
                self.assertEqual(
                    (
                        run_id,
                        year,
                        len(records),
                        fingerprint,
                    ),
                    (
                        "00000000-0000-0000-0000-000000000001",
                        2025,
                        3,
                        snapshot_fingerprint(snapshot_records(3, "control")),
                    ),
                ),
                events.append("snapshot-staged"),
            )[-1],
        )

        self.assertEqual(
            events,
            [
                "started",
                "external-setup",
                "snapshot-staged",
                "completed:complete",
                "closed",
            ],
        )
        self.assertEqual(completion["checkpoint"]["fiscal_year"], 2025)
        self.assertEqual(completion["metrics"]["fiscal_year"], 2025)

    def test_empty_proposal_page_is_explicit_empty_coverage(self) -> None:
        summary = TransferegovCollectionSummary(
            proposal_records=0,
            related_records=0,
            preserved_pages=1,
            inserted_records=0,
            existing_records=0,
            manifest_records=0,
            snapshot_fingerprint=EMPTY_SNAPSHOT_FINGERPRINT,
            snapshot_records=(),
        )

        self.assertEqual(summary.outcome, CollectionOutcome.EMPTY)

    def test_related_controls_start_before_fetch_and_close_per_endpoint(self) -> None:
        events: list[str] = []
        completions: dict[str, dict[str, object]] = {}

        class ControlProbe:
            def __init__(self, endpoint: str) -> None:
                self.endpoint = endpoint

            @property
            def run_id(self) -> str:
                return f"run-{self.endpoint}"

            def __enter__(self):
                events.append(f"started:{self.endpoint}")
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                del exc_type, exc_value, traceback
                events.append(f"closed:{self.endpoint}")
                return False

            def complete(self, **values):
                completions[self.endpoint] = values
                events.append(f"completed:{self.endpoint}")

        endpoint_records = {
            "distribuicoes-proposta": 2,
            "parcerias-proposta": 0,
            "empenhos-parceria": 4,
            "documentos-habeis-parceria": 0,
            "ordens-pagamento-documento": 3,
        }
        primary = ControlProbe("propostas-barreiras")
        related = {endpoint: ControlProbe(endpoint) for endpoint in endpoint_records}

        def operation() -> TransferegovCollectionSummary:
            self.assertEqual(
                set(events),
                {
                    "started:propostas-barreiras",
                    *(f"started:{endpoint}" for endpoint in endpoint_records),
                },
            )
            records = snapshot_records(10, "related")
            return TransferegovCollectionSummary(
                proposal_records=1,
                related_records=2,
                preserved_pages=6,
                inserted_records=10,
                existing_records=0,
                manifest_records=10,
                snapshot_fingerprint=snapshot_fingerprint(records),
                snapshot_records=records,
                distribution_records=2,
                partnership_records=0,
                commitment_records=4,
                payable_document_records=0,
                payment_order_records=3,
            )

        execute_controlled_transferegov(
            control=primary,  # type: ignore[arg-type]
            related_controls=related,  # type: ignore[arg-type]
            fiscal_year=2026,
            operation=operation,
            snapshot_stager=lambda *_values: events.append("snapshot-staged"),
        )

        self.assertEqual(
            completions["distribuicoes-proposta"]["observed_records"],
            2,
        )
        self.assertEqual(
            completions["parcerias-proposta"]["outcome"],
            CollectionOutcome.EMPTY,
        )
        self.assertEqual(
            completions["empenhos-parceria"]["observed_records"],
            4,
        )
        self.assertEqual(
            completions["documentos-habeis-parceria"]["outcome"],
            CollectionOutcome.EMPTY,
        )
        self.assertEqual(
            completions["ordens-pagamento-documento"]["observed_records"],
            3,
        )
        self.assertEqual(
            events.index("completed:propostas-barreiras"),
            max(events.index(f"completed:{endpoint}") for endpoint in endpoint_records)
            + 1,
        )

    def test_failure_is_visible_to_every_related_control(self) -> None:
        failures: dict[str, type[BaseException] | None] = {}

        class ControlProbe:
            def __init__(self, endpoint: str) -> None:
                self.endpoint = endpoint

            @property
            def run_id(self) -> str:
                return f"run-{self.endpoint}"

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                del exc_value, traceback
                failures[self.endpoint] = exc_type
                return False

            def complete(self, **_values):
                raise AssertionError("A cobertura nao pode ser concluida apos falha.")

        primary = ControlProbe("propostas-barreiras")
        related = {
            endpoint: ControlProbe(endpoint)
            for endpoint in (
                "distribuicoes-proposta",
                "parcerias-proposta",
                "empenhos-parceria",
                "documentos-habeis-parceria",
                "ordens-pagamento-documento",
            )
        }

        with self.assertRaisesRegex(RuntimeError, "fonte indisponivel"):
            execute_controlled_transferegov(
                control=primary,  # type: ignore[arg-type]
                related_controls=related,  # type: ignore[arg-type]
                fiscal_year=2026,
                operation=lambda: (_ for _ in ()).throw(
                    RuntimeError("fonte indisponivel")
                ),
                snapshot_stager=lambda *_values: self.fail(
                    "Uma coleta falha não pode materializar snapshot."
                ),
            )

        self.assertEqual(
            failures,
            {
                "propostas-barreiras": RuntimeError,
                **{endpoint: RuntimeError for endpoint in related},
            },
        )


if __name__ == "__main__":
    unittest.main()
