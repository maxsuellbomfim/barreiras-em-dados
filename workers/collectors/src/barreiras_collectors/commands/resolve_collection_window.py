"""Resolve uma janela curta e reproduzível para execução agendada."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

MAX_WINDOW_DAYS = 7
MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class CollectionWindow:
    since: str
    until: str


def resolve_collection_window(
    since: str,
    until: str,
    *,
    now: datetime | None = None,
) -> CollectionWindow:
    normalized_since = since.strip()
    normalized_until = until.strip()
    if bool(normalized_since) != bool(normalized_until):
        raise ValueError("--since e --until devem ser informados juntos.")

    reference = now or datetime.now(MUNICIPAL_TIMEZONE)
    local_reference = reference.astimezone(MUNICIPAL_TIMEZONE)
    if not normalized_since:
        yesterday = local_reference.date() - timedelta(days=1)
        return CollectionWindow(
            since=yesterday.isoformat(),
            until=yesterday.isoformat(),
        )

    try:
        since_date = datetime.strptime(normalized_since, "%Y-%m-%d").date()
        until_date = datetime.strptime(normalized_until, "%Y-%m-%d").date()
    except ValueError as error:
        raise ValueError("As datas devem usar o formato YYYY-MM-DD.") from error
    if since_date > until_date:
        raise ValueError("--since não pode ser posterior a --until.")
    if (until_date - since_date).days >= MAX_WINDOW_DAYS:
        raise ValueError(f"A janela não pode exceder {MAX_WINDOW_DAYS} dias.")
    if until_date > local_reference.date():
        raise ValueError("--until não pode estar no futuro em Barreiras.")
    return CollectionWindow(
        since=since_date.isoformat(),
        until=until_date.isoformat(),
    )


def write_github_output(
    window: CollectionWindow,
    environment: Mapping[str, str],
) -> None:
    raw_path = environment.get("GITHUB_OUTPUT", "").strip()
    if not raw_path:
        return
    output_path = Path(raw_path)
    with output_path.open("a", encoding="utf-8", newline="\n") as output:
        output.write(f"since={window.since}\n")
        output.write(f"until={window.until}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="")
    parser.add_argument("--until", default="")
    arguments = parser.parse_args(argv)
    try:
        window = resolve_collection_window(arguments.since, arguments.until)
    except ValueError as error:
        parser.error(str(error))
    write_github_output(window, os.environ)
    print(
        json.dumps(
            {
                "event": "collector_window_resolved",
                "source": "querido-diario",
                "territory_id": "2903201",
                "window_start": window.since,
                "window_end": window.until,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
