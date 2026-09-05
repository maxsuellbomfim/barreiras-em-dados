from __future__ import annotations

import hashlib
import json
import unittest

from barreiras_collectors.connectors.fns_payment_evidence import (
    FNSPaymentEvidenceError,
    parse_fns_payment_evidence,
)


def envelope(row: dict) -> bytes:
    return json.dumps(
        {
            "resultado": {
                "dados": [row],
                "pagina": 0,
                "itensPorPagina": 25,
                "total": 1,
                "totalPaginas": 1,
            }
        },
        ensure_ascii=False,
    ).encode()


def payment() -> dict:
    # Synthetic fixture: bank sentinels must never enter normalized evidence.
    return {
        "id": {
            "ano": "2025",
            "mes": "10",
            "esferaAdministrativa": "MUNICIPAL",
            "indicadorFundoAFundo": "S",
            "programaFundo": {"id": 65061},
            "processoEntidadePrograma": {
                "projeto": {"numeroSubprojeto": "36000000000202500"}
            },
        },
        "anoPagamento": "2025",
        "mesPagamento": "10",
        "uf": "BA",
        "numeroDocumentoSiafi": "055607",
        "tipoDocumentoPagamento": "OB",
        "dataCriacaoSiafi": "24/10/2025",
        "competencia": "Única em 2025",
        "valorTotal": 5000000,
        "valorDescontoTotal": 0,
        "valorLiquido": 5000000,
        "valorAnulacao": 0,
        "motivoRejeicao": "",
        "codigoBanco": "BANK_SENTINEL",
        "codigoAgencia": "AGENCY_SENTINEL",
        "contaCorrente": "ACCOUNT_SENTINEL",
        "unknown": "PRIVATE_SENTINEL",
    }


def order() -> dict:
    return {
        "codigoIBGE": "290320",
        "municipio": "BARREIRAS",
        "uf": "BA",
        "anoExercicio": "2025",
        "mesExercicio": "10",
        "competencia": "Única em 2025",
        "valor": 5000000,
        "valorTotal": 5000000,
        "motivoRejeicao": "",
        "dsObservacao": (
            "PAGAMENTO DA PROPOSTA 36000000000202500 - UF BA - "
            "EMENDA: (50410002) COMISSÃO DA SAÚDE - "
            "SOLICITANTE: (4438) PARLAMENTAR DE EXEMPLO"
        ),
    }


def parse(p: dict | None = None, o: dict | None = None, **scope) -> dict:
    return parse_fns_payment_evidence(
        envelope(payment() if p is None else p),
        envelope(order() if o is None else o),
        action_id=scope.get("action_id", 65061),
        payment_year=scope.get("payment_year", 2025),
        order_number=scope.get("order_number", "055607"),
    )


class FNSPaymentEvidenceTests(unittest.TestCase):
    def test_payment_scope_is_explicit_and_strict(self):
        for scope in [
            {"action_id": True},
            {"action_id": 0},
            {"payment_year": True},
            {"payment_year": 2024},
            {"order_number": "257001000012025OB055607"},
        ]:
            with self.subTest(scope=scope), self.assertRaises(FNSPaymentEvidenceError):
                parse(**scope)

    def test_zero_paid_is_not_a_payment_and_input_size_is_bounded(self):
        p, o = payment(), order()
        p.update(valorTotal=0, valorLiquido=0)
        o.update(valor=0, valorTotal=0)
        with self.assertRaises(FNSPaymentEvidenceError):
            parse(p, o)
        p["unknown"] = "x" * (128 * 1024)
        with self.assertRaises(FNSPaymentEvidenceError):
            parse(p)

    def test_invalid_page_metadata_is_blocked_for_both_responses(self):
        for side in ("payment", "order"):
            for key, value in [
                ("pagina", 2),
                ("pagina", True),
                ("itensPorPagina", 0),
                ("itensPorPagina", True),
            ]:
                p, o = json.loads(envelope(payment())), json.loads(envelope(order()))
                target = p if side == "payment" else o
                target["resultado"][key] = value
                with (
                    self.subTest(side=side, key=key),
                    self.assertRaises(FNSPaymentEvidenceError),
                ):
                    parse_fns_payment_evidence(
                        json.dumps(p).encode(),
                        json.dumps(o).encode(),
                        action_id=65061,
                        payment_year=2025,
                        order_number="055607",
                    )

    def test_known_fns_ob_competence_encoding_does_not_modify_names_or_hashes(self):
        o = order()
        o["competencia"] = "Única em 2025".encode().decode("latin-1")
        result = parse(o=o)
        self.assertEqual(result["author_name"], "COMISSÃO DA SAÚDE")
        self.assertEqual(
            result["order_sha256"], hashlib.sha256(envelope(o)).hexdigest()
        )

    def test_separates_collective_author_and_requester_without_identity_inference(self):
        result = parse()
        self.assertEqual(result["author_name"], "COMISSÃO DA SAÚDE")
        self.assertEqual(result["requester_name"], "PARLAMENTAR DE EXEMPLO")
        self.assertEqual(result["requester_source_code"], "4438")
        self.assertEqual(result["amendment_number"], "50410002")
        self.assertIsNone(result["amendment_year"])
        self.assertEqual(result["paid_amount"], "5000000.00")
        self.assertEqual(result["document_date"], "2025-10-24")
        self.assertEqual(result["municipality_ibge"], "2903201")
        self.assertEqual(result["link_status"], "unlinked")

    def test_whitelist_and_hashes_do_not_expose_bank_fields_or_raw_observation(self):
        result = parse()
        self.assertEqual(
            set(result),
            {
                "schema_version",
                "action_id",
                "payment_year",
                "order_number",
                "document_date",
                "proposal_number",
                "amendment_number",
                "amendment_year",
                "author_name",
                "requester_name",
                "requester_source_code",
                "municipality_ibge",
                "paid_amount",
                "gross_amount",
                "deduction_amount",
                "payment_sha256",
                "order_sha256",
                "link_status",
            },
        )
        self.assertNotIn("SENTINEL", json.dumps(result))
        self.assertEqual(
            result["payment_sha256"], hashlib.sha256(envelope(payment())).hexdigest()
        )
        self.assertEqual(
            result["order_sha256"], hashlib.sha256(envelope(order())).hexdigest()
        )

    def test_missing_requester_is_unknown_not_the_author(self):
        o = order()
        o["dsObservacao"] = o["dsObservacao"].split(" - SOLICITANTE:")[0]
        result = parse(o=o)
        self.assertIsNone(result["requester_name"])
        self.assertIsNone(result["requester_source_code"])

    def test_decimal_deductions_reconcile_exactly(self):
        p, o = payment(), order()
        p.update(valorTotal="10.30", valorDescontoTotal="0.20", valorLiquido="10.10")
        o.update(valor="10.10", valorTotal="10.10")
        self.assertEqual(parse(p, o)["paid_amount"], "10.10")

    def test_invalid_or_unsupported_payment_is_blocked(self):
        for key, value in [
            ("uf", "SP"),
            ("anoPagamento", "2024"),
            ("mesPagamento", "11"),
            ("numeroDocumentoSiafi", "000000"),
            ("tipoDocumentoPagamento", "NE"),
            ("dataCriacaoSiafi", "31/02/2025"),
            ("dataCriacaoSiafi", "24/10/2024"),
            ("valorLiquido", "4999999.99"),
            ("valorTotal", True),
            ("valorTotal", "NaN"),
            ("valorTotal", "Infinity"),
            ("valorTotal", "5000000.001"),
            ("valorAnulacao", 1),
            ("motivoRejeicao", "SENSITIVE_ERROR"),
            ("valorDescontoTotal", -1),
        ]:
            with self.subTest(key=key, value=value):
                p = payment()
                p[key] = value
                with self.assertRaises(FNSPaymentEvidenceError):
                    parse(p=p)

    def test_invalid_order_or_territory_is_blocked(self):
        for key, value in [
            ("codigoIBGE", "292740"),
            ("municipio", "SALVADOR"),
            ("uf", "SP"),
            ("anoExercicio", "2024"),
            ("mesExercicio", "11"),
            ("competencia", "Outra"),
            ("valor", 1),
            ("valorTotal", 1),
            ("motivoRejeicao", "PRIVATE_ERROR"),
        ]:
            with self.subTest(key=key):
                o = order()
                o[key] = value
                with self.assertRaises(FNSPaymentEvidenceError):
                    parse(o=o)

    def test_nested_scope_mismatch_is_blocked(self):
        for key, value in [
            ("ano", "2024"),
            ("mes", "09"),
            ("esferaAdministrativa", "ESTADUAL"),
            ("indicadorFundoAFundo", "N"),
        ]:
            p = payment()
            p["id"][key] = value
            with self.subTest(key=key), self.assertRaises(FNSPaymentEvidenceError):
                parse(p=p)
        with self.assertRaises(FNSPaymentEvidenceError):
            parse(action_id=68909)

    def test_ambiguous_observation_is_not_partially_parsed(self):
        base = order()["dsObservacao"]
        for observation in [
            base + " - SOLICITANTE: (4125) OUTRA PESSOA",
            base + " CONTA 123456",
            base.replace("UF BA", "UF SP"),
            base.replace("36000000000202500", "36000000001202500"),
            base + "\nTEXTO",
            base.replace("COMISSÃO", "<b>COMISSÃO</b>"),
            "TEXTO SEM FORMATO CONHECIDO",
            base.replace("(4438)", "(12345678901)"),
        ]:
            o = order()
            o["dsObservacao"] = observation
            with (
                self.subTest(observation=observation),
                self.assertRaises(FNSPaymentEvidenceError),
            ):
                parse(o=o)

    def test_missing_fields_and_invalid_json_fail_without_source_text(self):
        for body in [
            b"PRIVATE_ERROR",
            b'{"resultado": null}',
            b'{"resultado": {}, "resultado": {}}',
            b'{"x": NaN}',
        ]:
            with self.assertRaises(FNSPaymentEvidenceError) as caught:
                parse_fns_payment_evidence(
                    body,
                    envelope(order()),
                    action_id=65061,
                    payment_year=2025,
                    order_number="055607",
                )
            self.assertNotIn("PRIVATE_ERROR", str(caught.exception))
        for key in payment():
            if key in {"codigoBanco", "codigoAgencia", "contaCorrente", "unknown"}:
                continue
            p = payment()
            del p[key]
            with self.subTest(key=key), self.assertRaises(FNSPaymentEvidenceError):
                parse(p=p)

    def test_empty_multiple_or_paginated_responses_are_not_accepted(self):
        valid = json.loads(envelope(payment()))
        for key, value in [
            ("total", 0),
            ("total", 2),
            ("total", True),
            ("totalPaginas", 2),
            ("dados", []),
            ("dados", [payment(), payment()]),
        ]:
            bad = json.loads(json.dumps(valid))
            bad["resultado"][key] = value
            with self.subTest(key=key), self.assertRaises(FNSPaymentEvidenceError):
                parse_fns_payment_evidence(
                    json.dumps(bad).encode(),
                    envelope(order()),
                    action_id=65061,
                    payment_year=2025,
                    order_number="055607",
                )
