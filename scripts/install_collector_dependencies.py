"""Install the fixed financial collector dependencies with bounded retries."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

MAX_ATTEMPTS = 3
ATTEMPT_TIMEOUT_SECONDS = 180
RETRY_DELAYS_SECONDS = (5, 10)


def install_dependencies() -> int:
    """Leave pip output visible and return its final failure instead of success."""
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        ".[postgres,storage]",
    ]
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            result = subprocess.run(  # noqa: S603 - fixed executable and arguments
                command,
                cwd=Path(__file__).resolve().parents[1],
                timeout=ATTEMPT_TIMEOUT_SECONDS,
                check=False,
            )
            returncode = result.returncode
            status = "succeeded" if returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            # subprocess.run kills and waits for the pip process on timeout.
            returncode = 124
            status = "timeout"
        except OSError:
            # A missing/unlaunchable executable is not an index/network outage.
            returncode = 127
            status = "launch_failed"

        print(
            json.dumps(
                {
                    "event": "collector_dependencies_install",
                    "attempt": attempt,
                    "max_attempts": MAX_ATTEMPTS,
                    "status": status,
                    "returncode": returncode,
                }
            ),
            flush=True,
        )
        if returncode == 0 or status == "launch_failed" or attempt == MAX_ATTEMPTS:
            return returncode
        time.sleep(RETRY_DELAYS_SECONDS[attempt - 1])

    raise AssertionError("unreachable retry state")


def main() -> int:
    if len(sys.argv) != 1:
        print("This installer does not accept arguments.", file=sys.stderr)
        return 2
    return install_dependencies()


if __name__ == "__main__":
    raise SystemExit(main())
