"""Compare private documentary observations, without asserting a paid transfer."""

import json
from decimal import Decimal

from .fns_order_pages import inspect_order_captures
from .fns_payment_evidence import _digits, _money, _reject_constant, _unique_object
from .fns_payment_pages import normalize_payment_pages


def inspect_document_link(
    payment_pages: list[bytes],
    order_captures: list[dict],
    *,
    action_id: int,
    payment_year: int,
    order_number: str,
) -> dict:
    """Payment originals must belong to the caller's validated acquisition scope.

    Reads originals afresh rather than trusting caller-edited normalized rows.
    No identity/author resolution, database writes or publication permissions.
    """
    base = {"publication_allowed": False}
    try:
        _digits(order_number, 6)
        normalized = normalize_payment_pages(
            payment_pages, action_id=action_id, payment_year=payment_year
        )
        if normalized["status"] == "invalid_pages":
            return dict(base, status="invalid_payment_pages")
        candidates = [
            r
            for r in normalized["records"]
            if r["order_scope"]["numeroDocumentoSiafi"] == order_number
        ]
        if len(candidates) != 1:
            return dict(
                base, status="ambiguous_payment" if candidates else "payment_not_found"
            )
        payment = candidates[0]
        scope = payment["order_scope"]
        order = inspect_order_captures(order_captures, scope)
        if order["status"] in ("invalid_capture", "invalid_pages"):
            return dict(base, status="invalid_order_capture")
        lineage = dict(
            base,
            document_key=payment["document_key"],
            payment_sha256=payment["source_sha256"],
            payment_page=payment["source_page"],
            payment_row=payment["source_row"],
            order_sha256=order["page_sha256"],
        )
        if payment["review_reasons"] or order["status"] == "review_required":
            return dict(lineage, status="review_required")
        if order["status"] != "unique_territorial_row":
            return dict(lineage, status="order_" + order["status"])
        raw = order_captures[order["source_page"] - 1]["body"]
        rows = json.loads(
            raw,
            parse_float=Decimal,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )["resultado"]["dados"]
        row = next(r for r in rows if r["codigoIBGE"] == "290320")
        competence = scope["competencia"]
        # Only the exact already-reproduced UTF-8/Latin-1 echo is accepted.
        if (
            row["anoExercicio"] != scope["ano"]
            or row["mesExercicio"] != scope["mes"]
            or row["competencia"]
            not in (competence, competence.encode("utf-8").decode("latin-1"))
            or _money(order["amount"]) != _money(payment["amounts"]["net"])
        ):
            return dict(lineage, status="document_conflict")
        return dict(lineage, status="consistent_documentary_pair")
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        StopIteration,
        ArithmeticError,
        RecursionError,
    ):
        return dict(base, status="invalid_evidence")
