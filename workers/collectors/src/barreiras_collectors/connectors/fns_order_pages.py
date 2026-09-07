"""Inspect a complete OB response, without inferring payment or authorship."""

import hashlib
import json
from decimal import Decimal

from .fns_payment_evidence import (
    MAX_RESPONSE_BYTES,
    _money,
    _reject_constant,
    _require,
    _unique_object,
)


def inspect_order_pages(pages: list[bytes]) -> dict:
    """Caller must bind every original to the same exact official OB request.

    The response does not identify its OB globally. This diagnostic does not
    create a payment, assign a politician or replace the stricter pair reader.
    Rejected/ambiguous originals remain in private custody for review.
    """
    try:
        _require(isinstance(pages, list) and 0 < len(pages) <= 100)
        hashes, candidates = [], []
        expected = None
        conflict = False
        for index, raw in enumerate(pages):
            _require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_RESPONSE_BYTES)
            result = json.loads(
                raw,
                parse_float=Decimal,
                parse_constant=_reject_constant,
                object_pairs_hook=_unique_object,
            )["resultado"]
            for key in ("pagina", "total", "totalPaginas", "itensPorPagina"):
                _require(type(result[key]) is int)
            total, count = result["total"], result["itensPorPagina"]
            _require(total > 0 and count > 0 and result["pagina"] == index)
            _require(
                result["totalPaginas"] == len(pages) == (total + count - 1) // count
            )
            metadata = (total, count, result["totalPaginas"])
            if expected is None:
                expected = metadata
            _require(metadata == expected)
            rows = result["dados"]
            _require(
                isinstance(rows, list)
                and len(rows) == min(count, total - index * count)
            )
            digest = hashlib.sha256(raw).hexdigest()
            _require(digest not in hashes)
            hashes.append(digest)
            for row in rows:
                _require(isinstance(row, dict))
                for key in ("codigoIBGE", "municipio", "uf"):
                    _require(isinstance(row[key], str) and bool(row[key]))
                code_matches = row["codigoIBGE"] == "290320"
                name_matches = row["municipio"] == "BARREIRAS"
                if code_matches or name_matches:
                    if not (code_matches and name_matches and row["uf"] == "BA"):
                        conflict = True
                    else:
                        candidates.append((index + 1, row))
        base = {"page_sha256": hashes, "publication_allowed": False}
        if conflict:
            return {**base, "status": "territory_conflict"}
        if len(candidates) > 1:
            return {**base, "status": "ambiguous"}
        if not candidates:
            return {**base, "status": "not_found"}
        page_number, row = candidates[0]
        _require(isinstance(row["motivoRejeicao"], str))
        if row["motivoRejeicao"] != "":
            return {**base, "status": "review_required", "source_page": page_number}
        amount = _money(row["valor"])
        return {
            **base,
            "status": "unique_territorial_row",
            "source_page": page_number,
            "municipality_ibge": "2903201",
            "amount": f"{amount:.2f}",
        }
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        ArithmeticError,
        RecursionError,
    ):
        return {"status": "invalid_pages", "publication_allowed": False}
