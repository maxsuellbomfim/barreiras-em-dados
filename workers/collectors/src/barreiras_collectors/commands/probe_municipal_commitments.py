"""Sonda de um mês fechado de empenhos da Prefeitura, sem persistir nada.

Imprime um resumo JSON verificável (total declarado, repetições, hash da
grade, citações de contrato). ``--save-raw`` grava a grade bruta intacta para
conferência; não há soma de valores nem gravação em banco.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from ..connectors import municipal_expenses as expenses
from .plan_payroll_backfill import parse_month

_CONTRACT_CITATION = re.compile(r"\bcontrato\s+n", re.IGNORECASE)


def summarize(result: expenses.MonthlyCommitments) -> dict[str, object]:
    unique = {row[expenses.FIELD_KEY]: row for row in result.rows}
    return {
        "source_code": result.source_code,
        "month": f"{result.year:04d}-{result.month:02d}",
        "coverage": result.coverage,
        "declared_total": result.declared_total,
        "repeated_rows": result.repeated_rows,
        "unique_commitments": len(unique),
        "by_key_prefix": dict(Counter(key[:2] for key in unique)),
        "cite_contract": sum(
            1
            for row in unique.values()
            if _CONTRACT_CITATION.search(row.get(expenses.FIELD_HISTORY, ""))
        ),
        "grid_sha256": result.grid_sha256,
        "grid_bytes": len(result.grid_body),
        "received_at": result.received_at,
        "source_field_names": dict(result.source_field_names),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--month", required=True, help="AAAA-MM de um mês fechado")
    parser.add_argument("--save-raw", type=Path)
    args = parser.parse_args(argv)
    month = parse_month(args.month)
    try:
        result = expenses.fetch_monthly_commitments(
            month.year, month.month, today=date.today()
        )
    except expenses.MunicipalExpensesError as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    if args.save_raw is not None:
        args.save_raw.write_bytes(result.grid_body)
    json.dump(summarize(result), sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
