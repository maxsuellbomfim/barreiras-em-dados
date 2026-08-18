from __future__ import annotations

import csv
import hashlib
import io
import unittest
import zipfile
from datetime import UTC, datetime

from barreiras_collectors.connectors.cgu_federal_amendments import (
    MAIN_COLUMNS,
    CGUFederalAmendmentArchiveError,
    fetch_cgu_federal_amendments,
    parse_cgu_federal_amendments_archive,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import RetryPolicy

CONVENIO_COLUMNS = (
    "Código da Emenda",
    "Código Função",
    "Nome Função",
    "Código Subfunção",
    "Nome Subfunção",
    "Localidade do gasto",
    "Tipo de Emenda",
    "Data Publicação Convênio",
    "Convenente",
    "Objeto Convênio",
    "Número Convênio",
    "Valor Convênio",
)
FAVORECIDO_COLUMNS = (
    "Código da Emenda",
    "Código do Autor da Emenda",
    "Nome do Autor da Emenda",
    "Número da emenda",
    "Tipo de Emenda",
    "Ano/Mês",
    "Código do Favorecido",
    "Favorecido",
    "Natureza Jurídica",
    "Tipo Favorecido",
    "UF Favorecido",
    "Município Favorecido",
    "Valor Recebido",
)


def amendment_row(**overrides: str) -> dict[str, str]:
    row = {
        "Código da Emenda": "202340720005",
        "Ano da Emenda": "2023",
        "Tipo de Emenda": "Emenda Individual - Transferências com Finalidade Definida",
        "Código do Autor da Emenda": "4072",
        "Nome do Autor da Emenda": "TITO",
        "Número da emenda": "0005",
        "Localidade de aplicação do recurso": "BARREIRAS - BA",
        "Código Município IBGE": "2903201",
        "Município": "BARREIRAS",
        "Código UF IBGE": "2900000",
        "UF": "BAHIA",
        "Região": "Nordeste",
        "Código Função": "05",
        "Nome Função": "Defesa nacional",
        "Código Subfunção": "153",
        "Nome Subfunção": "Defesa terrestre",
        "Código Programa": "6012",
        "Nome Programa": "DEFESA NACIONAL",
        "Código Ação": "20PY",
        "Nome Ação": "ADEQUACAO DE ATIVOS DE INFRAESTRUTURA",
        "Código Plano Orçamentário": "0000",
        "Nome Plano Orçamentário": "DESPESAS DIVERSAS",
        "Valor Empenhado": "199925,68",
        "Valor Liquidado": "199925,68",
        "Valor Pago": "199925,68",
        "Valor Restos A Pagar Inscritos": "0,00",
        "Valor Restos A Pagar Cancelados": "0,00",
        "Valor Restos A Pagar Pagos": "0,00",
    }
    row.update(overrides)
    return row


def _csv_bytes(columns: tuple[str, ...], rows: list[dict[str, str]]) -> bytes:
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
    return output.getvalue().encode("cp1252")


def archive_bytes(
    rows: list[dict[str, str]],
    *,
    main_columns: tuple[str, ...] = MAIN_COLUMNS,
) -> bytes:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr(
            "EmendasParlamentares.csv",
            _csv_bytes(main_columns, rows),
        )
        package.writestr(
            "EmendasParlamentares_Convenios.csv",
            _csv_bytes(CONVENIO_COLUMNS, []),
        )
        package.writestr(
            "EmendasParlamentares_PorFavorecido.csv",
            _csv_bytes(FAVORECIDO_COLUMNS, []),
        )
    return archive.getvalue()


class DownloadTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.requests: list[tuple[str, int]] = []

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds
        self.requests.append((url, max_body_bytes))
        return self.response


def download_response(body: bytes) -> HttpResponse:
    return HttpResponse(
        status=200,
        headers={
            "Content-Type": "application/x-zip-compressed",
            "Content-Length": str(len(body)),
            "ETag": '"official-etag"',
            "Last-Modified": "Wed, 05 Aug 2026 17:47:14 GMT",
            "X-Api-Key": "never-preserve",
        },
        body=body,
        final_url=(
            "https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/"
            "saida/emendas-parlamentares/EmendasParlamentares.zip"
        ),
    )


class CGUFederalAmendmentParserTests(unittest.TestCase):
    def test_filters_by_exact_ibge_and_preserves_financial_stages_as_decimals(
        self,
    ) -> None:
        selected = parse_cgu_federal_amendments_archive(
            archive_bytes(
                [
                    amendment_row(),
                    amendment_row(
                        **{
                            "Código da Emenda": "202240720005",
                            "Ano da Emenda": "2022",
                            "Valor Empenhado": "290000,00",
                            "Valor Liquidado": "0,00",
                            "Valor Pago": "0,00",
                            "Valor Restos A Pagar Inscritos": "290000,00",
                            "Valor Restos A Pagar Cancelados": "45499,65",
                            "Valor Restos A Pagar Pagos": "244500,35",
                        }
                    ),
                    amendment_row(
                        **{
                            "Código da Emenda": "202340720006",
                            "Localidade de aplicação do recurso": (
                                "LUIS EDUARDO MAGALHAES - BA"
                            ),
                            "Código Município IBGE": "2919553",
                            "Município": "LUIS EDUARDO MAGALHAES",
                        }
                    ),
                ]
            )
        )

        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]["amendment_code"], "202340720005")
        self.assertEqual(selected[0]["municipality_ibge"], "2903201")
        self.assertEqual(selected[0]["committed_amount"], "199925.68")
        self.assertEqual(selected[1]["outstanding_cancelled_amount"], "45499.65")
        self.assertEqual(selected[1]["outstanding_paid_amount"], "244500.35")
        self.assertNotIn("total_paid_amount", selected[1])

    def test_rejects_schema_drift_and_duplicate_natural_identity(self) -> None:
        with self.assertRaisesRegex(CGUFederalAmendmentArchiveError, "cabeçalho"):
            parse_cgu_federal_amendments_archive(
                archive_bytes([amendment_row()], main_columns=MAIN_COLUMNS[:-1])
            )
        with self.assertRaisesRegex(CGUFederalAmendmentArchiveError, "duplicada"):
            parse_cgu_federal_amendments_archive(
                archive_bytes([amendment_row(), amendment_row()])
            )

    def test_rows_without_official_code_in_distinct_years_are_not_duplicates(
        self,
    ) -> None:
        unavailable = {
            "Código da Emenda": "Sem informação",
            "Código do Autor da Emenda": "S/I",
            "Nome do Autor da Emenda": "Sem informação",
            "Número da emenda": "S/I",
        }
        selected = parse_cgu_federal_amendments_archive(
            archive_bytes(
                [
                    amendment_row(**unavailable, **{"Ano da Emenda": "2014"}),
                    amendment_row(**unavailable, **{"Ano da Emenda": "2015"}),
                ]
            )
        )
        self.assertEqual(
            [item["fiscal_year"] for item in selected], [2014, 2015]
        )
        self.assertEqual(selected[0]["amendment_code"], "Sem informação")


class CGUFederalAmendmentDownloadTests(unittest.TestCase):
    def test_binds_redirected_download_to_official_host_and_snapshot(self) -> None:
        body = archive_bytes([amendment_row()])
        transport = DownloadTransport(download_response(body))

        snapshot = fetch_cgu_federal_amendments(
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
            now=lambda: datetime(2026, 8, 16, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(snapshot.endpoint_code, "federal-amendments-open-data")
        self.assertEqual(snapshot.body_sha256, hashlib.sha256(body).hexdigest())
        self.assertEqual(snapshot.total_items, 1)
        self.assertEqual(snapshot.first_fiscal_year, 2023)
        self.assertEqual(snapshot.last_fiscal_year, 2023)
        self.assertNotIn("x-api-key", snapshot.response_headers)
        self.assertEqual(len(transport.requests), 1)


if __name__ == "__main__":
    unittest.main()
