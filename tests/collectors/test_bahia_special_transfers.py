from __future__ import annotations

import hashlib
import io
import json
import logging
import ssl
import unittest
import zipfile
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.error import URLError

from barreiras_collectors.connectors.bahia_special_transfers import (
    ARCHIVE_NAME,
    CATALOG_URL,
    DOWNLOAD_URL,
    EXPECTED_MEMBER_COLUMNS,
    PAYMENT_MEMBER_NAME,
    TIMEOUT_SECONDS,
    BahiaSpecialTransferArchiveError,
    fetch_special_transfer_archive,
    fetch_special_transfer_catalog,
    parse_special_transfer_archive,
)
from barreiras_collectors.resilience import CircuitBreaker, CircuitState, RetryPolicy


def _csv_bytes(columns: tuple[str, ...], values: tuple[str, ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = __import__("csv").writer(stream, delimiter=";", lineterminator="\n")
    writer.writerow(columns)
    if values:
        writer.writerow(values)
    return stream.getvalue().encode("utf-8-sig")


def archive_bytes(
    *,
    missing_member: str | None = None,
    extra_member: bool = False,
    columns_override: dict[str, tuple[str, ...]] | None = None,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member, columns in EXPECTED_MEMBER_COLUMNS.items():
            if member == missing_member:
                continue
            active_columns = (columns_override or {}).get(member, columns)
            values = tuple(
                "restricted-test-value"
                if column == "CNPJ_CPF_CREDOR_PAGAMENTO"
                else "1"
                for column in active_columns
            )
            archive.writestr(member, _csv_bytes(active_columns, values))
        if extra_member:
            archive.writestr("unexpected.csv", b"a;b\n1;2\n")
    return output.getvalue()


def catalog_body(*, size: int, resource_url: str = DOWNLOAD_URL) -> bytes:
    return json.dumps(
        {
            "success": True,
            "result": {
                "id": "f2ecd7fa-24ce-4be2-80d5-08e2c11e3e1c",
                "name": "transferencias-especiais",
                "metadata_modified": "2026-08-20T11:14:09.000000",
                "resources": [
                    {
                        "id": "809f9b7d-c252-482d-9c92-f2169d48c29c",
                        "name": "TransferenciasEspeciais.zip",
                        "format": "ZIP",
                        "size": size,
                        "last_modified": "2026-08-20T11:14:09.000000",
                        "url": resource_url,
                    }
                ],
            },
        }
    ).encode()


class SequenceTransport:
    def __init__(self, responses: list[SimpleNamespace | Exception]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, int]] = []

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds
        self.requests.append((url, max_body_bytes))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def response(body: bytes, *, final_url: str, content_type: str) -> SimpleNamespace:
    return SimpleNamespace(
        status=200,
        body=body,
        final_url=final_url,
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            "ETag": '"official"',
            "X-Api-Key": "must-not-be-preserved",
        },
    )


class BahiaSpecialTransferConnectorTests(unittest.TestCase):
    def test_transport_exhaustion_logs_each_attempt_without_sensitive_reason(self):
        marker = "private-body-token-must-not-appear"
        transport = SequenceTransport(
            [URLError(TimeoutError(marker)) for _ in range(4)]
        )
        delays = []
        breaker = CircuitBreaker(failure_threshold=4)
        logger = logging.getLogger("bahia-special-timeout-test")
        with self.assertLogs(logger, level="WARNING") as captured:
            with self.assertRaisesRegex(BahiaSpecialTransferArchiveError, "catálogo"):
                fetch_special_transfer_catalog(
                    transport=transport,
                    circuit_breaker=breaker,
                    random_value=lambda: 1,
                    sleep=delays.append,
                    logger=logger,
                )
        events = [json.loads(record.getMessage()) for record in captured.records]
        self.assertEqual(len(transport.requests), 4)
        self.assertEqual(delays, [0.5, 1.0, 2.0])
        self.assertEqual(breaker.state, CircuitState.OPEN)
        self.assertEqual([event["attempt"] for event in events], [1, 2, 3, 4])
        self.assertEqual(
            [event["will_retry"] for event in events], [True, True, True, False]
        )
        for event in events:
            self.assertEqual(
                event,
                {
                    "event": "collector_http_transport_error",
                    "source": "bahia-open-data",
                    "endpoint": "state-special-transfers",
                    "resource": "catalog",
                    "attempt": event["attempt"],
                    "max_attempts": 4,
                    "timeout_seconds": TIMEOUT_SECONDS,
                    "error_kind": "timeout",
                    "will_retry": event["will_retry"],
                },
            )
        self.assertNotIn(marker, " ".join(captured.output))

    def test_archive_transport_diagnostic_distinguishes_tls_without_changing_retries(
        self,
    ):
        body = archive_bytes()
        catalog = fetch_special_transfer_catalog(
            transport=SequenceTransport(
                [
                    response(
                        catalog_body(size=len(body)),
                        final_url=CATALOG_URL,
                        content_type="application/json",
                    ),
                ]
            )
        )
        marker = "certificate-detail-must-not-appear"
        transport = SequenceTransport(
            [
                URLError(ssl.SSLError(marker)),
                response(body, final_url=DOWNLOAD_URL, content_type="application/zip"),
            ]
        )
        logger = logging.getLogger("bahia-special-tls-test")
        with self.assertLogs(logger, level="WARNING") as captured:
            archive = fetch_special_transfer_archive(
                catalog=catalog,
                transport=transport,
                logger=logger,
                sleep=lambda _: None,
            )
        event = json.loads(captured.records[0].getMessage())
        self.assertEqual(event["resource"], "archive")
        self.assertEqual(event["error_kind"], "tls")
        self.assertEqual(event["will_retry"], True)
        self.assertEqual(archive.attempts, 2)
        self.assertNotIn(marker, " ".join(captured.output))

    def test_http_exhaustion_remains_a_failure_and_identifies_catalog(self):
        responses = [
            SimpleNamespace(status=503, body=b"private-body") for _ in range(4)
        ]
        transport = SequenceTransport(responses)
        logger = logging.getLogger("bahia-special-http-test")
        with self.assertLogs(logger, level="INFO") as captured:
            with self.assertRaisesRegex(
                BahiaSpecialTransferArchiveError, "indisponível"
            ):
                fetch_special_transfer_catalog(
                    transport=transport, logger=logger, sleep=lambda _: None
                )
        events = [json.loads(record.getMessage()) for record in captured.records]
        self.assertEqual(len(events), 4)
        self.assertTrue(all(event["resource"] == "catalog" for event in events))
        self.assertEqual([event["status"] for event in events], [503] * 4)
        self.assertNotIn("private-body", " ".join(captured.output))

    def test_validates_five_views_without_exposing_rows_or_identifiers(self) -> None:
        manifests = parse_special_transfer_archive(archive_bytes())

        self.assertEqual(len(manifests), 5)
        self.assertEqual(
            {manifest["member_name"] for manifest in manifests},
            set(EXPECTED_MEMBER_COLUMNS),
        )
        self.assertTrue(all(manifest["row_count"] == 1 for manifest in manifests))
        self.assertTrue(all("rows" not in manifest for manifest in manifests))
        serialized = json.dumps(manifests, ensure_ascii=False)
        self.assertNotIn("restricted-test-value", serialized)

        payment = next(
            item for item in manifests if item["member_name"] == PAYMENT_MEMBER_NAME
        )
        self.assertEqual(
            payment["restricted_columns"],
            ["CNPJ_CPF_CREDOR_PAGAMENTO"],
        )
        self.assertEqual(payment["territorial_scope"], "object_text_only")

    def test_rejects_missing_extra_or_drifted_views(self) -> None:
        first_member = next(iter(EXPECTED_MEMBER_COLUMNS))
        cases = (
            archive_bytes(missing_member=first_member),
            archive_bytes(extra_member=True),
            archive_bytes(columns_override={first_member: ("changed",)}),
        )
        for body in cases:
            with self.subTest(size=len(body)):
                with self.assertRaises(BahiaSpecialTransferArchiveError):
                    parse_special_transfer_archive(body)

    def test_counts_malformed_payment_rows_only_by_structured_boundaries(self) -> None:
        member = PAYMENT_MEMBER_NAME
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, columns in EXPECTED_MEMBER_COLUMNS.items():
                if name != member:
                    archive.writestr(
                        name,
                        _csv_bytes(columns, tuple("1" for _ in columns)),
                    )
                    continue
                header = _csv_bytes(columns, ()).decode("utf-8-sig")
                rows = (
                    '"1234567890123456789";"001";"masked";"Credor";'
                    '"01/01/2022";"10,00";"";"Objeto com "aspas"; e linha\n'
                    'seguinte";"1";"2022";"2022.3.18.18401.312.5040.600013.6";'
                    '"Sim";"https://www.transparencia.ba.gov.br/Pagamento/DetalharPagamento?id=1"\n'
                    '"123456789012345678";"002";"masked";"Credor";'
                    '"02/01/2022";"20,00";"";"Outro";"2";"2022";'
                    '"2022.3.18.18401.304.1399.600022.6";"Em Processamento";'
                    '"https://www.transparencia.ba.gov.br/Pagamento/DetalharPagamento?id=2"\n'
                )
                archive.writestr(member, ("\ufeff" + header + rows).encode("utf-8"))

        manifests = parse_special_transfer_archive(output.getvalue())

        payment = next(item for item in manifests if item["member_name"] == member)
        self.assertEqual(payment["row_count"], 2)
        self.assertEqual(
            payment["row_count_status"],
            "validated_with_source_warnings",
        )
        self.assertEqual(payment["validation_warnings"]["missing_check_digit_rows"], 1)

    def test_binds_archive_to_exact_ckan_resource_and_safe_headers(self) -> None:
        archive = archive_bytes()
        transport = SequenceTransport(
            [
                response(
                    catalog_body(size=len(archive)),
                    final_url=CATALOG_URL,
                    content_type="application/json",
                ),
                response(
                    archive,
                    final_url=DOWNLOAD_URL,
                    content_type="application/zip",
                ),
            ]
        )

        def now():
            return datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

        catalog = fetch_special_transfer_catalog(
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
            now=now,
        )
        snapshot = fetch_special_transfer_archive(
            catalog=catalog,
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
            now=now,
        )

        self.assertEqual(snapshot.total_items, 5)
        self.assertEqual(snapshot.body_sha256, hashlib.sha256(archive).hexdigest())
        self.assertEqual(snapshot.catalog_sha256, catalog.body_sha256)
        self.assertNotIn("x-api-key", snapshot.response_headers)
        self.assertEqual(transport.requests[1], (DOWNLOAD_URL, len(archive)))
        self.assertEqual(snapshot.resource_name, ARCHIVE_NAME)

    def test_rejects_catalog_pointing_outside_official_resource(self) -> None:
        body = catalog_body(size=100, resource_url="https://example.org/file.zip")
        transport = SequenceTransport(
            [response(body, final_url=CATALOG_URL, content_type="application/json")]
        )

        with self.assertRaisesRegex(BahiaSpecialTransferArchiveError, "oficial"):
            fetch_special_transfer_catalog(
                transport=transport,
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _seconds: None,
            )


if __name__ == "__main__":
    unittest.main()
