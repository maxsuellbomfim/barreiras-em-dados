"""Planeja a próxima competência documental TCM-BA sem alterar o banco."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from ..persistence.postgres import PostgresCollectionRepository


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seleciona a competência TCM-BA mais antiga ainda incompleta."
    )
    parser.add_argument("--year-from", type=int, default=2021)
    args = parser.parse_args(argv)
    if not 2000 <= args.year_from <= 2100:
        parser.error("--year-from deve estar entre 2000 e 2100.")

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("O planejamento TCM-BA exige DATABASE_URL.")
    competence = PostgresCollectionRepository.from_dsn(
        database_url
    ).next_tcm_ba_document_competence(year_from=args.year_from)
    if competence is not None:
        print(competence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
