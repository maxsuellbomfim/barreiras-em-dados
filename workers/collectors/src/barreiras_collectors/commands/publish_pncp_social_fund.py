"""Publish only the reviewed Social Fund pair from preserved private bytes."""

import argparse
import json
import logging
import re
from datetime import UTC, datetime

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.pncp import RegistrySnapshot
from ..persistence.postgres import PostgresCollectionRepository
from ..settings import PersistenceSettings
from .collect_pncp_municipal_link_evidence import CONTRACT, RESOURCES, validate_pair
from .pncp_runtime import build_authenticated_object_store


def failure_code(error):
    """Expose a bounded error class and SQLSTATE, never driver text or parameters."""
    name = type(error).__name__
    name = name if re.fullmatch(r"[A-Za-z]{1,80}", name) else "Error"
    state = getattr(error, "sqlstate", None)
    state = (
        state
        if isinstance(state, str) and re.fullmatch(r"[0-9A-Z]{5}", state)
        else "unknown"
    )
    return f"{name}:{state}"


def publish_pair(connection, object_store):
    rows = connection.execute(
        """select a.id,a.source_url,a.object_key,a.sha256,a.retrieved_at,a.http_status
        from source.collection_partitions p
        cross join lateral jsonb_array_elements(p.checkpoint->'evidence') e
        join raw.raw_artifacts a on a.id=(e->>'artifact_id')::uuid
        where p.partition_key=%s and p.status='complete'
          and p.observed_records=2 and a.sha256=e->>'sha256'""",
        (f"municipal-link:{CONTRACT}",),
    ).fetchall()
    by_url = {row[1]: row for row in rows}
    if len(rows) != 2 or set(by_url) != {url for _, url in RESOURCES}:
        raise ValueError("Complete preserved pair required; publication blocked.")
    snapshots, ids = [], []
    for resource, url in RESOURCES:
        artifact_id, _, key, digest, retrieved_at, status = by_url[url]
        body = object_store.read(key)
        if not 2 <= len(body) <= 32768:
            raise ValueError("Invalid evidence size; publication blocked.")
        ids.append(artifact_id)
        snapshots.append(
            RegistrySnapshot(
                resource=resource,
                url=url,
                final_url=url,
                fetched_at=str(retrieved_at),
                http_status=status,
                body=body,
                body_sha256=digest,
                media_type="application/json",
            )
        )
    validate_pair(*snapshots)
    result = connection.execute(
        "select procurement.publish_social_fund_pair(%s,%s,%s,%s)",
        (ids[0], snapshots[0].body, ids[1], snapshots[1].body),
    ).fetchone()[0]
    if result != {"contracts": 1, "procurements": 1, "status": "published"}:
        raise ValueError("Unexpected publication result.")
    return result


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    settings = PersistenceSettings.from_env()
    if settings.mode != "postgres-supabase" or not settings.database_url:
        raise RuntimeError("Cloud persistence required.")
    import psycopg

    logging.basicConfig(level=logging.WARNING, format="%(message)s", force=True)
    today = datetime.now(UTC).date()
    control = CollectionControl(
        repository=PostgresCollectionRepository.from_dsn(settings.database_url),
        source_code="pncp",
        endpoint_code="registry-api",
        idempotency_key=build_execution_idempotency_key("pncp-social-fund-publication"),
        collector_version="pncp-reviewed-social-fund/1.0.0",
        parser_version="pncp-reviewed-social-fund/1.0.0",
        partition_key=f"publication:{CONTRACT}",
        period_start=today,
        period_end=today,
    )
    with control:
        try:
            store = build_authenticated_object_store(settings)
            with psycopg.connect(settings.database_url) as connection:
                result = publish_pair(connection, store)
        except Exception as error:
            # Database errors may include bound private JSON: never propagate them.
            raise RuntimeError(
                f"Social Fund publication failed ({failure_code(error)}); "
                "private details omitted."
            ) from None
        control.complete(
            outcome=CollectionOutcome.COMPLETE,
            observed_records=2,
            checkpoint=result,
            metrics={"scope": "reviewed_social_fund_pair"},
        )
    print(json.dumps({"event": "pncp_social_fund_published", **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
