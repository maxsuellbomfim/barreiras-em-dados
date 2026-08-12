from __future__ import annotations

import hashlib
import json
import unittest
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

from barreiras_collectors.connectors.transferegov import (
    BARREIRAS_IBGE_CODE,
    TransferegovError,
    fetch_partnerships_page,
    fetch_proposals_page,
    fetch_resource_distributions_page,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    RetryPolicy,
)


class ScriptedTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[str] = []

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.requests.append(url)
        return self.responses.pop(0)


def response(
    status: int,
    payload: object,
    *,
    headers: dict[str, str] | None = None,
) -> HttpResponse:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return HttpResponse(
        status=status,
        headers=headers or {"Content-Type": "application/json"},
        body=body,
        final_url="https://api-publica.transferegov.gestao.gov.br/parcerias/proposta",
    )


def envelope(data: list[dict], *, pages: int = 1, page: int = 1) -> dict:
    return {
        "data": data,
        "total_pages": pages,
        "total_items": len(data),
        "page_number": page,
        "page_size": len(data),
    }


class TransferegovParceriasTests(unittest.TestCase):
    def test_child_resources_require_a_proposal_validated_for_barreiras(self) -> None:
        with self.assertRaisesRegex(ValueError, "validada para Barreiras"):
            fetch_resource_distributions_page(
                proposal_id=30854,
                validated_proposal_ids=frozenset({9274}),
                page=1,
                transport=ScriptedTransport([]),
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _seconds: None,
            )

    def test_malformed_success_response_counts_as_source_failure(self) -> None:
        breaker = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout_seconds=60,
            monotonic=lambda: 10.0,
        )

        with self.assertRaisesRegex(TransferegovError, "envelope"):
            fetch_proposals_page(
                page=1,
                transport=ScriptedTransport([response(200, {"data": {}})]),
                retry_policy=RetryPolicy(max_attempts=1),
                circuit_breaker=breaker,
                sleep=lambda _seconds: None,
            )

        self.assertEqual(breaker.state, CircuitState.OPEN)

    def test_persistent_source_failures_open_the_shared_circuit(self) -> None:
        breaker = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout_seconds=60,
            monotonic=lambda: 10.0,
        )
        transport = ScriptedTransport([response(503, {"detail": "temporario"})])

        with self.assertRaises(CircuitOpenError):
            fetch_proposals_page(
                page=1,
                transport=transport,
                retry_policy=RetryPolicy(max_attempts=3),
                circuit_breaker=breaker,
                sleep=lambda _seconds: None,
            )

        self.assertEqual(len(transport.requests), 1)

    def test_permanent_client_error_does_not_open_availability_circuit(self) -> None:
        breaker = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout_seconds=60,
            monotonic=lambda: 10.0,
        )

        with self.assertRaisesRegex(TransferegovError, "HTTP 404"):
            fetch_proposals_page(
                page=1,
                transport=ScriptedTransport([response(404, {"detail": "ausente"})]),
                retry_policy=RetryPolicy(max_attempts=1),
                circuit_breaker=breaker,
                sleep=lambda _seconds: None,
            )

        self.assertEqual(breaker.state, CircuitState.CLOSED)

    def test_retry_after_seconds_is_respected_for_rate_limit(self) -> None:
        sleeps: list[float] = []
        transport = ScriptedTransport(
            [
                response(429, {"detail": "limite"}, headers={"Retry-After": "9"}),
                response(200, envelope([])),
            ]
        )

        fetch_proposals_page(
            page=1,
            transport=transport,
            retry_policy=RetryPolicy(
                max_attempts=2,
                base_delay_seconds=1,
                max_delay_seconds=4,
            ),
            random_value=lambda: 0.0,
            sleep=sleeps.append,
        )

        self.assertEqual(sleeps, [9.0])

    def test_retry_after_http_date_is_respected_for_rate_limit(self) -> None:
        now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
        retry_at = format_datetime(now + timedelta(seconds=11), usegmt=True)
        sleeps: list[float] = []
        transport = ScriptedTransport(
            [
                response(429, {"detail": "limite"}, headers={"Retry-After": retry_at}),
                response(200, envelope([])),
            ]
        )

        fetch_proposals_page(
            page=1,
            transport=transport,
            retry_policy=RetryPolicy(
                max_attempts=2,
                base_delay_seconds=1,
                max_delay_seconds=4,
            ),
            random_value=lambda: 0.0,
            now=lambda: now,
            sleep=sleeps.append,
        )

        self.assertEqual(sleeps, [11.0])

    def test_proposals_are_scoped_to_barreiras_and_preserve_source_bytes(self) -> None:
        payload = envelope(
            [
                {
                    "id_proposta": 9274,
                    "id_programa": 15,
                    "cnpj_ente_recebedor": "08595187000125",
                    "nm_ente_recebedor": "FUNDO MUNICIPAL DE SAUDE DE BARREIRAS",
                    "cd_ibge_recebedor": 2903201,
                    "nm_municipio_recebedor": "BARREIRAS",
                    "sg_uf_recebedor": "BA",
                    "ds_objeto": "INCREMENTO DA MEDIA E ALTA COMPLEXIDADE (MAC)",
                    "situacao_proposta": "Aprovada",
                    "vl_total_planejamento_gastos": 250000.0,
                    "ano_proposta": 2025,
                    "dt_proposta": "2025-07-21",
                }
            ]
        )
        scripted = response(200, payload)
        transport = ScriptedTransport([scripted])

        page = fetch_proposals_page(
            page=1,
            page_size=50,
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=lambda _seconds: None,
        )

        self.assertEqual(
            transport.requests,
            [
                "https://api-publica.transferegov.gestao.gov.br/parcerias/"
                "proposta?cd_ibge_recebedor=2903201&pagina=1&tamanho_da_pagina=50"
            ],
        )
        self.assertEqual(page.source_code, "transferegov-parcerias")
        self.assertEqual(page.endpoint_code, "propostas-barreiras")
        self.assertEqual(page.items[0]["id_proposta"], 9274)
        self.assertEqual(page.collection_status, "success")
        self.assertEqual(
            page.cursor,
            {"page": 1, "size": 50, "response_size": 1, "offset": 0},
        )
        self.assertEqual(page.window_start, page.requested_at)
        self.assertEqual(page.window_end, page.received_at)
        self.assertEqual(page.raw_body, scripted.body)
        self.assertEqual(page.body_sha256, hashlib.sha256(scripted.body).hexdigest())

    def test_empty_official_page_is_preserved_as_explicit_empty_coverage(self) -> None:
        scripted = response(200, envelope([]))

        page = fetch_proposals_page(
            page=1,
            transport=ScriptedTransport([scripted]),
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
        )

        self.assertEqual(page.items, ())
        self.assertEqual(page.collection_status, "empty")
        self.assertEqual(page.total_items, 0)
        self.assertEqual(page.raw_body, scripted.body)

    def test_incoherent_pagination_cannot_be_published_as_empty_coverage(self) -> None:
        inconsistent = envelope([], pages=1, page=1)
        inconsistent["total_items"] = 3

        with self.assertRaisesRegex(TransferegovError, "paginação"):
            fetch_proposals_page(
                page=2,
                transport=ScriptedTransport([response(200, inconsistent)]),
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _seconds: None,
            )

    def test_only_documented_safe_response_headers_are_preserved(self) -> None:
        scripted = response(
            200,
            envelope([]),
            headers={
                "Content-Type": "application/json",
                "ETag": '"fonte-1"',
                "X-Api-Key": "segredo-nao-deve-ser-preservado",
            },
        )

        page = fetch_proposals_page(
            page=1,
            transport=ScriptedTransport([scripted]),
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
        )

        self.assertEqual(
            page.response_headers,
            {"content-type": "application/json", "etag": '"fonte-1"'},
        )

    def test_api_result_outside_barreiras_is_rejected_even_with_official_filter(
        self,
    ) -> None:
        payload = envelope(
            [
                {
                    "id_proposta": 9999,
                    "cd_ibge_recebedor": 2927408,
                    "nm_municipio_recebedor": "SALVADOR",
                }
            ]
        )

        with self.assertRaisesRegex(TransferegovError, "fora de Barreiras"):
            fetch_proposals_page(
                page=1,
                transport=ScriptedTransport([response(200, payload)]),
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _seconds: None,
            )

    def test_related_resources_must_reference_the_requested_parent(self) -> None:
        wrong_distribution = envelope(
            [
                {
                    "id_distribuicao_recurso_proposta": 14886,
                    "id_proposta": 30854,
                    "in_tipo_distribuicao": "Emenda",
                    "valor_emenda": 250000.0,
                }
            ]
        )

        with self.assertRaisesRegex(TransferegovError, "proposta 9274"):
            fetch_resource_distributions_page(
                proposal_id=9274,
                validated_proposal_ids=frozenset({9274}),
                page=1,
                transport=ScriptedTransport([response(200, wrong_distribution)]),
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _seconds: None,
            )

    def test_related_endpoints_use_integer_identifiers_and_keep_stages_separate(
        self,
    ) -> None:
        distributions = envelope(
            [
                {
                    "id_distribuicao_recurso_proposta": 43389,
                    "id_proposta": 30854,
                    "in_tipo_distribuicao": "Emenda",
                    "nm_parlamentar_proposta": "COMISSAO DA SAUDE",
                    "valor_emenda": 5000000.0,
                }
            ]
        )
        partnerships = envelope(
            [
                {
                    "id_parceria": 30785,
                    "id_proposta": 30854,
                    "cd_parceria": 202500030009,
                    "in_situacao_parceria": "Aprovada",
                }
            ]
        )
        transport = ScriptedTransport(
            [response(200, distributions), response(200, partnerships)]
        )

        distribution_page = fetch_resource_distributions_page(
            proposal_id=30854,
            validated_proposal_ids=frozenset({30854}),
            page=1,
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
        )
        partnership_page = fetch_partnerships_page(
            proposal_id=30854,
            validated_proposal_ids=frozenset({30854}),
            page=1,
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
        )

        self.assertEqual(BARREIRAS_IBGE_CODE, 2903201)
        self.assertEqual(distribution_page.items[0]["valor_emenda"], 5000000.0)
        self.assertEqual(partnership_page.items[0]["id_parceria"], 30785)
        self.assertIn("id_proposta=30854", transport.requests[0])
        self.assertIn("id_proposta=30854", transport.requests[1])
        self.assertNotEqual(
            distribution_page.endpoint_code,
            partnership_page.endpoint_code,
        )

    def test_retries_transient_http_status_and_rejects_malformed_envelope(self) -> None:
        transport = ScriptedTransport(
            [response(503, {"detail": "temporario"}), response(200, envelope([]))]
        )

        page = fetch_proposals_page(
            page=1,
            transport=transport,
            retry_policy=RetryPolicy(max_attempts=2),
            sleep=lambda _seconds: None,
        )

        self.assertEqual(page.collection_status, "empty")
        self.assertEqual(len(transport.requests), 2)

        with self.assertRaisesRegex(TransferegovError, "envelope"):
            fetch_proposals_page(
                page=1,
                transport=ScriptedTransport([response(200, {"data": {}})]),
                retry_policy=RetryPolicy(max_attempts=1),
                sleep=lambda _seconds: None,
            )


if __name__ == "__main__":
    unittest.main()
