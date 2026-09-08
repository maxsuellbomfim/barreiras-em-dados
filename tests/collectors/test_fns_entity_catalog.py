import hashlib
import json
import unittest

from barreiras_collectors.connectors.fns_entity_catalog import inspect_entity_catalog


def capture(page=1, total=1, ids=None, year=2025):
    rows = [
        dict(
            cpfCnpj=i,
            uf="BA",
            codigoMunicipioIBGE="290320",
            razaoSocial="PRIVATE_NAME",
            cpfCnpjFormatado="PRIVATE_ID",
        )
        for i in (ids if ids is not None else ["12345678901"])
    ]
    body = json.dumps(
        dict(
            resultado=dict(
                dados=rows,
                pagina=page - 1,
                total=total,
                totalPaginas=(total + 9) // 10,
                itensPorPagina=10,
            )
        )
    ).encode()
    url = (
        "https://consultafns.saude.gov.br/recursos/consulta-detalhada/entidades"
        f"?ano={year}&tipoConsulta=3&estado=BA&municipio=290320&page={page}&count=10"
    )
    return dict(
        body=body,
        request_url=url,
        final_url=url,
        http_status=200,
        sha256=hashlib.sha256(body).hexdigest(),
        byte_size=len(body),
    )


class EntityCatalogTests(unittest.TestCase):
    def test_complete_private_plan_does_not_infer_pharmacy_or_identity(self):
        result = inspect_entity_catalog([capture()], payment_year=2025)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["entities"], 1)
        self.assertEqual(len(result["references"]), 1)
        self.assertFalse(result["publication_allowed"])
        self.assertEqual(result["program_classification"], "not_performed")
        for secret in ("12345678901", "PRIVATE_NAME", "PRIVATE_ID"):
            self.assertNotIn(secret, json.dumps(result))

    def test_full_pagination_is_required(self):
        first = capture(total=11, ids=[str(i) for i in range(1, 11)])
        last = capture(page=2, total=11, ids=["11"])
        self.assertEqual(
            inspect_entity_catalog([first], payment_year=2025)["status"], "partial"
        )
        self.assertEqual(
            inspect_entity_catalog([last, first], payment_year=2025)["entities"], 11
        )
        self.assertEqual(
            inspect_entity_catalog([first, last], payment_year=2025)["status"],
            "complete",
        )

    def test_empty_is_not_uncollected(self):
        self.assertEqual(
            inspect_entity_catalog([], payment_year=2025)["status"], "not_collected"
        )
        self.assertEqual(
            inspect_entity_catalog([capture(total=0, ids=[])], payment_year=2025)[
                "status"
            ],
            "empty",
        )

    def test_duplicate_identity_or_page_and_changed_total_fail_closed(self):
        for pages in (
            [capture(), capture()],
            [capture(total=2, ids=["1", "1"])],
            [
                capture(total=11, ids=[str(i) for i in range(10)]),
                capture(page=2, total=12, ids=["11", "12"]),
            ],
        ):
            self.assertEqual(
                inspect_entity_catalog(pages, payment_year=2025)["status"],
                "invalid_capture",
            )

    def test_scope_integrity_and_query_fail_closed(self):
        for field, value in (
            ("sha256", "0" * 64),
            ("http_status", 500),
            ("byte_size", 1),
            ("final_url", "https://example.com"),
        ):
            c = capture()
            c[field] = value
            self.assertEqual(
                inspect_entity_catalog([c], payment_year=2025)["status"],
                "invalid_capture",
            )
        c = capture()
        c["request_url"] += "&ano=2025"
        c["final_url"] = c["request_url"]
        self.assertEqual(
            inspect_entity_catalog([c], payment_year=2025)["status"], "invalid_capture"
        )
        self.assertEqual(
            inspect_entity_catalog([capture(year=2024)], payment_year=2025)["status"],
            "invalid_capture",
        )

    def test_partial_page_and_duplicate_json_fail_closed(self):
        self.assertEqual(
            inspect_entity_catalog([capture(total=10)], payment_year=2025)["status"],
            "invalid_capture",
        )
        c = capture()
        c["body"] = c["body"].replace(b'"total": 1', b'"total": 1, "total": 1')
        c["sha256"] = hashlib.sha256(c["body"]).hexdigest()
        c["byte_size"] = len(c["body"])
        self.assertEqual(
            inspect_entity_catalog([c], payment_year=2025)["status"], "invalid_capture"
        )
