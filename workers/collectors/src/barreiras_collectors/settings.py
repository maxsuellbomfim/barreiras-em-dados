"""Validação de ambiente sem carregar ou registrar segredos."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse


class EnvironmentValidationError(ValueError):
    """Uma variável está ausente, insegura ou fora dos limites aceitos."""


@dataclass(frozen=True)
class CollectorSettings:
    app_env: str
    querido_diario_base_url: str
    querido_diario_territory_id: str
    requests_per_minute: int
    connect_timeout_seconds: float
    read_timeout_seconds: float
    max_attempts: int

    @classmethod
    def from_env(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> CollectorSettings:
        values = environment if environment is not None else os.environ
        app_env = values.get("APP_ENV", "development")
        if app_env not in {"development", "test", "staging", "production"}:
            raise EnvironmentValidationError("APP_ENV inválido.")

        base_url = values.get(
            "QUERIDO_DIARIO_BASE_URL",
            "https://api.queridodiario.ok.org.br",
        ).rstrip("/")
        parsed = urlparse(base_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.queridodiario.ok.org.br"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise EnvironmentValidationError(
                "QUERIDO_DIARIO_BASE_URL deve usar o host HTTPS oficial."
            )

        territory_id = values.get("QUERIDO_DIARIO_TERRITORY_ID", "2903201")
        if territory_id != "2903201":
            raise EnvironmentValidationError(
                "O coletor municipal aceita apenas o território IBGE 2903201."
            )

        requests_per_minute = _bounded_int(
            values,
            "QUERIDO_DIARIO_REQUESTS_PER_MINUTE",
            default=30,
            minimum=1,
            maximum=60,
        )
        connect_timeout = _bounded_float(
            values,
            "HTTP_CONNECT_TIMEOUT_SECONDS",
            default=5,
            minimum=1,
            maximum=60,
        )
        read_timeout = _bounded_float(
            values,
            "HTTP_READ_TIMEOUT_SECONDS",
            default=30,
            minimum=1,
            maximum=300,
        )
        max_attempts = _bounded_int(
            values,
            "HTTP_MAX_ATTEMPTS",
            default=5,
            minimum=1,
            maximum=10,
        )

        for public_key in (
            "NEXT_PUBLIC_SUPABASE_SECRET_KEY",
            "NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY",
        ):
            if values.get(public_key):
                raise EnvironmentValidationError(
                    f"{public_key} nunca pode ser exposta ao frontend."
                )

        return cls(
            app_env=app_env,
            querido_diario_base_url=base_url,
            querido_diario_territory_id=territory_id,
            requests_per_minute=requests_per_minute,
            connect_timeout_seconds=connect_timeout,
            read_timeout_seconds=read_timeout,
            max_attempts=max_attempts,
        )


@dataclass(frozen=True)
class PersistenceSettings:
    mode: str
    local_data_directory: Path | None
    database_url: str | None
    supabase_url: str | None
    supabase_secret_key: str | None
    raw_artifacts_bucket: str | None

    @classmethod
    def from_env(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> PersistenceSettings:
        values = environment if environment is not None else os.environ
        collector = CollectorSettings.from_env(values)
        mode = values.get("PERSISTENCE_MODE", "filesystem").strip()
        if mode not in {"filesystem", "postgres-supabase"}:
            raise EnvironmentValidationError(
                "PERSISTENCE_MODE deve ser filesystem ou postgres-supabase."
            )
        if mode == "filesystem":
            if collector.app_env not in {"development", "test"}:
                raise EnvironmentValidationError(
                    "Persistência em filesystem é permitida apenas em development/test."
                )
            raw_directory = values.get(
                "LOCAL_DATA_DIRECTORY",
                "data/local-evidence",
            ).strip()
            local_directory = Path(raw_directory)
            if (
                not raw_directory
                or local_directory.is_absolute()
                or any(part in {"", ".", ".."} for part in local_directory.parts)
            ):
                raise EnvironmentValidationError(
                    "LOCAL_DATA_DIRECTORY deve ser um caminho relativo seguro."
                )
            return cls(
                mode=mode,
                local_data_directory=local_directory,
                database_url=None,
                supabase_url=None,
                supabase_secret_key=None,
                raw_artifacts_bucket=None,
            )

        database_url = _required(values, "DATABASE_URL")
        supabase_url = _required(values, "SUPABASE_URL").rstrip("/")
        secret_key = _required(values, "SUPABASE_SECRET_KEY")
        bucket = values.get("SUPABASE_RAW_ARTIFACTS_BUCKET", "raw-artifacts")
        if bucket != "raw-artifacts":
            raise EnvironmentValidationError(
                "SUPABASE_RAW_ARTIFACTS_BUCKET deve ser raw-artifacts."
            )

        parsed_database = urlparse(database_url)
        if (
            parsed_database.scheme not in {"postgres", "postgresql"}
            or not parsed_database.hostname
            or not parsed_database.username
        ):
            raise EnvironmentValidationError("DATABASE_URL não é uma URL PostgreSQL.")

        local_database = parsed_database.hostname in {"127.0.0.1", "localhost"}
        database_query = parse_qs(parsed_database.query)
        ssl_mode = database_query.get("sslmode", [None])[0]
        if not local_database and ssl_mode not in {
            "require",
            "verify-ca",
            "verify-full",
        }:
            raise EnvironmentValidationError(
                "DATABASE_URL remota deve exigir TLS por sslmode."
            )
        if (
            collector.app_env in {"staging", "production"}
            and parsed_database.username == "postgres"
        ):
            raise EnvironmentValidationError(
                "DATABASE_URL deve usar login dedicado do worker."
            )

        parsed_supabase = urlparse(supabase_url)
        local_supabase = parsed_supabase.hostname in {"127.0.0.1", "localhost"}
        local_allowed = collector.app_env in {"development", "test"}
        if (
            not parsed_supabase.hostname
            or parsed_supabase.username
            or parsed_supabase.password
            or parsed_supabase.query
            or parsed_supabase.fragment
            or parsed_supabase.path not in {"", "/"}
            or (
                parsed_supabase.scheme != "https"
                and not (
                    local_allowed
                    and local_supabase
                    and parsed_supabase.scheme == "http"
                )
            )
        ):
            raise EnvironmentValidationError("SUPABASE_URL inválida ou insegura.")

        is_new_secret = secret_key.startswith("sb_secret_")
        is_legacy_jwt = secret_key.count(".") == 2
        if (
            len(secret_key) < 24
            or any(character.isspace() for character in secret_key)
            or not (is_new_secret or is_legacy_jwt)
        ):
            raise EnvironmentValidationError(
                "SUPABASE_SECRET_KEY não possui formato de chave server-side."
            )

        return cls(
            mode=mode,
            local_data_directory=None,
            database_url=database_url,
            supabase_url=supabase_url,
            supabase_secret_key=secret_key,
            raw_artifacts_bucket=bucket,
        )


def _bounded_int(
    values: Mapping[str, str],
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(values.get(name, str(default)))
    except ValueError as error:
        raise EnvironmentValidationError(f"{name} deve ser inteiro.") from error
    if not minimum <= parsed <= maximum:
        raise EnvironmentValidationError(
            f"{name} deve estar entre {minimum} e {maximum}."
        )
    return parsed


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise EnvironmentValidationError(f"{name} é obrigatória.")
    return value


def _bounded_float(
    values: Mapping[str, str],
    name: str,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        parsed = float(values.get(name, str(default)))
    except ValueError as error:
        raise EnvironmentValidationError(f"{name} deve ser numérica.") from error
    if not minimum <= parsed <= maximum:
        raise EnvironmentValidationError(
            f"{name} deve estar entre {minimum:g} e {maximum:g}."
        )
    return parsed
