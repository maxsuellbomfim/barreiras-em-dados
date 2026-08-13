from __future__ import annotations

import hashlib
import unittest
from dataclasses import dataclass
from datetime import UTC, datetime

from barreiras_reconciliation.identity_import import (
    IdentityImportError,
    IdentityImportService,
)
from barreiras_reconciliation.identity_repository import IdentityTarget
from barreiras_reconciliation.private_identifiers import PrivateIdentifierCipher

from tests.reconciliation.test_tse_candidate_registry import registry_zip

CPF_FIXTURE = "52998224725"


@dataclass
class FakeRepository:
    targets: tuple[IdentityTarget, ...]
    registrations: list[object]

    def eligible_targets(self, election_year: int) -> tuple[IdentityTarget, ...]:
        return tuple(
            target for target in self.targets if target.election_year == election_year
        )

    def register(self, registration: object) -> str:
        self.registrations.append(registration)
        return "inserted"


def _target(candidate_id: str = "123") -> IdentityTarget:
    return IdentityTarget(
        source_kind="municipal",
        source_external_id="cm:vereador:123",
        election_year=2024,
        office="Vereador",
        candidate_id=candidate_id,
        origin_raw_record_id="00000000-0000-4000-8000-000000000001",
        source_collected_at=datetime(2026, 8, 13, tzinfo=UTC),
        votes_in_barreiras=321,
    )


def _package(candidate_id: str = "123") -> bytes:
    return registry_zip(
        [
            {
                "ANO_ELEICAO": "2024",
                "SG_UF": "BA",
                "DS_CARGO": "VEREADOR",
                "SQ_CANDIDATO": candidate_id,
                "NR_CPF_CANDIDATO": CPF_FIXTURE,
                "NM_CANDIDATO": "PESSOA TESTE",
                "NM_URNA_CANDIDATO": "PESSOA",
            }
        ]
    )


class IdentityImportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeRepository((_target(),), [])
        self.service = IdentityImportService(
            repository=self.repository,
            cipher=PrivateIdentifierCipher(
                encryption_key=bytes(range(32)),
                fingerprint_key=bytes(range(32, 64)),
                key_version=1,
            ),
        )

    def test_encrypts_exact_official_row_and_registers_without_plaintext_cpf(
        self,
    ) -> None:
        package = _package()

        summary = self.service.import_package(year=2024, package=package)

        self.assertEqual(summary.selected, 1)
        self.assertEqual(summary.inserted, 1)
        self.assertEqual(summary.conflicted, 0)
        registration = self.repository.registrations[0]
        self.assertEqual(
            registration.archive_sha256,
            hashlib.sha256(package).hexdigest(),
        )
        self.assertEqual(registration.target.candidate_id, "123")
        self.assertEqual(registration.protected_identifier.last_four, "4725")
        self.assertNotIn(CPF_FIXTURE, repr(registration))
        self.assertNotIn(
            CPF_FIXTURE.encode("ascii"),
            registration.protected_source.encrypted_payload,
        )

    def test_fails_closed_before_any_write_when_an_approved_target_is_missing(
        self,
    ) -> None:
        self.repository.targets = (_target("123"), _target("999"))

        with self.assertRaisesRegex(IdentityImportError, "1 candidatura"):
            self.service.import_package(year=2024, package=_package("123"))

        self.assertEqual(self.repository.registrations, [])

    def test_refuses_an_empty_scope_instead_of_reporting_false_success(self) -> None:
        self.repository.targets = ()

        with self.assertRaisesRegex(IdentityImportError, "nenhuma identidade"):
            self.service.import_package(year=2024, package=_package())


if __name__ == "__main__":
    unittest.main()
