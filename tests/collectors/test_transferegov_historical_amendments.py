from __future__ import annotations

import csv
import hashlib
import io
import unittest
import zipfile
from datetime import UTC, datetime

from barreiras_collectors.connectors.transferegov_historical_amendments import (
    CSV_COLUMNS,
    HistoricalAmendmentArchiveError,
    fetch_historical_amendments,
    parse_historical_amendments_archive,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import RetryPolicy


def amendment_row(**overrides: str) -> dict[str, str]:
    row = {
        "ID_PROPOSTA": "9001",
        "QUALIF_PROPONENTE": "Proposta de Município",
        "COD_PROGRAMA_EMENDA": "5500020210001",
        "NR_EMENDA": "20210001",
        "NOME_PARLAMENTAR": "PARLAMENTAR TESTE",
        "BENEFICIARIO_EMENDA": "13654405000195",
        "IND_IMPOSITIVO": "SIM",
        "TIPO_PARLAMENTAR": "INDIVIDUAL",
        "VALOR_REPASSE_PROPOSTA_EMENDA": "1910443,64",
        "VALOR_REPASSE_EMENDA": "2000000",
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
        package.writestr("siconv_emenda.csv", output.getvalue().encode("utf-8"))
        if extra_member:
            package.writestr("unexpected.csv", b"field\nvalue\n")
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
        "name": "siconv_emenda.zip",
        "url": (
            "https://trsfgovprodstrgaccpublic.blob.core.windows.net/"
            "trsfgov-prod-public-data/siconv_emenda.zip"
        ),
        "download_url": (
            "https://api-publica.transferegov.gestao.gov.br/"
            "downloads/dadosgov/siconv_emenda.zip"
        ),
        "byte_size": len(body),
        "last_modified": "Wed, 12 Aug 2026 11:18:29 GMT",
        "etag": "0xEMENDA",
        "content_md5": None,
        "content_type": "application/octet-stream",
    }


def download_response(body: bytes, *, etag: str = "0xEMENDA") -> HttpResponse:
    return HttpResponse(
        status=200,
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(body)),
            "ETag": etag,
            "X-Api-Key": "never-preserve",
        },
        body=body,
        final_url=(
            "https://api-publica.transferegov.gestao.gov.br/"
            "downloads/dadosgov/siconv_emenda.zip"
        ),
    )


class HistoricalAmendmentParserTests(unittest.TestCase):
    def test_selects_only_known_proposals_and_minimizes_beneficiary_identifier(
        self,
    ) -> None:
        selected = parse_historical_amendments_archive(
            archive_bytes(
                [
                    amendment_row(),
                    amendment_row(ID_PROPOSTA="9999", NR_EMENDA="20210002"),
                    amendment_row(
                        ID_PROPOSTA="9001",
                        NR_EMENDA="20210003",
                        NOME_PARLAMENTAR="COMISSAO TESTE",
                        TIPO_PARLAMENTAR="COMISSAO",
                        IND_IMPOSITIVO="NAO",
                    ),
                ]
            ),
            proposal_ids=frozenset({"9001"}),
        )

        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]["id_proposta"], "9001")
        self.assertEqual(selected[0]["autor_nome"], "PARLAMENTAR TESTE")
        self.assertEqual(selected[0]["valor_repasse_proposta_emenda"], "1910443.64")
        self.assertEqual(selected[0]["valor_repasse_emenda"], "2000000")
        self.assertEqual(selected[0]["beneficiario_tipo"], "cnpj")
        self.assertEqual(selected[0]["beneficiario_ultimos_4"], "0195")
        self.assertNotIn("BENEFICIARIO_EMENDA", selected[0])
        self.assertNotIn("beneficiario_identificador", selected[0])

    def test_rejects_cpf_beneficiary_in_normalized_projection(self) -> None:
        with self.assertRaisesRegex(HistoricalAmendmentArchiveError, "CPF"):
            parse_historical_amendments_archive(
                archive_bytes([amendment_row(BENEFICIARIO_EMENDA="12345678901")]),
                proposal_ids=frozenset({"9001"}),
            )

    def test_rejects_duplicate_natural_identity(self) -> None:
        with self.assertRaisesRegex(HistoricalAmendmentArchiveError, "duplicada"):
            parse_historical_amendments_archive(
                archive_bytes([amendment_row(), amendment_row()]),
                proposal_ids=frozenset({"9001"}),
            )

    def test_rejects_unexpected_header_or_extra_member(self) -> None:
        with self.assertRaisesRegex(HistoricalAmendmentArchiveError, "cabeçalho"):
            parse_historical_amendments_archive(
                archive_bytes([amendment_row()], columns=CSV_COLUMNS[:-1]),
                proposal_ids=frozenset({"9001"}),
            )
        with self.assertRaisesRegex(HistoricalAmendmentArchiveError, "único CSV"):
            parse_historical_amendments_archive(
                archive_bytes([amendment_row()], extra_member=True),
                proposal_ids=frozenset({"9001"}),
            )


class HistoricalAmendmentDownloadTests(unittest.TestCase):
    def test_binds_download_to_catalog_and_proposal_scope(self) -> None:
        body = archive_bytes([amendment_row()])
        transport = DownloadTransport(download_response(body))

        snapshot = fetch_historical_amendments(
            catalog_entry=catalog_entry(body),
            proposal_ids=frozenset({"9001"}),
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
            now=lambda: datetime(2026, 8, 13, 16, 0, tzinfo=UTC),
        )

        self.assertEqual(snapshot.endpoint_code, "emendas-historicas")
        self.assertEqual(snapshot.body_sha256, hashlib.sha256(body).hexdigest())
        self.assertEqual(snapshot.proposal_ids, ("9001",))
        self.assertEqual(snapshot.total_items, 1)
        self.assertNotIn("x-api-key", snapshot.response_headers)
        self.assertEqual(transport.requests, [(snapshot.request_url, len(body))])

    def test_refuses_empty_or_invalid_proposal_scope(self) -> None:
        body = archive_bytes([amendment_row()])
        for proposal_ids in (frozenset(), frozenset({"not-numeric"})):
            with self.subTest(proposal_ids=proposal_ids):
                with self.assertRaises(ValueError):
                    fetch_historical_amendments(
                        catalog_entry=catalog_entry(body),
                        proposal_ids=proposal_ids,
                        transport=DownloadTransport(download_response(body)),
                        retry_policy=RetryPolicy(max_attempts=1),
                        sleep=lambda _seconds: None,
                    )

    def test_rejects_catalog_etag_drift(self) -> None:
        body = archive_bytes([amendment_row()])
        with self.assertRaisesRegex(HistoricalAmendmentArchiveError, "ETag"):
            fetch_historical_amendments(
                catalog_entry=catalog_entry(body),
                proposal_ids=frozenset({"9001"}),
                transport=DownloadTransport(download_response(body, etag="changed")),
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _seconds: None,
            )

    def test_rejects_catalog_entry_with_unofficial_blob(self) -> None:
        body = archive_bytes([amendment_row()])
        entry = catalog_entry(body)
        entry["url"] = "https://example.org/siconv_emenda.zip"
        with self.assertRaisesRegex(HistoricalAmendmentArchiveError, "blob"):
            fetch_historical_amendments(
                catalog_entry=entry,
                proposal_ids=frozenset({"9001"}),
                transport=DownloadTransport(download_response(body)),
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _seconds: None,
            )


if __name__ == "__main__":
    unittest.main()
