from __future__ import annotations

import hashlib
import unittest

from barreiras_reconciliation.private_identifiers import (
    InvalidCpfError,
    PrivateIdentifierCipher,
    normalize_cpf,
)

CPF_FIXTURE = "529982247" + "25"


class PrivateIdentifierCipherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.encryption_key = bytes(range(32))
        self.fingerprint_key = bytes(range(32, 64))
        self.cipher = PrivateIdentifierCipher(
            encryption_key=self.encryption_key,
            fingerprint_key=self.fingerprint_key,
            key_version=1,
        )

    def test_normalizes_and_validates_an_official_cpf(self) -> None:
        self.assertEqual(normalize_cpf("529.982.247-" + "25"), CPF_FIXTURE)

    def test_rejects_invalid_or_repeated_cpf_digits(self) -> None:
        for value in ("529.982.247-" + "24", "1" * 11, "123"):
            with self.subTest(value=value), self.assertRaises(InvalidCpfError):
                normalize_cpf(value)

    def test_encrypts_with_aes_256_gcm_and_keeps_only_last_four_visible(self) -> None:
        protected = self.cipher.protect(
            "529.982.247-" + "25",
            person_context="tse:2024:123456789012",
            nonce=bytes(range(12)),
        )

        self.assertEqual(len(protected.encrypted_value), 11)
        self.assertEqual(len(protected.nonce), 12)
        self.assertEqual(len(protected.authentication_tag), 16)
        self.assertEqual(protected.last_four, "4725")
        self.assertEqual(protected.key_version, 1)
        self.assertNotIn(CPF_FIXTURE.encode("ascii"), protected.encrypted_value)
        self.assertEqual(
            self.cipher.reveal(
                protected,
                person_context="tse:2024:123456789012",
            ),
            CPF_FIXTURE,
        )

    def test_fingerprint_is_deterministic_but_uses_a_separate_key(self) -> None:
        first = self.cipher.protect(
            CPF_FIXTURE,
            person_context="tse:2024:1",
            nonce=bytes(range(12)),
        )
        second = self.cipher.protect(
            CPF_FIXTURE,
            person_context="tse:2024:2",
            nonce=bytes(range(12, 24)),
        )
        other_key = PrivateIdentifierCipher(
            encryption_key=self.encryption_key,
            fingerprint_key=b"x" * 32,
            key_version=1,
        ).protect(
            CPF_FIXTURE,
            person_context="tse:2024:1",
            nonce=bytes(range(12)),
        )

        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertNotEqual(first.fingerprint, other_key.fingerprint)
        self.assertRegex(first.fingerprint, r"^[0-9a-f]{64}$")

    def test_authenticated_context_prevents_reuse_for_another_person(
        self,
    ) -> None:
        protected = self.cipher.protect(
            CPF_FIXTURE,
            person_context="tse:2024:1",
            nonce=bytes(range(12)),
        )

        with self.assertRaises(ValueError):
            self.cipher.reveal(protected, person_context="tse:2024:2")

    def test_encrypts_the_exact_official_source_payload_separately(self) -> None:
        payload = (
            b'{"nr_cpf_candidato":"'
            + CPF_FIXTURE.encode("ascii")
            + b'","sq_candidato":"123"}'
        )
        protected = self.cipher.protect_payload(
            payload,
            evidence_context="tse-candidate-registry:2024:123",
            nonce=bytes(range(12)),
        )

        self.assertEqual(
            protected.payload_sha256,
            hashlib.sha256(payload).hexdigest(),
        )
        self.assertNotIn(CPF_FIXTURE.encode("ascii"), protected.encrypted_payload)
        self.assertEqual(
            self.cipher.reveal_payload(
                protected,
                evidence_context="tse-candidate-registry:2024:123",
            ),
            payload,
        )


if __name__ == "__main__":
    unittest.main()
