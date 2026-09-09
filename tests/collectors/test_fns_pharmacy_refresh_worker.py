import copy
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

from barreiras_collectors.persistence.fns_pharmacy import prepare_pharmacy_import
from barreiras_collectors.persistence.fns_pharmacy_refresh_worker import (
    PostgresPharmacyRefreshRepository,
    execute_refresh,
)

from tests.collectors.test_fns_pharmacy_identity import register
from tests.collectors.test_fns_pharmacy_reconciliation import observation
from tests.collectors.test_fns_pharmacy_refresh import append_payment


class RefreshWorkerTests(unittest.TestCase):
    def setUp(self):
        self.previous = observation()
        self.previous["payment_capture"]["received_at"] = "2026-09-09T00:00:00Z"
        self.current = append_payment(self.previous)
        self.register = register()
        self.register["retrieved_at"] = "2026-09-08T00:00:00Z"
        self.events = []
        self.repository = Mock()
        self.repository.load_baseline.return_value = dict(
            snapshot_id=1,
            approved=True,
            observation=self.previous,
            register=self.register,
        )
        self.repository.verify_publication.return_value = True

        @contextmanager
        def transaction():
            self.events.append("begin")
            try:
                yield
                self.events.append("commit")
            except Exception:
                self.events.append("rollback")
                raise

        self.repository.transaction = transaction
        self.store = Mock()
        self.bodies = {}

        def put(**values):
            self.events.append("upload")
            self.bodies[values["object_key"]] = values["body"]

        self.store.put_if_absent.side_effect = put
        self.store.read.side_effect = self.bodies.__getitem__

    def run_refresh(self, current=None):
        return execute_refresh(
            repository=self.repository,
            object_store=self.store,
            current=current or self.current,
            current_register=self.register,
        )

    def test_append_reads_storage_before_transaction_and_verifies_before_commit(self):
        result = self.run_refresh()
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["added_documents"], 1)
        self.assertEqual(self.events, ["upload", "upload", "begin", "commit"])
        self.repository.import_plan.assert_called_once()
        self.repository.verify_publication.assert_called_once()
        self.assertNotIn("plan", result)
        self.assertNotIn(self.current["beneficiary"], str(result))

    def test_public_mismatch_rolls_back_without_raw_exception(self):
        self.repository.verify_publication.return_value = False
        with self.assertRaisesRegex(RuntimeError, "^Pharmacy refresh failed$"):
            self.run_refresh()
        self.assertEqual(self.events[-1], "rollback")

    def test_storage_mismatch_never_imports(self):
        self.store.read.side_effect = lambda key: b"wrong"
        with self.assertRaisesRegex(RuntimeError, "^Pharmacy refresh failed$"):
            self.run_refresh()
        self.repository.import_plan.assert_not_called()

    def test_unchanged_and_conflicts_do_not_upload_or_import(self):
        for current, expected in [
            (self.previous, "unchanged"),
            (observation(net="12.00"), "review_required"),
        ]:
            self.assertEqual(self.run_refresh(current)["status"], expected)
        self.store.put_if_absent.assert_not_called()

    def test_unknown_baseline_requires_review_and_does_not_trust_input(self):
        self.repository.load_baseline.return_value = None
        self.assertEqual(self.run_refresh()["reason"], "no_approved_baseline")
        self.store.put_if_absent.assert_not_called()

    def test_invalid_body_and_private_error_are_sanitized(self):
        current = copy.deepcopy(self.current)
        current["payment_capture"]["body"] = b"tampered"
        self.assertEqual(self.run_refresh(current)["status"], "invalid_evidence")
        self.repository.load_baseline.side_effect = RuntimeError("private identifier")
        with self.assertRaisesRegex(RuntimeError, "^Pharmacy refresh failed$") as error:
            self.run_refresh()
        self.assertIsNone(error.exception.__cause__)
        self.store.put_if_absent.assert_not_called()


class PostgresRefreshAdapterTests(unittest.TestCase):
    def setUp(self):
        self.connection = Mock(autocommit=True)
        # Mock does not synthesize context-manager methods.
        from unittest.mock import MagicMock

        self.connection.cursor.return_value = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.store = Mock()
        template = (
            Path(__file__).resolve().parents[2] / "scripts/sql/import-pharmacy-plan.sql"
        ).read_text(encoding="utf-8")
        self.repository = PostgresPharmacyRefreshRepository(
            self.connection, self.store, template
        )

    def test_baseline_uses_latest_scope_and_rehashes_both_originals(self):
        obs = observation()
        pay = obs["payment_capture"]
        reg = register()
        artifacts = []
        for capture, media, url in [
            (pay, "application/json", pay["request_url"]),
            (
                reg,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                reg["source_url"],
            ),
        ]:
            artifacts.append(
                dict(
                    sha256=capture["sha256"],
                    byte_size=capture["byte_size"],
                    http_status=200,
                    source_url=url,
                    content_type=media,
                    object_key=capture["sha256"],
                    retrieved_at="2026-09-09T00:00:00Z",
                )
            )
        self.cursor.fetchone.return_value = dict(
            id=19, approved=True, payment=artifacts[0], register=artifacts[1]
        )
        self.store.read.side_effect = [pay["body"], reg["body"]]
        result = self.repository.load_baseline(obs)
        self.assertEqual(result["snapshot_id"], 19)
        self.assertEqual(result["observation"]["payment_capture"]["body"], pay["body"])
        self.assertEqual(result["register"]["body"], reg["body"])
        query, params = self.cursor.execute.call_args.args
        self.assertIn("order by s.id desc limit 1", query)
        self.assertNotIn(obs["beneficiary"], query)
        self.assertEqual(params[1], 2025)
        self.store.read.side_effect = [b"wrong"]
        with self.assertRaisesRegex(ValueError, "Invalid baseline bytes"):
            self.repository.load_baseline(obs)

    def test_projection_comparison_requires_exact_rows_not_just_counts(self):
        obs = observation()
        obs["payment_capture"]["received_at"] = "2026-09-09T00:00:00Z"
        reg = register()
        reg["retrieved_at"] = "2026-09-09T00:00:00Z"
        plan = prepare_pharmacy_import([obs], register_capture=reg)
        snap = plan["snapshots"][0]
        payload = snap["documents"][0]["payload"]
        row = dict(
            id=payload["document_key"],
            establishment=payload["establishment"],
            date=payload["document_date"],
            amount=payload["net"],
            sha256=snap["payment_sha256"],
            register_sha256=snap["register_sha256"],
        )
        self.cursor.fetchall.return_value = [row]
        self.assertTrue(self.repository.verify_publication(plan))
        for rows in [
            [],
            [row, row],
            [dict(row, amount="11.00")],
            [dict(row, establishment="OUTRA")],
        ]:
            self.cursor.fetchall.return_value = rows
            self.assertFalse(self.repository.verify_publication(plan))

    def test_template_cannot_commit_before_projection_verification(self):
        self.assertFalse(self.repository.template.startswith("begin;"))
        self.assertFalse(self.repository.template.endswith("commit;\n"))
        self.connection.autocommit = False
        with self.assertRaises(ValueError):
            PostgresPharmacyRefreshRepository(self.connection, self.store, "")

    def test_plan_text_cannot_close_the_sql_dollar_block(self):
        from unittest.mock import patch

        from psycopg import sql

        original = sql.Literal.as_string
        plan = {"text": "name ' $import$; SELECT 'not SQL'"}
        with patch.object(
            sql.Literal, "as_string", lambda value, context: original(value)
        ):
            self.repository.import_plan(plan)
        statement = self.connection.execute.call_args.args[0]
        delimiter = statement.splitlines()[0].removeprefix("do ")
        self.assertTrue(delimiter.startswith("$pharmacy_"))
        self.assertEqual(statement.count(delimiter), 2)
        self.assertIn("$import$", statement)
        self.assertNotIn("__PLAN_JSON__", statement)
