from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import call, patch

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "install_collector_dependencies.py"
)
SPEC = importlib.util.spec_from_file_location("install_collector_dependencies", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallCollectorDependenciesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.output = io.StringIO()
        self.error = io.StringIO()

    def test_first_success_uses_fixed_command_and_does_not_capture_output(self) -> None:
        with (
            patch.object(installer.subprocess, "run") as run,
            patch.object(installer.time, "sleep") as sleep,
            redirect_stdout(self.output),
            redirect_stderr(self.error),
        ):
            run.return_value = subprocess.CompletedProcess([], 0)
            self.assertEqual(installer.install_dependencies(), 0)

        run.assert_called_once_with(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                ".[postgres,storage]",
            ],
            cwd=SCRIPT.parents[1],
            timeout=180,
            check=False,
        )
        sleep.assert_not_called()

    def test_transient_failure_retries_then_stops_at_success(self) -> None:
        with (
            patch.object(installer.subprocess, "run") as run,
            patch.object(installer.time, "sleep") as sleep,
            redirect_stdout(self.output),
            redirect_stderr(self.error),
        ):
            run.side_effect = [
                subprocess.CompletedProcess([], 1),
                subprocess.CompletedProcess([], 0),
            ]
            self.assertEqual(installer.install_dependencies(), 0)

        self.assertEqual(run.call_count, 2)
        sleep.assert_called_once_with(5)

    def test_exhaustion_preserves_final_error_code_and_bounded_waits(self) -> None:
        with (
            patch.object(installer.subprocess, "run") as run,
            patch.object(installer.time, "sleep") as sleep,
            redirect_stdout(self.output),
            redirect_stderr(self.error),
        ):
            run.side_effect = [
                subprocess.CompletedProcess([], 1),
                subprocess.CompletedProcess([], 2),
                subprocess.CompletedProcess([], 7),
            ]
            self.assertEqual(installer.install_dependencies(), 7)

        self.assertEqual(run.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(5), call(10)])
        self.assertIn('"returncode": 7', self.output.getvalue())

    def test_timeout_can_recover_without_unbounded_waiting(self) -> None:
        with (
            patch.object(installer.subprocess, "run") as run,
            patch.object(installer.time, "sleep") as sleep,
            redirect_stdout(self.output),
            redirect_stderr(self.error),
        ):
            run.side_effect = [
                subprocess.TimeoutExpired("hidden command", 180),
                subprocess.CompletedProcess([], 0),
            ]
            self.assertEqual(installer.install_dependencies(), 0)

        self.assertEqual(run.call_count, 2)
        sleep.assert_called_once_with(5)
        self.assertIn('"status": "timeout"', self.output.getvalue())
        self.assertNotIn("hidden command", self.output.getvalue())

    def test_exhausted_timeouts_fail_with_124(self) -> None:
        with (
            patch.object(installer.subprocess, "run") as run,
            patch.object(installer.time, "sleep") as sleep,
            redirect_stdout(self.output),
            redirect_stderr(self.error),
        ):
            run.side_effect = subprocess.TimeoutExpired("hidden command", 180)
            self.assertEqual(installer.install_dependencies(), 124)

        self.assertEqual(run.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(5), call(10)])

    def test_launch_error_fails_without_dumping_exception_or_retrying(self) -> None:
        with (
            patch.object(installer.subprocess, "run") as run,
            patch.object(installer.time, "sleep") as sleep,
            redirect_stdout(self.output),
            redirect_stderr(self.error),
        ):
            run.side_effect = OSError("sensitive local details")
            self.assertEqual(installer.install_dependencies(), 127)

        run.assert_called_once()
        sleep.assert_not_called()
        self.assertNotIn(
            "sensitive local details", self.output.getvalue() + self.error.getvalue()
        )

    def test_child_output_is_not_suppressed_and_no_success_is_invented(self) -> None:
        def failing_pip(*_args, **_kwargs):
            print("ERROR: dependency unavailable", file=sys.stderr)
            return subprocess.CompletedProcess([], 1)

        with (
            patch.object(installer.subprocess, "run", side_effect=failing_pip),
            patch.object(installer.time, "sleep"),
            redirect_stdout(self.output),
            redirect_stderr(self.error),
        ):
            self.assertEqual(installer.install_dependencies(), 1)

        self.assertEqual(
            self.error.getvalue().count("ERROR: dependency unavailable"), 3
        )
        self.assertNotIn('"status": "succeeded"', self.output.getvalue())

    def test_extra_arguments_cannot_replace_the_install_command(self) -> None:
        with (
            patch.object(installer.sys, "argv", [str(SCRIPT), "arbitrary-command"]),
            patch.object(installer, "install_dependencies") as install,
            redirect_stdout(self.output),
            redirect_stderr(self.error),
        ):
            self.assertEqual(installer.main(), 2)

        install.assert_not_called()


if __name__ == "__main__":
    unittest.main()
