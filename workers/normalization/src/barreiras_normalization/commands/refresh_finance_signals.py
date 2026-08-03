"""Atualiza sinais financeiros determinísticos e suas evidências."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Calcula sinais financeiros para triagem pública."
    )
    parser.parse_args(argv)
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL é obrigatória")

    from barreiras_collectors.persistence.postgres import PostgresCollectionRepository

    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), force=True)
    logger = logging.getLogger(__name__)
    repository = PostgresCollectionRepository.from_dsn(database_url)
    connection = repository.connection_factory()
    try:
        with connection.transaction():
            connection.execute("set local statement_timeout = '30s'")
            row = connection.execute(
                "select analysis.refresh_finance_signals() as inserted_count"
            ).fetchone()
        inserted_count = int(row["inserted_count"] if row else 0)
    finally:
        connection.close()

    logger.info("finance_signals_refreshed inserted=%s", inserted_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
