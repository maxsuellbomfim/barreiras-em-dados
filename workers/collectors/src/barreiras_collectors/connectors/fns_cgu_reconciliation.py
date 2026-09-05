"""Reconciliation of a scoped FNS payment against a complete CGU annual archive."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from decimal import Decimal

from .cgu_federal_amendment_documents import (
    CGUFederalAmendmentDocumentArchiveError,
    parse_cgu_federal_amendment_documents_archive,
)
from .fns_payment_evidence import parse_fns_payment_evidence

# Institutional identifiers observed in the official FNS entity selector and
# independently checked in the CGU records. No person's identifier is inferred.
FMS_BARREIRAS_CNPJ = "08595187000125"
FNS_MANAGEMENT_UNIT = "257001"
METHOD = "fns-cgu-payment-reconciliation/1.0.0"


class FNSCGUReconciliationError(ValueError):
    """An input archive cannot be validated; not equivalent to no match."""


def reconcile_fns_cgu_payment(
    *,
    payment_body: bytes,
    order_body: bytes,
    action_id: int,
    payment_year: int,
    order_number: str,
    cgu_archive_body: bytes,
) -> dict:
    """Produce a review candidate, never a publication or an added payment.

    Reparse the complete annual ZIP rather than accepting a paginated API or
    caller-filtered list that might hide a second matching record. A new ZIP
    produces a new archive hash/key: an old review must not silently carry over.
    The FNS OB lacks UG/gestao, so even a unique candidate requires review.
    """
    fns = parse_fns_payment_evidence(
        payment_body,
        order_body,
        action_id=action_id,
        payment_year=payment_year,
        order_number=order_number,
    )
    try:
        rows = parse_cgu_federal_amendment_documents_archive(
            cgu_archive_body,
            archive_year=payment_year,
        )
    except CGUFederalAmendmentDocumentArchiveError:
        raise FNSCGUReconciliationError(
            "Arquivo anual CGU inválido; reconciliação não executada."
        ) from None

    # Select broadly first. Never cherry-pick one line by value/date/amendment
    # and hide other lines, other gestoes or other issuers sharing the short OB.
    candidates = [
        row
        for row in rows
        if (
            row["expense_stage"] == "payment"
            and row["beneficiary_code"] == FMS_BARREIRAS_CNPJ
            and row["municipality_ibge"] == "2903201"
            and str(row["document_code"]).endswith(f"{payment_year}OB{order_number}")
        )
    ]
    report = {
        "methodology_version": METHOD,
        "status": "not_found",
        "publication_allowed": False,
        "candidate_count": len(candidates),
        "candidate": None,
    }
    if not candidates:
        return report
    if len(candidates) != 1:
        return {**report, "status": "ambiguous"}
    row = candidates[0]
    code = str(row["document_code"])
    document_match = re.fullmatch(
        rf"(?P<ug>[0-9]{{6}})[0-9]{{5}}{payment_year}OB{order_number}", code
    )
    amendment = fns["amendment_number"]
    amendment_type = unicodedata.normalize("NFKD", str(row["amendment_type"]))
    amendment_type = "".join(
        c for c in amendment_type if not unicodedata.combining(c)
    ).lower()
    valid = (
        document_match is not None
        and document_match["ug"] == row["management_unit_code"] == FNS_MANAGEMENT_UNIT
        and row["document_date"] == fns["document_date"]
        and Decimal(str(row["paid_amount"])) == Decimal(fns["paid_amount"])
        and row["amendment_code"] == f"{row['amendment_year']}{amendment}"
        and row["amendment_number"] == amendment[-4:]
        and row["author_code"] == amendment[:4] == "5041"
        # Only this collective-author mapping was independently verified.
        # Other authors/types remain conflicts for review, not name matches.
        and amendment_type == "emenda de comissao"
        and row["author_name"] == "COM. DA SAUDE"
        and fns["author_name"] == "COMISSÃO DA SAÚDE"
        and row["state_code"] == row["beneficiary_state"] == "BA"
        and row["beneficiary_municipality"] == "BARREIRAS"
    )
    if not valid:
        return {**report, "status": "conflict"}
    candidate = {
        "document_code": code,
        "amendment_code": row["amendment_code"],
        "amendment_year": row["amendment_year"],
        "document_date": fns["document_date"],
        "paid_amount": fns["paid_amount"],
        "municipality_ibge": "2903201",
        "cgu_author_name": row["author_name"],
        "fns_author_name": fns["author_name"],
        "requester_name": fns["requester_name"],
        "requester_source_code": fns["requester_source_code"],
        "proposal_number": fns["proposal_number"],
        "payment_sha256": fns["payment_sha256"],
        "order_sha256": fns["order_sha256"],
        "cgu_archive_sha256": hashlib.sha256(cgu_archive_body).hexdigest(),
        "source_row_number": row["source_row_number"],
        "aggregation_policy": "evidence_only_no_additional_payment",
    }
    candidate["reconciliation_key"] = hashlib.sha256(
        json.dumps(
            {"methodology_version": METHOD, **candidate},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return {**report, "status": "unique_candidate", "candidate": candidate}
