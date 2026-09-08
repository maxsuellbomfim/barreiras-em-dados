"""Bounded private inventory of FNS Other Payments entities, not pharmacies.

The catalog identifies queries to inspect, never a program or legal identity.
Only trusted acquisition metadata may be passed here. Raw identifiers stay in
the private source bytes; references point to their original page and row.
"""

import hashlib
import json
import re
from urllib.parse import parse_qsl, urlsplit

from .fns_payment_evidence import (
    MAX_RESPONSE_BYTES,
    _reject_constant,
    _require,
    _unique_object,
)


def inspect_entity_catalog(captures: list[dict], *, payment_year: int) -> dict:
    """Require a consistent, complete page set before closing the catalog."""
    blocked = dict(status="invalid_capture", publication_allowed=False)
    try:
        _require(type(payment_year) is int and 2021 <= payment_year <= 2100)
        _require(isinstance(captures, list) and len(captures) <= 100)
        if not captures:
            return dict(status="not_collected", publication_allowed=False)
        pages, identities, references = {}, set(), []
        expected_total = None
        for capture in captures:
            body = capture["body"]
            _require(isinstance(body, bytes) and 0 < len(body) <= MAX_RESPONSE_BYTES)
            _require(
                type(capture["http_status"]) is int and capture["http_status"] == 200
            )
            _require(
                type(capture["byte_size"]) is int and capture["byte_size"] == len(body)
            )
            sha = hashlib.sha256(body).hexdigest()
            _require(capture["sha256"] == sha)
            url = capture["request_url"]
            _require(isinstance(url, str) and not any(c.isspace() for c in url))
            _require(url == capture["final_url"])
            parsed = urlsplit(url)
            _require(
                parsed.scheme == "https" and parsed.netloc == "consultafns.saude.gov.br"
            )
            _require(
                parsed.path == "/recursos/consulta-detalhada/entidades"
                and not parsed.fragment
            )
            pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
            query = dict(pairs)
            _require(len(pairs) == len(query))
            page_text = query.get("page", "")
            _require(bool(re.fullmatch(r"[1-9][0-9]{0,2}", page_text)))
            page = int(page_text)
            _require(1 <= page <= 100 and page not in pages)
            _require(
                query
                == dict(
                    ano=str(payment_year),
                    tipoConsulta="3",
                    estado="BA",
                    municipio="290320",
                    page=str(page),
                    count="10",
                )
            )
            data = json.loads(
                body, parse_constant=_reject_constant, object_pairs_hook=_unique_object
            )["resultado"]
            _require(
                all(
                    type(data[k]) is int
                    for k in ("pagina", "total", "totalPaginas", "itensPorPagina")
                )
            )
            total = data["total"]
            _require(
                0 <= total <= 1000
                and data["pagina"] == page - 1
                and data["itensPorPagina"] == 10
            )
            total_pages = (total + 9) // 10
            _require(data["totalPaginas"] == total_pages)
            _require(page <= max(1, total_pages))
            if expected_total is None:
                expected_total = total
            _require(total == expected_total)
            rows = data["dados"]
            _require(
                isinstance(rows, list)
                and len(rows) == min(10, max(0, total - (page - 1) * 10))
            )
            for index, row in enumerate(rows, 1):
                _require(
                    row["uf"] == "BA" and str(row["codigoMunicipioIBGE"]) == "290320"
                )
                identifier = row["cpfCnpj"]
                _require(
                    isinstance(identifier, str)
                    and re.fullmatch(r"[0-9]{1,14}", identifier)
                )
                _require(identifier not in identities)
                identities.add(identifier)
                references.append(dict(page=page, source_row=index, source_sha256=sha))
            pages[page] = sha
        complete = sorted(pages) == list(range(1, max(1, total_pages) + 1))
        return dict(
            status=("empty" if expected_total == 0 else "complete")
            if complete
            else "partial",
            entities=len(identities),
            expected_entities=expected_total,
            pages_observed=len(pages),
            pages_expected=max(1, total_pages),
            references=sorted(references, key=lambda r: (r["page"], r["source_row"])),
            program_classification="not_performed",
            publication_allowed=False,
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        RecursionError,
    ):
        return blocked
