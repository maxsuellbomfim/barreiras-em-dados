import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from barreiras_collectors.commands.audit_fns_comparisons import audit, main


class AuditCommandTests(unittest.TestCase):
    def connection(self, records=(), artifacts=()):
        c = Mock()
        c.execute.side_effect = [
            Mock(),
            Mock(),
            Mock(fetchall=lambda: list(records)),
            Mock(fetchall=lambda: list(artifacts)),
        ]
        return c

    def test_empty_is_not_a_successful_financial_zero(self):
        c = self.connection()
        result, code = audit(c, action_id=66458, payment_year=2025)
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "no_comparisons")
        self.assertFalse(result["publication_allowed"])
        sql = c.execute.call_args_list[0].args[0].lower()
        self.assertIn("read only", sql)
        self.assertIn("repeatable read", sql)
        self.assertEqual(c.execute.call_args_list[2].args[1], ("66458", "2025"))

    def test_invalid_scope_does_not_query_database(self):
        c = Mock()
        with self.assertRaises(ValueError):
            audit(c, action_id=66458, payment_year=2020)
        c.execute.assert_not_called()

    @patch(
        "barreiras_collectors.commands.audit_fns_comparisons.inspect_comparison_freshness"
    )
    def test_pending_is_nonzero_and_raw_fields_never_leave_command(self, inspect):
        inspect.return_value = dict(
            status="current_preserved_evidence",
            comparison_status="order_not_found",
            publication_allowed=False,
        )
        result, code = audit(
            self.connection(
                [dict(payload={"PRIVATE": "secret"}, payload_sha256="hash")]
            ),
            action_id=66458,
            payment_year=2025,
        )
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "needs_attention")
        self.assertNotIn("PRIVATE", json.dumps(result))

    @patch(
        "barreiras_collectors.commands.audit_fns_comparisons.inspect_comparison_freshness"
    )
    def test_current_documentary_comparison_is_not_publication(self, inspect):
        inspect.return_value = dict(
            status="current_preserved_evidence",
            comparison_status="consistent_documentary_pair",
            publication_allowed=False,
        )
        result, code = audit(
            self.connection([dict(payload={}, payload_sha256="hash")]),
            action_id=66458,
            payment_year=2025,
        )
        self.assertEqual(code, 0)
        self.assertFalse(result["publication_allowed"])

    def test_truncation_fails_instead_of_reporting_partial_success(self):
        with self.assertRaises(ValueError):
            audit(self.connection([{}] * 1001), action_id=66458, payment_year=2025)
        with self.assertRaises(ValueError):
            audit(self.connection([], [{}] * 10001), action_id=66458, payment_year=2025)

    @patch(
        "barreiras_collectors.commands.audit_fns_comparisons.PostgresSettings.from_env"
    )
    def test_configuration_error_is_sanitized(self, settings):
        settings.side_effect = RuntimeError("PRIVATE password")
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--action-id", "66458", "--payment-year", "2025"])
        self.assertEqual(code, 1)
        self.assertNotIn("PRIVATE", output.getvalue())
