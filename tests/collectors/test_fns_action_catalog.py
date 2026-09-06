import json
import unittest

from barreiras_collectors.connectors.fns_action_catalog import (
    FNSCatalogError,
    plan_fns_actions,
)


def page(number, rows, total=3, pages=2):
    return json.dumps(
        {
            "resultado": {
                "pagina": number,
                "total": total,
                "totalPaginas": pages,
                "itensPorPagina": 2,
                "dados": rows,
            }
        }
    ).encode()


def row(identifier, description="Outra ação", value="2.00"):
    return {
        "id": identifier,
        "descricao": description,
        "valorTotal": value,
        "valorDescontoTotal": "0.00",
        "valorLiquido": value,
        "valorTotalGeral": "4.00",
        "valorDescontoTotalGeral": "0.00",
        "valorLiquidoGeral": "4.00",
    }


class FNSActionCatalogTests(unittest.TestCase):
    def setUp(self):
        self.pages = [
            page(1, [row(10, "EMENDA - SAÚDE"), row(11)]),
            page(2, [row(0, "", "0.00")]),
        ]

    def test_all_actions_are_planned_not_only_emenda_descriptions(self):
        result = plan_fns_actions(self.pages)
        self.assertEqual(result["action_ids"], [10, 11])
        self.assertEqual(result["zero_group_rows"], 1)
        self.assertEqual(result["net_amount"], "4.00")
        self.assertEqual(result["payment_coverage"], "not_collected")
        self.assertFalse(result["publication_allowed"])

    def test_missing_repeated_or_reordered_pages_rejected(self):
        for pages in (self.pages[:1], self.pages[::-1], [self.pages[0]] * 2):
            with self.subTest(pages=pages), self.assertRaises(FNSCatalogError):
                plan_fns_actions(pages)

    def test_duplicate_positive_id_rejected(self):
        with self.assertRaises(FNSCatalogError):
            plan_fns_actions([page(1, [row(10), row(10)]), self.pages[1]])

    def test_totals_and_zero_groups_must_reconcile(self):
        for field, value in (
            ("valorLiquido", "2.01"),
            ("valorTotalGeral", "5"),
            ("id", True),
            ("valorTotal", "NaN"),
        ):
            body = json.loads(self.pages[0])
            body["resultado"]["dados"][0][field] = value
            with self.subTest(field=field), self.assertRaises(FNSCatalogError):
                plan_fns_actions([json.dumps(body).encode(), self.pages[1]])
        with self.assertRaises(FNSCatalogError):
            plan_fns_actions([self.pages[0], page(2, [row(0)])])

    def test_multiple_distinct_zero_groups_preserved(self):
        bodies = [
            page(1, [row(10), row(11)], total=4),
            page(2, [row(0, "", "0.00"), row(0, "", "0.00")], total=4),
        ]
        self.assertEqual(plan_fns_actions(bodies)["zero_group_rows"], 2)

    def test_empty_input_does_not_prove_empty_year(self):
        with self.assertRaises(FNSCatalogError):
            plan_fns_actions([])

    def test_totals_can_be_null_after_first_row_but_not_missing_everywhere(self):
        bodies = [json.loads(body) for body in self.pages]
        for body in bodies:
            for item in body["resultado"]["dados"]:
                if item["id"] != 10:
                    for field in (
                        "valorTotalGeral",
                        "valorDescontoTotalGeral",
                        "valorLiquidoGeral",
                    ):
                        item[field] = None
        self.assertEqual(
            plan_fns_actions([json.dumps(b).encode() for b in bodies])["net_amount"],
            "4.00",
        )
        for body in bodies:
            for item in body["resultado"]["dados"]:
                for field in (
                    "valorTotalGeral",
                    "valorDescontoTotalGeral",
                    "valorLiquidoGeral",
                ):
                    item.pop(field)
        with self.assertRaises(FNSCatalogError):
            plan_fns_actions([json.dumps(b).encode() for b in bodies])
