from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from barreiras_collectors.commands.resolve_collection_window import (
    CollectionWindow,
    resolve_collection_window,
    write_github_output,
)
from barreiras_collectors.commands.write_failure_record import (
    build_failure_record,
    write_failure_record,
)


class ResolveCollectionWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)

    def test_defaults_to_previous_day_in_barreiras(self) -> None:
        window = resolve_collection_window("", "", now=self.now)

        self.assertEqual(
            window,
            CollectionWindow(since="2026-07-30", until="2026-07-30"),
        )

    def test_accepts_short_explicit_backfill(self) -> None:
        window = resolve_collection_window(
            "2026-07-24",
            "2026-07-30",
            now=self.now,
        )

        self.assertEqual(window.since, "2026-07-24")
        self.assertEqual(window.until, "2026-07-30")

    def test_rejects_partial_invalid_future_or_large_window(self) -> None:
        cases = (
            ("2026-07-30", ""),
            ("30/07/2026", "2026-07-30"),
            ("2026-07-30", "2026-07-29"),
            ("2026-07-23", "2026-07-30"),
            ("2026-08-01", "2026-08-01"),
        )
        for since, until in cases:
            with self.subTest(since=since, until=until):
                with self.assertRaises(ValueError):
                    resolve_collection_window(since, until, now=self.now)

    def test_writes_window_and_mode_to_github_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output.txt"
            write_github_output(
                CollectionWindow("2026-07-30", "2026-07-30"),
                {"GITHUB_OUTPUT": str(output_path)},
            )

            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                "since=2026-07-30\nuntil=2026-07-30\nmode=recent\n",
            )


class ScheduledWorkflowTests(unittest.TestCase):
    def test_finance_group_runs_transferegov_as_an_independent_job(self) -> None:
        repository_root = Path(__file__).parents[2]
        workflow = (
            repository_root
            / ".github"
            / "workflows"
            / "collect-finance-documents.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("include_transferegov:", workflow)
        self.assertIn("transferegov:", workflow)
        self.assertIn(
            "barreiras_collectors.commands.collect_transferegov_parcerias",
            workflow,
        )
        self.assertIn(
            "barreiras_collectors.commands.collect_transferegov_download_catalog",
            workflow,
        )
        self.assertIn(
            "MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_EMAIL",
            workflow,
        )
        self.assertEqual(
            workflow.count("collect_transferegov_parcerias"),
            1,
        )
        self.assertEqual(
            workflow.count("collect_transferegov_download_catalog"),
            1,
        )
        transferegov_job = workflow[workflow.index("  transferegov:") :]
        self.assertNotIn("inputs.max_pages", transferegov_job)

    def test_finance_group_runs_siconfi_dca_before_state_jobs(self) -> None:
        repository_root = Path(__file__).parents[2]
        workflow = (
            repository_root
            / ".github"
            / "workflows"
            / "collect-finance-documents.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("include_siconfi_dca:", workflow)
        self.assertIn("  siconfi_dca:", workflow)
        self.assertEqual(workflow.count("collect_siconfi_dca"), 1)
        state_job = workflow[workflow.index("  bahia_state_amendments:") :]
        self.assertIn("- siconfi_dca", state_job)

    def test_manual_dates_are_not_interpolated_into_the_shell_script(self) -> None:
        repository_root = Path(__file__).parents[2]
        workflow = (
            repository_root / ".github" / "workflows" / "collect-querido-diario.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("REQUESTED_SINCE: ${{ inputs.since }}", workflow)
        self.assertIn("REQUESTED_UNTIL: ${{ inputs.until }}", workflow)
        self.assertNotIn('--since "${{ inputs.since }}"', workflow)
        self.assertNotIn('--until "${{ inputs.until }}"', workflow)

    def test_backfill_schedule_resolves_window_and_honors_skip(self) -> None:
        repository_root = Path(__file__).parents[2]
        workflow = (
            repository_root / ".github" / "workflows" / "collect-querido-diario.yml"
        ).read_text(encoding="utf-8")

        self.assertIn('- cron: "17 2,8,14,20 * * *"', workflow)
        self.assertIn("resolve_backfill_window", workflow)
        self.assertIn("if: steps.window.outputs.skip != 'true'", workflow)
        self.assertIn('QUERIDO_DIARIO_BACKFILL_HORIZON: "2021-01-01"', workflow)
        # Todo agendamento que não é a coleta da véspera é backfill.
        self.assertIn('!= "17 11 * * *"', workflow)

    def test_backfill_does_not_repeat_recent_only_steps(self) -> None:
        repository_root = Path(__file__).parents[2]
        workflow = (
            repository_root / ".github" / "workflows" / "collect-querido-diario.yml"
        ).read_text(encoding="utf-8")

        self.assertGreaterEqual(
            workflow.count("steps.window.outputs.mode != 'backfill'"),
            7,
        )

    def test_catalog_failure_does_not_skip_preserved_document_processing(self) -> None:
        repository_root = Path(__file__).parents[2]
        workflow = (
            repository_root / ".github" / "workflows" / "collect-querido-diario.yml"
        ).read_text(encoding="utf-8")

        catalog = workflow.index("- name: Preservar catálogo oficial do Diário")
        direct = workflow.index("- name: Coletar edições diretas do Diário")
        ocr = workflow.index("- name: OCR das páginas escaneadas")
        integral = workflow.index("- name: Organizar edições em documentos integrais")
        failure_gate = workflow.find("- name: Sinalizar falha do catálogo oficial")

        self.assertGreaterEqual(failure_gate, 0)
        self.assertLess(catalog, direct)
        self.assertLess(direct, ocr)
        self.assertLess(integral, failure_gate)
        catalog_block = workflow[catalog:direct]
        self.assertIn("id: official_catalog", catalog_block)
        self.assertIn("continue-on-error: true", catalog_block)
        self.assertIn("steps.official_catalog.outcome == 'failure'", workflow)

    def test_new_scanned_pdf_can_be_extracted_after_ocr_in_the_same_run(self) -> None:
        repository_root = Path(__file__).parents[2]
        workflow = (
            repository_root / ".github" / "workflows" / "collect-querido-diario.yml"
        ).read_text(encoding="utf-8")

        first_extraction = workflow.find(
            "- name: Preparar texto e candidatos determinísticos"
        )
        ocr = workflow.find("- name: OCR das páginas escaneadas")
        second_extraction = workflow.find(
            "- name: Extrair candidatos determinísticos após OCR"
        )

        self.assertGreaterEqual(first_extraction, 0)
        self.assertGreaterEqual(ocr, 0)
        self.assertGreaterEqual(second_extraction, 0)
        self.assertLess(first_extraction, ocr)
        self.assertLess(ocr, second_extraction)


class FailureRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = {
            "COLLECTION_SINCE": "2026-07-30",
            "COLLECTION_UNTIL": "2026-07-30",
            "GITHUB_REPOSITORY": "example/barreiras-em-dados",
            "GITHUB_WORKFLOW": "Coletar Querido Diário",
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "2",
            "GITHUB_SHA": "a" * 40,
            "SUPABASE_WORKLOAD_PASSWORD": "must-not-leak",
            "DATABASE_URL": "must-not-leak",
        }

    def test_record_contains_replay_context_but_no_secrets(self) -> None:
        record = build_failure_record(
            self.environment,
            occurred_at=datetime(2026, 7, 31, 12, 0, tzinfo=UTC),
        )
        serialized = json.dumps(record)

        self.assertEqual(record["status"], "pending_manual_replay")
        self.assertEqual(record["window_start"], "2026-07-30")
        self.assertIn("/actions/runs/123", record["workflow_url"])
        self.assertNotIn("must-not-leak", serialized)
        self.assertNotIn("DATABASE_URL", serialized)

    def test_writes_relative_json_and_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = Path("artifacts") / "collector-failure.json"
            prior = Path.cwd()
            try:
                import os

                os.chdir(root)
                written = write_failure_record(destination, self.environment)
                payload = json.loads(written.read_text(encoding="utf-8"))
            finally:
                os.chdir(prior)

            self.assertEqual(payload["source"], "querido-diario")
            with self.assertRaises(ValueError):
                write_failure_record(Path("../outside.json"), self.environment)


if __name__ == "__main__":
    unittest.main()
