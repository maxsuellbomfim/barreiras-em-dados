"""Fecha falhas de coleta já recuperadas e execuções órfãs.

A decisão é da função SQL versionada ``source.reconcile_collection_failures``;
este comando só a executa no agendamento e registra o resultado.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from ..persistence.postgres import PostgresCollectionRepository
from ..settings import PersistenceSettings


def reconcile(repository: PostgresCollectionRepository) -> dict[str, int]:
    connection = repository.connection_factory()
    try:
        with connection.transaction():
            rows = connection.execute(
                "select rule, resolved_count"
                " from source.reconcile_collection_failures()"
            ).fetchall()
            orphans = connection.execute(
                "select source.close_orphaned_collection_runs() as closed"
            ).fetchall()
    finally:
        connection.close()
    counts = {str(row["rule"]): int(row["resolved_count"]) for row in rows}
    counts["orphaned_runs_closed"] = int(orphans[0]["closed"])
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser().parse_args(argv)
    settings = PersistenceSettings.from_env()
    if settings.database_url is None:
        raise RuntimeError(
            "A reconciliação requer PERSISTENCE_MODE=postgres-supabase."
        )
    counts = reconcile(PostgresCollectionRepository.from_dsn(settings.database_url))
    print(
        json.dumps(
            {"event": "collection_failures_reconciled", **counts},
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
