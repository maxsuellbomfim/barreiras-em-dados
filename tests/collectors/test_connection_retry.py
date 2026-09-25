from __future__ import annotations

import unittest
from contextlib import redirect_stderr
from io import StringIO

from barreiras_collectors.persistence.postgres import (
    ROLE_CONNECTION_LIMIT_WAITS_SECONDS,
    connect_with_role_limit_retry,
)

ROLE_LIMIT = 'FATAL:  too many connections for role "collector_querido_diario"'


class FlakyConnect:
    def __init__(self, failures: list[Exception]) -> None:
        self.failures = failures
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return "conexão"


class ConnectionRetryTests(unittest.TestCase):
    def test_waits_while_role_limit_is_reached(self) -> None:
        connect = FlakyConnect([OSError(ROLE_LIMIT), OSError(ROLE_LIMIT)])
        waits: list[float] = []

        with redirect_stderr(StringIO()):
            result = connect_with_role_limit_retry(connect, OSError, waits.append)

        self.assertEqual(result, "conexão")
        self.assertEqual(waits, [5, 10])

    def test_other_errors_fail_immediately(self) -> None:
        connect = FlakyConnect([OSError("password authentication failed")])
        waits: list[float] = []

        with self.assertRaisesRegex(OSError, "password"):
            connect_with_role_limit_retry(connect, OSError, waits.append)
        self.assertEqual(waits, [])

    def test_persistent_limit_raises_original_error(self) -> None:
        attempts = len(ROLE_CONNECTION_LIMIT_WAITS_SECONDS) + 1
        connect = FlakyConnect([OSError(ROLE_LIMIT) for _ in range(attempts)])
        waits: list[float] = []

        with (
            redirect_stderr(StringIO()),
            self.assertRaisesRegex(OSError, "too many connections"),
        ):
            connect_with_role_limit_retry(connect, OSError, waits.append)
        self.assertEqual(connect.calls, attempts)
        self.assertEqual(waits, list(ROLE_CONNECTION_LIMIT_WAITS_SECONDS))


if __name__ == "__main__":
    unittest.main()
