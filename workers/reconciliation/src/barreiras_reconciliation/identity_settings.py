"""Configuração fail-closed do workload privado de identidades."""

from __future__ import annotations

import base64
import binascii
import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

PRODUCTION_SSL_ROOT_CERTIFICATE = "config/certificates/supabase-prod-ca-2021.crt"
_KEY_BYTES = 32


@dataclass(frozen=True, slots=True)
class IdentitySettings:
    database_url: str = field(repr=False)
    database_role: str
    encryption_key: bytes = field(repr=False)
    fingerprint_key: bytes = field(repr=False)
    key_version: int

    @classmethod
    def from_env(cls, environment: Mapping[str, str]) -> IdentitySettings:
        database_url = _required(environment, "IDENTITY_DATABASE_URL")
        parsed = urlparse(database_url)
        if (
            parsed.scheme not in {"postgres", "postgresql"}
            or not parsed.hostname
            or not parsed.username
            or not parsed.password
        ):
            raise ValueError("IDENTITY_DATABASE_URL não é uma URL PostgreSQL.")
        database_role = parsed.username.split(".", maxsplit=1)[0]
        if database_role != "identity_registry":
            raise ValueError("IDENTITY_DATABASE_URL deve usar identity_registry.")

        local_database = parsed.hostname in {"127.0.0.1", "localhost"}
        query = parse_qs(parsed.query)
        if not local_database and (
            query.get("sslmode", [None])[0] != "verify-full"
            or query.get("sslrootcert", [None])[0]
            != PRODUCTION_SSL_ROOT_CERTIFICATE
        ):
            raise ValueError(
                "IDENTITY_DATABASE_URL remota deve usar sslmode=verify-full "
                "e a CA oficial versionada."
            )

        encryption_key = _decode_key(environment, "IDENTITY_AES_KEY_B64")
        fingerprint_key = _decode_key(environment, "IDENTITY_HMAC_KEY_B64")
        if hmac.compare_digest(encryption_key, fingerprint_key):
            raise ValueError("As chaves AES e HMAC devem ser distintas.")
        try:
            key_version = int(_required(environment, "IDENTITY_KEY_VERSION"))
        except ValueError as error:
            raise ValueError("IDENTITY_KEY_VERSION deve ser inteiro.") from error
        if key_version < 1:
            raise ValueError("IDENTITY_KEY_VERSION deve ser positiva.")

        return cls(
            database_url=database_url,
            database_role=database_role,
            encryption_key=encryption_key,
            fingerprint_key=fingerprint_key,
            key_version=key_version,
        )


def _decode_key(environment: Mapping[str, str], name: str) -> bytes:
    encoded = _required(environment, name)
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"{name} deve usar Base64 válido.") from error
    if len(decoded) != _KEY_BYTES:
        raise ValueError(f"{name} deve conter exatamente 32 bytes.")
    return decoded


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} é obrigatória.")
    return value
