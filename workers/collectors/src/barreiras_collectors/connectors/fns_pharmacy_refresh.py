"""Private transition assessment for a previously reviewed pharmacy scope.

The caller must obtain approval from the authoritative registry, not user input.
This function never persists or approves anything. New scopes and changed
identity evidence require a separate decision; additions must preserve every
previous document's financial and order-query fields, not only the net amount.
"""

from .fns_pharmacy_reconciliation import reconcile_pharmacy_captures


def assess_refresh(
    *, previous, current, previous_register, current_register, previous_approved
):
    def result(status, reason, retained=0, added=0):
        return dict(
            status=status,
            reason=reason,
            retained_documents=retained,
            added_documents=added,
            publication_allowed=False,
        )

    try:
        if previous_approved is not True:
            return result("review_required", "previous_snapshot_not_approved")
        if any(previous[k] != current[k] for k in ("beneficiary", "payment_year")):
            return result("review_required", "different_scope")
        before = reconcile_pharmacy_captures(
            [previous], register_capture=previous_register
        )
        after = reconcile_pharmacy_captures(
            [current], register_capture=current_register
        )
        if any(r["status"] != "reconciled_private" for r in (before, after)):
            return result("invalid_evidence", "documentary_validation_failed")
        if previous_register["sha256"] != current_register["sha256"]:
            return result("review_required", "identity_evidence_changed")

        def payloads(report):
            return {
                row["document_key"]: {k: v for k, v in row.items() if k != "evidence"}
                for row in report["records"]
            }

        old, new = payloads(before), payloads(after)
        if not old:
            return result("review_required", "empty_baseline")
        if old.keys() - new.keys():
            return result("review_required", "document_removed")
        if any(old[key] != new[key] for key in old):
            return result("review_required", "document_changed")
        added = len(new.keys() - old.keys())
        return result(
            "append_only" if added else "unchanged",
            "existing_documents_preserved",
            len(old),
            added,
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return result("invalid_evidence", "invalid_transition_input")
