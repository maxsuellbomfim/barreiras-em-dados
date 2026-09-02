"""Importação fail-closed de identificadores oficiais do TSE."""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from .identity_repository import (
    IdentifierGapRegistration,
    IdentityRegistration,
    IdentityTarget,
)
from .private_identifiers import PrivateIdentifierCipher
from .tse_candidate_registry import (
    candidates_from_registry,
    extract_bahia_registry,
    source_url,
)

PARSER_VERSION = "tse-candidate-registry/1.2.0"


class IdentityImportError(RuntimeError):
    """O lote não pode ser persistido com segurança."""


class IdentityRepositoryProtocol(Protocol):
    def eligible_targets(self, election_year: int) -> tuple[IdentityTarget, ...]: ...

    def register(self, registration: IdentityRegistration) -> str: ...

    def register_unavailable(self, registration: IdentifierGapRegistration) -> str: ...


@dataclass(frozen=True, slots=True)
class IdentityImportSummary:
    election_year: int
    selected: int
    inserted: int
    unchanged: int
    conflicted: int
    unavailable: int


class IdentityImportService:
    def __init__(
        self,
        *,
        repository: IdentityRepositoryProtocol,
        cipher: PrivateIdentifierCipher,
    ) -> None:
        self.repository = repository
        self.cipher = cipher

    def import_package(self, *, year: int, package: bytes) -> IdentityImportSummary:
        targets = self.repository.eligible_targets(year)
        return self.import_package_for_targets(
            year=year,
            package=package,
            targets=targets,
        )

    def import_package_for_targets(
        self,
        *,
        year: int,
        package: bytes,
        targets: tuple[IdentityTarget, ...],
    ) -> IdentityImportSummary:
        if not targets:
            raise IdentityImportError(
                f"O recorte de {year} não contém nenhuma identidade aprovada."
            )
        state_csv = extract_bahia_registry(package, year)
        candidate_ids = {target.candidate_id for target in targets}
        identities = candidates_from_registry(
            state_csv,
            year=year,
            approved_candidate_ids=candidate_ids,
        )
        by_candidate = {identity.candidate_id: identity for identity in identities}
        missing = sorted(candidate_ids - by_candidate.keys())
        if missing:
            raise IdentityImportError(
                f"A fonte oficial não retornou {len(missing)} candidatura(s) "
                "do recorte aprovado; nenhuma identidade foi gravada."
            )

        archive_sha256 = hashlib.sha256(package).hexdigest()
        state_file_sha256 = hashlib.sha256(state_csv).hexdigest()
        counts = {"inserted": 0, "unchanged": 0, "conflicted": 0}
        unavailable = 0
        for target in targets:
            identity = by_candidate[target.candidate_id]
            evidence_context = f"tse-candidate-registry:{year}:{target.candidate_id}"
            protected_source = self.cipher.protect_payload(
                identity.private_source_payload,
                evidence_context=evidence_context,
            )
            if identity.cpf is None:
                self.repository.register_unavailable(
                    IdentifierGapRegistration(
                        target=target,
                        source_record_key=f"candidate:{year}:{target.candidate_id}",
                        source_url=source_url(year),
                        archive_sha256=archive_sha256,
                        state_file_sha256=state_file_sha256,
                        parser_version=PARSER_VERSION,
                        reason=identity.identifier_issue or "invalid_official_value",
                        protected_source=protected_source,
                    )
                )
                unavailable += 1
                continue
            person_context = f"tse:{year}:{target.candidate_id}"
            registration = IdentityRegistration(
                target=target,
                source_record_key=f"candidate:{year}:{target.candidate_id}",
                source_url=source_url(year),
                archive_sha256=archive_sha256,
                state_file_sha256=state_file_sha256,
                parser_version=PARSER_VERSION,
                display_name=identity.civil_name,
                normalized_name=_normalize_name(identity.civil_name),
                ballot_name=identity.ballot_name,
                protected_identifier=self.cipher.protect(
                    identity.cpf,
                    person_context=person_context,
                ),
                protected_source=protected_source,
            )
            status = self.repository.register(registration)
            counts[status] += 1

        return IdentityImportSummary(
            election_year=year,
            selected=len(targets),
            inserted=counts["inserted"],
            unchanged=counts["unchanged"],
            conflicted=counts["conflicted"],
            unavailable=unavailable,
        )


def _normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_name = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(ascii_name.casefold().split())
