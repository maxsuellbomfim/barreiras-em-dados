from __future__ import annotations

import logging
import unittest
from datetime import date

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


if __name__ == "__main__":
    unittest.main()
