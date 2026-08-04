from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from barreiras_collectors.commands import collect_querido_diario
from barreiras_collectors.connectors.gazette_documents import (
    GazetteDocumentClient,
)
from barreiras_collectors.connectors.querido_diario import QueridoDiarioClient
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.http import ResponseTooLargeError

ROOT = Path(__file__).parents[2]
FIXTURE_PATH = ROOT / "fixtures" / "sources" / "querido_diario" / "gazettes-page-1.json"


class NoopRateLimiter:
    def acquire(self) -> None:
        return None


class PageTransport:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        return HttpResponse(
            status=200,
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=self.body,
            final_url=url,
        )


class DocumentTransport:
    """Devolve um corpo determinístico distinto por URL baixada."""

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        if url.endswith(".txt"):
            body = f"conteudo-txt-{url}".encode()
        else:
            body = b"%PDF-1.7 " + url.encode()
        # O CDN real devolve um tipo impreciso; o coletor deve normalizar.
        return HttpResponse(
            status=200,
            headers={"Content-Type": "binary/octet-stream"},
            body=body,
            final_url=url,
        )


def run_command(extra_environment: dict[str, str] | None = None) -> int:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    page_body = json.dumps(
        fixture["response"],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    def make_page_client(**kwargs):
        kwargs.update(
            transport=PageTransport(page_body),
            rate_limiter=NoopRateLimiter(),
        )
        return QueridoDiarioClient(**kwargs)

    def make_document_client(**kwargs):
        kwargs.update(
            transport=DocumentTransport(),
            rate_limiter=NoopRateLimiter(),
        )
        return GazetteDocumentClient(**kwargs)

    environment = {
        "APP_ENV": "test",
        "PERSISTENCE_MODE": "filesystem",
        "LOCAL_DATA_DIRECTORY": "data/local-evidence",
        **(extra_environment or {}),
    }
    with (
        patch.dict(os.environ, environment, clear=False),
        patch.object(
            collect_querido_diario,
            "QueridoDiarioClient",
            make_page_client,
        ),
        patch.object(
            collect_querido_diario,
            "GazetteDocumentClient",
            make_document_client,
        ),
    ):
        return collect_querido_diario.main(
            ["--since", "2026-07-01", "--until", "2026-07-02"]
        )


class CollectDocumentsCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_directory = Path.cwd()
        self._workspace = tempfile.TemporaryDirectory()
        os.chdir(self._workspace.name)

    def tearDown(self) -> None:
        os.chdir(self._previous_directory)
        self._workspace.cleanup()

    def document_manifests(self) -> list[Path]:
        root = Path("data/local-evidence/manifests/document-manifests")
        return sorted(root.glob("sha256/*/*/*.json"))

    def stored_objects(self) -> list[Path]:
        root = Path("data/local-evidence/objects")
        return sorted(path for path in root.rglob("*") if path.is_file())

    def test_collects_txt_and_pdf_as_child_artifacts_and_replays_clean(
        self,
    ) -> None:
        self.assertEqual(run_command(), 0)

        # 2 edições: uma com txt+pdf, outra somente pdf.
        self.assertEqual(len(self.document_manifests()), 3)
        # 1 página JSON + 3 documentos.
        self.assertEqual(len(self.stored_objects()), 4)

        self.assertEqual(run_command(), 0)

        self.assertEqual(len(self.document_manifests()), 3)
        self.assertEqual(len(self.stored_objects()), 4)

    def test_budget_limits_downloads_and_logs_skipped(self) -> None:
        with self.assertLogs(
            "barreiras_collectors.commands.collect_querido_diario",
            level="WARNING",
        ) as captured:
            exit_code = run_command(
                {"QUERIDO_DIARIO_MAX_DOCUMENTS_PER_RUN": "1"}
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(self.document_manifests()), 1)
        self.assertTrue(
            any(
                "collector_documents_budget_exhausted" in line
                for line in captured.output
            )
        )

    def test_oversized_document_is_recorded_and_does_not_abort_window(self) -> None:
        original_fetch = GazetteDocumentClient.fetch

        def fetch_with_one_oversized_pdf(client, url, *, role):
            if role == "pdf":
                raise ResponseTooLargeError("documento de teste excede o limite")
            return original_fetch(client, url, role=role)

        with (
            patch.object(GazetteDocumentClient, "fetch", fetch_with_one_oversized_pdf),
            self.assertLogs(
                "barreiras_collectors.commands.collect_querido_diario",
                level="WARNING",
            ) as captured,
        ):
            exit_code = run_command()

        self.assertEqual(exit_code, 0)
        self.assertTrue(
            any("collector_document_failed" in line for line in captured.output)
        )
        self.assertTrue(
            any("ResponseTooLargeError" in line for line in captured.output)
        )
        self.assertGreaterEqual(len(self.document_manifests()), 1)


if __name__ == "__main__":
    unittest.main()
