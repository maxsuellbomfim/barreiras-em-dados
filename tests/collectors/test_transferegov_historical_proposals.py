from __future__ import annotations

import csv
import hashlib
import io
import unittest
import zipfile
from datetime import UTC, datetime

from barreiras_collectors.connectors.transferegov_historical_proposals import (
    HistoricalProposalArchiveError,
    fetch_historical_proposals,
    parse_historical_proposals_archive,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import RetryPolicy

CSV_COLUMNS = (
    "ID_PROPOSTA",
    "UF_PROPONENTE",
    "MUNIC_PROPONENTE",
    "COD_MUNIC_IBGE",
    "COD_ORGAO_SUP",
    "DESC_ORGAO_SUP",
    "NATUREZA_JURIDICA",
    "NR_PROPOSTA",
    "DIA_PROP",
    "MES_PROP",
    "ANO_PROP",
    "DIA_PROPOSTA",
    "COD_ORGAO",
    "DESC_ORGAO",
    "MODALIDADE",
    "IDENTIF_PROPONENTE",
    "NM_PROPONENTE",
    "CEP_PROPONENTE",
    "ENDERECO_PROPONENTE",
    "BAIRRO_PROPONENTE",
    "NM_BANCO",
    "SITUACAO_CONTA",
    "SITUACAO_PROJETO_BASICO",
    "SIT_PROPOSTA",
    "DIA_INIC_VIGENCIA_PROPOSTA",
    "DIA_FIM_VIGENCIA_PROPOSTA",
    "OBJETO_PROPOSTA",
    "ITEM_INVESTIMENTO",
    "ENVIADA_MANDATARIA",
    "NOME_SUBTIPO_PROPOSTA",
    "DESCRICAO_SUBTIPO_PROPOSTA",
    "VL_GLOBAL_PROP",
    "VL_REPASSE_PROP",
    "VL_CONTRAPARTIDA_PROP",
    "CD_AGENCIA",
    "CD_CONTA",
)


def proposal_row(**overrides: str) -> dict[str, str]:
    row = {
        "ID_PROPOSTA": "9001",
        "UF_PROPONENTE": "BA",
        "MUNIC_PROPONENTE": "BARREIRAS",
        "COD_MUNIC_IBGE": "2903201",
        "COD_ORGAO_SUP": "55000",
        "DESC_ORGAO_SUP": "MINISTERIO DO DESENVOLVIMENTO",
        "NATUREZA_JURIDICA": "ADMINISTRACAO PUBLICA MUNICIPAL",
        "NR_PROPOSTA": "000001/2021",
        "DIA_PROP": "15",
        "MES_PROP": "6",
        "ANO_PROP": "2021",
        "DIA_PROPOSTA": "15/06/2021",
        "COD_ORGAO": "55000",
        "DESC_ORGAO": "MINISTERIO DO DESENVOLVIMENTO",
        "MODALIDADE": "CONVENIO",
        "IDENTIF_PROPONENTE": "13654405000195",
        "NM_PROPONENTE": "MUNICIPIO DE BARREIRAS",
        "CEP_PROPONENTE": "47800000",
        "ENDERECO_PROPONENTE": "RUA OFICIAL",
        "BAIRRO_PROPONENTE": "CENTRO",
        "NM_BANCO": "BANCO PUBLICO",
        "SITUACAO_CONTA": "ATIVA",
        "SITUACAO_PROJETO_BASICO": "APROVADO",
        "SIT_PROPOSTA": "PROPOSTA APROVADA",
        "DIA_INIC_VIGENCIA_PROPOSTA": "01/01/2022",
        "DIA_FIM_VIGENCIA_PROPOSTA": "31/12/2023",
        "OBJETO_PROPOSTA": "CONSTRUIR EQUIPAMENTO PUBLICO",
        "ITEM_INVESTIMENTO": "INFRAESTRUTURA",
        "ENVIADA_MANDATARIA": "NAO",
        "NOME_SUBTIPO_PROPOSTA": "NAO INFORMADO",
        "DESCRICAO_SUBTIPO_PROPOSTA": "NAO INFORMADO",
        "VL_GLOBAL_PROP": "1250000.50",
        "VL_REPASSE_PROP": "1200000.50",
        "VL_CONTRAPARTIDA_PROP": "50000.00",
        "CD_AGENCIA": "1234",
        "CD_CONTA": "999999",
    }
    row.update(overrides)
    return row


def archive_bytes(
    rows: list[dict[str, str]],
    *,
    columns: tuple[str, ...] = CSV_COLUMNS,
    extra_member: bool = False,
) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=columns,
        delimiter=";",
        lineterminator="\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(rows)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("siconv_proposta.csv", output.getvalue().encode("utf-8"))
        if extra_member:
            package.writestr("nao-contratado.csv", b"coluna\nvalor\n")
    return archive.getvalue()


class DownloadTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.requests: list[tuple[str, int]] = []

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds
        self.requests.append((url, max_body_bytes))
        return self.response


def catalog_entry(body: bytes) -> dict[str, object]:
    return {
        "name": "siconv_proposta.zip",
        "url": (
            "https://trsfgovprodstrgaccpublic.blob.core.windows.net/"
            "trsfgov-prod-public-data/siconv_proposta.zip"
        ),
        "download_url": (
            "https://api-publica.transferegov.gestao.gov.br/"
            "downloads/dadosgov/siconv_proposta.zip"
        ),
        "byte_size": len(body),
        "last_modified": "Wed, 12 Aug 2026 11:18:29 GMT",
        "etag": "0x8DEF8636FB12944",
        "content_md5": None,
        "content_type": "application/octet-stream",
    }


def download_response(
    body: bytes,
    *,
    etag: str = "0x8DEF8636FB12944",
    final_url: str | None = None,
) -> HttpResponse:
    return HttpResponse(
        status=200,
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(body)),
            "ETag": etag,
            "X-Api-Key": "nao-preservar",
        },
        body=body,
        final_url=final_url
        or (
            "https://api-publica.transferegov.gestao.gov.br/"
            "downloads/dadosgov/siconv_proposta.zip"
        ),
    )


class HistoricalProposalParserTests(unittest.TestCase):
    def test_selects_exact_ibge_and_period_without_exposing_bank_fields(self) -> None:
        selected = parse_historical_proposals_archive(
            archive_bytes(
                [
                    proposal_row(),
                    proposal_row(ID_PROPOSTA="9002", ANO_PROP="2020"),
                    proposal_row(
                        ID_PROPOSTA="9003",
                        COD_MUNIC_IBGE="2927408",
                        MUNIC_PROPONENTE="SALVADOR",
                    ),
                ]
            ),
            year_from=2021,
            year_to=2026,
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["id_proposta"], "9001")
        self.assertEqual(selected[0]["cod_municipio_ibge"], "2903201")
        self.assertEqual(selected[0]["ano_proposta"], 2021)
        self.assertEqual(selected[0]["valor_global"], "1250000.50")
        self.assertEqual(selected[0]["valor_repasse"], "1200000.50")
        self.assertEqual(selected[0]["valor_contrapartida"], "50000.00")
        self.assertNotIn("CD_AGENCIA", selected[0])
        self.assertNotIn("CD_CONTA", selected[0])
        self.assertNotIn("agencia", selected[0])
        self.assertNotIn("conta", selected[0])

    def test_rejects_archive_with_unexpected_csv_contract(self) -> None:
        changed_columns = CSV_COLUMNS[:-1]

        with self.assertRaisesRegex(HistoricalProposalArchiveError, "cabeçalho"):
            parse_historical_proposals_archive(
                archive_bytes([proposal_row()], columns=changed_columns),
                year_from=2021,
                year_to=2026,
            )


class HistoricalProposalDownloadTests(unittest.TestCase):
    def test_downloads_proxy_url_and_binds_archive_to_catalog_metadata(self) -> None:
        body = archive_bytes([proposal_row()])
        transport = DownloadTransport(download_response(body))

        snapshot = fetch_historical_proposals(
            catalog_entry=catalog_entry(body),
            year_from=2021,
            year_to=2026,
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
            now=lambda: datetime(2026, 8, 12, 16, 0, tzinfo=UTC),
        )

        self.assertEqual(snapshot.source_code, "transferegov-downloads")
        self.assertEqual(snapshot.endpoint_code, "propostas-historicas")
        self.assertEqual(snapshot.artifact_kind, "archive")
        self.assertEqual(snapshot.raw_body, body)
        self.assertEqual(snapshot.body_sha256, hashlib.sha256(body).hexdigest())
        self.assertEqual(snapshot.items[0]["id_proposta"], "9001")
        self.assertEqual(
            snapshot.cursor,
            {"offset": 0, "size": 1, "year_from": 2021, "year_to": 2026},
        )
        self.assertEqual(
            snapshot.response_headers,
            {
                "content-type": "application/octet-stream",
                "content-length": str(len(body)),
                "etag": "0x8DEF8636FB12944",
            },
        )
        self.assertEqual(
            transport.requests,
            [(str(catalog_entry(body)["download_url"]), len(body))],
        )

    def test_rejects_archive_size_that_no_longer_matches_catalog(self) -> None:
        body = archive_bytes([proposal_row()])
        declared = catalog_entry(body)
        declared["byte_size"] = len(body) + 1

        with self.assertRaisesRegex(HistoricalProposalArchiveError, "tamanho"):
            fetch_historical_proposals(
                catalog_entry=declared,
                year_from=2021,
                year_to=2026,
                transport=DownloadTransport(download_response(body)),
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _seconds: None,
            )

    def test_rejects_archive_etag_that_no_longer_matches_catalog(self) -> None:
        body = archive_bytes([proposal_row()])

        with self.assertRaisesRegex(HistoricalProposalArchiveError, "ETag"):
            fetch_historical_proposals(
                catalog_entry=catalog_entry(body),
                year_from=2021,
                year_to=2026,
                transport=DownloadTransport(
                    download_response(body, etag="0xALTERADO")
                ),
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _seconds: None,
            )


class HistoricalProposalParserSafetyTests(unittest.TestCase):
    def test_rejects_archive_with_more_than_the_contracted_member(self) -> None:
        with self.assertRaisesRegex(HistoricalProposalArchiveError, "um único CSV"):
            parse_historical_proposals_archive(
                archive_bytes([proposal_row()], extra_member=True),
                year_from=2021,
                year_to=2026,
            )

    def test_rejects_truncated_zip_instead_of_returning_empty_coverage(self) -> None:
        body = archive_bytes([proposal_row()])

        with self.assertRaisesRegex(HistoricalProposalArchiveError, "ZIP"):
            parse_historical_proposals_archive(
                body[:-20],
                year_from=2021,
                year_to=2026,
            )

    def test_refuses_cpf_in_the_normalized_municipal_projection(self) -> None:
        with self.assertRaisesRegex(HistoricalProposalArchiveError, "CNPJ"):
            parse_historical_proposals_archive(
                archive_bytes(
                    [proposal_row(IDENTIF_PROPONENTE="12345678901")]
                ),
                year_from=2021,
                year_to=2026,
            )

    def test_rejects_non_decimal_financial_value(self) -> None:
        with self.assertRaisesRegex(HistoricalProposalArchiveError, "VL_GLOBAL_PROP"):
            parse_historical_proposals_archive(
                archive_bytes([proposal_row(VL_GLOBAL_PROP="1.2.3")]),
                year_from=2021,
                year_to=2026,
            )


if __name__ == "__main__":
    unittest.main()
