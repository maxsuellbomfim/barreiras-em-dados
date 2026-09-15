import hashlib
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace

from barreiras_collectors.commands import collect_pncp_municipal_link_evidence as cmd
from barreiras_collectors.connectors.pncp import RegistrySnapshot


def snapshots():
    contract = {
        "numeroControlePNCP": cmd.CONTRACT,
        "numeroControlePNCPCompra": cmd.PARENT,
        "orgaoEntidade": {"cnpj": cmd.MUNICIPAL_CNPJ},
        "unidadeOrgao": {"codigoIbge": "2903201"},
        "valorGlobal": 28780,
    }
    parent = {
        "numeroControlePNCP": cmd.PARENT,
        "orgaoEntidade": {"cnpj": cmd.FUND_CNPJ},
        "unidadeOrgao": {"codigoIbge": "2903201"},
    }
    result = []
    for (resource, url), payload in zip(cmd.RESOURCES, (contract, parent), strict=True):
        body = json.dumps(payload).encode()
        result.append(
            RegistrySnapshot(
                resource,
                url,
                url,
                "2026-09-15T21:00:00Z",
                200,
                body,
                hashlib.sha256(body).hexdigest(),
                "application/json",
            )
        )
    return result


class MunicipalLinkEvidenceTests(unittest.TestCase):
    def test_exact_pair_preserved_before_validation_without_publication(self):
        pages = snapshots()
        calls = []
        service = SimpleNamespace(
            persist=lambda page: (
                calls.append(page.body)
                or SimpleNamespace(
                    raw_artifact_id=f"artifact-{len(calls)}", created=True
                )
            )
        )
        summary = cmd.collect_pair(service=service, fetch=lambda *args: pages.pop(0))
        self.assertEqual(len(calls), 2)
        self.assertEqual(summary["validated_artifacts"], 2)
        self.assertFalse(summary["publication_authorized"])
        self.assertNotIn("28780", json.dumps(summary))

    def test_mismatching_parent_municipality_or_cnpj_is_rejected(self):
        for index, field, value in [
            (0, "numeroControlePNCPCompra", "other"),
            (1, "numeroControlePNCP", "other"),
            (1, "orgaoEntidade", {"cnpj": cmd.MUNICIPAL_CNPJ}),
            (1, "unidadeOrgao", {"codigoIbge": "other"}),
        ]:
            pages = snapshots()
            payload = json.loads(pages[index].body)
            payload[field] = value
            body = json.dumps(payload).encode()
            pages[index] = replace(
                pages[index], body=body, body_sha256=hashlib.sha256(body).hexdigest()
            )
            with self.subTest(field=field), self.assertRaises(ValueError):
                cmd.validate_pair(*pages)

    def test_validation_rejects_changed_hash_redirect_and_ambiguous_link_fields(self):
        for update in (
            {"body_sha256": "0" * 64},
            {"final_url": "https://example.org"},
            {"http_status": 404},
        ):
            pages = snapshots()
            pages[0] = replace(pages[0], **update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                cmd.validate_pair(*pages)
        pages = snapshots()
        payload = json.loads(pages[0].body)
        payload["numeroControlePncpCompra"] = "conflict"
        body = json.dumps(payload).encode()
        pages[0] = replace(
            pages[0], body=body, body_sha256=hashlib.sha256(body).hexdigest()
        )
        with self.assertRaises(ValueError):
            cmd.validate_pair(*pages)

    def test_invalid_pair_stays_private_and_fails_after_preservation(self):
        pages = snapshots()
        pages[1] = replace(pages[1], body=b"{}")
        saved = []
        service = SimpleNamespace(
            persist=lambda p: (
                saved.append(p) or SimpleNamespace(raw_artifact_id="id", created=False)
            )
        )
        with self.assertRaises(ValueError):
            cmd.collect_pair(service=service, fetch=lambda *args: pages.pop(0))
        self.assertEqual(len(saved), 2)

    def test_control_starts_before_operation_and_is_not_completed_on_error(self):
        events = []

        class Control:
            def __enter__(self):
                events.append("start")
                return self

            def __exit__(self, *args):
                events.append("exit")

            def complete(self, **kwargs):
                events.append("complete")

        def operation():
            self.assertEqual(events, ["start"])
            raise ValueError("failed")

        with self.assertRaises(ValueError):
            cmd.execute_controlled_pair(control=Control(), operation=operation)
        self.assertEqual(events, ["start", "exit"])
