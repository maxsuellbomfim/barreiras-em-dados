"""Planeja a próxima competência documental TCM-BA sem alterar o banco."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence

from ..persistence.postgres import PostgresCollectionRepository


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seleciona a competência TCM-BA mais antiga ainda incompleta."
    )
    parser.add_argument("--year-from", type=int, default=2021)
    parser.add_argument(
        "--report",
        action="store_true",
        help="Emite contadores sanitizados antes da competência selecionada.",
    )
    args = parser.parse_args(argv)
    if not 2000 <= args.year_from <= 2100:
        parser.error("--year-from deve estar entre 2000 e 2100.")

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("O planejamento TCM-BA exige DATABASE_URL.")
    repository = PostgresCollectionRepository.from_dsn(database_url)
    competence = repository.next_tcm_ba_document_competence(year_from=args.year_from)
    if args.report:
        report: dict[str, object] = {
            "event": "tcm_ba_document_plan",
            "competence": competence,
            "coverage_status": "complete" if competence is None else "partial",
        }
        if competence is not None:
            selection = repository.tcm_ba_document_references(
                competence=competence,
                limit=1,
            )
            if (
                selection.competence != competence
                or selection.expected_total_documents <= 0
                or selection.preserved_documents < 0
                or selection.pending_documents <= 0
                or selection.preserved_documents + selection.pending_documents
                != selection.expected_total_documents
            ):
                raise RuntimeError("O progresso documental TCM-BA é inconsistente.")
            report.update(
                expected_documents=selection.expected_total_documents,
                preserved_documents=selection.preserved_documents,
                remaining_documents=selection.pending_documents,
            )
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    if competence is not None:
        print(competence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
