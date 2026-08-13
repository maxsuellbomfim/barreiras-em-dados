from __future__ import annotations

import hashlib
import unittest
from datetime import UTC, datetime

from barreiras_collectors.connectors.transferegov_download_catalog import (
    REQUIRED_HISTORICAL_FILES,
    TransferegovDownloadCatalogError,
    fetch_download_catalog,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import RetryPolicy

OFFICIAL_BLOB_HOST = (
    "trsfgovprodstrgaccpublic.blob.core.windows.net"
)
OFFICIAL_CONTAINER = "trsfgov-prod-public-data"


class OneShotTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.requests: list[str] = []

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.requests.append(url)
        return self.response


def catalog_xml(
    *,
    names: tuple[str, ...] = (),
    next_marker: str = "",
    url_override: dict[str, str] | None = None,
    container_url: str | None = None,
) -> bytes:
    selected = names or tuple(sorted(REQUIRED_HISTORICAL_FILES))
    overrides = url_override or {}
    blobs = []
    for index, name in enumerate(selected, start=1):
        url = overrides.get(
            name,
            f"https://{OFFICIAL_BLOB_HOST}/{OFFICIAL_CONTAINER}/{name}",
        )
        blobs.append(
            f"""
            <Blob>
              <Name>{name}</Name>
              <Url>{url}</Url>
              <Properties>
                <Last-Modified>Wed, 12 Aug 2026 11:18:4{index % 10} GMT</Last-Modified>
                <Etag>0x8DEF8637{index:07X}</Etag>
                <Content-Length>{index * 1024}</Content-Length>
                <Content-Type>application/octet-stream</Content-Type>
                <Content-MD5>YWJjZA==</Content-MD5>
                <BlobType>BlockBlob</BlobType>
              </Properties>
            </Blob>
            """
        )
    return (
        "\ufeff<?xml version=\"1.0\" encoding=\"utf-8\"?>"
        "<EnumerationResults "
        f'ContainerName="{container_url or f"https://{OFFICIAL_BLOB_HOST}/{OFFICIAL_CONTAINER}/"}">'
        f"<Blobs>{''.join(blobs)}</Blobs>"
        f"<NextMarker>{next_marker}</NextMarker>"
        "</EnumerationResults>"
    ).encode()


def response(body: bytes, *, headers: dict[str, str] | None = None) -> HttpResponse:
    return HttpResponse(
        status=200,
        headers=headers or {"Content-Type": "application/xml", "ETag": '"catalog"'},
        body=body,
        final_url=(
            "https://api-publica.transferegov.gestao.gov.br/"
            "downloads/dadosgov/?restype=container&comp=list"
        ),
    )


class TransferegovDownloadCatalogTests(unittest.TestCase):
    def test_preserves_complete_catalog_and_selects_required_files(self) -> None:
        body = catalog_xml()
        transport = OneShotTransport(response(body))

        snapshot = fetch_download_catalog(
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
            now=lambda: datetime(2026, 8, 12, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(snapshot.source_code, "transferegov-downloads")
        self.assertEqual(snapshot.endpoint_code, "dados-abertos-catalogo")
        self.assertEqual(
            {entry["name"] for entry in snapshot.items},
            REQUIRED_HISTORICAL_FILES,
        )
        self.assertEqual(snapshot.collection_status, "success")
        self.assertEqual(snapshot.raw_body, body)
        self.assertEqual(snapshot.body_sha256, hashlib.sha256(body).hexdigest())
        self.assertEqual(snapshot.total_items, len(REQUIRED_HISTORICAL_FILES))
        self.assertEqual(
            snapshot.response_headers,
            {"content-type": "application/xml", "etag": '"catalog"'},
        )
        self.assertEqual(len(transport.requests), 1)

    def test_missing_required_file_cannot_close_catalog_coverage(self) -> None:
        names = tuple(sorted(REQUIRED_HISTORICAL_FILES - {"siconv_emenda.zip"}))

        with self.assertRaisesRegex(
            TransferegovDownloadCatalogError,
            "siconv_emenda.zip",
        ):
            fetch_download_catalog(
                transport=OneShotTransport(response(catalog_xml(names=names))),
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _seconds: None,
            )

    def test_untrusted_blob_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            TransferegovDownloadCatalogError,
            "URL oficial",
        ):
            fetch_download_catalog(
                transport=OneShotTransport(
                    response(
                        catalog_xml(
                            url_override={
                                "siconv_emenda.zip": (
                                    "https://example.invalid/siconv_emenda.zip"
                                )
                            }
                        )
                    )
                ),
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _seconds: None,
            )

    def test_container_url_with_query_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            TransferegovDownloadCatalogError,
            "contêiner fora da URL oficial",
        ):
            fetch_download_catalog(
                transport=OneShotTransport(
                    response(
                        catalog_xml(
                            container_url=(
                                f"https://{OFFICIAL_BLOB_HOST}/"
                                f"{OFFICIAL_CONTAINER}/?sig=nao-preservar"
                            )
                        )
                    )
                ),
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _seconds: None,
            )

    def test_non_empty_next_marker_is_partial_not_complete(self) -> None:
        with self.assertRaisesRegex(
            TransferegovDownloadCatalogError,
            "pagina\u00e7\u00e3o",
        ):
            fetch_download_catalog(
                transport=OneShotTransport(
                    response(catalog_xml(next_marker="continuacao"))
                ),
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _seconds: None,
            )

    def test_sensitive_response_headers_are_not_preserved(self) -> None:
        snapshot = fetch_download_catalog(
            transport=OneShotTransport(
                response(
                    catalog_xml(),
                    headers={
                        "Content-Type": "application/xml",
                        "ETag": '"catalog"',
                        "X-Api-Key": "segredo",
                    },
                )
            ),
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
        )

        self.assertNotIn("x-api-key", snapshot.response_headers)


if __name__ == "__main__":
    unittest.main()
