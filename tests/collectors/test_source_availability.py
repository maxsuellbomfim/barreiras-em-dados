import unittest
from datetime import UTC, datetime, timedelta

from barreiras_collectors.source_availability import (
    SOURCE_UNAVAILABLE_EXIT_CODE,
    UNHANDLED_FAILURE_EXIT_CODE,
    SourceFreshness,
    optional_source_paused,
    unavailable_exit_code,
)

NOW = datetime(2026, 9, 28, 12, tzinfo=UTC)


def freshness(hours_ago: float | None, *, expected: int | None = 24, grace: int = 48):
    return SourceFreshness(
        last_valid_at=None if hours_ago is None else NOW - timedelta(hours=hours_ago),
        expected_hours=expected,
        grace_hours=grace,
    )


class UnavailableExitCodeTests(unittest.TestCase):
    def test_within_deadline_is_handled_warning(self) -> None:
        self.assertEqual(
            unavailable_exit_code(freshness(71), now=NOW), SOURCE_UNAVAILABLE_EXIT_CODE
        )
        self.assertEqual(
            unavailable_exit_code(freshness(72), now=NOW), SOURCE_UNAVAILABLE_EXIT_CODE
        )

    def test_beyond_deadline_is_unhandled_failure(self) -> None:
        self.assertEqual(
            unavailable_exit_code(freshness(72.01), now=NOW),
            UNHANDLED_FAILURE_EXIT_CODE,
        )

    def test_without_policy_or_history_never_hides_failure(self) -> None:
        self.assertEqual(
            unavailable_exit_code(freshness(1, expected=None), now=NOW),
            UNHANDLED_FAILURE_EXIT_CODE,
        )
        self.assertEqual(
            unavailable_exit_code(freshness(None), now=NOW), UNHANDLED_FAILURE_EXIT_CODE
        )


class OptionalSourcePauseTests(unittest.TestCase):
    def ago(self, days: float) -> datetime:
        return NOW - timedelta(days=days)

    def test_pauses_after_14_days_without_success_until_weekly_probe(self) -> None:
        self.assertTrue(
            optional_source_paused(
                last_success_at=self.ago(40), last_attempt_at=self.ago(1), now=NOW
            )
        )
        # Uma semana depois da última tentativa, tenta de novo.
        self.assertFalse(
            optional_source_paused(
                last_success_at=self.ago(40), last_attempt_at=self.ago(7), now=NOW
            )
        )

    def test_recent_success_or_no_history_never_pauses(self) -> None:
        self.assertFalse(
            optional_source_paused(
                last_success_at=self.ago(13), last_attempt_at=self.ago(0.1), now=NOW
            )
        )
        self.assertFalse(
            optional_source_paused(last_success_at=None, last_attempt_at=None, now=NOW)
        )
        self.assertTrue(
            optional_source_paused(
                last_success_at=None, last_attempt_at=self.ago(2), now=NOW
            )
        )


if __name__ == "__main__":
    unittest.main()
