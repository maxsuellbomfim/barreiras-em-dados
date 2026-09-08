"""Read-only private FNS diagnostic; never interpret absence as financial zero."""

import argparse
import json
from collections import Counter

from ..connectors.fns_comparison_freshness import inspect_comparison_freshness
from ..settings import PostgresSettings


def audit(connection, *, action_id: int, payment_year: int):
    """Use a fresh, non-autocommit connection; output counts of versions, not money."""
    if (
        type(action_id) is not int
        or action_id <= 0
        or type(payment_year) is not int
        or not 2021 <= payment_year <= 2100
    ):
        raise ValueError("Invalid audit scope")
    connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    connection.execute("SET LOCAL statement_timeout = '20s'")
    records = connection.execute(
        """select r.payload, r.payload_sha256 from raw.raw_records r
        join raw.raw_artifacts a on a.id=r.raw_artifact_id
        join source.source_endpoints e on e.id=a.source_endpoint_id
        join source.data_sources s on s.id=e.data_source_id
        where s.slug='fns-consulta-detalhada' and e.slug='payment-detail'
          and r.record_type='fns_document_comparison'
          and r.payload->>'action_id'=%s and r.payload->>'payment_year'=%s
        limit 1001""",
        (str(action_id), str(payment_year)),
    ).fetchall()
    artifacts = connection.execute(
        """select a.metadata->>'request_url' request_url,
          a.metadata->>'final_url' final_url, a.sha256, a.retrieved_at, a.http_status
        from raw.raw_artifacts a
        join source.source_endpoints e on e.id=a.source_endpoint_id
        join source.data_sources s on s.id=e.data_source_id
        where s.slug='fns-consulta-detalhada'
          and e.slug in ('payment-detail','payment-order-detail') limit 10001"""
    ).fetchall()
    if len(records) > 1000 or len(artifacts) > 10000:
        raise ValueError("Audit exceeds bounded history")
    states, comparisons = Counter(), Counter()
    for row in records:
        result = inspect_comparison_freshness(
            row["payload"], row["payload_sha256"], artifacts
        )
        states[result["status"]] += 1
        if "comparison_status" in result:
            comparisons[result["comparison_status"]] += 1
    clear = bool(records) and comparisons["consistent_documentary_pair"] == len(records)
    report = dict(
        event="fns_comparison_audit",
        action_id=action_id,
        payment_year=payment_year,
        status="no_comparisons"
        if not records
        else "current_documentary_evidence"
        if clear
        else "needs_attention",
        comparison_versions=len(records),
        artifacts_scanned=len(artifacts),
        freshness_states=dict(states),
        comparison_states=dict(comparisons),
        read_only=True,
        publication_allowed=False,
    )
    return report, 0 if clear else 2


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Confere comparações FNS privadas sem publicar valores."
    )
    parser.add_argument("--action-id", type=int, required=True)
    parser.add_argument("--payment-year", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        settings = PostgresSettings.from_env()
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(
            settings.database_url, connect_timeout=20, row_factory=dict_row
        ) as connection:
            report, code = audit(
                connection, action_id=args.action_id, payment_year=args.payment_year
            )
    except Exception:
        # Neither credentials nor driver exception text may enter CLI logs.
        print(
            json.dumps(
                dict(
                    event="fns_comparison_audit",
                    status="failed",
                    publication_allowed=False,
                )
            )
        )
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
