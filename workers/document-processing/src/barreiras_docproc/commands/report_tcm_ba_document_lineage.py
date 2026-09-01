"""Relata a linhagem oficial de um PDF TCM-BA pelo hash preservado."""

from __future__ import annotations

import argparse
import logging
import re
from collections.abc import Sequence
from typing import Protocol

from barreiras_collectors.logging import log_event
from barreiras_collectors.settings import CollectorSettings, PostgresSettings

from ..tcm_ba_document_families import TcmBaDocumentLineage
from ..tcm_ba_document_family_repository import (
    TcmBaDocumentFamilyExtractionRepository,
)


class LineageRepository(Protocol):
    def document_lineage_by_sha256(
        self,
        artifact_sha256: str,
    ) -> tuple[TcmBaDocumentLineage, ...]: ...


def main(
    argv: Sequence[str] | None = None,
    *,
    repository: LineageRepository | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Localiza a competência e a categoria oficial de um PDF TCM-BA."
    )
    parser.add_argument("--sha256", required=True)
    arguments = parser.parse_args(argv)
    artifact_sha256 = arguments.sha256.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", artifact_sha256):
        parser.error("--sha256 deve conter 64 caracteres hexadecimais.")

    collector_settings = CollectorSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    active_repository = repository
    if active_repository is None:
        postgres = PostgresSettings.from_env()
        active_repository = TcmBaDocumentFamilyExtractionRepository.from_dsn(
            postgres.database_url
        )
    rows = active_repository.document_lineage_by_sha256(artifact_sha256)
    logger = logging.getLogger(__name__)
    if not rows:
        log_event(
            logger,
            logging.ERROR,
            "tcm_ba_document_lineage_not_found",
            artifact_sha256=artifact_sha256,
            matches=0,
            gate="BLOCK",
        )
        return 1
    for row in rows:
        log_event(
            logger,
            logging.INFO,
            "tcm_ba_document_lineage_found",
            artifact_sha256=row.artifact_sha256,
            artifact_id=row.artifact_id,
            object_key=row.object_key,
            source_record_key=row.source_record_key,
            competence=row.competence,
            official_category=row.official_category,
            official_category_code=row.official_category_code,
            family=row.family,
            document_name=row.document_name,
            matches=len(rows),
            gate="PASS",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
