"""Resumable private acquisition, not payment validation or publication.

The store must durably encrypt originals and serialize access for one run.
A directory is one acquisition snapshot: use a new directory to refresh it.
Multi-page detail bytes remain private pending documentary reconciliation.
"""

import hashlib
import json
import time
from datetime import UTC, datetime
from urllib.parse import urlencode

from .fns_entity_catalog import inspect_entity_catalog
from .fns_payment_evidence import (
    MAX_RESPONSE_BYTES,
    _reject_constant,
    _require,
    _unique_object,
)


class _Pause(Exception):
    pass


def collect_year(year, store, transport, *, max_requests=20, sleep=time.sleep):
    """Bounded 6 rpm acquisition; replay validates every preserved page again."""
    state = dict(
        year=year,
        status="running",
        pages_preserved=0,
        publication_allowed=False,
        requests=0,
    )
    try:
        _require(type(year) is int and 2021 <= year <= 2100)
        _require(type(max_requests) is int and 1 <= max_requests <= 100)
        prior = store.load("run")
        if prior is not None and prior["year"] != year:
            return dict(status="failed", publication_allowed=False)
        store.save("run", state)  # Before first network request, even early failures.

        def page_capture(resource, page, count, beneficiary=None):
            query = dict(
                ano=str(year),
                tipoConsulta="3",
                estado="BA",
                municipio="290320",
                page=str(page),
                count=str(count),
            )
            if beneficiary is not None:
                query["cpfCnpjUg"] = beneficiary
            url = (
                "https://consultafns.saude.gov.br/recursos/consulta-detalhada/"
                + resource
                + "?"
                + urlencode(query)
            )
            key = hashlib.sha256(url.encode()).hexdigest()
            capture = store.load(key)
            if capture is None:
                for attempt in range(3):
                    if state["requests"] >= max_requests:
                        raise _Pause()
                    state["requests"] += 1
                    store.save("run", state)
                    sleep(10 * (2**attempt))
                    try:
                        response = transport.get(
                            url,
                            headers={"Accept": "application/json"},
                            timeout_seconds=45,
                            max_body_bytes=MAX_RESPONSE_BYTES,
                        )
                        if response.status in (408, 429, 500, 502, 503, 504):
                            raise OSError("Retryable source response")
                        _require(response.status == 200 and response.final_url == url)
                        media = {k.lower(): v for k, v in response.headers.items()}.get(
                            "content-type", ""
                        )
                        _require(
                            media.split(";")[0].strip().lower() == "application/json"
                        )
                        capture = dict(
                            body=response.body,
                            request_url=url,
                            final_url=response.final_url,
                            http_status=response.status,
                            byte_size=len(response.body),
                            sha256=hashlib.sha256(response.body).hexdigest(),
                            received_at=datetime.now(UTC).isoformat(),
                        )
                        store.save(key, capture)
                        _require(store.load(key) == capture)
                        break
                    except (OSError, TimeoutError):
                        if attempt == 2:
                            raise
            _require(capture["request_url"] == url == capture["final_url"])
            _require(
                type(capture["http_status"]) is int and capture["http_status"] == 200
            )
            raw = capture["body"]
            _require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_RESPONSE_BYTES)
            _require(
                capture["sha256"] == hashlib.sha256(raw).hexdigest()
                and capture["byte_size"] == len(raw)
            )
            data = json.loads(
                raw, parse_constant=_reject_constant, object_pairs_hook=_unique_object
            )["resultado"]
            _require(
                all(
                    type(data[k]) is int
                    for k in ("pagina", "total", "totalPaginas", "itensPorPagina")
                )
            )
            total = data["total"]
            _require(0 <= total <= count * 100 and data["pagina"] == page - 1)
            _require(
                data["totalPaginas"] == (total + count - 1) // count
                and data["itensPorPagina"] == count
            )
            _require(page <= max(1, data["totalPaginas"]))
            rows = data["dados"]
            _require(
                isinstance(rows, list)
                and len(rows) == min(count, max(0, total - (page - 1) * count))
            )
            state["pages_preserved"] += 1
            return capture, data

        catalogs, entities = [], []
        first, data = page_capture("entidades", 1, 10)
        catalogs.append(first)
        entities.extend(data["dados"])
        for page in range(2, data["totalPaginas"] + 1):
            captured, next_data = page_capture("entidades", page, 10)
            catalogs.append(captured)
            entities.extend(next_data["dados"])
        result = inspect_entity_catalog(catalogs, payment_year=year)
        _require(result["status"] in ("complete", "empty"))
        for entity in entities:
            _, details = page_capture("detalhe-pagamento", 1, 25, entity["cpfCnpj"])
            expected = details["total"]
            for page in range(1, max(1, details["totalPaginas"]) + 1):
                if page > 1:
                    _, details = page_capture(
                        "detalhe-pagamento", page, 25, entity["cpfCnpj"]
                    )
                _require(details["total"] == expected)
                _require(
                    all(
                        r["uf"] == "BA" and str(r["anoPagamento"]) == str(year)
                        for r in details["dados"]
                    )
                )
        state["status"] = result["status"]
        state["catalog_entities"] = result["entities"]
    except _Pause:
        state["status"] = "partial"
    except Exception:
        # Never include URL, identifiers, source text or transport exception.
        state["status"] = "failed"
    store.save("run", state)
    return state
