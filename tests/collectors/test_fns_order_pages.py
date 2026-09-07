import json
import unittest

from barreiras_collectors.connectors.fns_order_pages import inspect_order_pages


def body(page, rows, total=3):
    return json.dumps(
        {
            "resultado": {
                "pagina": page,
                "itensPorPagina": 2,
                "total": total,
                "totalPaginas": 2,
                "dados": rows,
            }
        }
    ).encode()


def row(code="290320", name="BARREIRAS", reason=""):
    return {
        "codigoIBGE": code,
        "municipio": name,
        "uf": "BA",
        "valor": "1493.93",
        "motivoRejeicao": reason,
        "contaCorrente": "PRIVATE",
    }


class OrderPagesTests(unittest.TestCase):
    def setUp(self):
        self.pages = [
            body(0, [row("290070", "ALAGOINHAS"), row()]),
            body(1, [row("290460", "BRUMADO")]),
        ]

    def test_unique_barreiras_requires_full_scope_and_minimizes_output(self):
        result = inspect_order_pages(self.pages)
        self.assertEqual(result["status"], "unique_territorial_row")
        self.assertEqual(result["amount"], "1493.93")
        self.assertFalse(result["publication_allowed"])
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertEqual(len(result["page_sha256"]), 2)

    def test_missing_repeated_or_reordered_pages_are_invalid(self):
        for pages in ([], self.pages[:1], self.pages[::-1], [self.pages[0]] * 2):
            self.assertEqual(inspect_order_pages(pages)["status"], "invalid_pages")

    def test_second_barreiras_on_later_page_is_ambiguous_even_if_identical(self):
        self.pages[1] = body(1, [row()])
        self.assertEqual(inspect_order_pages(self.pages)["status"], "ambiguous")

    def test_rejection_is_review_not_a_payment_or_automatic_zero(self):
        self.pages[0] = body(
            0, [row("290070", "ALAGOINHAS"), row(reason="PRIVATE CANCELAMENTO")]
        )
        result = inspect_order_pages(self.pages)
        self.assertEqual(result["status"], "review_required")
        self.assertNotIn("amount", result)
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_absent_is_not_invalid_or_zero(self):
        self.pages[0] = body(0, [row("290070", "ALAGOINHAS"), row("290460", "BRUMADO")])
        self.assertEqual(inspect_order_pages(self.pages)["status"], "not_found")

    def test_code_name_disagreement_blocks_selection(self):
        self.pages[1] = body(1, [row("290460", "BARREIRAS")])
        self.assertEqual(
            inspect_order_pages(self.pages)["status"], "territory_conflict"
        )

    def test_malformed_json_and_money_fail_closed(self):
        self.assertEqual(inspect_order_pages([b"PRIVATE"])["status"], "invalid_pages")
        target = row()
        target["valor"] = "NaN"
        self.pages[0] = body(0, [row("290070", "ALAGOINHAS"), target])
        self.assertEqual(inspect_order_pages(self.pages)["status"], "invalid_pages")
