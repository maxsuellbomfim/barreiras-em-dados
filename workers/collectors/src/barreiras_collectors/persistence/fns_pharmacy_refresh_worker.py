"""Private refresh execution. Acquisition/scheduling remain separate concerns.

Only a database-selected baseline can be used. Storage is immutable and read
back before SQL; import, approval and public projection verification commit
together. Errors deliberately omit source identifiers and database diagnostics.
"""

import hashlib
import json

from ..connectors.fns_pharmacy_identity import REGISTER_PAGE
from .fns_pharmacy import _sha, prepare_pharmacy_refresh


def execute_refresh(*, repository, object_store, current, current_register=None):
    """Execute one complete beneficiary/year observation, never an annual claim."""
    try:
        baseline = repository.load_baseline(current)
        if baseline is None:
            return dict(
                status="review_required",
                reason="no_approved_baseline",
                publication_allowed=False,
                retained_documents=0,
                added_documents=0,
            )
        report = prepare_pharmacy_refresh(
            previous=baseline["observation"],
            current=current,
            previous_register=baseline["register"],
            current_register=current_register or baseline["register"],
            previous_approved=baseline["approved"],
            previous_snapshot_id=baseline["snapshot_id"],
        )
        plan = report.pop("plan")
        if plan is None:
            return report
        current_register = current_register or baseline["register"]
        bodies = {
            current["payment_capture"]["sha256"]: current["payment_capture"]["body"],
            current_register["sha256"]: current_register["body"],
        }
        for artifact in plan["artifacts"]:
            body = bodies[artifact["sha256"]]
            if len(body) != artifact["byte_size"]:
                raise ValueError("Invalid artifact size")
            object_store.put_if_absent(
                object_key=artifact["object_key"],
                body=body,
                content_type=artifact["content_type"],
                expected_sha256=artifact["sha256"],
            )
            restored = object_store.read(artifact["object_key"])
            if (
                restored != body
                or hashlib.sha256(restored).hexdigest() != artifact["sha256"]
            ):
                raise ValueError("Invalid artifact readback")
        with repository.transaction():
            repository.import_plan(plan)
            if repository.verify_publication(plan) is not True:
                raise ValueError("Public projection mismatch")
        return dict(
            report,
            status="published",
            reason="verified_refresh",
            publication_allowed=True,
        )
    except Exception:
        raise RuntimeError("Pharmacy refresh failed") from None


class PostgresPharmacyRefreshRepository:
    """Operator connection only; this adapter does not grant database authority.

    Require autocommit for the baseline read, then an explicit transaction for
    the import. The SQL guard rejects a revoked or superseded baseline under
    its database locks, even if it changed during the Storage/network reads.
    """

    def __init__(self, connection, object_store):
        if not connection.autocommit:
            raise ValueError("Pharmacy connection must use explicit transactions")
        self.connection = connection
        self.object_store = object_store

    def _capture(self, artifact, *, payment):
        body = self.object_store.read(artifact["object_key"])
        if (
            len(body) != artifact["byte_size"]
            or hashlib.sha256(body).hexdigest() != artifact["sha256"]
        ):
            raise ValueError("Invalid baseline bytes")
        capture = dict(
            body=body,
            sha256=artifact["sha256"],
            byte_size=artifact["byte_size"],
            http_status=artifact["http_status"],
        )
        url = artifact["source_url"]
        if payment:
            capture.update(
                request_url=url, final_url=url, received_at=artifact["retrieved_at"]
            )
        else:
            capture.update(
                source_url=url,
                retrieved_at=artifact["retrieved_at"],
                referrer_url=REGISTER_PAGE,
            )
            if artifact["content_type"] == "application/pdf":
                suffix = "/@@download/file"
                if not url.endswith(suffix):
                    raise ValueError("Invalid renewal source")
                capture.update(
                    format="renewal_pdf", referrer_url=url[: -len(suffix)] + "/view"
                )
        return capture

    def load_baseline(self, current):
        from psycopg.rows import dict_row

        scope = _sha(["fns-pharmacy", current["beneficiary"], current["payment_year"]])
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "select * from source.get_pharmacy_refresh_baseline(%s,%s)",
                (scope, current["payment_year"]),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return dict(
            snapshot_id=row["id"],
            approved=row["approved"],
            observation=dict(
                beneficiary=current["beneficiary"],
                payment_year=current["payment_year"],
                payment_capture=self._capture(row["payment"], payment=True),
            ),
            register=self._capture(row["register"], payment=False),
        )

    def transaction(self):
        return self.connection.transaction()

    def known_scope_keys(self, year):
        from psycopg.rows import tuple_row

        with self.connection.cursor(row_factory=tuple_row) as cursor:
            cursor.execute(
                "select scope_key from source.get_pharmacy_refresh_scopes(%s)",
                (year,),
            )
            rows = cursor.fetchall()
        if len(rows) > 1000:
            raise ValueError("Pharmacy scope limit exceeded")
        return {row[0] for row in rows}

    def import_plan(self, plan):
        self.connection.execute(
            "select source.import_pharmacy_refresh(%s::jsonb)",
            (json.dumps(plan, ensure_ascii=False),),
        )

    def verify_publication(self, plan):
        from psycopg.rows import dict_row

        for snapshot in plan["snapshots"]:
            with self.connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    select id, establishment, date::text, amount, sha256,
                        register_sha256
                    from source.get_pharmacy_refresh_rows(%s,%s,%s) order by id
                """,
                    (
                        snapshot["payment_year"],
                        snapshot["payment_sha256"],
                        snapshot["register_sha256"],
                    ),
                )
                actual = cursor.fetchall()
            expected = sorted(
                (
                    dict(
                        id=d["payload"]["document_key"],
                        establishment=d["payload"]["establishment"],
                        date=d["payload"]["document_date"],
                        amount=d["payload"]["net"],
                        sha256=snapshot["payment_sha256"],
                        register_sha256=snapshot["register_sha256"],
                    )
                    for d in snapshot["documents"]
                ),
                key=lambda row: row["id"],
            )
            if actual != expected:
                return False
        return True
