"""Coleta direta das edições do Diário Oficial de Barreiras por número.

O cursor caminha para frente a partir da última edição conhecida no banco.
"Edição seguinte não existe" (404 nos anos candidatos) é o fim explícito da
janela, nunca uma falha; qualquer outro erro interrompe com exceção.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from ..logging import log_event
from .gazette_documents import CollectedDocument, GazetteDocumentClient
from .official_diary_catalog import ALLOWED_HOSTS as CATALOG_ALLOWED_HOSTS
from .querido_diario import PermanentHttpError

SOURCE_CODE = "barreiras-diario-oficial"
ENDPOINT_CODE = "pdf-direto"
DIRECT_DIARY_ALLOWED_HOSTS = CATALOG_ALLOWED_HOSTS | frozenset(
    {"barreiras.ba.gov.br", "www.barreiras.ba.gov.br"}
)


class EditionNotFoundError(RuntimeError):
    """A edição não existe nos anos candidatos: fim da janela do cursor."""


@dataclass(frozen=True)
class DirectEdition:
    edition_number: int
    year: int
    document: CollectedDocument


@dataclass(frozen=True)
class DirectEditionTarget:
    """Edição que o catálogo oficial afirma existir, com URL verificável."""

    edition_number: int
    year: int
    publication_url: str


def edition_url(year: int, edition_number: int) -> str:
    return (
        "https://barreiras.ba.gov.br/diario/pdf/"
        f"{year}/diario{edition_number}.pdf"
    )


def fetch_edition(
    client: GazetteDocumentClient,
    edition_number: int,
    *,
    today: date,
) -> DirectEdition:
    """Tenta o ano corrente e o anterior (virada de ano) antes de desistir."""
    last_error: PermanentHttpError | None = None
    for year in (today.year, today.year - 1):
        try:
            document = client.fetch(
                edition_url(year, edition_number),
                role="pdf",
            )
            return DirectEdition(
                edition_number=edition_number,
                year=year,
                document=document,
            )
        except PermanentHttpError as error:
            if error.status_code == 404:
                last_error = error
                continue
            raise
    raise EditionNotFoundError(
        f"Edição {edition_number} não encontrada nos anos candidatos."
    ) from last_error


def collect_editions(
    client: GazetteDocumentClient,
    persist: Callable[[DirectEdition], object],
    *,
    start_edition: int,
    limit: int,
    today: date,
    logger: logging.Logger,
) -> tuple[int, bool]:
    """Coleta edições sequenciais; devolve (persistidas, cursor_esgotado)."""
    persisted = 0
    for edition_number in range(start_edition, start_edition + limit):
        try:
            edition = fetch_edition(client, edition_number, today=today)
        except EditionNotFoundError:
            log_event(
                logger,
                logging.INFO,
                "collector_direct_diary_cursor_end",
                source=SOURCE_CODE,
                next_edition=edition_number,
                persisted=persisted,
            )
            return persisted, True
        persist(edition)
        persisted += 1
        log_event(
            logger,
            logging.INFO,
            "collector_direct_edition_persisted",
            source=SOURCE_CODE,
            edition=edition.edition_number,
            year=edition.year,
            artifact_hash=edition.document.body_sha256,
        )
    return persisted, False


def collect_catalog_editions(
    client: GazetteDocumentClient,
    persist: Callable[[DirectEdition], object],
    *,
    targets: tuple[DirectEditionTarget, ...],
    logger: logging.Logger,
) -> tuple[int, tuple[int, ...]]:
    """Preserva alvos explícitos sem deixar uma lacuna ocultar os seguintes."""
    persisted = 0
    unavailable: list[int] = []
    for target in targets:
        try:
            document = client.fetch(target.publication_url, role="pdf")
        except PermanentHttpError as error:
            if error.status_code != 404:
                raise
            unavailable.append(target.edition_number)
            log_event(
                logger,
                logging.WARNING,
                "collector_catalog_edition_unavailable",
                source=SOURCE_CODE,
                edition=target.edition_number,
                year=target.year,
                status=error.status_code,
            )
            continue
        edition = DirectEdition(
            edition_number=target.edition_number,
            year=target.year,
            document=document,
        )
        persist(edition)
        persisted += 1
        log_event(
            logger,
            logging.INFO,
            "collector_direct_edition_persisted",
            source=SOURCE_CODE,
            edition=edition.edition_number,
            year=edition.year,
            artifact_hash=edition.document.body_sha256,
            discovery="official-catalog",
        )
    return persisted, tuple(unavailable)
