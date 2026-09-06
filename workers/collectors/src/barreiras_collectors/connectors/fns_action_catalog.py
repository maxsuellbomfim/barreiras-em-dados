"""Plan all actions from a preserved FNS catalogue, never classify authorship."""

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


class FNSCatalogError(ValueError):
    """Catalogue cannot establish a complete, internally consistent action list."""


def plan_fns_actions(pages: list[bytes]) -> dict:
    """Caller binds originals to the exact year/entity request; no network or writes.

    Completeness here refers only to the supplied action catalogue. Payment and
    amendment coverage cannot be inferred from action descriptions or totals.
    """
    try:
        _require(isinstance(pages, list) and 0 < len(pages) <= 100)
        actions, hashes, seen = [], [], set()
        totals = [Decimal(0), Decimal(0), Decimal(0)]
        official = None
        metadata = None
        rows_seen = zero_groups = 0
        for index, body in enumerate(pages, 1):
            _require(isinstance(body, bytes) and 0 < len(body) <= MAX_RESPONSE_BYTES)
            result = json.loads(
                body,
                parse_float=Decimal,
                parse_constant=_reject_constant,
                object_pairs_hook=_unique_object,
            )["resultado"]
            for key in ("pagina", "total", "totalPaginas", "itensPorPagina"):
                _require(type(result[key]) is int and result[key] > 0)
            _require(result["pagina"] == index)
            current = (
                result["total"],
                result["totalPaginas"],
                result["itensPorPagina"],
            )
            if metadata is None:
                metadata = current
            _require(metadata == current and current[1] == len(pages))
            _require((current[0] + current[2] - 1) // current[2] == current[1])
            rows = result["dados"]
            _require(isinstance(rows, list))
            _require(
                len(rows) == min(current[2], current[0] - (index - 1) * current[2])
            )
            hashes.append(hashlib.sha256(body).hexdigest())
            for row in rows:
                _require(isinstance(row, dict))
                identifier = row["id"]
                _require(type(identifier) is int and identifier >= 0)
                amounts = [
                    _money(row[key])
                    for key in ("valorTotal", "valorDescontoTotal", "valorLiquido")
                ]
                stated_raw = [
                    row.get(key)
                    for key in (
                        "valorTotalGeral",
                        "valorDescontoTotalGeral",
                        "valorLiquidoGeral",
                    )
                ]
                _require(amounts[0] - amounts[1] == amounts[2])
                if not all(value is None for value in stated_raw):
                    stated = [_money(value) for value in stated_raw]
                    if official is None:
                        official = stated
                    _require(stated == official)
                if identifier == 0:
                    _require(all(value == 0 for value in amounts))
                    zero_groups += 1
                else:
                    _require(identifier not in seen)
                    seen.add(identifier)
                    actions.append(identifier)
                totals = [
                    left + right for left, right in zip(totals, amounts, strict=True)
                ]
                rows_seen += 1
        _require(totals == official)
        return {
            "action_ids": actions,
            "catalogue_rows": rows_seen,
            "zero_group_rows": zero_groups,
            "page_sha256": hashes,
            "gross_amount": f"{totals[0]:.2f}",
            "discount_amount": f"{totals[1]:.2f}",
            "net_amount": f"{totals[2]:.2f}",
            "payment_coverage": "not_collected",
            "publication_allowed": False,
        }
    except (ValueError, TypeError, KeyError, IndexError, ArithmeticError):
        raise FNSCatalogError(
            "Incomplete or inconsistent FNS action catalogue"
        ) from None
