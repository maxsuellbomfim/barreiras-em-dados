import hashlib
import json
import unittest
from urllib.parse import urlencode

from barreiras_collectors.connectors.fns_document_link import inspect_document_link

from tests.collectors.test_fns_payment_pages import page, payment


class DocumentLinkTests(unittest.TestCase):
    def setUp(self):
        self.payments = [page(0, payment()), page(1, payment("000002"))]
        self.scope = dict(
            anoPagamento="2025",
            ano="2024",
            mes="11",
            competencia="NOV de 2024",
            uf="BA",
            numeroDocumentoSiafi="000001",
            tipoDocumentoPagamento="OB",
        )
        self.row = dict(
            codigoIBGE="290320",
            municipio="BARREIRAS",
            uf="BA",
            valor=95,
            motivoRejeicao="",
            anoExercicio="2024",
            mesExercicio="11",
            competencia="NOV de 2024",
        )

    def link(self):
        raw = json.dumps(
            dict(
                resultado=dict(
                    pagina=0,
                    total=1,
                    totalPaginas=1,
                    itensPorPagina=10,
                    dados=[self.row],
                )
            )
        ).encode()
        capture = dict(
            body=raw,
            sha256=hashlib.sha256(raw).hexdigest(),
            http_status=200,
            url="https://consultafns.saude.gov.br/recursos/consulta-detalhada/detalhe-ordem-bancaria?"
            + urlencode(dict(self.scope, page=1, count=10)),
        )
        return inspect_document_link(
            self.payments,
            [capture],
            action_id=66458,
            payment_year=2025,
            order_number="000001",
        )

    def test_consistent_pair_is_not_publication(self):
        result = self.link()
        self.assertEqual(result["status"], "consistent_documentary_pair")
        self.assertFalse(result["publication_allowed"])
        self.assertNotIn("PRIVATE", str(result))

    def test_different_amount_or_echo_blocks(self):
        self.row["valor"] = 96
        self.assertEqual(self.link()["status"], "document_conflict")
        self.row["valor"] = 95
        self.row["mesExercicio"] = "02"
        self.assertEqual(self.link()["status"], "document_conflict")

    def test_different_request_scope_blocks(self):
        self.scope["numeroDocumentoSiafi"] = "000002"
        self.assertEqual(self.link()["status"], "invalid_order_capture")

    def test_rejection_on_either_side_requires_review(self):
        self.row["motivoRejeicao"] = "PRIVATE"
        self.assertEqual(self.link()["status"], "review_required")
        self.row["motivoRejeicao"] = ""
        self.payments[0] = page(0, payment(reason="PRIVATE"))
        self.assertEqual(self.link()["status"], "review_required")

    def test_duplicate_payment_is_not_selected_arbitrarily(self):
        self.payments[1] = page(1, payment())
        self.assertEqual(self.link()["status"], "ambiguous_payment")
