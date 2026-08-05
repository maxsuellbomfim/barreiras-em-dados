"""Infraestrutura comum dos comandos PNCP executados em nuvem."""

from __future__ import annotations

from collections.abc import Mapping

from ..persistence.storage import SupabaseStorageObjectStore
from ..settings import PersistenceSettings


def resolve_checkpoint_offset(
    checkpoint: Mapping[str, object] | None,
) -> int:
    """Aceita somente cursor inteiro não negativo; checkpoint ruim reinicia."""
    value = checkpoint.get("next_offset") if checkpoint else None
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def build_authenticated_object_store(
    settings: PersistenceSettings,
) -> SupabaseStorageObjectStore:
    """Autentica a identidade técnica e devolve o bucket bruto do PNCP."""
    required = (
        settings.supabase_url,
        settings.supabase_publishable_key,
        settings.supabase_workload_email,
        settings.supabase_workload_password,
        settings.raw_artifacts_bucket,
    )
    if any(value is None for value in required):
        raise RuntimeError("Configuração de nuvem incompleta.")
    try:
        from supabase import create_client
    except ImportError as error:
        raise RuntimeError(
            "Instale a dependência opcional 'storage' para coletar."
        ) from error

    client = create_client(settings.supabase_url, settings.supabase_publishable_key)
    try:
        authentication = client.auth.sign_in_with_password(
            {
                "email": settings.supabase_workload_email,
                "password": settings.supabase_workload_password,
            }
        )
    except Exception as error:
        raise RuntimeError(
            "Falha ao autenticar a identidade técnica do Storage."
        ) from error
    if authentication.session is None or authentication.user is None:
        raise RuntimeError("O Storage não forneceu uma sessão autenticada.")
    return SupabaseStorageObjectStore(
        client.storage.from_(settings.raw_artifacts_bucket)
    )
