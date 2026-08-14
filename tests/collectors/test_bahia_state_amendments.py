from __future__ import annotations

import csv
import hashlib
import io
import json
import ssl
import unittest
import zipfile
from base64 import b64decode
from datetime import UTC, datetime
from pathlib import Path

from barreiras_collectors.connectors.bahia_state_amendments import (
    EXPECTED_MEMBER_COLUMNS,
    BahiaStateAmendmentArchiveError,
    fetch_state_amendment_archive,
    fetch_state_amendment_catalog,
    parse_state_amendment_archive,
)
from barreiras_collectors.http import HttpResponse, UrllibTransport
from barreiras_collectors.resilience import RetryPolicy

RELATIONSHIP_DIAGRAM_URL = (
    "https://dados.ba.gov.br/dataset/"
    "1436b3e7-6594-4683-bfa5-b2e3a6c69e07/resource/"
    "f463ff7d-569c-4b48-b1d3-c80f017779df/download/"
    "emendas-parlamentares-relacionamento_views.png"
)
RELATIONSHIP_DIAGRAM_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "/x8AAusB9Wl2n6sAAAAASUVORK5CYII="
)


def _csv_bytes(columns: tuple[str, ...], rows: list[tuple[str, ...]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def _quoted_header(columns: tuple[str, ...]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(
        output,
        delimiter=";",
        lineterminator="\r\n",
        quoting=csv.QUOTE_ALL,
    )
    writer.writerow(columns)
    return output.getvalue().encode("utf-8")


def archive_bytes(
    *,
    missing_member: str | None = None,
    extra_member: bool = False,
    columns_override: dict[str, tuple[str, ...]] | None = None,
    body_override: dict[str, bytes] | None = None,
) -> bytes:
    archive = io.BytesIO()
    overrides = columns_override or {}
    body_overrides = body_override or {}
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name, columns in EXPECTED_MEMBER_COLUMNS.items():
            if name == missing_member:
                continue
            active_columns = overrides.get(name, columns)
            row = tuple("1" for _ in active_columns)
            package.writestr(
                name,
                body_overrides.get(name, _csv_bytes(active_columns, [row])),
            )
        if extra_member:
            package.writestr("unexpected.csv", b"field\nvalue\n")
    return archive.getvalue()


def catalog_body(*, size: int, resource_url: str | None = None) -> bytes:
    return json.dumps(
        {
            "success": True,
            "result": {
                "id": "1436b3e7-6594-4683-bfa5-b2e3a6c69e07",
                "name": "emendas-parlamentares",
                "title": "Emendas Parlamentares Estaduais",
                "metadata_modified": "2026-08-12T09:34:57.991157",
                "resources": [
                    {
                        "id": "2d284f2e-79cc-4e3c-a45b-6fc903a6e2d0",
                        "name": "EmendasParlamentares.zip",
                        "format": "ZIP",
                        "url": resource_url
                        or (
                            "https://dados.ba.gov.br/dataset/"
                            "1436b3e7-6594-4683-bfa5-b2e3a6c69e07/resource/"
                            "2d284f2e-79cc-4e3c-a45b-6fc903a6e2d0/download/"
                            "emendasparlamentares.zip"
                        ),
                        "last_modified": "2026-08-12T09:34:57",
                        "size": size,
                    }
                ],
            },
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode()


def catalog_body_with_relationship(*, archive_size: int) -> bytes:
    payload = json.loads(catalog_body(size=archive_size))
    payload["result"]["resources"].append(
        {
            "id": "f463ff7d-569c-4b48-b1d3-c80f017779df",
            "name": "Emendas Parlamentares - Relacionamento_Views.png",
            "format": "PNG",
            "url": RELATIONSHIP_DIAGRAM_URL,
            "last_modified": "2025-02-13T11:06:47.506964",
            "size": len(RELATIONSHIP_DIAGRAM_PNG),
        }
    )
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()


class SequenceTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, int]] = []

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds
        self.requests.append((url, max_body_bytes))
        return self.responses.pop(0)


def response(body: bytes, *, final_url: str, content_type: str) -> HttpResponse:
    return HttpResponse(
        status=200,
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            "ETag": '"official-version"',
            "X-Api-Key": "never-preserve",
        },
        body=body,
        final_url=final_url,
    )


class BahiaStateAmendmentArchiveTests(unittest.TestCase):
    def test_preserves_official_relationship_diagram_without_inventing_territory(
        self,
    ) -> None:
        from barreiras_collectors.connectors import bahia_state_amendments

        self.assertTrue(
            hasattr(
                bahia_state_amendments,
                "fetch_state_amendment_relationship_diagram",
            ),
            "o conector ainda não preserva o diagrama oficial",
        )
        archive = archive_bytes()
        transport = SequenceTransport(
            [
                response(
                    catalog_body_with_relationship(archive_size=len(archive)),
                    final_url=(
                        "https://dados.ba.gov.br/api/3/action/"
                        "package_show?id=emendas-parlamentares"
                    ),
                    content_type="application/json",
                ),
                response(
                    RELATIONSHIP_DIAGRAM_PNG,
                    final_url=RELATIONSHIP_DIAGRAM_URL,
                    content_type="image/png",
                ),
            ]
        )
        catalog = fetch_state_amendment_catalog(
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
        )

        snapshot = (
            bahia_state_amendments.fetch_state_amendment_relationship_diagram(
                catalog=catalog,
                transport=transport,
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _seconds: None,
            )
        )

        self.assertEqual(snapshot.artifact_kind, "document")
        self.assertEqual(snapshot.media_type, "image/png")
        self.assertEqual(snapshot.body_size_bytes, len(RELATIONSHIP_DIAGRAM_PNG))
        self.assertEqual(
            snapshot.body_sha256,
            hashlib.sha256(RELATIONSHIP_DIAGRAM_PNG).hexdigest(),
        )
        self.assertEqual(snapshot.items[0]["territorial_key"], "not_available")
        self.assertEqual(
            snapshot.items[0]["relationship_scope"],
            "execution_internal_codes_only",
        )

    def test_source_specific_ca_bundle_is_loaded_without_replacing_default_trust(
        self,
    ) -> None:
        bundle = Path(
            "config/certificates/sectigo-public-server-authentication-ov-r36-chain.pem"
        )
        self.assertTrue(bundle.is_file(), "o bundle TLS oficial da fonte deve existir")

        baseline = ssl.create_default_context()
        try:
            transport = UrllibTransport(
                frozenset({"dados.ba.gov.br"}),
                additional_ca_bundle=bundle,
            )
        except TypeError as error:
            self.fail(f"o transporte deve aceitar uma cadeia adicional: {error}")

        trusted_common_names = {
            value
            for certificate in transport._ssl_context.get_ca_certs()
            for relative_distinguished_name in certificate.get("subject", ())
            for key, value in relative_distinguished_name
            if key == "commonName"
        }
        self.assertIn(
            "Sectigo Public Server Authentication CA OV R36",
            trusted_common_names,
        )
        self.assertGreaterEqual(
            len(transport._ssl_context.get_ca_certs()),
            len(baseline.get_ca_certs()),
        )

    def test_validates_all_five_csv_contracts_without_normalizing_money(self) -> None:
        body = archive_bytes()

        members = parse_state_amendment_archive(body)

        self.assertEqual(len(members), 5)
        self.assertEqual(
            {member["member_name"] for member in members},
            set(EXPECTED_MEMBER_COLUMNS),
        )
        self.assertTrue(all(member["row_count"] == 1 for member in members))
        self.assertTrue(
            all(member["row_count_status"] == "validated" for member in members)
        )
        self.assertTrue(all(len(member["content_sha256"]) == 64 for member in members))
        self.assertTrue(all("rows" not in member for member in members))

    def test_rejects_missing_extra_or_drifted_members(self) -> None:
        first_member = next(iter(EXPECTED_MEMBER_COLUMNS))
        cases = (
            archive_bytes(missing_member=first_member),
            archive_bytes(extra_member=True),
            archive_bytes(columns_override={first_member: ("changed",)}),
        )
        for body in cases:
            with self.subTest(size=len(body)):
                with self.assertRaises(BahiaStateAmendmentArchiveError):
                    parse_state_amendment_archive(body)

    def test_preserves_source_csv_when_its_rows_cannot_be_counted_safely(self) -> None:
        member = "VW_PAINEL_EMENDAS_PARLAMENTARES_PAGAMENTOS.csv"
        columns = EXPECTED_MEMBER_COLUMNS[member]
        header = _csv_bytes(columns, []).decode("utf-8-sig")
        malformed_quote = ("1;\"foo\"bar\";" + ";".join("1" for _ in range(8))).encode(
            "utf-8"
        )
        body = archive_bytes(
            body_override={
                member: (
                    b"\xef\xbb\xbf"
                    + header.encode("utf-8")
                    + malformed_quote
                    + b"\n"
                )
            }
        )

        manifests = parse_state_amendment_archive(body)

        payment = next(item for item in manifests if item["member_name"] == member)
        self.assertIsNone(payment["row_count"])
        self.assertEqual(payment["row_count_status"], "source_csv_malformed")
        self.assertEqual(payment["physical_line_count"], 1)

        wrong_width = archive_bytes(
            body_override={
                member: b"\xef\xbb\xbf"
                + header.encode("utf-8")
                + malformed_quote
                + b";unexpected\n"
            }
        )
        wrong_width_manifest = parse_state_amendment_archive(wrong_width)
        payment = next(
            item for item in wrong_width_manifest if item["member_name"] == member
        )
        self.assertIsNone(payment["row_count"])
        self.assertEqual(payment["row_count_status"], "source_csv_malformed")

    def test_counts_payment_rows_by_official_identifiers_despite_broken_quotes(
        self,
    ) -> None:
        member = "VW_PAINEL_EMENDAS_PARLAMENTARES_PAGAMENTOS.csv"
        header = _quoted_header(EXPECTED_MEMBER_COLUMNS[member])
        rows = (
            b'"1960100032200018568";"19601.0003.22.0001856-8";'
            b'"CREDOR UM";"11/03/2022 00:00:00";"175000,00";"Sim";'
            b'"";"Veiculo conforme NF"s 1906; processo oficial";'
            b'"1960100032100112450";"2021.3.19.19601.313.1099.500091.5"\r\n'
            b'"2080100722500002523";"20801.0072.25.0000252-3";'
            b'"CREDOR DOIS";"27/02/2025 00:00:00";"5970,00";"Nao";'
            b'"";"Primeira linha\r\nSegunda linha; com detalhe";'
            b'"2080100722400006131";"2024.3.20.20801.437.7873.500128.5"\r\n'
            b'"850100022400018653";"85010.0022.40.0018653-";'
            b'"MUNICIPIO TESTE";"11/12/2024 00:00:00";"1131,54";"Sim";'
            b'"";"Identificador sem digito publicado pela fonte";'
            b'"850100022400008621";"2024.3.8.8501.434.7894.500072.5"\r\n'
        )
        body = archive_bytes(
            body_override={member: b"\xef\xbb\xbf" + header + rows}
        )

        manifests = parse_state_amendment_archive(body)

        payment = next(item for item in manifests if item["member_name"] == member)
        self.assertEqual(payment["row_count"], 3)
        self.assertEqual(
            payment["row_count_status"],
            "validated_with_source_warnings",
        )
        self.assertEqual(
            payment["validation_warnings"],
            {
                "record_boundary_recovery_used": True,
                "missing_check_digit_rows": 1,
            },
        )

    def test_binds_archive_to_ckan_resource_and_preserves_safe_headers(self) -> None:
        archive = archive_bytes()
        catalog_url = (
            "https://dados.ba.gov.br/api/3/action/"
            "package_show?id=emendas-parlamentares"
        )
        download_url = (
            "https://dados.ba.gov.br/dataset/"
            "1436b3e7-6594-4683-bfa5-b2e3a6c69e07/resource/"
            "2d284f2e-79cc-4e3c-a45b-6fc903a6e2d0/download/"
            "emendasparlamentares.zip"
        )
        transport = SequenceTransport(
            [
                response(
                    catalog_body(size=len(archive)),
                    final_url=catalog_url,
                    content_type="application/json",
                ),
                response(
                    archive,
                    final_url=download_url,
                    content_type="application/zip",
                ),
            ]
        )

        catalog = fetch_state_amendment_catalog(
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
            now=lambda: datetime(2026, 8, 13, 16, 0, tzinfo=UTC),
        )
        snapshot = fetch_state_amendment_archive(
            catalog=catalog,
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
            now=lambda: datetime(2026, 8, 13, 16, 1, tzinfo=UTC),
        )

        self.assertEqual(catalog.total_items, 1)
        self.assertEqual(snapshot.total_items, 5)
        self.assertEqual(snapshot.body_sha256, hashlib.sha256(archive).hexdigest())
        self.assertEqual(snapshot.catalog_sha256, catalog.body_sha256)
        self.assertNotIn("x-api-key", snapshot.response_headers)
        self.assertEqual(transport.requests[1], (download_url, len(archive)))

    def test_rejects_unofficial_download_url(self) -> None:
        archive = archive_bytes()
        body = catalog_body(size=len(archive), resource_url="https://example.org/file.zip")
        transport = SequenceTransport(
            [
                response(
                    body,
                    final_url=(
                        "https://dados.ba.gov.br/api/3/action/"
                        "package_show?id=emendas-parlamentares"
                    ),
                    content_type="application/json",
                )
            ]
        )

        with self.assertRaisesRegex(BahiaStateAmendmentArchiveError, "oficial"):
            fetch_state_amendment_catalog(
                transport=transport,
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _seconds: None,
            )


if __name__ == "__main__":
    unittest.main()
