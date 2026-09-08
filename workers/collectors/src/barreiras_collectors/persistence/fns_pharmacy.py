"""Deterministic private import plan; no upload, approval or public totals."""

import hashlib
import json
from datetime import datetime

from ..connectors.fns_pharmacy_reconciliation import reconcile_pharmacy_captures


def _sha(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def prepare_pharmacy_import(captures, *, register_capture):
    try:
        report = reconcile_pharmacy_captures(
            captures, register_capture=register_capture
        )
        if report["status"] != "reconciled_private":
            raise ValueError("unreconciled")
        artifacts, snapshots, scopes = {}, [], set()

        def artifact(capture, kind):
            sha = capture["sha256"]
            retrieved = (
                capture["retrieved_at"]
                if kind == "register"
                else capture["received_at"]
            )
            if datetime.fromisoformat(retrieved).utcoffset() is None:
                raise ValueError("timestamp")
            suffix = "xlsx" if kind == "register" else "json"
            value = dict(
                sha256=sha,
                byte_size=capture["byte_size"],
                object_key=f"fns/payments/pharmacy/sha256/{sha[:2]}/{sha}.{suffix}",
                retrieved_at=retrieved,
                endpoint=kind,
                source_url=capture["source_url"]
                if kind == "register"
                else capture["request_url"],
                http_status=None if kind == "register" else capture["http_status"],
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                if kind == "register"
                else "application/json",
            )
            if sha in artifacts and artifacts[sha] != value:
                raise ValueError("artifact conflict")
            artifacts[sha] = value
            return sha

        reg_sha = artifact(register_capture, "register")
        for item in captures:
            scope = _sha(["fns-pharmacy", item["beneficiary"], item["payment_year"]])
            if scope in scopes:
                raise ValueError("one snapshot per scope per import")
            scopes.add(scope)
            pay_sha = artifact(item["payment_capture"], "payment")
            documents = []
            for row in report["records"]:
                refs = [e for e in row["evidence"] if e["payment_sha256"] == pay_sha]
                if not refs:
                    continue
                if len(refs) != 1:
                    raise ValueError("ambiguous evidence")
                ref = refs[0]
                payload = dict(
                    document_key=row["document_key"],
                    document_date=row["document_date"],
                    net=row["amounts"]["net"],
                    source_row=ref["source_row"],
                    establishment=row["establishment"],
                    register_row=ref["register_row"],
                    register_sha256=reg_sha,
                )
                documents.append(
                    dict(
                        payload=payload,
                        payload_sha256=_sha(payload),
                        idempotency_key=_sha([pay_sha, payload]),
                    )
                )
            if (
                not documents
                or len({d["payload"]["establishment"] for d in documents}) != 1
            ):
                raise ValueError("invalid document scope")
            snapshots.append(
                dict(
                    scope_key=scope,
                    payment_year=item["payment_year"],
                    payment_sha256=pay_sha,
                    register_sha256=reg_sha,
                    establishment=documents[0]["payload"]["establishment"],
                    documents=sorted(
                        documents, key=lambda d: d["payload"]["source_row"]
                    ),
                )
            )
        plan = dict(
            artifacts=sorted(artifacts.values(), key=lambda a: a["sha256"]),
            snapshots=sorted(snapshots, key=lambda s: s["scope_key"]),
            publication_allowed=False,
            version="fns-pharmacy-import/1.0.0",
        )
        return dict(**plan, plan_sha256=_sha(plan))
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("Invalid pharmacy import evidence") from None
