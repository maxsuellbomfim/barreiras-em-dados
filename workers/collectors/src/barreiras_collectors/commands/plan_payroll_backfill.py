"""Planeja uma janela mensal limitada sem acessar fonte ou credencial."""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path

ALLOWED_BATCH_LIMITS = frozenset({1, 3, 6})
MONTH_PATTERN = re.compile(r"20[2-9][0-9]-(?:0[1-9]|1[0-2])")


def parse_month(value: str) -> date:
    if MONTH_PATTERN.fullmatch(value) is None:
        raise ValueError("competência exige AAAA-MM desde 2020")
    year, month = (int(part) for part in value.split("-"))
    return date(year, month, 1)


def previous_month(value: date) -> date:
    if value.month == 1:
        return date(value.year - 1, 12, 1)
    return date(value.year, value.month - 1, 1)


def plan_months(
    *,
    start_month: str,
    end_month: str,
    max_months: int,
) -> tuple[str, ...]:
    if max_months not in ALLOWED_BATCH_LIMITS:
        raise ValueError("limite defensivo deve ser 1, 3 ou 6")
    start = parse_month(start_month)
    end = parse_month(end_month)
    if start > end:
        raise ValueError("competência inicial não pode ser posterior à final")

    planned: list[str] = []
    cursor = end
    while cursor >= start:
        if len(planned) >= max_months:
            raise ValueError(f"janela excede o limite de {max_months} competências")
        planned.append(cursor.strftime("%Y-%m"))
        cursor = previous_month(cursor)
    return tuple(planned)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Valida e ordena um lote histórico mensal da folha."
    )
    parser.add_argument("--start-month", required=True)
    parser.add_argument("--end-month", required=True)
    parser.add_argument("--max-months", required=True, type=int)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        months = plan_months(
            start_month=args.start_month,
            end_month=args.end_month,
            max_months=args.max_months,
        )
    except ValueError as error:
        parser.error(str(error))

    with args.github_output.open("a", encoding="utf-8", newline="\n") as output:
        output.write(f"months={' '.join(months)}\n")
        output.write(f"count={len(months)}\n")
    print(
        f"Lote validado com {len(months)} competência(s), "
        "da mais recente para a mais antiga."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
