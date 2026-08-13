"""Proteção de identificadores pessoais usados somente na reconciliação.

O CPF nunca sai deste limite em texto simples. A cifra usa AES-256-GCM e a
comparação determinística usa HMAC-SHA-256 com uma chave independente.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_CPF_DIGITS = re.compile(r"\D+")
_AES_KEY_BYTES = 32
_NONCE_BYTES = 12
_TAG_BYTES = 16


class InvalidCpfError(ValueError):
    """O valor não representa um CPF estruturalmente válido."""


@dataclass(frozen=True, slots=True)
class ProtectedIdentifier:
    encrypted_value: bytes
    nonce: bytes
    authentication_tag: bytes
    fingerprint: str
    last_four: str
    key_version: int


@dataclass(frozen=True, slots=True)
class ProtectedSourcePayload:
    encrypted_payload: bytes
    nonce: bytes
    authentication_tag: bytes
    payload_sha256: str
    key_version: int


def normalize_cpf(value: str) -> str:
    digits = _CPF_DIGITS.sub("", value)
    if len(digits) != 11 or len(set(digits)) == 1:
        raise InvalidCpfError("CPF inválido.")

    def check_digit(prefix: str) -> str:
        weight = len(prefix) + 1
        total = sum(int(digit) * (weight - index) for index, digit in enumerate(prefix))
        remainder = (total * 10) % 11
        return "0" if remainder == 10 else str(remainder)

    if check_digit(digits[:9]) != digits[9] or check_digit(digits[:10]) != digits[10]:
        raise InvalidCpfError("CPF inválido.")
    return digits


class PrivateIdentifierCipher:
    def __init__(
        self,
        *,
        encryption_key: bytes,
        fingerprint_key: bytes,
        key_version: int,
    ) -> None:
        if len(encryption_key) != _AES_KEY_BYTES:
            raise ValueError("A chave AES deve ter 32 bytes.")
        if len(fingerprint_key) < _AES_KEY_BYTES:
            raise ValueError("A chave HMAC deve ter ao menos 32 bytes.")
        if hmac.compare_digest(encryption_key, fingerprint_key):
            raise ValueError("As chaves de cifra e HMAC devem ser distintas.")
        if key_version < 1:
            raise ValueError("A versão da chave deve ser positiva.")
        self._aesgcm = AESGCM(encryption_key)
        self._fingerprint_key = fingerprint_key
        self._key_version = key_version

    def protect(
        self,
        cpf: str,
        *,
        person_context: str,
        nonce: bytes | None = None,
    ) -> ProtectedIdentifier:
        normalized = normalize_cpf(cpf)
        active_nonce = nonce if nonce is not None else os.urandom(_NONCE_BYTES)
        if len(active_nonce) != _NONCE_BYTES:
            raise ValueError("O nonce AES-GCM deve ter 12 bytes.")
        aad = self._associated_data(person_context)
        ciphertext_and_tag = self._aesgcm.encrypt(
            active_nonce,
            normalized.encode("ascii"),
            aad,
        )
        return ProtectedIdentifier(
            encrypted_value=ciphertext_and_tag[:-_TAG_BYTES],
            nonce=active_nonce,
            authentication_tag=ciphertext_and_tag[-_TAG_BYTES:],
            fingerprint=hmac.new(
                self._fingerprint_key,
                normalized.encode("ascii"),
                hashlib.sha256,
            ).hexdigest(),
            last_four=normalized[-4:],
            key_version=self._key_version,
        )

    def reveal(
        self,
        protected: ProtectedIdentifier,
        *,
        person_context: str,
    ) -> str:
        try:
            plaintext = self._aesgcm.decrypt(
                protected.nonce,
                protected.encrypted_value + protected.authentication_tag,
                self._associated_data(person_context),
            )
        except InvalidTag as error:
            raise ValueError("Identificador ou contexto não autenticado.") from error
        return plaintext.decode("ascii")

    def protect_payload(
        self,
        payload: bytes,
        *,
        evidence_context: str,
        nonce: bytes | None = None,
    ) -> ProtectedSourcePayload:
        if not payload:
            raise ValueError("A evidência oficial não pode estar vazia.")
        active_nonce = nonce if nonce is not None else os.urandom(_NONCE_BYTES)
        if len(active_nonce) != _NONCE_BYTES:
            raise ValueError("O nonce AES-GCM deve ter 12 bytes.")
        encrypted = self._aesgcm.encrypt(
            active_nonce,
            payload,
            self._evidence_associated_data(evidence_context),
        )
        return ProtectedSourcePayload(
            encrypted_payload=encrypted[:-_TAG_BYTES],
            nonce=active_nonce,
            authentication_tag=encrypted[-_TAG_BYTES:],
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            key_version=self._key_version,
        )

    def reveal_payload(
        self,
        protected: ProtectedSourcePayload,
        *,
        evidence_context: str,
    ) -> bytes:
        try:
            return self._aesgcm.decrypt(
                protected.nonce,
                protected.encrypted_payload + protected.authentication_tag,
                self._evidence_associated_data(evidence_context),
            )
        except InvalidTag as error:
            raise ValueError("Evidência ou contexto não autenticado.") from error

    def _associated_data(self, person_context: str) -> bytes:
        normalized_context = person_context.strip()
        if not normalized_context:
            raise ValueError("O contexto da pessoa é obrigatório.")
        return f"barreiras360:cpf:v{self._key_version}:{normalized_context}".encode()

    def _evidence_associated_data(self, evidence_context: str) -> bytes:
        normalized_context = evidence_context.strip()
        if not normalized_context:
            raise ValueError("O contexto da evidência é obrigatório.")
        return (
            f"barreiras360:identifier-source:v{self._key_version}:{normalized_context}"
        ).encode()
