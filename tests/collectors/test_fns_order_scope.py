import hashlib
import unittest
from urllib.parse import urlencode

from barreiras_collectors.connectors.fns_order_pages import inspect_order_captures
from test_fns_order_pages import body, row


class OrderScopeTests(unittest.TestCase):
    def test_verified_capture_does_not_bypass_cancellation(self):
        raw = body(0, [row(reason="PRIVATE CANCELAMENTO"), row("1", "OUTRO")])
        self.captures[0].update(body=raw, sha256=hashlib.sha256(raw).hexdigest())
        result = inspect_order_captures(self.captures, self.scope)
        self.assertEqual(result["status"], "review_required")
        self.assertFalse(result["publication_allowed"])
        self.assertNotIn("amount", result)
        self.assertNotIn("PRIVATE", str(result))

    def setUp(self):
        self.scope = dict(
            anoPagamento="2025",
            mes="04",
            ano="2025",
            competencia="Única em 2025",
            uf="BA",
            numeroDocumentoSiafi="016551",
            tipoDocumentoPagamento="OB",
        )
        self.captures = []
        for index, rows in enumerate(([row(), row("1", "OUTRO")], [row("2", "OUTRO")])):
            raw = body(index, rows)
            self.captures.append(
                dict(
                    url="https://consultafns.saude.gov.br/recursos/consulta-detalhada/detalhe-ordem-bancaria?"
                    + urlencode(dict(self.scope, page=str(index + 1), count="2")),
                    body=raw,
                    sha256=hashlib.sha256(raw).hexdigest(),
                    http_status=200,
                )
            )

    def test_bound_pages_keep_diagnostic_not_publication(self):
        result = inspect_order_captures(self.captures, self.scope)
        self.assertEqual(result["status"], "unique_territorial_row")
        self.assertFalse(result["publication_allowed"])

    def test_mixed_order_competence_or_page_blocks(self):
        for old, new in [
            ("016551", "018794"),
            ("mes=04", "mes=06"),
            ("page=2", "page=1"),
        ]:
            with self.subTest(new=new):
                captures = [dict(c) for c in self.captures]
                captures[1]["url"] = captures[1]["url"].replace(old, new)
                self.assertEqual(
                    inspect_order_captures(captures, self.scope)["status"],
                    "invalid_capture",
                )

    def test_untrusted_host_duplicate_parameter_and_extra_query_block(self):
        for url in [
            self.captures[0]["url"].replace("consultafns.saude.gov.br", "example.com"),
            self.captures[0]["url"] + "&page=1",
            self.captures[0]["url"] + "&token=PRIVATE",
        ]:
            captures = [dict(c) for c in self.captures]
            captures[0]["url"] = url
            result = inspect_order_captures(captures, self.scope)
            self.assertEqual(
                result, dict(status="invalid_capture", publication_allowed=False)
            )

    def test_wrong_hash_http_or_count_blocks(self):
        for key, value in [
            ("sha256", "0" * 64),
            ("http_status", 500),
            ("url", self.captures[0]["url"].replace("count=2", "count=3")),
        ]:
            captures = [dict(c) for c in self.captures]
            captures[0][key] = value
            self.assertEqual(
                inspect_order_captures(captures, self.scope)["status"],
                "invalid_capture",
            )
