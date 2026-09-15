"""Preserve the reviewed municipal/fund pair privately; never normalize it."""

import argparse
import hashlib
import json
import logging
from datetime import UTC, datetime

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

MUNICIPAL_CNPJ = "13654405000195"
FUND_CNPJ = "13250888000162"
CONTRACT = f"{MUNICIPAL_CNPJ}-2-000023/2026"
PARENT = f"{FUND_CNPJ}-1-000003/2026"
RESOURCES = (
    (
        f"municipal-link:contract:{CONTRACT}",
        f"https://pncp.gov.br/api/pncp/v1/orgaos/{MUNICIPAL_CNPJ}/contratos/2026/23",
    ),
    (
        f"municipal-link:procurement:{PARENT}",
        f"https://pncp.gov.br/api/consulta/v1/orgaos/{FUND_CNPJ}/compras/2026/3",
    ),
)


def _require(condition):
    if not condition:
        raise ValueError(
            "Municipal link evidence is incompatible; publication blocked."
        )


def validate_pair(contract, parent):
    payloads = []
    for snapshot, (resource, url), cnpj, key in zip(
        (contract, parent),
        RESOURCES,
        (MUNICIPAL_CNPJ, FUND_CNPJ),
        (CONTRACT, PARENT),
        strict=True,
    ):
        _require(
            snapshot.resource == resource and snapshot.url == snapshot.final_url == url
        )
        _require(snapshot.http_status == 200)
        _require(hashlib.sha256(snapshot.body).hexdigest() == snapshot.body_sha256)
        data = json.loads(snapshot.body)
        _require(isinstance(data, dict) and data.get("numeroControlePNCP") == key)
        _require(isinstance(data.get("orgaoEntidade"), dict))
        _require(data["orgaoEntidade"].get("cnpj") == cnpj)
        _require(isinstance(data.get("unidadeOrgao"), dict))
        _require(data["unidadeOrgao"].get("codigoIbge") == "2903201")
        payloads.append(data)
    links = [
        payloads[0][name]
        for name in ("numeroControlePNCPCompra", "numeroControlePncpCompra")
        if name in payloads[0]
    ]
    _require(bool(links) and all(link == PARENT for link in links))


def collect_pair(*, service, fetch=fetch_registry_snapshot):
    pages, evidence = [], []
    for resource, url in RESOURCES:
        snapshot = fetch(resource, url)
        # The existing service uploads immutable bytes and reads them back by hash.
        result = service.persist(snapshot)
        pages.append(snapshot)
        evidence.append(
            {"artifact_id": result.raw_artifact_id, "sha256": snapshot.body_sha256}
        )
    validate_pair(*pages)
    return {
        "validated_artifacts": len(pages),
        "evidence": evidence,
        "publication_authorized": False,
        "contract_control": CONTRACT,
        "procurement_control": PARENT,
    }


def execute_controlled_pair(*, control, operation):
    with control:
        summary = operation()
        control.complete(
            outcome=CollectionOutcome.COMPLETE,
            observed_records=2,
            checkpoint=summary,
            metrics={
                "scope": "private_municipal_link_evidence",
                "validated_artifacts": 2,
                "publication_authorized": False,
            },
        )
    return summary


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    settings = PersistenceSettings.from_env()
    if settings.mode != "postgres-supabase" or settings.database_url is None:
        raise RuntimeError("Cloud persistence required.")
    logging.basicConfig(level=logging.WARNING, format="%(message)s", force=True)
    repository = PostgresCollectionRepository.from_dsn(settings.database_url)
    today = datetime.now(UTC).date()
    control = CollectionControl(
        repository=repository,
        source_code="pncp",
        endpoint_code="registry-api",
        idempotency_key=build_execution_idempotency_key("pncp-municipal-link-evidence"),
        collector_version=PNCP_COLLECTOR_VERSION,
        parser_version="pncp-municipal-link/1.0.0",
        partition_key=f"municipal-link:{CONTRACT}",
        period_start=today,
        period_end=today,
    )

    def operation():
        service = PncpRegistryPersistenceService(
            object_store=build_authenticated_object_store(settings),
            repository=repository,
        )
        return collect_pair(service=service)

    summary = execute_controlled_pair(control=control, operation=operation)
    print(
        json.dumps(
            {
                "event": "pncp_municipal_link_preserved",
                "validated_artifacts": 2,
                "publication_authorized": summary["publication_authorized"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
