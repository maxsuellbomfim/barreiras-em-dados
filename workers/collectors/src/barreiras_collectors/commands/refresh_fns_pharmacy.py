"""Controlled private acquisition and publication of pharmacy observations."""

import json
import time

from ..collection_control import CollectionOutcome
from ..connectors.fns_collection_resume import collect_year
from ..persistence.fns_pharmacy import _sha
from ..persistence.fns_pharmacy_refresh_worker import execute_refresh


def refresh_year(
    *,
    year,
    control,
    store,
    transport,
    repository,
    object_store,
    max_requests=20,
    sleep=time.sleep,
):
    """Register before acquisition; count reviewed documents, never sum money.

    A complete outcome describes this acquisition's catalogue and supported
    pharmacy observations, not service execution or municipal revenue.
    Missing historical scopes and unsupported details remain partial.
    """
    with control:
        try:
            return _refresh_year(
                year=year,
                control=control,
                store=store,
                transport=transport,
                repository=repository,
                object_store=object_store,
                max_requests=max_requests,
                sleep=sleep,
            )
        except Exception:
            # The control repository must never receive raw driver/source errors.
            raise RuntimeError("Pharmacy acquisition failed") from None


def _refresh_year(
    *, year, control, store, transport, repository, object_store, max_requests, sleep
):
    known = repository.known_scope_keys(year)
    observations = []
    acquisition = collect_year(
        year,
        store,
        transport,
        max_requests=max_requests,
        sleep=sleep,
        observations=observations,
    )
    status = acquisition["status"]
    if status == "failed":
        raise RuntimeError("Pharmacy acquisition failed")
    report = dict(
        event="pharmacy_refresh",
        year=year,
        status=status,
        pages_preserved=acquisition["pages_preserved"],
        verified_documents=0,
        published_scopes=0,
        unchanged_scopes=0,
        pending_scopes=0,
        missing_scopes=0,
        excluded_scopes=0,
    )
    if status == "partial":
        control.complete(
            outcome=CollectionOutcome.PARTIAL,
            observed_records=0,
            checkpoint=report,
            metrics=report,
        )
        return report
    if status not in ("complete", "empty"):
        raise ValueError("Unknown pharmacy acquisition state")
    seen = set()
    for observation in observations:
        scope = _sha(["fns-pharmacy", observation["beneficiary"], year])
        captures = observation["payment_captures"]
        # Acquisition already validated these bodies, hashes and pagination.
        programs = {
            row.get("nomeComponente")
            for capture in captures
            for row in json.loads(capture["body"])["resultado"]["dados"]
        }
        if programs and None not in programs and "FARMACIA POPULAR" not in programs:
            report["excluded_scopes"] += 1
            continue
        seen.add(scope)
        if len(captures) != 1 or programs != {"FARMACIA POPULAR"}:
            report["pending_scopes"] += 1
            continue
        result = execute_refresh(
            repository=repository,
            object_store=object_store,
            current=dict(
                beneficiary=observation["beneficiary"],
                payment_year=year,
                payment_capture=captures[0],
            ),
        )
        if result["status"] in ("published", "unchanged"):
            report["verified_documents"] += (
                result["retained_documents"] + result["added_documents"]
            )
            report[
                "published_scopes"
                if result["status"] == "published"
                else "unchanged_scopes"
            ] += 1
        else:
            report["pending_scopes"] += 1
    report["missing_scopes"] = len(known - seen)
    if report["pending_scopes"] or report["missing_scopes"]:
        report["status"] = "partial"
    control.complete(
        outcome=CollectionOutcome(report["status"]),
        observed_records=report["verified_documents"],
        checkpoint=report,
        metrics=report,
    )
    return report


def main(argv=None):
    """Windows operator entry point; secrets come only from existing settings."""
    import argparse
    from datetime import date
    from pathlib import Path

    from ..collection_control import CollectionControl, build_execution_idempotency_key
    from ..http import UrllibTransport
    from ..persistence.fns_pharmacy_refresh_worker import (
        PostgresPharmacyRefreshRepository,
    )
    from ..persistence.postgres import PostgresCollectionRepository
    from ..persistence.storage import SupabaseStorageObjectStore
    from ..settings import PersistenceSettings
    from .collect_fns_other_payments_local import PrivateStore

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--max-requests", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        if not 2021 <= args.year <= 2100 or not 1 <= args.max_requests <= 100:
            raise ValueError("Invalid refresh scope")
        settings = PersistenceSettings.from_env()
        if settings.mode != "postgres-supabase":
            raise ValueError("Cloud persistence required")
        import psycopg

        from supabase import create_client

        control = CollectionControl(
            repository=PostgresCollectionRepository.from_dsn(settings.database_url),
            source_code="fns-farmacia-popular",
            endpoint_code="payment",
            idempotency_key=build_execution_idempotency_key("pharmacy-refresh"),
            collector_version="pharmacy-refresh/1.0.0",
            parser_version="pharmacy-refresh/1.0.0",
            partition_key=f"pharmacy-refresh:{args.year}",
            period_start=date(args.year, 1, 1),
            period_end=date(args.year, 12, 31),
        )
        with control:
            try:
                client = create_client(
                    settings.supabase_url, settings.supabase_publishable_key
                )
                auth = client.auth.sign_in_with_password(
                    dict(
                        email=settings.supabase_workload_email,
                        password=settings.supabase_workload_password,
                    )
                )
                if auth.session is None or auth.user is None:
                    raise ValueError("Storage authentication failed")
                objects = SupabaseStorageObjectStore(
                    client.storage.from_(settings.raw_artifacts_bucket)
                )
                template = (
                    Path(__file__).resolve().parents[5]
                    / "scripts/sql/import-pharmacy-plan.sql"
                ).read_text(encoding="utf-8")
                with psycopg.connect(
                    settings.database_url, autocommit=True, connect_timeout=20
                ) as connection:
                    connection.execute("set statement_timeout='30s'")
                    connection.execute("set lock_timeout='10s'")
                    repository = PostgresPharmacyRefreshRepository(
                        connection, objects, template
                    )
                    with PrivateStore(args.directory) as store:
                        report = _refresh_year(
                            year=args.year,
                            control=control,
                            store=store,
                            transport=UrllibTransport(
                                frozenset({"consultafns.saude.gov.br"})
                            ),
                            repository=repository,
                            object_store=objects,
                            max_requests=args.max_requests,
                            sleep=time.sleep,
                        )
            except Exception:
                raise RuntimeError("Pharmacy acquisition failed") from None
        print(json.dumps(report))
        return 0 if report["status"] in ("complete", "empty") else 2
    except Exception:
        print('{"event":"pharmacy_refresh","status":"failed"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
