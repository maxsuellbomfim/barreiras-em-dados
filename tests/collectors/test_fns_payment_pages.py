import json
import unittest

from barreiras_collectors.connectors.fns_payment_pages import normalize_payment_pages


def payment(number="000001", reason=""):
    return dict(
        id=dict(mes="11", ano="2024", processoFormatado="25000.017577/2025-48"),
        anoPagamento="2025",
        mesPagamento="02",
        dataCriacaoSiafi="07/02/2025",
        numeroDocumentoSiafi=number,
        tipoDocumentoPagamento="OB",
        uf="BA",
        competencia="NOV de 2024",
        valorTotal=100,
        valorDescontoTotal=5,
        valorLiquido=95,
        valorAnulacao=0,
        motivoRejeicao=reason,
        contaCorrente="PRIVATE",
    )


def page(index, item):
    return json.dumps(
        dict(
            resultado=dict(
                pagina=index, total=2, totalPaginas=2, itensPorPagina=1, dados=[item]
            )
        )
    ).encode()


class PaymentPagesTests(unittest.TestCase):
    def test_invalid_money_and_duplicate_json_keys_fail_closed(self):
        item = payment()
        item["valorTotal"] = "NaN"
        self.assertEqual(
            self.normalize([item, payment("000002")]),
            dict(status="invalid_pages", publication_allowed=False),
        )
        raw = page(0, payment()).replace(b'"total": 2', b'"total": 2, "total": 2')
        result = normalize_payment_pages(
            [raw, page(1, payment("000002"))], action_id=1, payment_year=2025
        )
        self.assertEqual(result["status"], "invalid_pages")

    def normalize(self, rows=None):
        rows = rows or [payment(), payment("000002")]
        return normalize_payment_pages(
            [page(i, r) for i, r in enumerate(rows)], action_id=66458, payment_year=2025
        )

    def test_cross_year_competence_is_not_payment_date(self):
        result = self.normalize()
        self.assertEqual(result["status"], "normalized")
        self.assertEqual(result["records"][0]["order_scope"]["ano"], "2024")
        self.assertEqual(result["records"][0]["order_scope"]["mes"], "11")
        self.assertEqual(result["records"][0]["document_date"], "2025-02-07")
        self.assertEqual(result["document_totals"]["net"], "190.00")
        self.assertFalse(result["publication_allowed"])
        self.assertNotIn("PRIVATE", str(result))

    def test_rejection_and_distinct_orders_are_retained(self):
        result = self.normalize(
            [payment(reason="PRIVATE CANCELAMENTO"), payment("000002")]
        )
        self.assertEqual(len(result["records"]), 2)
        self.assertIn("source_rejection", result["records"][0]["review_reasons"])
        self.assertNotEqual(
            result["records"][0]["document_key"], result["records"][1]["document_key"]
        )
        self.assertEqual(result["status"], "review_required")

    def test_repeated_document_is_flagged_not_dropped(self):
        result = self.normalize([payment(), payment()])
        self.assertEqual(len(result["records"]), 2)
        self.assertTrue(
            all(
                "repeated_document_key" in r["review_reasons"]
                for r in result["records"]
            )
        )

    def test_unbalanced_and_annulled_are_review(self):
        item = payment()
        item["valorLiquido"] = 90
        item["valorAnulacao"] = 1
        reasons = self.normalize([item, payment("000002")])["records"][0][
            "review_reasons"
        ]
        self.assertIn("unbalanced_amounts", reasons)
        self.assertIn("source_annulment", reasons)

    def test_incomplete_and_invalid_scope_fail_closed(self):
        self.assertEqual(
            normalize_payment_pages(
                [page(0, payment())], action_id=1, payment_year=2025
            )["status"],
            "invalid_pages",
        )
        item = payment()
        item["anoPagamento"] = "2026"
        self.assertEqual(
            self.normalize([item, payment("000002")])["status"], "invalid_pages"
        )
