import json
import unittest

from barreiras_docproc.financial_assist import (
    build_financial_messages,
    parse_financial_assist_response,
)

EXCERPT = (
    "Data: De 01/06/2026 até 30/06/2026\n"
    "1.0.0.0.00.0.0.00.00.00 Receitas Correntes "
    "1.090.453.144,00 106.245.940,88 532.630.204,77 0,00 557.822.939,23"
)


class FinancialAssistTests(unittest.TestCase):
    def test_prompt_forbids_arithmetic_and_requires_literal_evidence(self):
        messages = build_financial_messages(EXCERPT)
        joined = " ".join(message["content"] for message in messages)
        self.assertIn("Nunca some", joined)
        self.assertIn("evidence", joined)

    def test_response_is_accepted_only_with_literal_row_anchor(self):
        payload = {
            "document_kind": "revenue_statement",
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "explanation": "Relatorio mensal de receitas orcamentarias.",
            "rows": [
                {
                    "code": "1.0.0.0.00.0.0.00.00.00",
                    "description": "Receitas Correntes",
                    "forecast": "1.090.453.144,00",
                    "period": "106.245.940,88",
                    "accumulated": "532.630.204,77",
                    "difference_more": "0,00",
                    "difference_less": "557.822.939,23",
                    "evidence": (
                        "1.0.0.0.00.0.0.00.00.00 Receitas Correntes "
                        "1.090.453.144,00 106.245.940,88 532.630.204,77 "
                        "0,00 557.822.939,23"
                    ),
                }
            ],
        }
        result = parse_financial_assist_response(
            json.dumps(payload), excerpt=EXCERPT
        )
        self.assertEqual(result["rows"][0]["accumulated"], "532.630.204,77")

    def test_response_rejects_number_not_present_in_evidence(self):
        payload = {
            "document_kind": "revenue_statement",
            "period_start": None,
            "period_end": None,
            "explanation": None,
            "rows": [
                {
                    "code": "1.0.0.0.00.0.0.00.00.00",
                    "description": "Receitas Correntes",
                    "forecast": "1.090.453.144,00",
                    "period": "106.245.940,88",
                    "accumulated": "999.999.999,99",
                    "difference_more": "0,00",
                    "difference_less": "557.822.939,23",
                    "evidence": EXCERPT,
                }
            ],
        }
        with self.assertRaises(ValueError):
            parse_financial_assist_response(json.dumps(payload), excerpt=EXCERPT)


if __name__ == "__main__":
    unittest.main()
