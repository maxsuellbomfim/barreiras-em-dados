"""Manual, private PNCP contract discovery: one publication page per execution."""

import argparse
import hashlib
import json
import re
from datetime import date
from urllib.parse import urlencode

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.pncp import fetch_registry_snapshot
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import PNCP_COLLECTOR_VERSION, PncpRegistryPersistenceService
from ..settings import PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

CNPJ = "13654405000195"
PAGE_SIZE = 50


def page_request(since, until, page):
    start, end = date.fromisoformat(since), date.fromisoformat(until)
    if not 0 <= (end - start).days < 7 or type(page) is not int or not 1 <= page <= 100:
        raise ValueError("Use a publication window of 1-7 days and page 1-100.")
    resource = f"publication-contracts:{since}:{until}:page:{page}"
    url = "https://pncp.gov.br/api/consulta/v1/contratos?" + urlencode(
        {
            "dataInicial": start.strftime("%Y%m%d"),
            "dataFinal": end.strftime("%Y%m%d"),
            "cnpjOrgao": CNPJ,
            "pagina": page,
            "tamanhoPagina": PAGE_SIZE,
        }
    )
    return resource, url


def collect_page(*, since, until, page, service, fetch=fetch_registry_snapshot):
    resource, url = page_request(since, until, page)
    snapshot = fetch(resource, url)
    if (
        snapshot.resource != resource
        or snapshot.url != url
        or snapshot.final_url != url
        or snapshot.http_status != 200
        or hashlib.sha256(snapshot.body).hexdigest() != snapshot.body_sha256
    ):
        raise ValueError("Unverified PNCP publication response.")
    # Invalid source schemas remain preserved privately, never normalized.
    result = service.persist(snapshot)
    data = json.loads(snapshot.body)
    if not isinstance(data, dict):
        raise ValueError("PNCP publication response must be an object.")
    fields = ("numeroPagina", "totalPaginas", "totalRegistros", "paginasRestantes")
    if any(type(data.get(key)) is not int or data[key] < 0 for key in fields):
        raise ValueError("Missing or invalid PNCP pagination.")
    rows = data.get("data")
    total, pages = data["totalRegistros"], data["totalPaginas"]
    expected_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    valid_empty = total == 0 and page == 1 and pages in (0, 1)
    if (
        not isinstance(rows, list)
        or data["numeroPagina"] != page
        or (not valid_empty and (pages != expected_pages or not 1 <= page <= pages))
        or data["paginasRestantes"] != max(0, pages - page)
        or len(rows) != min(PAGE_SIZE, max(0, total - (page - 1) * PAGE_SIZE))
    ):
        raise ValueError("Inconsistent PNCP pagination; coverage not confirmed.")
    controls = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid PNCP contract.")
        key = row.get("numeroControlePNCP")
        owner = row.get("orgaoEntidade")
        if (
            not isinstance(key, str)
            or not re.fullmatch(rf"{CNPJ}-2-[0-9]{{6}}/[0-9]{{4}}", key)
            or not isinstance(owner, dict)
            or owner.get("cnpj") != CNPJ
        ):
            raise ValueError("Contract control or owner incompatible with query.")
        controls.append(key)
    if len(set(controls)) != len(controls):
        raise ValueError("Repeated PNCP contract on publication page.")
    return {
        "scope": "private_publication_page",
        "publication_authorized": False,
        "window_complete": False,
        "page": page,
        "records_on_page": len(rows),
        "reported_total": total,
        "reported_pages": pages,
        "next_page": page + 1 if page < pages else None,
        "artifact_id": result.raw_artifact_id,
        "sha256": snapshot.body_sha256,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--page", type=int, default=1)
    args = parser.parse_args(argv)
    resource, _ = page_request(args.since, args.until, args.page)
    settings = PersistenceSettings.from_env()
    if settings.mode != "postgres-supabase" or settings.database_url is None:
        raise RuntimeError("Cloud persistence required.")
    repository = PostgresCollectionRepository.from_dsn(settings.database_url)
    with CollectionControl(
        repository=repository,
        source_code="pncp",
        endpoint_code="registry-api",
        idempotency_key=build_execution_idempotency_key("pncp-publication-evidence"),
        collector_version=PNCP_COLLECTOR_VERSION,
        parser_version="pncp-publication-evidence/1.0.0",
        partition_key=resource,
        period_start=date.fromisoformat(args.since),
        period_end=date.fromisoformat(args.until),
    ) as control:
        service = PncpRegistryPersistenceService(
            object_store=build_authenticated_object_store(settings),
            repository=repository,
        )
        summary = collect_page(
            since=args.since, until=args.until, page=args.page, service=service
        )
        control.complete(
            outcome=CollectionOutcome.COMPLETE
            if summary["records_on_page"]
            else CollectionOutcome.EMPTY,
            observed_records=summary["records_on_page"],
            checkpoint=summary,
            metrics={"scope": summary["scope"], "publication_authorized": False},
        )
    print(json.dumps({"event": "pncp_publication_page_preserved", **summary}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
