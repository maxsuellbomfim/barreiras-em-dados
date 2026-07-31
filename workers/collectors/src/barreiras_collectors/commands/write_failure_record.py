"""Grava uma DLQ sanitizada para falhas do job agendado."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path


def build_failure_record(
    environment: Mapping[str, str],
    *,
    occurred_at: datetime | None = None,
) -> dict[str, str]:
    timestamp = occurred_at or datetime.now(UTC)
    repository = environment.get("GITHUB_REPOSITORY", "")
    run_id = environment.get("GITHUB_RUN_ID", "")
    workflow_url = (
        f"https://github.com/{repository}/actions/runs/{run_id}"
        if repository and run_id
        else ""
    )
    return {
        "event": "collector_run_failed",
        "source": "querido-diario",
        "territory_id": "2903201",
        "status": "pending_manual_replay",
        "window_start": environment.get("COLLECTION_SINCE", ""),
        "window_end": environment.get("COLLECTION_UNTIL", ""),
        "repository": repository,
        "workflow": environment.get("GITHUB_WORKFLOW", ""),
        "run_id": run_id,
        "run_attempt": environment.get("GITHUB_RUN_ATTEMPT", ""),
        "commit_sha": environment.get("GITHUB_SHA", ""),
        "workflow_url": workflow_url,
        "failed_at": timestamp.isoformat(),
    }


def write_failure_record(
    destination: Path,
    environment: Mapping[str, str],
) -> Path:
    if destination.is_absolute() or any(
        part in {"", ".", ".."} for part in destination.parts
    ):
        raise ValueError("O destino da DLQ deve ser um caminho relativo seguro.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = build_failure_record(environment)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--destination",
        default="artifacts/collector-failure.json",
        type=Path,
    )
    arguments = parser.parse_args(argv)
    try:
        destination = write_failure_record(arguments.destination, os.environ)
    except ValueError as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "event": "collector_failure_record_written",
                "destination": destination.as_posix(),
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
