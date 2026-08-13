"""Registra identidades políticas privadas a partir do cadastro oficial do TSE."""

from __future__ import annotations

import argparse
import json
import os

from ..identity_import import IdentityImportService
from ..identity_repository import IdentityRepository
from ..identity_settings import IdentitySettings
from ..private_identifiers import PrivateIdentifierCipher
from ..tse_registry_fetch import fetch_candidate_registry


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
        summary = service.import_package(
            year=year,
            package=fetch_candidate_registry(year),
        )
        requires_review = requires_review or summary.conflicted > 0
        print(
            json.dumps(
                {
                    "event": "private_identity_import",
                    "election_year": summary.election_year,
                    "selected": summary.selected,
                    "inserted": summary.inserted,
                    "unchanged": summary.unchanged,
                    "conflicted": summary.conflicted,
                    "unavailable": summary.unavailable,
                    "coverage_complete": summary.unavailable == 0,
                    "requires_review": summary.conflicted > 0,
                },
                sort_keys=True,
            )
        )
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
