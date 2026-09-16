import unittest
from types import SimpleNamespace

from tests.collectors.test_pncp_municipal_link_evidence import snapshots


class SocialFundPublicationTests(unittest.TestCase):
    def test_failure_diagnostic_never_exposes_driver_payload(self):
        from barreiras_collectors.commands.publish_pncp_social_fund import failure_code

        error = RuntimeError("private payload and credentials")
        error.sqlstate = "42501"
        self.assertEqual(failure_code(error), "RuntimeError:42501")
        error.sqlstate = "private payload"
        self.assertEqual(failure_code(error), "RuntimeError:unknown")

    def test_missing_or_invalid_bytes_never_call_publication(self):
        from barreiras_collectors.commands.publish_pncp_social_fund import publish_pair

        calls = []
        connection = SimpleNamespace(
            execute=lambda *args: (
                calls.append(args) or SimpleNamespace(fetchall=lambda: [])
            )
        )
        with self.assertRaises(ValueError):
            publish_pair(connection, SimpleNamespace(read=lambda key: b"{}"))
        self.assertEqual(len(calls), 1)

    def test_verified_pair_uses_only_private_function_and_original_bytes(self):
        from barreiras_collectors.commands.publish_pncp_social_fund import publish_pair

        pages = snapshots()
        rows = [
            (str(i), p.url, f"key-{i}", p.body_sha256, p.fetched_at, p.http_status)
            for i, p in enumerate(pages)
        ]
        calls = []

        def execute(sql, params=None):
            calls.append((sql, params))
            return SimpleNamespace(
                fetchall=lambda: rows,
                fetchone=lambda: (
                    {"contracts": 1, "procurements": 1, "status": "published"},
                ),
            )

        store = SimpleNamespace(read=lambda key: pages[int(key[-1])].body)
        self.assertEqual(
            publish_pair(SimpleNamespace(execute=execute), store)["status"], "published"
        )
        self.assertIn("publish_social_fund_pair", calls[1][0])
        self.assertEqual(calls[1][1], ("0", pages[0].body, "1", pages[1].body))
        calls.clear()
        store.read = lambda key: b"{}"
        with self.assertRaises(ValueError):
            publish_pair(SimpleNamespace(execute=execute), store)
        self.assertEqual(len(calls), 1)
