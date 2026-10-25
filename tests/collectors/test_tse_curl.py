import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from barreiras_collectors.connectors.tse_curl import TseCurlTransport


class TseCurlTests(unittest.TestCase):
    def test_download_is_bounded_and_redirects_are_not_followed(self):
        def run(args, **kwargs):
            self.assertIn("--max-filesize", args)
            self.assertNotIn("--location", args)
            self.assertEqual(args[1], "--disable")
            Path(args[args.index("--output") + 1]).write_bytes(b"zip")
            return subprocess.CompletedProcess(args, 0, "200", "")

        with (
            patch("shutil.which", return_value="curl.exe"),
            patch("subprocess.run", side_effect=run),
        ):
            response = TseCurlTransport().get(
                "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2026.zip",
                headers={},
                timeout_seconds=120,
                max_body_bytes=100,
            )
        self.assertEqual(response.body, b"zip")
        self.assertEqual(response.status, 200)

    def test_unapproved_host_is_rejected_before_subprocess(self):
        with (
            patch("shutil.which", return_value="curl.exe"),
            patch("subprocess.run") as run,
        ):
            with self.assertRaises(ValueError):
                TseCurlTransport().get(
                    "https://example.org/data",
                    headers={},
                    timeout_seconds=1,
                    max_body_bytes=10,
                )
            run.assert_not_called()
