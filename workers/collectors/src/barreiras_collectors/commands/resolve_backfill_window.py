"""Resolve a próxima janela retroativa a partir do que já foi coletado.

O backfill caminha para trás no tempo, uma janela curta por execução, até o
horizonte configurado. O progresso é derivado do banco: a âncora é a data mais
antiga já coberta (janela registrada ou edição preservada), então janelas
vazias também avançam o cursor e nada depende de estado externo.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ..persistence.postgres import PostgresCollectionRepository
from ..settings import CollectorSettings, PersistenceSettings
from .resolve_collection_window import MAX_WINDOW_DAYS, CollectionWindow

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def contiguous_coverage_anchor(
    *,
    horizon: date,
    today: date,
    covered_intervals: Sequence[tuple[date, date]],
) -> date:
    """Início da faixa contínua coberta que termina na véspera."""
    target = today - timedelta(days=1)
    if target < horizon:
        return horizon

    clipped = sorted(
        (
            (max(start, horizon), min(end, target))
            for start, end in covered_intervals
            if start <= target and end >= horizon
        ),
        key=lambda interval: interval[0],
    )
    merged: list[tuple[date, date]] = []
    for start, end in clipped:
        if not merged or start > merged[-1][1] + timedelta(days=1):
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        merged[-1] = (previous_start, max(previous_end, end))

    for start, end in reversed(merged):
        if start <= target <= end:
            return start
    return today


def resolve_backfill_window(
    *,
    horizon: date,
    anchor: date | None,
    today: date,
) -> CollectionWindow | None:
    """Devolve a próxima janela retroativa ou None quando o backfill acabou."""
    effective_anchor = anchor or today
    until = effective_anchor - timedelta(days=1)
    if until < horizon:
        return None
    since = max(horizon, until - timedelta(days=MAX_WINDOW_DAYS - 1))
    return CollectionWindow(since=since.isoformat(), until=until.isoformat())


def write_github_output(
    window: CollectionWindow | None,
    environment: Mapping[str, str],
) -> None:
    raw_path = environment.get("GITHUB_OUTPUT", "").strip()
    if not raw_path:
        return
    output_path = Path(raw_path)
    with output_path.open("a", encoding="utf-8", newline="\n") as output:
        if window is None:
            output.write("since=\nuntil=\nskip=true\nmode=backfill\n")
        else:
            output.write(f"since={window.since}\n")
            output.write(f"until={window.until}\n")
            output.write("skip=false\n")
            output.write("mode=backfill\n")


def coverage_anchor(
    repository: PostgresCollectionRepository,
    *,
    horizon: date = date(2000, 1, 1),
    today: date | None = None,
) -> date:
    """Início da faixa contínua comprovada por execuções bem-sucedidas."""
    connection = repository.connection_factory()
    try:
        rows = connection.execute(
            """
            select distinct
              run.collection_window_start::date as period_start,
              run.collection_window_end::date as period_end
            from source.collection_runs as run
            join source.source_endpoints as endpoint
              on endpoint.id = run.source_endpoint_id
            join source.data_sources as data_source
              on data_source.id = endpoint.data_source_id
            where data_source.slug = 'querido-diario'
              and run.status = 'succeeded'
              and run.collection_window_start is not null
              and run.collection_window_end is not null
            """
        ).fetchall()
    finally:
        connection.close()

    intervals: list[tuple[date, date]] = []
    for row in rows:
        raw_start = row["period_start"]
        raw_end = row["period_end"]
        start = (
            raw_start
            if isinstance(raw_start, date)
            else date.fromisoformat(str(raw_start))
        )
        end = (
            raw_end
            if isinstance(raw_end, date)
            else date.fromisoformat(str(raw_end))
        )
        intervals.append((start, end))

    effective_today = today or datetime.now(MUNICIPAL_TIMEZONE).date()
    return contiguous_coverage_anchor(
        horizon=horizon,
        today=effective_today,
        covered_intervals=intervals,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args(argv)

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    if persistence_settings.database_url is None:
        raise RuntimeError(
            "O backfill requer PERSISTENCE_MODE=postgres-supabase."
        )

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    today = datetime.now(MUNICIPAL_TIMEZONE).date()
    anchor = coverage_anchor(
        repository,
        horizon=collector_settings.backfill_horizon,
        today=today,
    )
    window = resolve_backfill_window(
        horizon=collector_settings.backfill_horizon,
        anchor=anchor,
        today=today,
    )
    write_github_output(window, os.environ)
    if window is None:
        event = {
            "event": "collector_backfill_complete",
            "source": "querido-diario",
            "territory_id": "2903201",
            "horizon": collector_settings.backfill_horizon.isoformat(),
            "anchor": anchor.isoformat() if anchor else None,
        }
    else:
        event = {
            "event": "collector_backfill_window_resolved",
            "source": "querido-diario",
            "territory_id": "2903201",
            "window_start": window.since,
            "window_end": window.until,
            "horizon": collector_settings.backfill_horizon.isoformat(),
        }
    print(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
