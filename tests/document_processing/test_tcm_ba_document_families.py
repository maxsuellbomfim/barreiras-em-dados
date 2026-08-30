from __future__ import annotations

import hashlib
import unittest

from barreiras_docproc.processing import TextArtifact
from barreiras_docproc.tcm_ba_document_families import (
    EXTRACTOR_VERSION,
    TcmBaCatalogDocument,
    classify_document_family,
    document_family_job_idempotency_key,
    document_family_payload,
)


class TcmBaDocumentFamilyTests(unittest.TestCase):
    def test_classifies_only_literal_official_catalog_codes(self) -> None:
        cases = {
            "PCMGE009 - Contratos e aditivos": "contracts_and_amendments",
            "pcmge010 - Convênios e avisos de crédito": "agreements_and_credit_notices",
            " PCMGE011 — Decretos de QDD ": "qdd_decrees",
            "PCMGE012 - Créditos adicionais especiais": "special_credit_decrees",
            "PCMGE013 - Créditos adicionais extraordinários": (
                "extraordinary_credit_decrees"
            ),
            "PCMGE014 - Créditos adicionais suplementares": (
                "supplementary_credit_decrees"
            ),
            "PCMGE015 - Demonstrativo analítico de despesa": (
                "analytical_budget_expense_statement"
            ),
            "PCMGE016 - Demonstrativo analítico de receita orçamentária": (
                "analytical_budget_revenue_statement"
            ),
            "PCMGE018 - Demonstrativo das contas do razão": (
                "general_ledger_accounts_statement"
            ),
            "PCMGE019 - Ingressos e desembolsos extraorçamentários": (
                "extra_budgetary_inflows_outflows_statement"
            ),
            "PCMGE020 - Dispensas e inexigibilidades ratificadas": (
                "ratified_procurement_waivers_and_noncompetitive_contracts"
            ),
            "Documentos Adicionais": "additional_documents",
        }

        for category, expected in cases.items():
            with self.subTest(category=category):
                classification = classify_document_family(category)
                self.assertEqual(classification.family, expected)
                self.assertEqual(classification.status, "classified")
                self.assertEqual(classification.basis, "official_catalog_category")

    def test_unrecognized_or_ambiguous_category_remains_unknown(self) -> None:
        for category in (
            "",
            "Contrato administrativo",
            "PCMGE999 - Categoria nova",
            "Documentos Adicionais - contratos",
        ):
            with self.subTest(category=category):
                classification = classify_document_family(category)
                self.assertEqual(classification.family, "unknown")
                self.assertEqual(classification.status, "unknown")

    def test_payload_omits_document_name_and_financial_values(self) -> None:
        document = TcmBaCatalogDocument(
            artifact=TextArtifact(
                raw_artifact_id="00000000-0000-0000-0000-000000000902",
                sha256="b" * 64,
                object_key="tcm-ba/monthly-documents/2021/01/a.pdf",
            ),
            source_record_key="tcm-ba:document:01/2021:abc",
            official_category="PCMGE009 - Contratos e aditivos",
        )

        payload = document_family_payload(
            document,
            classify_document_family(document.official_category),
        )

        self.assertEqual(payload["family"], "contracts_and_amendments")
        self.assertEqual(payload["official_category_code"], "PCMGE009")
        self.assertEqual(payload["extractor_version"], EXTRACTOR_VERSION)
        self.assertNotIn("name", payload)
        self.assertNotIn("amount", payload)
        self.assertNotIn("value", payload)
        self.assertNotIn("official_category", payload)

    def test_idempotency_changes_with_extractor_contract(self) -> None:
        key = document_family_job_idempotency_key("a" * 64)
        previous_key = hashlib.sha256(
            f"tcm-ba-document-family:{'a' * 64}:"
            "tcm-ba-document-family-inventory/1.1.0".encode()
        ).hexdigest()

        self.assertRegex(key, r"^[0-9a-f]{64}$")
        self.assertEqual(key, document_family_job_idempotency_key("a" * 64))
        self.assertNotEqual(key, previous_key)


if __name__ == "__main__":
    unittest.main()
