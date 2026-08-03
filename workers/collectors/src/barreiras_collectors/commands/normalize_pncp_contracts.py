"""Normaliza contratos PNCP preservados no modelo público rastreável."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from ..logging import log_event
from ..persistence.postgres import PostgresCollectionRepository
from ..settings import CollectorSettings, PersistenceSettings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Converte registros brutos de contratos PNCP em contratos, "
            "fornecedores e vínculos de contratação normalizados."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="máximo de contratos brutos processados nesta execução (1-5000)",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 5000:
        parser.error("--limit deve estar entre 1 e 5000")

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "A normalização PNCP requer PERSISTENCE_MODE=postgres-supabase."
        )
    if persistence_settings.database_url is None:
        raise RuntimeError("DATABASE_URL é obrigatória para normalizar PNCP.")

    metrics = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    ).normalize_pncp_contracts(args.limit)
    log_event(
        logging.getLogger(__name__),
        logging.INFO,
        "normalizer_pncp_contracts_completed",
        limit=args.limit,
        **{key: int(value) for key, value in metrics.items()},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
