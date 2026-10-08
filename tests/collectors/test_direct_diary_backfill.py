from __future__ import annotations

import logging
import unittest
from datetime import date

from barreiras_collectors.collection_control import CollectionControl, CollectionOutcome
from barreiras_collectors.commands.collect_direct_diary_backfill import (
    parse_years,
    run_backfill,
)
from barreiras_collectors.connectors.direct_diary import (
    BackfillResult,
    collect_missing_editions,
    edition_url,
    fetch_edition_in_years,
)
from barreiras_collectors.connectors.gazette_documents import GazetteDocumentClient
from barreiras_collectors.persistence.postgres import PostgresCollectionRepository
from barreiras_collectors.resilience import RetryPolicy

from tests.collectors.test_direct_diary import (
    MapTransport,
    NoopRateLimiter,
    TimeoutTransport,
)

YEARS = (2021, 2022, 2023)
LOGGER = logging.getLogger("test-direct-diary-backfill")


def make_client(transport) -> GazetteDocumentClient:
    return GazetteDocumentClient(
        max_document_bytes=1_000_000,
        allowed_hosts=frozenset({"barreiras.ba.gov.br", "www.barreiras.ba.gov.br"}),
        requests_per_minute=600,
        timeout_seconds=1,
        retry_policy=RetryPolicy(max_attempts=1),
        transport=transport,
        rate_limiter=NoopRateLimiter(),
    )


class FetchInYearsTests(unittest.TestCase):
    def test_tries_every_candidate_year_in_order(self) -> None:
        transport = MapTransport({edition_url(2022, 3700): b"%PDF-3700"})
        edition = fetch_edition_in_years(make_client(transport), 3700, years=YEARS)
        self.assertEqual((edition.edition_number, edition.year), (3700, 2022))
        self.assertEqual(
            transport.requests,
            [edition_url(2021, 3700), edition_url(2022, 3700)],
        )

    def test_requires_candidate_years(self) -> None:
        with self.assertRaises(ValueError):
            fetch_edition_in_years(make_client(MapTransport({})), 3700, years=())


class CollectMissingEditionsTests(unittest.TestCase):
    def test_404_does_not_end_the_window(self) -> None:
        transport = MapTransport(
            {
                edition_url(2021, 3353): b"%PDF-3353",
                edition_url(2023, 3900): b"%PDF-3900",
            }
        )
        persisted: list[tuple[int, int]] = []
        result = collect_missing_editions(
            make_client(transport),
            lambda edition: persisted.append((edition.edition_number, edition.year)),
            editions=(3353, 3354, 3900),
            years=YEARS,
            logger=LOGGER,
        )
        self.assertEqual(persisted, [(3353, 2021), (3900, 2023)])
        self.assertEqual(
            result, BackfillResult(persisted=2, not_found=(3354,), deferred=False)
        )

    def test_transient_failure_defers_the_rest(self) -> None:
        transport = TimeoutTransport({edition_url(2021, 3353): b"%PDF-3353"})
        persisted: list[int] = []
        result = collect_missing_editions(
            make_client(transport),
            lambda edition: persisted.append(edition.edition_number),
            editions=(3353, 3360, 3361),
            years=YEARS,
            logger=LOGGER,
        )
        self.assertEqual(persisted, [])
        self.assertTrue(result.deferred)
        self.assertEqual(result.persisted, 0)
        self.assertEqual(result.not_found, ())


class MissingEditionsRepositoryTests(unittest.TestCase):
    def test_excludes_preserved_and_known_missing_numbers(self) -> None:
        results = iter(
            (
                [{"edition": 3354}, {"edition": 3360}],
                [{"edition": 3353}, {"edition": 3355}, {"edition": 3356}],
            )
        )

        class Result:
            def __init__(self, rows):
                self.rows = iter(rows)

            def fetchone(self):
                return next(self.rows, None)

        class Connection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, object]] = []
                self.closed = False

            def execute(self, query, params=None):
                self.calls.append((query, params))
                return Result(next(results))

            def close(self):
                self.closed = True

        connection = Connection()
        repository = PostgresCollectionRepository(lambda: connection)  # type: ignore[arg-type]
        candidates, known_missing = repository.missing_direct_editions(
            first_edition=3353,
            last_edition=3988,
            partition_key="backfill:3353-3988",
            limit=3,
        )
        self.assertEqual(candidates, (3353, 3355, 3356))
        self.assertEqual(known_missing, (3354, 3360))
        self.assertEqual(connection.calls[0][1], ("backfill:3353-3988",))
        self.assertEqual(connection.calls[1][1], (3353, 3988, [3354, 3360], 3))
        self.assertIn("'gazette-direct-edition'", connection.calls[1][0])
        # psycopg envia inteiros pequenos como smallint; sem o cast o Postgres
        # não escolhe entre generate_series(int) e (bigint).
        self.assertIn(
            "generate_series(%s::integer, %s::integer)", connection.calls[1][0]
        )
        self.assertTrue(connection.closed)
        with self.assertRaises(ValueError):
            repository.missing_direct_editions(
                first_edition=10, last_edition=5, partition_key="x", limit=1
            )


class RunBackfillTests(unittest.TestCase):
    def _control(self, repository) -> CollectionControl:
        return CollectionControl(
            repository=repository,
            source_code="barreiras-diario-oficial",
            endpoint_code="pdf-direto",
            idempotency_key="direct-diary-backfill:execution:" + "a" * 40,
            collector_version="direct/1.0.0",
            partition_key="backfill:3353-3988",
            period_start=date(2021, 1, 1),
            period_end=date(2023, 12, 31),
            execution_origin="manual",
        )

    def test_merges_not_found_into_checkpoint_and_stays_partial(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.completed: dict[str, object] = {}

            def start_controlled_run(self, **values):
                return "run-1"

            def complete_controlled_run(self, **values):
                self.completed = values

            def fail_controlled_run(self, **values):
                raise AssertionError(values)

            def missing_direct_editions(self, **values):
                self.requested = values
                return (3353, 3354, 3355), (3400,)

        repository = Repository()
        outcome = run_backfill(
            repository=repository,  # type: ignore[arg-type]
            control=self._control(repository),
            first_edition=3353,
            last_edition=3988,
            years=YEARS,
            limit=3,
            collect=lambda *, editions: BackfillResult(2, (3354,), False),
            logger=LOGGER,
        )
        self.assertEqual(outcome, {"persisted": 2, "exhausted": False})
        self.assertEqual(repository.requested["partition_key"], "backfill:3353-3988")
        completed = repository.completed
        self.assertEqual(completed["outcome"], CollectionOutcome.PARTIAL)
        self.assertEqual(completed["observed_records"], 2)
        self.assertEqual(
            completed["checkpoint"],
            {
                "next_edition": 3356,
                "missing_editions": [3354, 3400],
                "years": [2021, 2022, 2023],
            },
        )

    def test_short_batch_closes_the_interval_as_complete(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.completed: dict[str, object] = {}

            def start_controlled_run(self, **values):
                return "run-2"

            def complete_controlled_run(self, **values):
                self.completed = values

            def fail_controlled_run(self, **values):
                raise AssertionError(values)

            def missing_direct_editions(self, **values):
                return (3988,), (3354, 3400)

        repository = Repository()
        run_backfill(
            repository=repository,  # type: ignore[arg-type]
            control=self._control(repository),
            first_edition=3353,
            last_edition=3988,
            years=YEARS,
            limit=15,
            collect=lambda *, editions: BackfillResult(1, (), False),
            logger=LOGGER,
        )
        completed = repository.completed
        self.assertEqual(completed["outcome"], CollectionOutcome.COMPLETE)
        # 636 números no intervalo, 2 inexistentes na origem.
        self.assertEqual(completed["observed_records"], 634)
        self.assertEqual(completed["checkpoint"]["next_edition"], 3989)

    def test_years_argument_is_validated(self) -> None:
        self.assertEqual(parse_years("2021,2022"), (2021, 2022))
        with self.assertRaises(ValueError):
            parse_years("1999")
        with self.assertRaises(ValueError):
            parse_years("")


if __name__ == "__main__":
    unittest.main()
