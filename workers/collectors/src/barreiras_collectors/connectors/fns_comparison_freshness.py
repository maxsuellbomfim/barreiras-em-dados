"""Read-only freshness against supplied preserved artifacts, not live FNS."""

import hashlib
import json
import re
from datetime import datetime
from urllib.parse import parse_qsl, urlsplit


def _url(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "consultafns.saude.gov.br"
        or parsed.fragment
        or parsed.path
        not in (
            "/recursos/consulta-detalhada/detalhe-pagamento",
            "/recursos/consulta-detalhada/detalhe-ordem-bancaria",
        )
    ):
        raise ValueError("Invalid origin")
    pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    if not pairs or len(dict(pairs)) != len(pairs):
        raise ValueError("Invalid query")
    return parsed.path, tuple(sorted(pairs))


def inspect_comparison_freshness(payload, payload_sha256, artifacts):
    """Caller supplies complete relevant artifact history, without SQL truncation.

    Does not download/hash Storage bytes or detect unpreserved source failures.
    Current means only the latest preserved responses match the comparison.
    No payment execution, public approval or completeness claim is produced.
    """
    base = dict(publication_allowed=False)
    try:
        actual = hashlib.sha256(
            json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        if actual != payload_sha256 or payload["publication_allowed"] is not False:
            return dict(base, status="invalid_comparison")
        if payload["methodology_version"] != "fns-document-comparison/1.0.0":
            return dict(base, status="unsupported_methodology")
        if payload["status"] not in {
            "consistent_documentary_pair",
            "review_required",
            "document_conflict",
            "order_not_found",
            "order_ambiguous",
            "order_territory_conflict",
        }:
            return dict(base, status="invalid_comparison")
        evidence = payload["payment_evidence"] + payload["order_evidence"]
        if (
            not payload["payment_evidence"]
            or not payload["order_evidence"]
            or len(evidence) > 200
        ):
            return dict(base, status="invalid_comparison")
        expected = {}
        for e in evidence:
            key = _url(e["request_url"])
            if (
                key in expected
                or _url(e["final_url"]) != key
                or not re.fullmatch("[0-9a-f]{64}", e["sha256"])
            ):
                return dict(base, status="invalid_comparison")
            expected[key] = e["sha256"]
    except (ValueError, TypeError, KeyError, AttributeError):
        return dict(base, status="invalid_comparison")
    try:
        if not isinstance(artifacts, list) or len(artifacts) > 10000:
            return dict(base, status="invalid_evidence")
        grouped = {k: [] for k in expected}

        def context(key):
            return key[0], tuple(
                (k, v) for k, v in key[1] if k not in ("page", "count")
            )

        contexts = {context(k) for k in expected}
        extras = []
        for artifact in artifacts:
            key = _url(artifact["request_url"])
            if context(key) not in contexts:
                continue
            at = datetime.fromisoformat(
                str(artifact["retrieved_at"]).replace("Z", "+00:00")
            )
            if at.tzinfo is None:
                return dict(base, status="invalid_evidence")
            if key in expected:
                grouped[key].append((at, artifact))
            else:
                extras.append((context(key), at))
        for key, sha in expected.items():
            if not grouped[key]:
                return dict(base, status="missing_evidence")
            latest = max(at for at, _ in grouped[key])
            current = [a for at, a in grouped[key] if at == latest]
            for a in current:
                if (
                    type(a["http_status"]) is not int
                    or a["http_status"] != 200
                    or _url(a["final_url"]) != key
                    or not re.fullmatch("[0-9a-f]{64}", a["sha256"])
                ):
                    return dict(base, status="invalid_evidence")
            hashes = {a["sha256"] for a in current}
            if len(hashes) > 1:
                return dict(base, status="conflicting_evidence")
            if hashes != {sha}:
                return dict(base, status="stale_evidence")
        for scope, at in extras:
            baseline = min(
                max(t for t, _ in rows)
                for k, rows in grouped.items()
                if context(k) == scope
            )
            if at >= baseline:
                return dict(base, status="pagination_changed")
        return dict(
            base,
            status="current_preserved_evidence",
            comparison_status=payload["status"],
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        return dict(base, status="invalid_evidence")
