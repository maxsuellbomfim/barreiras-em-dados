from __future__ import annotations

import json
import unittest
from dataclasses import asdict

from barreiras_collectors.connectors.cgu_sanctions import (
    CGUSanctionError,
    fetch_cgu_supplier_sanctions,
    parse_cgu_sanctions_bundle,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import RetryPolicy

API_KEY = "chave-de-teste-nunca-preservada"
CNPJ = "44493204000187"
BASE = "https://api.portaldatransparencia.gov.br/api-de-dados"
CEIS_URL = f"{BASE}/ceis?codigoSancionado={CNPJ}&pagina=1"
CNEP_URL = f"{BASE}/cnep?codigoSancionado={CNPJ}&pagina=1"
CEPIM_URL = f"{BASE}/cepim?cnpjSancionado={CNPJ}&pagina=1"
LENIENCIA_URL = f"{BASE}/acordos-leniencia?cnpjSancionado={CNPJ}&pagina=1"


def company_sanction(sanction_id: int = 288186) -> dict:
    return {
        "id": sanction_id,
        "dataReferencia": "18/08/2026",
        "dataInicioSancao": "14/12/2022",
        "dataFimSancao": "14/12/2032",
        "dataPublicacaoSancao": "Sem informação",
        "numeroProcesso": "00005096720148171140",
        "fundamentacao": [{"codigo": "LEI 8666 - ART. 87"}],
        "tipoSancao": {
            "descricaoResumida": "Impedimento/proibição de contratar",
        },
        "orgaoSancionador": {
            "nome": "Prefeitura Municipal de Exemplo",
            "esfera": "MUNICIPAL",
            "siglaUf": "BA",
            "poder": "Executivo",
        },
        "fonteSancao": {"nomeExibicao": "CGU"},
        "pessoa": {
            "tipo": "Pessoa Jurídica",
            "cnpjFormatado": "44.493.204/0001-87",
            "razaoSocialReceita": "COMERCIAL EXEMPLO LTDA",
        },
        "sancionado": {
            "nome": "COMERCIAL EXEMPLO LTDA",
            "codigoFormatado": "44.493.204/0001-87",
        },
    }


def natural_person_sanction() -> dict:
    record = company_sanction(999001)
    record["pessoa"] = {"tipo": "Pessoa Física", "cpfFormatado": "***.157.704-**"}
    record["sancionado"] = {
        "nome": "PESSOA FISICA SANCIONADA",
        "codigoFormatado": "435.157.704-53",
    }
    return record


def cepim_record(record_id: int = 5150) -> dict:
    return {
        "id": record_id,
        "dataReferencia": "01/08/2026",
        "motivo": "IRREGULARIDADE NA PRESTAÇÃO DE CONTAS",
        "orgaoSuperior": {
            "nome": "Ministério de Exemplo",
            "sigla": "MEX",
            "descricaoPoder": "EXECUTIVO",
        },
        "pessoaJuridica": {
            "cnpjFormatado": "44.493.204/0001-87",
            "nome": "ASSOCIACAO EXEMPLO",
            "razaoSocialReceita": "ASSOCIACAO EXEMPLO DE APOIO",
            "tipo": "Pessoa Jurídica",
        },
        "convenio": {"codigo": "123", "objeto": "Apoio local", "numero": "88/2020"},
    }


def leniency_record(record_id: int = 9021, cnpj_formatado: str = "44.493.204/0001-87") -> dict:
    return {
        "id": record_id,
        "dataInicioAcordo": "10/07/2019",
        "dataFimAcordo": "10/07/2029",
        "orgaoResponsavel": "Controladoria-Geral da União",
        "situacaoAcordo": "Acordo em cumprimento",
        "quantidade": 2,
        "sancoes": [
            {
                "nomeInformadoOrgaoResponsavel": "GRUPO EXEMPLO",
                "razaoSocial": "EXEMPLO ENGENHARIA S.A.",
                "nomeFantasia": "EXEMPLO",
                "cnpj": "44493204000187",
                "cnpjFormatado": cnpj_formatado,
            },
            {
                "nomeInformadoOrgaoResponsavel": "OUTRA EMPRESA",
                "razaoSocial": "OUTRA EMPRESA LTDA",
                "nomeFantasia": "OUTRA",
                "cnpj": "00000000000191",
                "cnpjFormatado": "00.000.000/0001-91",
            },
        ],
    }


class MappedTransport:
    def __init__(self, responses: dict[str, list[dict]]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del timeout_seconds, max_body_bytes
        self.requests.append((url, dict(headers)))
        body = json.dumps(self.responses.get(url, [])).encode("utf-8")
        return HttpResponse(
            status=200,
            headers={"Content-Type": "application/json"},
            body=body,
            final_url=url,
        )


def fetch(transport: MappedTransport, cnpjs=(CNPJ,)):
    return fetch_cgu_supplier_sanctions(
        cnpjs=cnpjs,
        api_key=API_KEY,
        transport=transport,
        retry_policy=RetryPolicy(max_attempts=1),
        sleep=lambda _seconds: None,
        request_interval_seconds=0,
    )


class CGUSanctionFetchTests(unittest.TestCase):
    def test_normalizes_company_sanction_and_masks_nothing_public(self) -> None:
        transport = MappedTransport({CEIS_URL: [company_sanction()]})
        snapshot = fetch(transport)
        self.assertEqual(snapshot.total_items, 1)
        item = snapshot.items[0]
        self.assertEqual(item["registry"], "ceis")
        self.assertEqual(item["sanction_id"], "288186")
        self.assertEqual(item["supplier_cnpj"], CNPJ)
        self.assertEqual(item["sanctioned_document"], CNPJ)
        self.assertEqual(item["start_date_text"], "14/12/2022")
        self.assertEqual(item["legal_basis_codes"], ["LEI 8666 - ART. 87"])
        self.assertEqual(snapshot.sanctioned_cnpjs, 1)
        self.assertEqual(snapshot.queried_cnpjs, 1)

    def test_natural_person_rows_never_become_items(self) -> None:
        transport = MappedTransport(
            {CEIS_URL: [natural_person_sanction(), company_sanction()]}
        )
        snapshot = fetch(transport)
        self.assertEqual(snapshot.total_items, 1)
        self.assertEqual(snapshot.skipped_natural_persons, 1)
        serialized = json.dumps(
            {k: v for k, v in asdict(snapshot).items() if k != "raw_body"},
            ensure_ascii=False,
            default=str,
        )
        self.assertNotIn("435.157.704-53", serialized)
        self.assertNotIn("43515770453", serialized)

    def test_api_key_is_sent_but_never_preserved(self) -> None:
        transport = MappedTransport({})
        snapshot = fetch(transport)
        self.assertTrue(
            all(
                headers.get("chave-api-dados") == API_KEY
                for _url, headers in transport.requests
            )
        )
        serialized = json.dumps(asdict(snapshot), ensure_ascii=False, default=str)
        self.assertNotIn(API_KEY, serialized)
        self.assertNotIn(API_KEY.encode(), snapshot.raw_body)

    def test_queries_all_registries_for_each_cnpj(self) -> None:
        transport = MappedTransport({})
        snapshot = fetch(transport)
        urls = [url for url, _headers in transport.requests]
        self.assertEqual(len(urls), 4)
        self.assertIn("/ceis?codigoSancionado=", urls[0])
        self.assertIn("/cnep?codigoSancionado=", urls[1])
        self.assertIn("/cepim?cnpjSancionado=", urls[2])
        self.assertIn("/acordos-leniencia?cnpjSancionado=", urls[3])
        self.assertEqual(snapshot.collection_status, "complete")
        # O repositório de persistência exige o contrato offset/size no cursor.
        self.assertEqual(snapshot.cursor, {"offset": 0, "size": 0})

    def test_normalizes_cepim_record_with_natural_person_gate(self) -> None:
        blocked = cepim_record(5151)
        blocked["pessoaJuridica"] = {
            "cpfFormatado": "***.157.704-**",
            "nome": "PESSOA FISICA IMPEDIDA",
            "tipo": "Pessoa Física",
        }
        transport = MappedTransport({CEPIM_URL: [cepim_record(), blocked]})
        snapshot = fetch(transport)
        self.assertEqual(snapshot.total_items, 1)
        self.assertEqual(snapshot.skipped_natural_persons, 1)
        item = snapshot.items[0]
        self.assertEqual(item["registry"], "cepim")
        self.assertEqual(item["sanction_id"], "5150")
        self.assertEqual(item["sanctioned_document"], CNPJ)
        self.assertEqual(
            item["sanction_type"], "IRREGULARIDADE NA PRESTAÇÃO DE CONTAS"
        )
        self.assertEqual(item["sanctioning_body"], "Ministério de Exemplo")
        self.assertEqual(item["reference_date_text"], "01/08/2026")
        serialized = json.dumps(
            {k: v for k, v in asdict(snapshot).items() if k != "raw_body"},
            ensure_ascii=False,
            default=str,
        )
        self.assertNotIn("157.704", serialized)

    def test_normalizes_leniency_agreement_only_for_queried_cnpj(self) -> None:
        transport = MappedTransport({LENIENCIA_URL: [leniency_record()]})
        snapshot = fetch(transport)
        self.assertEqual(snapshot.total_items, 1)
        item = snapshot.items[0]
        self.assertEqual(item["registry"], "leniencia")
        self.assertEqual(item["sanction_id"], "9021")
        self.assertEqual(item["supplier_cnpj"], CNPJ)
        self.assertEqual(item["sanctioned_name"], "EXEMPLO ENGENHARIA S.A.")
        self.assertEqual(item["sanction_type"], "Acordo em cumprimento")
        self.assertEqual(item["start_date_text"], "10/07/2019")
        self.assertEqual(item["end_date_text"], "10/07/2029")
        # A outra empresa do acordo não entra pela consulta deste CNPJ.
        self.assertNotIn("OUTRA EMPRESA", json.dumps(snapshot.items))

    def test_leniency_without_matching_company_is_counted_not_silent(self) -> None:
        transport = MappedTransport(
            {LENIENCIA_URL: [leniency_record(9022, "99.999.999/0001-99")]}
        )
        transport.responses[LENIENCIA_URL][0]["sancoes"][0]["cnpj"] = "99999999000199"
        snapshot = fetch(transport)
        self.assertEqual(snapshot.total_items, 0)
        self.assertEqual(snapshot.skipped_natural_persons, 1)

    def test_rejects_non_cnpj_input_and_missing_key(self) -> None:
        with self.assertRaisesRegex(CGUSanctionError, "somente CNPJ"):
            fetch(MappedTransport({}), cnpjs=("46300000000",))
        with self.assertRaisesRegex(CGUSanctionError, "chave da API"):
            fetch_cgu_supplier_sanctions(
                cnpjs=(CNPJ,),
                api_key="  ",
                transport=MappedTransport({}),
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _s: None,
                request_interval_seconds=0,
            )

    def test_rejected_key_fails_explicitly(self) -> None:
        class Unauthorized:
            def get(self, url, *, headers, timeout_seconds, max_body_bytes):
                del headers, timeout_seconds, max_body_bytes
                return HttpResponse(
                    status=401, headers={}, body=b"{}", final_url=url
                )

        with self.assertRaisesRegex(CGUSanctionError, "recusou a chave"):
            fetch_cgu_supplier_sanctions(
                cnpjs=(CNPJ,),
                api_key=API_KEY,
                transport=Unauthorized(),
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _s: None,
                request_interval_seconds=0,
            )

    def test_bundle_round_trip_matches_items(self) -> None:
        transport = MappedTransport({CNEP_URL: [company_sanction(777)]})
        snapshot = fetch(transport)
        items, skipped = parse_cgu_sanctions_bundle(snapshot.raw_body)
        self.assertEqual(items, snapshot.items)
        self.assertEqual(skipped, 0)


if __name__ == "__main__":
    unittest.main()
