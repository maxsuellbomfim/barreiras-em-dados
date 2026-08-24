from __future__ import annotations

import hashlib
import json
import unittest
from datetime import UTC, datetime

from barreiras_collectors.connectors.siconfi import (
    SiconfiContractError,
    fetch_siconfi_dca,
    parse_siconfi_dca_page,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import RetryPolicy


def dca_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "exercicio": 2021,
        "instituicao": "Prefeitura Municipal de Barreiras - BA",
        "cod_ibge": 2903201,
        "uf": "BA",
        "anexo": "DCA-Anexo I-E",
        "rotulo": "Total Geral da Despesa por Função",
        "coluna": "Despesas Pagas",
        "cod_conta": "TotalDespesas",
        "conta": "10 - Saúde",
        "valor": 163212630.95,
        "populacao": 156975,
    }
    item.update(overrides)
    return item


def page_body(
    items: list[dict[str, object]],
    *,
    offset: int = 0,
    limit: int = 5000,
    has_more: bool = False,
) -> bytes:
    return json.dumps(
        {
            "items": items,
            "hasMore": has_more,
            "limit": limit,
            "offset": offset,
            "count": len(items),
            "links": [],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


class SequenceTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[str] = []

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.requests.append(url)
        return self.responses.pop(0)


class CountingLimiter:
    def __init__(self) -> None:
        self.calls = 0

    def acquire(self) -> None:
        self.calls += 1


def response(body: bytes, *, final_url: str) -> HttpResponse:
    return HttpResponse(
        status=200,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Content-Length": str(len(body)),
            "ETag": '"official-etag"',
            "X-Api-Key": "never-preserve",
        },
        body=body,
        final_url=final_url,
    )


class SiconfiDcaContractTests(unittest.TestCase):
    def test_preserves_source_grain_and_decimal_text_without_float_math(self) -> None:
        body = page_body(
            [
                dca_item(),
                dca_item(
                    conta="99 - Ajuste publicado pela fonte",
                    valor=-12.34,
                ),
            ]
        )

        parsed = parse_siconfi_dca_page(
            body,
            expected_year=2021,
            expected_offset=0,
            expected_limit=5000,
        )

        self.assertEqual(parsed.items[0]["valor"], "163212630.95")
        self.assertEqual(parsed.items[1]["valor"], "-12.34")
        self.assertEqual(parsed.items[0]["conta"], "10 - Saúde")
        self.assertFalse(parsed.has_more)

    def test_rejects_wrong_entity_and_incoherent_pagination(self) -> None:
        with self.assertRaisesRegex(SiconfiContractError, "IBGE"):
            parse_siconfi_dca_page(
                page_body([dca_item(cod_ibge=2919553)]),
                expected_year=2021,
                expected_offset=0,
                expected_limit=5000,
            )
        with self.assertRaisesRegex(SiconfiContractError, "paginação"):
            parse_siconfi_dca_page(
                page_body([], offset=1, has_more=True),
                expected_year=2021,
                expected_offset=0,
                expected_limit=5000,
            )

    def test_rejects_duplicate_complete_source_identity(self) -> None:
        duplicate = dca_item()
        with self.assertRaisesRegex(SiconfiContractError, "duplicada"):
            parse_siconfi_dca_page(
                page_body([duplicate, duplicate]),
                expected_year=2021,
                expected_offset=0,
                expected_limit=5000,
            )


class SiconfiDcaDownloadTests(unittest.TestCase):
    def test_fetches_all_pages_with_official_url_rate_limit_and_safe_headers(
        self,
    ) -> None:
        first = page_body([dca_item()], limit=1, has_more=True)
        second = page_body(
            [dca_item(conta="12 - Educação", valor=42)],
            offset=1,
            limit=1,
        )
        transport = SequenceTransport(
            [
                response(
                    first,
                    final_url=(
                        "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca"
                        "?an_exercicio=2021&id_ente=2903201&limit=1&offset=0"
                    ),
                ),
                response(
                    second,
                    final_url=(
                        "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca"
                        "?an_exercicio=2021&id_ente=2903201&limit=1&offset=1"
                    ),
                ),
            ]
        )
        limiter = CountingLimiter()

        pages = fetch_siconfi_dca(
            year=2021,
            page_size=1,
            transport=transport,
            rate_limiter=limiter,
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
            now=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(len(pages), 2)
        self.assertEqual([page.offset for page in pages], [0, 1])
        self.assertEqual(limiter.calls, 2)
        self.assertIn("an_exercicio=2021", transport.requests[0])
        self.assertIn("id_ente=2903201", transport.requests[0])
        self.assertEqual(pages[0].body_sha256, hashlib.sha256(first).hexdigest())
        self.assertNotIn("x-api-key", pages[0].response_headers)


if __name__ == "__main__":
    unittest.main()
