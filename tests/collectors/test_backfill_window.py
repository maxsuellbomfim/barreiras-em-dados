from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from barreiras_collectors.commands.resolve_backfill_window import (
    contiguous_coverage_anchor,
    coverage_anchor,
    resolve_backfill_window,
    write_github_output,
)
from barreiras_collectors.commands.resolve_collection_window import (
    CollectionWindow,
)

HORIZON = date(2026, 1, 1)
TODAY = date(2026, 7, 31)


class ResolveBackfillWindowTests(unittest.TestCase):
    def test_isolated_old_run_does_not_hide_a_more_recent_gap(self) -> None:
        anchor = contiguous_coverage_anchor(
            horizon=date(2021, 1, 1),
            today=date(2026, 8, 5),
            covered_intervals=(
                (date(2021, 1, 1), date(2021, 1, 7)),
                (date(2026, 7, 31), date(2026, 8, 4)),
            ),
        )

        self.assertEqual(anchor, date(2026, 7, 31))

    def test_repository_anchor_uses_contiguous_successful_windows(self) -> None:
        class Result:
            def fetchone(self) -> dict[str, date]:
                return {"anchor": date(2021, 1, 1)}

            def fetchall(self) -> list[dict[str, date]]:
                return [
                    {
                        "period_start": date(2021, 1, 1),
                        "period_end": date(2021, 1, 7),
                    },
                    {
                        "period_start": date(2026, 7, 31),
                        "period_end": date(2026, 8, 4),
                    },
                ]

        class Connection:
            def execute(self, _query: str) -> Result:
                return Result()

            def close(self) -> None:
                return None

        class Repository:
            @staticmethod
            def connection_factory() -> Connection:
                return Connection()

        anchor = coverage_anchor(
            Repository(),  # type: ignore[arg-type]
            horizon=date(2021, 1, 1),
            today=date(2026, 8, 5),
        )

        self.assertEqual(anchor, date(2026, 7, 31))

    def test_walks_back_seven_days_from_anchor(self) -> None:
        window = resolve_backfill_window(
            horizon=HORIZON,
            anchor=date(2026, 6, 10),
            today=TODAY,
        )

        self.assertEqual(
            window,
            CollectionWindow(since="2026-06-03", until="2026-06-09"),
        )

    def test_clamps_last_window_at_horizon(self) -> None:
        window = resolve_backfill_window(
            horizon=HORIZON,
            anchor=date(2026, 1, 5),
            today=TODAY,
        )

        self.assertEqual(
            window,
            CollectionWindow(since="2026-01-01", until="2026-01-04"),
        )

    def test_returns_none_when_horizon_is_reached(self) -> None:
        self.assertIsNone(
            resolve_backfill_window(
                horizon=HORIZON,
                anchor=date(2026, 1, 1),
                today=TODAY,
            )
        )

    def test_uses_today_when_nothing_was_collected_yet(self) -> None:
        window = resolve_backfill_window(
            horizon=HORIZON,
            anchor=None,
            today=TODAY,
        )

        self.assertEqual(
            window,
            CollectionWindow(since="2026-07-24", until="2026-07-30"),
        )

    def test_progress_terminates_at_horizon(self) -> None:
        anchor: date | None = date(2026, 2, 20)
        windows = 0
        while True:
            window = resolve_backfill_window(
                horizon=HORIZON,
                anchor=anchor,
                today=TODAY,
            )
            if window is None:
                break
            windows += 1
            anchor = date.fromisoformat(window.since)
            self.assertLessEqual(windows, 60, "backfill não termina")
        self.assertEqual(anchor, HORIZON)

    def test_github_output_marks_skip_when_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output.txt"
            write_github_output(None, {"GITHUB_OUTPUT": str(output_path)})
            write_github_output(
                CollectionWindow("2026-06-03", "2026-06-09"),
                {"GITHUB_OUTPUT": str(output_path)},
            )

            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                "since=\nuntil=\nskip=true\nmode=backfill\n"
                "since=2026-06-03\nuntil=2026-06-09\nskip=false\n"
                "mode=backfill\n",
            )


if __name__ == "__main__":
    unittest.main()
