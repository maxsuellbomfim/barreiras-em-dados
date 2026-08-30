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
            "PCMGE021 - Extratos e conciliações bancárias": (
                "bank_statements_and_reconciliations"
            ),
            "PCMGE022 - Guias de multas e ressarcimentos do TCM": (
                "tcm_fines_and_reimbursements_revenue_guides"
            ),
            "PCMGE023 - Guias de alienação de bens": ("asset_disposal_revenue_guides"),
            "PCMGE024 - Alteração do plano plurianual": ("multi_year_plan_amendments"),
            "PCMGE025 - Alterações da LDO": "budget_guidelines_law_amendments",
            "PCMGE026 - Alteração do plano de cargos e salários": (
                "positions_and_salaries_plan_amendments"
            ),
            "PCMGE027 - Alterações da lei de diárias": (
                "travel_allowance_law_amendments"
            ),
            "PCMGE028 - Revisão dos subsídios dos agentes políticos": (
                "political_agent_compensation_reviews"
            ),
            "PCMGE029 - Leis de créditos especiais": "special_credit_laws",
            "PCMGE030 - Leis de créditos suplementares": ("supplementary_credit_laws"),
            "PCMGE031 - Ofício de encaminhamento da prestação mensal": (
                "monthly_accounts_submission_letter"
            ),
            "PCMGE035 - Processos de pagamento da folha sintética": (
                "synthetic_payroll_payment_processes"
            ),
            "PCMGE037 - Processos de pagamento da educação (25%)": (
                "education_25_percent_payment_processes"
            ),
            "PCMGE038 - Processos de pagamento da saúde (15%)": (
                "health_15_percent_payment_processes"
            ),
            "PCMGE041 - Processos de pagamento do FUNDEB (40%)": (
                "fundeb_40_percent_payment_processes"
            ),
            "PCMGE043 - Processos de pagamento do FUNDEB (60%)": (
                "fundeb_60_percent_payment_processes"
            ),
            "PCMGE046 - Folha sintética dos agentes políticos": (
                "political_agents_synthetic_payroll_payment_processes"
            ),
            "PCMGE049 - Processos de pagamento orçamentário": (
                "budgetary_payment_processes"
            ),
            "PCMGE050 - Processos de pagamento extraorçamentário": (
                "extra_budgetary_payment_processes"
            ),
            "PCMGE051 - Processos licitatórios homologados": (
                "homologated_procurement_processes"
            ),
            "PCMGE053 - Relação de contas e aplicações financeiras": (
                "bank_accounts_and_financial_investments_register"
            ),
            "PCMGE054 - Relação das guias de receitas arrecadadas": (
                "collected_revenue_guides_register"
            ),
            "PCMGE055 - Relação de pagamentos extraorçamentários": (
                "extra_budgetary_payment_process_register"
            ),
            "PCMGE056 - Relação de pagamentos orçamentários": (
                "budgetary_payment_process_register"
            ),
            "PCMGE058 - Relatório do Controle Interno": "internal_control_report",
            "PCMGE075 - Lei de diretrizes orçamentárias": "budget_guidelines_law",
            "PCMGE076 - Lei orçamentária anual": "annual_budget_law",
            "PCMGE077 - Programação financeira e cronograma de desembolso": (
                "financial_schedule_and_disbursement_timeline"
            ),
            "PCMGE078 - Metas bimestrais de arrecadação": ("bimonthly_revenue_targets"),
            "PCMGE079 - Lei de estrutura administrativa": (
                "administrative_structure_law"
            ),
            "PCMGE080 - Estatuto do servidor público": "civil_service_statute",
            "PCMGE081 - Lei do regime próprio de previdência": (
                "municipal_pension_regime_law"
            ),
            "PCMGE082 - Lei de contratação temporária": "temporary_hiring_law",
            "PCMGE083 - Código tributário municipal": "municipal_tax_code",
            "PCMGE084 - Lei de ordenamento e uso do solo": "land_use_law",
            "PCMGE085 - Calendário de feriados": "holiday_calendar",
            "PCMGE091 - Lei do plano de cargos e salários": (
                "positions_and_salaries_plan_law"
            ),
            "PCMGE094 - Lei municipal de diárias": "travel_allowance_law",
            "PCMGE095 - Lei Orgânica do Município": "municipal_organic_law",
            "PCMGE096 - Lei dos subsídios dos agentes políticos": (
                "political_agent_compensation_law"
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
        self.assertEqual(EXTRACTOR_VERSION, "tcm-ba-document-family-inventory/1.3.0")
        key = document_family_job_idempotency_key("a" * 64)
        previous_key = hashlib.sha256(
            f"tcm-ba-document-family:{'a' * 64}:"
            "tcm-ba-document-family-inventory/1.2.0".encode()
        ).hexdigest()

        self.assertRegex(key, r"^[0-9a-f]{64}$")
        self.assertEqual(key, document_family_job_idempotency_key("a" * 64))
        self.assertNotEqual(key, previous_key)


if __name__ == "__main__":
    unittest.main()
