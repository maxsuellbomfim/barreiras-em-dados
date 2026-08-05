from __future__ import annotations

import logging
import unittest
from datetime import date
from urllib.error import URLError

import barreiras_collectors.commands.collect_direct_diary as direct_diary_command
import barreiras_collectors.connectors.direct_diary as direct_diary
from barreiras_collectors.commands.collect_direct_diary import (
    execute_controlled_direct_diary,
)
from barreiras_collectors.connectors.direct_diary import (
    DirectEdition,
    EditionNotFoundError,
    collect_editions,
    edition_url,
    fetch_edition,
)
from barreiras_collectors.connectors.gazette_documents import (
    GazetteDocumentClient,
)
from barreiras_collectors.connectors.querido_diario import PermanentHttpError
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.persistence.postgres import PostgresCollectionRepository
from barreiras_collectors.resilience import RetryPolicy

TODAY = date(2026, 8, 1)


class MapTransport:
    """Devolve 200 para URLs conhecidas e 404 para o resto."""

    def __init__(self, bodies: dict[str, bytes]) -> None:
        self.bodies = bodies
        self.requests: list[str] = []

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.requests.append(url)
        body = self.bodies.get(url)
        if body is None:
            return HttpResponse(
                status=404,
                headers={},
                body=b"nao encontrado",
                final_url=url,
            )
        return HttpResponse(
            status=200,
            headers={"Content-Type": "application/pdf"},
            body=body,
            final_url=url,
        )


class RedirectMapTransport(MapTransport):
    """Simula o redirecionamento do catálogo para o nome real do PDF."""

    def __init__(self, responses: dict[str, tuple[bytes, str]]) -> None:
        super().__init__({})
        self.responses = responses

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.requests.append(url)
        response = self.responses.get(url)
        if response is None:
            return HttpResponse(
                status=404,
                headers={},
                body=b"nao encontrado",
                final_url=url,
            )
        body, final_url = response
        return HttpResponse(
            status=200,
            headers={"Content-Type": "application/pdf"},
            body=body,
            final_url=final_url,
        )


class TimeoutTransport(MapTransport):
    """Simula indisponibilidade transitória do servidor do Diário."""

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.requests.append(url)
        raise URLError(TimeoutError("timed out"))


class NoopRateLimiter:
    def acquire(self) -> None:
        return None


def make_client(bodies: dict[str, bytes]) -> GazetteDocumentClient:
    return GazetteDocumentClient(
        max_document_bytes=1024,
        transport=MapTransport(bodies),
        rate_limiter=NoopRateLimiter(),  # type: ignore[arg-type]
        retry_policy=RetryPolicy(max_attempts=2),
        sleep=lambda _seconds: None,
    )


def pdf(edition: int) -> bytes:
    return b"%PDF-1.7 edicao " + str(edition).encode()


class FetchEditionTests(unittest.TestCase):
    def test_fetches_current_year_edition(self) -> None:
        client = make_client({edition_url(2026, 4671): pdf(4671)})

        edition = fetch_edition(client, 4671, today=TODAY)

        self.assertEqual(edition.edition_number, 4671)
        self.assertEqual(edition.year, 2026)
        self.assertTrue(edition.document.raw_body.startswith(b"%PDF-"))

    def test_falls_back_to_previous_year(self) -> None:
        client = make_client({edition_url(2025, 4600): pdf(4600)})

        edition = fetch_edition(client, 4600, today=TODAY)

        self.assertEqual(edition.year, 2025)

    def test_missing_in_both_years_is_cursor_end(self) -> None:
        client = make_client({})

        with self.assertRaises(EditionNotFoundError):
            fetch_edition(client, 4700, today=TODAY)

    def test_non_404_permanent_error_propagates(self) -> None:
        class ForbiddenTransport(MapTransport):
            def get(self, url, **kwargs):
                return HttpResponse(
                    status=403,
                    headers={},
                    body=b"bloqueado",
                    final_url=url,
                )

        client = GazetteDocumentClient(
            max_document_bytes=1024,
            transport=ForbiddenTransport({}),
            rate_limiter=NoopRateLimiter(),  # type: ignore[arg-type]
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=lambda _seconds: None,
        )

        with self.assertRaises(PermanentHttpError):
            fetch_edition(client, 4700, today=TODAY)

    def test_direct_collector_rejects_unrelated_artifact_mirrors(self) -> None:
        client = GazetteDocumentClient(
            max_document_bytes=1024,
            allowed_hosts=direct_diary.DIRECT_DIARY_ALLOWED_HOSTS,
            transport=MapTransport({}),
            rate_limiter=NoopRateLimiter(),  # type: ignore[arg-type]
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
        )

        try:
            client.fetch(
                "https://data.queridodiario.ok.org.br/arquivo.pdf",
                role="pdf",
            )
        except Exception as error:
            self.assertIsInstance(error, ValueError)
        else:
            self.fail("o espelho não relacionado foi aceito")


class CollectEditionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.persisted: list[DirectEdition] = []
        self.logger = logging.getLogger("test-direct-diary")

    def persist(self, edition: DirectEdition) -> None:
        self.persisted.append(edition)

    def test_collects_sequential_editions_until_404(self) -> None:
        client = make_client(
            {
                edition_url(2026, 4671): pdf(4671),
                edition_url(2026, 4672): pdf(4672),
            }
        )

        persisted, exhausted = collect_editions(
            client,
            self.persist,
            start_edition=4671,
            limit=10,
            today=TODAY,
            logger=self.logger,
        )

        self.assertEqual(persisted, 2)
        self.assertTrue(exhausted)
        self.assertEqual(
            [edition.edition_number for edition in self.persisted],
            [4671, 4672],
        )

    def test_zero_new_editions_is_explicit_not_an_error(self) -> None:
        persisted, exhausted = collect_editions(
            make_client({}),
            self.persist,
            start_edition=4704,
            limit=5,
            today=TODAY,
            logger=self.logger,
        )

        self.assertEqual(persisted, 0)
        self.assertTrue(exhausted)
        self.assertEqual(self.persisted, [])

    def test_stops_at_limit_without_exhausting_cursor(self) -> None:
        bodies = {
            edition_url(2026, number): pdf(number)
            for number in range(4671, 4681)
        }

        persisted, exhausted = collect_editions(
            make_client(bodies),
            self.persist,
            start_edition=4671,
            limit=3,
            today=TODAY,
            logger=self.logger,
        )

        self.assertEqual(persisted, 3)
        self.assertFalse(exhausted)

    def test_transient_timeout_defers_probe_without_aborting_pipeline(self) -> None:
        client = GazetteDocumentClient(
            max_document_bytes=1024,
            transport=TimeoutTransport({}),
            rate_limiter=NoopRateLimiter(),  # type: ignore[arg-type]
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
        )

        persisted, exhausted = collect_editions(
            client,
            self.persist,
            start_edition=4707,
            limit=3,
            today=TODAY,
            logger=self.logger,
        )

        self.assertEqual(persisted, 0)
        self.assertFalse(exhausted)
        self.assertEqual(self.persisted, [])

    def test_catalog_target_follows_extra_edition_redirect(self) -> None:
        """A edição 4704 existe com nome não canônico e deve ser preservada."""
        target_type = getattr(direct_diary, "DirectEditionTarget", None)
        collect_targets = getattr(direct_diary, "collect_catalog_editions", None)
        self.assertTrue(callable(target_type), "falta o contrato do alvo oficial")
        self.assertTrue(
            callable(collect_targets),
            "falta a coleta orientada pelas edições existentes no catálogo",
        )

        targets = tuple(
            target_type(
                edition_number=number,
                year=2026,
                publication_url=(
                    "https://pmbarreiras.diariomtransparente.com.br/"
                    f"publicacao?referencia={reference}"
                ),
            )
            for number, reference in ((4704, "16976"), (4705, "16978"), (4706, "16980"))
        )
        extra_edition_url = (
            "https://barreiras.ba.gov.br/diario/pdf/2026/"
            "diario4704-edicaoextra.pdf"
        )
        responses = {
            targets[0].publication_url: (pdf(4704), extra_edition_url),
            targets[1].publication_url: (
                pdf(4705),
                edition_url(2026, 4705),
            ),
            targets[2].publication_url: (
                pdf(4706),
                edition_url(2026, 4706),
            ),
        }
        client = GazetteDocumentClient(
            max_document_bytes=1024,
            allowed_hosts=frozenset(
                {
                    "pmbarreiras.diariomtransparente.com.br",
                    "barreiras.ba.gov.br",
                }
            ),
            transport=RedirectMapTransport(responses),
            rate_limiter=NoopRateLimiter(),  # type: ignore[arg-type]
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=lambda _seconds: None,
        )

        persisted, unavailable = collect_targets(
            client,
            self.persist,
            targets=targets,
            logger=self.logger,
        )

        self.assertEqual(persisted, 3)
        self.assertEqual(unavailable, ())
        self.assertEqual(
            [edition.edition_number for edition in self.persisted],
            [4704, 4705, 4706],
        )
        self.assertEqual(self.persisted[0].document.final_url, extra_edition_url)


class ControlledDirectCollectionTests(unittest.TestCase):
    def test_control_starts_before_external_setup_and_records_coverage(self) -> None:
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

        def operation() -> tuple[int, bool, int]:
            if events != ["started"]:
                raise AssertionError("controle deve iniciar antes do setup externo")
            events.append("external-setup")
            return (0, True, 4704)

        result = execute_controlled_direct_diary(
            control=ControlProbe(),  # type: ignore[arg-type]
            operation=operation,
        )

        self.assertEqual(result, (0, True, 4704))
        self.assertEqual(
            events,
            ["started", "external-setup", "completed:empty", "closed"],
        )

    def test_external_setup_failure_is_seen_by_control(self) -> None:
        events: list[str] = []

        class ControlProbe:
            def __enter__(self):
                events.append("started")
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                del traceback
                events.append(f"failed:{exc_type.__name__}:{exc_value}")
                return False

            def complete(self, **values):
                raise AssertionError(f"não deveria concluir: {values}")

        def failing_setup() -> tuple[int, bool, int]:
            raise RuntimeError("falha de autenticação")

        with self.assertRaisesRegex(RuntimeError, "autenticação"):
            execute_controlled_direct_diary(
                control=ControlProbe(),  # type: ignore[arg-type]
                operation=failing_setup,
            )

        self.assertEqual(
            events,
            ["started", "failed:RuntimeError:falha de autenticação"],
        )
    def test_known_catalog_gap_records_partial_coverage(self) -> None:
        events: list[str] = []

        class ControlProbe:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                del exc_type, exc_value, traceback
                return False

            def complete(self, **values):
                events.append(values["outcome"].value)

        result = direct_diary_command.DirectDiaryRunResult(
            persisted=2,
            catalog_persisted=2,
            probe_persisted=0,
            cursor_exhausted=True,
            next_edition=4707,
            unavailable_catalog_editions=(4704,),
        )

        execute_controlled_direct_diary(
            control=ControlProbe(),  # type: ignore[arg-type]
            operation=lambda: result,
        )

        self.assertEqual(events, ["partial"])


class CatalogTargetRepositoryTests(unittest.TestCase):
    def test_returns_unpreserved_catalog_editions_as_explicit_targets(self) -> None:
        rows = iter(
            (
                {
                    "edition_number": 4706,
                    "edition_year": 2026,
                    "publication_url": (
                        "https://pmbarreiras.diariomtransparente.com.br/"
                        "publicacao?referencia=16980"
                    ),
                },
                {
                    "edition_number": 4705,
                    "edition_year": 2026,
                    "publication_url": (
                        "https://pmbarreiras.diariomtransparente.com.br/"
                        "publicacao?referencia=16978"
                    ),
                },
            )
        )

        class Result:
            def fetchone(self):
                return next(rows, None)

        class Connection:
            def __init__(self) -> None:
                self.params = None
                self.closed = False

            def execute(self, query, params=None):
                del query
                self.params = params
                return Result()

            def close(self):
                self.closed = True

        connection = Connection()
        repository = PostgresCollectionRepository(lambda: connection)  # type: ignore[arg-type]
        pending = getattr(repository, "pending_direct_catalog_editions", None)
        self.assertTrue(
            callable(pending),
            "o repositório ainda não expõe as edições do catálogo sem PDF",
        )

        targets = pending(6)

        self.assertEqual([target.edition_number for target in targets], [4706, 4705])
        self.assertEqual(targets[0].year, 2026)
        self.assertEqual(connection.params, (6,))
        self.assertTrue(connection.closed)


class DirectDiaryRunTests(unittest.TestCase):
    def test_run_preserves_catalog_targets_before_probing_the_next_number(self) -> None:
        run_collection = getattr(
            direct_diary_command,
            "collect_direct_diary_run",
            None,
        )
        self.assertTrue(
            callable(run_collection),
            "falta a orquestração catálogo -> PDF -> próxima edição",
        )
        targets = (
            direct_diary.DirectEditionTarget(
                edition_number=4704,
                year=2026,
                publication_url=(
                    "https://pmbarreiras.diariomtransparente.com.br/"
                    "publicacao?referencia=16976"
                ),
            ),
            direct_diary.DirectEditionTarget(
                edition_number=4705,
                year=2026,
                publication_url=(
                    "https://pmbarreiras.diariomtransparente.com.br/"
                    "publicacao?referencia=16978"
                ),
            ),
            direct_diary.DirectEditionTarget(
                edition_number=4706,
                year=2026,
                publication_url=(
                    "https://pmbarreiras.diariomtransparente.com.br/"
                    "publicacao?referencia=16980"
                ),
            ),
        )
        responses = {
            targets[0].publication_url: (
                pdf(4704),
                "https://barreiras.ba.gov.br/diario/pdf/2026/"
                "diario4704-edicaoextra.pdf",
            ),
            targets[1].publication_url: (
                pdf(4705),
                edition_url(2026, 4705),
            ),
            targets[2].publication_url: (
                pdf(4706),
                edition_url(2026, 4706),
            ),
        }
        client = GazetteDocumentClient(
            max_document_bytes=1024,
            allowed_hosts=direct_diary.DIRECT_DIARY_ALLOWED_HOSTS,
            transport=RedirectMapTransport(responses),
            rate_limiter=NoopRateLimiter(),  # type: ignore[arg-type]
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=lambda _seconds: None,
        )

        class Repository:
            def pending_direct_catalog_editions(self, limit):
                self.target_limit = limit
                return targets

            def next_direct_edition_number(self, first_edition):
                self.first_edition = first_edition
                return 4707

        persisted: list[DirectEdition] = []
        repository = Repository()

        result = run_collection(
            repository=repository,
            client=client,
            persist=persisted.append,
            first_edition=4600,
            limit=6,
            today=TODAY,
            logger=logging.getLogger("test-direct-diary-run"),
        )

        self.assertEqual(result.persisted, 3)
        self.assertEqual(result.catalog_persisted, 3)
        self.assertEqual(result.probe_persisted, 0)
        self.assertTrue(result.cursor_exhausted)
        self.assertEqual(result.next_edition, 4707)
        self.assertEqual(result.unavailable_catalog_editions, ())
        self.assertEqual(
            [edition.edition_number for edition in persisted],
            [4704, 4705, 4706],
        )


if __name__ == "__main__":
    unittest.main()
