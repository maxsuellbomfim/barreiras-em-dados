"""Private, bounded reconciliation of FNS pharmacy observations, not CGU money.

A shared order-query fingerprint is only a query relationship. It neither
proves order ownership nor permits attributing the entire order to a pharmacy.
Inputs are preserved captures from trusted acquisition, never public payloads.
"""

import hashlib
import json
import re
from decimal import Decimal

from .fns_payment_evidence import _require
from .fns_pharmacy_identity import inspect_pharmacy_identity
from .fns_pharmacy_pages import inspect_pharmacy_capture


def _fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _order_query(row: dict) -> str:
    # Exactly the parameters used by the official order detail query, excluding
    # pagination. No beneficiary parameter exists in that query.
    year, month = str(row["id"]["ano"]), str(row["id"]["mes"])
    _require(bool(re.fullmatch(r"[0-9]{4}", year)))
    _require(bool(re.fullmatch(r"[0-9]{1,2}", month)) and 1 <= int(month) <= 12)
    competence = row["competencia"]
    _require(isinstance(competence, str) and 0 < len(competence) <= 80)
    _require(not re.search(r"[\x00-\x1f\x7f]", competence))
    return _fingerprint(
        [
            str(row["anoPagamento"]),
            int(month),
            int(year),
            competence,
            row["uf"],
            row["numeroDocumentoSiafi"],
            row["tipoDocumentoPagamento"],
        ]
    )


def reconcile_pharmacy_captures(
    captures: list[dict], *, register_capture: dict
) -> dict:
    """Retain unique document observations and expose conflicts, never sum totals.

    All observations in this batch must pass both existing readers. Distinct
    snapshots of the same beneficiary/year must agree on the document set and
    amounts/query. No latest-wins overwrite and no silent removal are allowed.
    Even successful output requires a separate persisted publication decision.
    """
    blocked = dict(status="invalid_evidence", records=[], publication_allowed=False)
    try:
        _require(isinstance(captures, list) and 0 < len(captures) <= 20)
        documents, snapshots, query_beneficiaries = {}, {}, {}
        reasons, conflicts = set(), set()
        observations = 0
        for item in captures:
            beneficiary, year = item["beneficiary"], item["payment_year"]
            capture = item["payment_capture"]
            identity = inspect_pharmacy_identity(
                register_capture=register_capture,
                payment_capture=capture,
                beneficiary=beneficiary,
                payment_year=year,
            )
            _require(identity["status"] == "institution_matched")
            page = inspect_pharmacy_capture(
                capture, beneficiary=beneficiary, payment_year=year
            )
            _require(page["status"] == "documentary_consistent")
            # Duplicate keys/nonfinite JSON were already rejected by the reader.
            rows = json.loads(capture["body"], parse_float=Decimal)["resultado"][
                "dados"
            ]
            keys = frozenset(r["document_key"] for r in page["records"])
            scope = (beneficiary, year)
            if scope in snapshots and snapshots[scope] != keys:
                reasons.add("snapshot_document_set_changed")
            snapshots[scope] = keys
            for row, record in zip(rows, page["records"], strict=True):
                observations += 1
                query = _order_query(row)
                query_beneficiaries.setdefault(query, set()).add(beneficiary)
                key = record["document_key"]
                payload = dict(
                    document_key=key,
                    document_date=record["document_date"],
                    amounts=record["amounts"],
                    order_query_sha256=query,
                    establishment=identity["establishment"],
                )
                evidence = dict(
                    payment_sha256=record["source_sha256"],
                    source_row=record["source_row"],
                    register_sha256=identity["register_sha256"],
                    register_row=identity["register_row"],
                )
                if "register_page" in identity:
                    evidence["register_page"] = identity["register_page"]
                if key not in documents:
                    documents[key] = dict(payload=payload, evidence=[])
                elif documents[key]["payload"] != payload:
                    reasons.add("conflicting_document")
                    conflicts.add(key)
                if evidence not in documents[key]["evidence"]:
                    documents[key]["evidence"].append(evidence)
        unique_observations = sum(len(d["evidence"]) for d in documents.values())
        records = [
            dict(
                **documents[k]["payload"],
                evidence=sorted(
                    documents[k]["evidence"],
                    key=lambda e: (e["payment_sha256"], e["source_row"]),
                ),
            )
            for k in sorted(documents)
        ]
        return dict(
            status="review_required" if reasons else "reconciled_private",
            records=[] if reasons else records,
            review_reasons=sorted(reasons),
            conflicting_document_keys=sorted(conflicts),
            observed_documents=len(documents),
            repeated_observations=observations - unique_observations,
            shared_order_queries=sum(len(b) > 1 for b in query_beneficiaries.values()),
            publication_allowed=False,
            historical_registration_verified=False,
            cross_source_reconciliation="not_performed",
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        ArithmeticError,
    ):
        return blocked
