"""Registra identidades políticas privadas a partir do cadastro oficial do TSE."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable

from ..identity_import import IdentityImportError, IdentityImportService
from ..identity_repository import IdentityRepository
from ..identity_settings import IdentitySettings
from ..private_identifiers import PrivateIdentifierCipher
from ..tse_registry_fetch import fetch_candidate_registry


def import_identity_year(
    *,
    year: int,
    repository: IdentityRepository,
    service: IdentityImportService,
    fetcher: Callable[[int], bytes] = fetch_candidate_registry,
    refresh: bool = False,
) -> dict[str, object]:
    targets = repository.eligible_targets(year)
    if not targets:
        raise IdentityImportError(
            f"O recorte de {year} não contém nenhuma identidade aprovada."
        )
    evidenced = repository.evidenced_candidate_ids(year)
    pending = {target.candidate_id for target in targets} - evidenced
    if not refresh and not pending:
        return {
            "event": "private_identity_import_skipped",
            "election_year": year,
            "selected": len(targets),
            "pending": 0,
            "evidence_coverage_complete": True,
            "requires_review": False,
            "reason": "all_eligible_candidates_evidenced",
        }

    summary = service.import_package_for_targets(
        year=year,
        package=fetcher(year),
        targets=targets,
    )
    return {
        "event": "private_identity_import",
        "election_year": summary.election_year,
        "selected": summary.selected,
        "pending_before_download": len(pending),
        "inserted": summary.inserted,
        "unchanged": summary.unchanged,
        "conflicted": summary.conflicted,
        "unavailable": summary.unavailable,
        "evidence_coverage_complete": True,
        "coverage_complete": summary.unavailable == 0,
        "requires_review": summary.conflicted > 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--year",
        action="append",
        dest="years",
        type=int,
        required=True,
        help="Ano eleitoral oficial a importar; pode ser repetido.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "Força nova leitura do arquivo oficial mesmo quando todas as "
            "candidaturas elegíveis já possuem evidência privada."
        ),
    )
    args = parser.parse_args(argv)
    settings = IdentitySettings.from_env(os.environ)
    repository = IdentityRepository.from_dsn(settings.database_url)
    service = IdentityImportService(
        repository=repository,
        cipher=PrivateIdentifierCipher(
            encryption_key=settings.encryption_key,
            fingerprint_key=settings.fingerprint_key,
            key_version=settings.key_version,
        ),
    )

    requires_review = False
    for year in sorted(set(args.years)):
        event = import_identity_year(
            year=year,
            repository=repository,
            service=service,
            refresh=args.refresh,
        )
        requires_review = requires_review or bool(event["requires_review"])
        print(json.dumps(event, sort_keys=True))
    if requires_review:
        print(
            json.dumps(
                {
                    "event": "private_identity_review_required",
                    "message": "Há conflitos de identidade para revisão restrita.",
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
