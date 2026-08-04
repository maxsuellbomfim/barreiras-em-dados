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


def coverage_anchor(repository: PostgresCollectionRepository) -> date | None:
    """Data mais antiga já coberta pela coleta do Querido Diário."""
    connection = repository.connection_factory()
    try:
        row = connection.execute(
            """
            select least(
              (
                select min(run.collection_window_start)::date
                from source.collection_runs as run
                join source.source_endpoints as endpoint
                  on endpoint.id = run.source_endpoint_id
                join source.data_sources as data_source
                  on data_source.id = endpoint.data_source_id
                where data_source.slug = 'querido-diario'
                  and run.status = 'succeeded'
                  and run.collection_window_start is not null
              ),
              (
                select min((record.payload ->> 'date')::date)
                from raw.raw_records as record
                where record.record_type = 'querido_diario_gazette'
              )
            ) as anchor
            """
        ).fetchone()
    finally:
        connection.close()
    if row is None or row["anchor"] is None:
        return None
    value = row["anchor"]
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


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
    anchor = coverage_anchor(repository)
    today = datetime.now(MUNICIPAL_TIMEZONE).date()
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
