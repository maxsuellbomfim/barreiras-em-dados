import json
import unittest

from barreiras_normalization.monthly_assist import (
    MonthlyFinanceFacts,
    build_monthly_assist_messages,
    parse_monthly_assist_response,
)


def facts(status: str = "operational") -> MonthlyFinanceFacts:
    return MonthlyFinanceFacts(
        closure_id="body:2026-06-01",
        period_start="2026-06-01",
        period_end="2026-06-30",
        public_body_name="Prefeitura Municipal de Barreiras",
        closure_status=status,
        coverage_note="Diferenca operacional; nao e saldo fiscal.",
        revenue_report_amount="97976757.57",
        expense_paid_amount="78296115.78",
        operational_difference_amount="19680641.79",
    )


class MonthlyAssistTests(unittest.TestCase):
    def test_prompt_keeps_facts_and_forbids_ia_calculation(self) -> None:
        messages = build_monthly_assist_messages(facts())
        self.assertIn("Não faça contas", messages[0]["content"])
        self.assertIn("97976757.57", messages[1]["content"])
        self.assertIn("sem algarismos", messages[1]["content"])

    def test_parser_accepts_plain_language_without_numbers(self) -> None:
        response = json.dumps(
            {
                "commentary": (
                    "O fechamento reune os relatorios comparaveis disponiveis e mostra "
                    "a diferenca operacional entre entradas declaradas e pagamentos "
                    "efetivados."
                ),
                "statement_class": "fact",
            }
        )
        outcome = parse_monthly_assist_response(response, facts=facts())
        self.assertEqual(outcome.statement_class, "fact")

    def test_parser_rejects_numbers_and_reputational_claims(self) -> None:
        for commentary in (
            "A prefeitura teve R$ 10 de resultado.",
            "Ha indicios de corrupcao neste mes.",
            "O mes tem cobertura completa em 2026.",
        ):
            with self.subTest(commentary=commentary):
                response = json.dumps(
                    {"commentary": commentary, "statement_class": "fact"}
                )
                with self.assertRaises(ValueError):
                    parse_monthly_assist_response(response, facts=facts())

    def test_parser_requires_coverage_explanation_when_data_is_missing(self) -> None:
        response = json.dumps(
            {
                "commentary": "O periodo esta pronto para leitura.",
                "statement_class": "fact",
            }
        )
        with self.assertRaisesRegex(ValueError, "cobertura"):
            parse_monthly_assist_response(response, facts=facts("needs_data"))

    def test_parser_rejects_missing_data_claim_for_operational_closure(self) -> None:
        response = json.dumps(
            {
                "commentary": "Os relatorios comparaveis ainda nao estao disponiveis.",
                "statement_class": "fact",
            }
        )
        with self.assertRaisesRegex(ValueError, "contradiz"):
            parse_monthly_assist_response(response, facts=facts("operational"))
