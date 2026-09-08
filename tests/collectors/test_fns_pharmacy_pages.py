import hashlib
import json
import unittest

from barreiras_collectors.connectors.fns_pharmacy_pages import inspect_pharmacy_capture


def capture(rows=None):
    rows = (
        rows
        if rows is not None
        else [
            dict(
                nomeComponente="FARMACIA POPULAR",
                uf="BA",
                anoPagamento="2025",
                mesPagamento="02",
                dataCriacaoSiafi="07/02/2025",
                competencia="JAN de 2025",
                numeroDocumentoSiafi="000001",
                tipoDocumentoPagamento="OB",
                id=dict(esferaAdministrativa="PRIVADA", programaFundo=dict(id=1)),
                valorTotal="10.10",
                valorDescontoTotal="0.10",
                valorLiquido="10.00",
                valorAnulacao=0,
                motivoRejeicao="",
                valorTotalGeral="10.10",
                valorDescontoTotalGeral="0.10",
                valorLiquidoGeral="10.00",
                contaCorrente="DO_NOT_EXPOSE",
                processo="DO_NOT_EXPOSE",
            )
        ]
    )
    body = json.dumps(
        dict(
            resultado=dict(
                dados=rows, pagina=0, total=len(rows), totalPaginas=1, itensPorPagina=25
            )
        )
    ).encode()
    url = (
        "https://consultafns.saude.gov.br/recursos/consulta-detalhada/"
        "detalhe-pagamento?ano=2025&tipoConsulta=3&estado=BA&municipio=290320"
        "&page=1&count=25&cpfCnpjUg=00000000000000"
    )
    return dict(
        body=body,
        request_url=url,
        final_url=url,
        http_status=200,
        byte_size=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
    )


class PharmacyTests(unittest.TestCase):
    def test_empty_nonfinite_and_duplicate_json_fail_closed(self):
        self.assertEqual(self.inspect(capture([]))["status"], "invalid_capture")
        for transform in (
            lambda raw: raw.replace(b'"total": 1', b'"total": 1, "total": 1'),
            lambda raw: raw.replace(b'"10.10"', b'NaN'),
        ):
            c = capture()
            c["body"] = transform(c["body"])
            c["byte_size"] = len(c["body"])
            c["sha256"] = hashlib.sha256(c["body"]).hexdigest()
            self.assertEqual(self.inspect(c)["status"], "invalid_capture")

    def inspect(self, c):
        return inspect_pharmacy_capture(
            c, beneficiary="00000000000000", payment_year=2025
        )

    def test_private_allowlist_and_documentary_totals(self):
        result = self.inspect(capture())
        self.assertEqual(result["status"], "documentary_consistent")
        self.assertEqual(result["document_totals"]["net"], "10.00")
        self.assertFalse(result["publication_allowed"])
        self.assertEqual(result["identity_verification"], "pending")
        self.assertEqual(result["reconciliation"], "pending")
        self.assertNotIn("DO_NOT_EXPOSE", json.dumps(result))
        self.assertNotIn("00000000000000", json.dumps(result))

    def test_restricted_program_has_no_records_or_amounts(self):
        row = json.loads(capture()["body"])["resultado"]["dados"][0]
        row["nomeComponente"] = "DEMANDAS JUDICIAIS"
        self.assertEqual(
            self.inspect(capture([row])),
            dict(status="unsupported_program", publication_allowed=False),
        )

    def test_scope_hash_and_redirect_fail_closed(self):
        for field, value in [
            ("sha256", "0" * 64),
            ("byte_size", 1),
            ("final_url", "https://example.com"),
            ("http_status", 500),
        ]:
            c = capture()
            c[field] = value
            self.assertEqual(self.inspect(c)["status"], "invalid_capture")
        for old, new in [
            ("tipoConsulta=3", "tipoConsulta=2"),
            ("municipio=290320", "municipio=1"),
            ("cpfCnpjUg=00000000000000", "cpfCnpjUg=11111111111111"),
        ]:
            c = capture()
            c["request_url"] = c["final_url"] = c["request_url"].replace(old, new)
            self.assertEqual(self.inspect(c)["status"], "invalid_capture")

    def test_duplicate_parameters_and_partial_page_fail_closed(self):
        c = capture()
        c["request_url"] += "&ano=2025"
        c["final_url"] = c["request_url"]
        self.assertEqual(self.inspect(c)["status"], "invalid_capture")
        c = capture()
        data = json.loads(c["body"])
        data["resultado"]["total"] = 26
        c["body"] = json.dumps(data).encode()
        c["byte_size"] = len(c["body"])
        c["sha256"] = hashlib.sha256(c["body"]).hexdigest()
        self.assertEqual(self.inspect(c)["status"], "invalid_capture")

    def test_repeated_rows_and_total_mismatch_require_review(self):
        row = json.loads(capture()["body"])["resultado"]["dados"][0]
        self.assertEqual(self.inspect(capture([row, row]))["status"], "review_required")
        row["valorLiquidoGeral"] = "99.00"
        self.assertEqual(self.inspect(capture([row]))["status"], "review_required")

    def test_annulment_and_rejection_require_review(self):
        for field, value in [("valorAnulacao", 1), ("motivoRejeicao", "DO_NOT_EXPOSE")]:
            row = json.loads(capture()["body"])["resultado"]["dados"][0]
            row[field] = value
            result = self.inspect(capture([row]))
            self.assertEqual(result["status"], "review_required")
            self.assertNotIn("DO_NOT_EXPOSE", json.dumps(result))
