from __future__ import annotations

import csv
import io
import unittest
import zipfile
from datetime import UTC, datetime

from barreiras_collectors.connectors.cgu_federal_amendment_documents import (
    DOCUMENT_COLUMNS,
    CGUFederalAmendmentDocumentArchiveError,
    fetch_cgu_federal_amendment_documents,
    parse_cgu_federal_amendment_documents_archive,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import RetryPolicy


def document_row(**overrides: str) -> dict[str, str]:
    row = {
        "Código da Emenda": "202544600002",
        "Ano da Emenda": "2025",
        "Código do Autor da Emenda": "4460",
        "Nome do Autor da Emenda": "RICARDO MAIA",
        "Número da emenda": "0002",
        "Valor Empenhado": "250000,00",
        "Valor Pago": "0,00",
        "Tipo de Emenda": "Emenda Individual",
        "Data Documento": "04/07/2025",
        "Código Documento": "257001000012025NE463689",
        "Localidade de aplicação do recurso": "BARREIRAS - BA",
        "UF de aplicação do recurso": "BA",
        "Município de aplicação do recurso": "BARREIRAS",
        "Código IBGE do município de aplicação do recurso": "2903201",
        "Fase da despesa": "Empenho",
        "Código favorecido": "13654574000107",
        "Favorecido": "FUNDO MUNICIPAL DE SAUDE DE BARREIRAS",
        "Tipo Favorecido": "FUNDO PÚBLICO",
        "UF Favorecido": "BA",
        "Município Favorecido": "BARREIRAS",
        "Código UG": "257001",
        "UG": "FUNDO NACIONAL DE SAUDE",
        "Código Unidade Orçamentária": "36901",
        "Unidade Orçamentária": "FUNDO NACIONAL DE SAUDE",
        "Código Órgão SIAFI": "36000",
        "Órgão": "MINISTERIO DA SAUDE",
        "Código Órgão Superior SIAFI": "36000",
        "Órgão Superior": "MINISTERIO DA SAUDE",
        "Código Grupo Despesa": "4",
        "Grupo Despesa": "INVESTIMENTOS",
        "Código Elemento Despesa": "41",
        "Elemento Despesa": "CONTRIBUICOES",
        "Código Modalidade Aplicação Despesa": "40",
        "Modalidade Aplicação Despesa": "TRANSFERENCIAS A MUNICIPIOS",
        "Código Plano Orçamentário": "0000",
        "Plano Orçamentário": "DESPESAS DIVERSAS",
        "Código Função": "10",
        "Função": "SAUDE",
        "Código SubFunção": "302",
        "SubFunção": "ASSISTENCIA HOSPITALAR E AMBULATORIAL",
        "Código Programa": "5118",
        "Programa": "ATENCAO ESPECIALIZADA A SAUDE",
        "Código Ação": "2E90",
        "Ação": "INCREMENTO TEMPORARIO AO CUSTEIO",
        "Linguagem Cidadã": "Apoio ao custeio da saúde",
        "Código Subtítulo (Localizador)": "0029",
        "Subtítulo (Localizador)": "NO ESTADO DA BAHIA",
        "Possui convênio?": "NÃO",
    }
    row.update(overrides)
    return row


def archive_bytes(year: int, rows: list[dict[str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=DOCUMENT_COLUMNS,
        delimiter=";",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr(
            f"{year}_EmendasParlamentares_PorDocumento.csv",
            output.getvalue().encode("cp1252"),
        )
    return archive.getvalue()


class DownloadTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del url, headers, timeout_seconds, max_body_bytes
        return self.response


class CGUFederalAmendmentDocumentTests(unittest.TestCase):
    def test_filters_exact_ibge_and_preserves_document_stage(self) -> None:
        selected = parse_cgu_federal_amendment_documents_archive(
            archive_bytes(
                2025,
                [
                    document_row(),
                    document_row(
                        **{
                            "Código Documento": "257001000012025OB055607",
                            "Data Documento": "24/10/2025",
                            "Fase da despesa": "Pagamento",
                            "Valor Empenhado": "0,00",
                            "Valor Pago": "-1250,75",
                        }
                    ),
                    document_row(
                        **{
                            "Código Documento": "other-city",
                            (
                                "Código IBGE do município de aplicação "
                                "do recurso"
                            ): "2927408",
                            "Município de aplicação do recurso": "SALVADOR",
                        }
                    ),
                ],
            ),
            archive_year=2025,
        )

        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]["document_date"], "2025-07-04")
        self.assertEqual(selected[0]["expense_stage"], "commitment")
        self.assertEqual(selected[0]["committed_amount"], "250000.00")
        self.assertEqual(selected[1]["expense_stage"], "payment")
        self.assertEqual(selected[1]["paid_amount"], "-1250.75")
        self.assertEqual(selected[1]["municipality_ibge"], "2903201")

    def test_rejects_wrong_member_year_and_unknown_stage(self) -> None:
        with self.assertRaisesRegex(
            CGUFederalAmendmentDocumentArchiveError, "ano solicitado"
        ):
            parse_cgu_federal_amendment_documents_archive(
                archive_bytes(2024, [document_row()]),
                archive_year=2025,
            )
        with self.assertRaisesRegex(
            CGUFederalAmendmentDocumentArchiveError, "fase"
        ):
            parse_cgu_federal_amendment_documents_archive(
                archive_bytes(
                    2025,
                    [document_row(**{"Fase da despesa": "Reservado"})],
                ),
                archive_year=2025,
            )

    def test_keeps_distinct_installments_and_drops_only_exact_duplicate(self) -> None:
        repeated = document_row(
            **{
                "Código da Emenda": "202450410002",
                "Ano da Emenda": "2024",
                "Código Documento": "257001000012024OB018682",
                "Data Documento": "24/06/2024",
                "Fase da despesa": "Pagamento",
                "Valor Empenhado": "0,00",
                "Valor Pago": "7500000,00",
            }
        )
        second_installment = {
            **repeated,
            "Valor Pago": "2500000,00",
        }
        selected = parse_cgu_federal_amendment_documents_archive(
            archive_bytes(2024, [repeated, repeated, second_installment]),
            archive_year=2024,
        )

        self.assertEqual(len(selected), 2)
        self.assertEqual(
            {item["paid_amount"] for item in selected},
            {"7500000.00", "2500000.00"},
        )
        self.assertEqual(
            len({item["document_line_fingerprint"] for item in selected}),
            2,
        )

    def test_fetch_binds_year_to_official_redirect(self) -> None:
        body = archive_bytes(2025, [document_row()])
        response = HttpResponse(
            status=200,
            headers={
                "Content-Type": "application/x-zip-compressed",
                "Content-Length": str(len(body)),
                "ETag": '"official-etag"',
                "Last-Modified": "Wed, 05 Aug 2026 17:47:20 GMT",
                "Authorization": "never-preserve",
            },
            body=body,
            final_url=(
                "https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/"
                "saida/emendas-parlamentares-documentos/"
                "2025_EmendasParlamentaresPorDocumento.zip"
            ),
        )
        snapshot = fetch_cgu_federal_amendment_documents(
            2025,
            transport=DownloadTransport(response),
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
            now=lambda: datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(snapshot.archive_year, 2025)
        self.assertEqual(snapshot.total_items, 1)
        self.assertEqual(snapshot.window_start, "2025-01-01")
        self.assertEqual(snapshot.window_end, "2025-12-31")
        self.assertNotIn("authorization", snapshot.response_headers)


if __name__ == "__main__":
    unittest.main()
