"""Mede, sem persistir datas, a geometria das emissões ausentes TCM-BA."""

from __future__ import annotations

import argparse
import hashlib
import logging
from collections.abc import Sequence

from barreiras_collectors.logging import log_event
from barreiras_collectors.persistence.storage import SupabaseStorageObjectStore
from barreiras_collectors.settings import CollectorSettings, PersistenceSettings

from ..pdf_layout import derive_pdf_layout
from ..private_logging import configure_private_logging
from ..processing import ArtifactMismatchError, ObjectReader, TextArtifact
from ..tcm_ba_commitment_date_diagnostic import (
    TcmBaIssueDateLayoutBenchmark,
    benchmark_issue_date_layout,
    benchmark_payload,
)
from ..tcm_ba_commitment_repository import TcmBaCommitmentExtractionRepository


def benchmark_exit_code(
    benchmark: TcmBaIssueDateLayoutBenchmark,
    *,
    expected_candidates: int,
) -> int:
    return int(
        not benchmark.complete or benchmark.missing_candidates != expected_candidates
    )


def verified_layout_loader(object_reader: ObjectReader):
    def load(artifact: TextArtifact):
        raw_body = object_reader.read(artifact.object_key)
        if hashlib.sha256(raw_body).hexdigest() != artifact.sha256:
            raise ArtifactMismatchError(
                "O PDF restaurado diverge do hash registrado do artefato."
            )
        return derive_pdf_layout(raw_body)

    return load


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Produz somente contagens agregadas do layout de datas ausentes, "
            "sem persistir ou registrar datas."
        )
    )
    parser.add_argument("--limit", type=int, default=500)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.limit <= 500:
        parser.error("--limit deve estar entre 1 e 500.")

    collector_settings = CollectorSettings.from_env()
    persistence = PersistenceSettings.from_env()
    configure_private_logging(collector_settings.log_level)
    if persistence.mode != "postgres-supabase":
        raise RuntimeError("O benchmark de datas requer Storage autenticado.")
    if (
        persistence.database_url is None
        or persistence.supabase_url is None
        or persistence.supabase_publishable_key is None
        or persistence.supabase_workload_email is None
        or persistence.supabase_workload_password is None
        or persistence.raw_artifacts_bucket is None
    ):
        raise RuntimeError("Configuração de nuvem incompleta.")
    try:
        from supabase import create_client
    except ImportError as error:
        raise RuntimeError(
            "Instale a dependência opcional 'storage' para ler os PDFs."
        ) from error

    client = create_client(
        persistence.supabase_url,
        persistence.supabase_publishable_key,
    )
    try:
        authentication = client.auth.sign_in_with_password(
            {
                "email": persistence.supabase_workload_email,
                "password": persistence.supabase_workload_password,
            }
        )
    except Exception as error:
        raise RuntimeError(
            "Falha ao autenticar a identidade técnica do Storage."
        ) from error
    if authentication.session is None or authentication.user is None:
        raise RuntimeError("O Storage não forneceu uma sessão autenticada.")

    repository = TcmBaCommitmentExtractionRepository.from_dsn(persistence.database_url)
    targets = repository.issue_date_layout_targets(limit=arguments.limit)
    breakdown = repository.commitment_missing_field_breakdown()
    object_reader = SupabaseStorageObjectStore(
        client.storage.from_(persistence.raw_artifacts_bucket)
    )
    benchmark = benchmark_issue_date_layout(
        targets,
        layout_loader=verified_layout_loader(object_reader),
    )
    exit_code = benchmark_exit_code(
        benchmark,
        expected_candidates=breakdown.missing_issue_date,
    )
    payload = benchmark_payload(benchmark)
    payload["expected_candidates"] = breakdown.missing_issue_date
    payload["gate"] = "PASS" if exit_code == 0 else "BLOCK"
    log_event(
        logging.getLogger(__name__),
        logging.INFO if exit_code == 0 else logging.ERROR,
        "tcm_ba_commitment_issue_date_layout_benchmark",
        **payload,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())