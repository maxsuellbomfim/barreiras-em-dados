"""Votação nominal em Barreiras, do repositório de dados do TSE.

É esta fonte que dá o **vínculo territorial** do ADR 0014: quantos votos
cada candidatura recebeu no município. Sem esse número, chamar alguém de
"representante da região" seria opinião.

O pacote nacional pode ultrapassar 120 MiB e traz um CSV por UF. Baixamos
o pacote, extraímos só o arquivo da Bahia e preservamos como artefato o
**recorte de Barreiras** — a plataforma é municipal, e guardar o país
inteiro seria desproporcional. O hash do pacote e o do CSV estadual ficam
registrados no artefato, então qualquer pessoa reproduz o recorte a
partir da fonte oficial.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import time
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime

from ..http import HttpTransport, UrllibTransport
from ..logging import log_event
from ..resilience import RetryPolicy
from .pncp import PncpPage

SOURCE_CODE = "tse"
ENDPOINT_CODE = "votacao-munzona"
ALLOWED_HOSTS = frozenset({"cdn.tse.jus.br"})
RETRYABLE = frozenset({408, 425, 429, 500, 502, 503, 504})
# Código do município no cadastro do TSE (não é o código IBGE).
BARREIRAS_TSE_CODE = "33634"
STATE_CODE = "BA"
TIMEOUT_SECONDS = 120.0
# The 2022 national archive is currently about 556 MB. Keep headroom for
# normal growth while still bounding memory use for an intentionally large
# upstream response.
MAX_PACKAGE_BYTES = 640 * 1024 * 1024
PARSER_VERSION = "tse-votacao-munzona/1.0.0"

# Colunas exigidas: ausência é falha explícita, não coluna vazia.
REQUIRED_COLUMNS = (
    "ANO_ELEICAO",
    "CD_MUNICIPIO",
    "NM_MUNICIPIO",
    "DS_CARGO",
    "SQ_CANDIDATO",
    "NR_CANDIDATO",
    "NM_CANDIDATO",
    "NM_URNA_CANDIDATO",
    "SG_PARTIDO",
    "QT_VOTOS_NOMINAIS",
    "DS_SIT_TOT_TURNO",
    "NR_TURNO",
)


class TseError(RuntimeError):
    """Falha explícita ao consultar o repositório do TSE."""


def package_url(year: int) -> str:
    return (
        "https://cdn.tse.jus.br/estatistica/sead/odsele/"
        f"votacao_candidato_munzona/votacao_candidato_munzona_{year}.zip"
    )


def extract_state_csv(package: bytes, year: int) -> bytes:
    """CSV da Bahia de dentro do pacote nacional."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(package))
    except zipfile.BadZipFile as error:
        raise TseError("O pacote do TSE não é um ZIP válido.") from error
    expected = f"votacao_candidato_munzona_{year}_{STATE_CODE}.csv"
    for name in archive.namelist():
        if name.upper().endswith(expected.upper()):
            return archive.read(name)
    raise TseError(
        f"O pacote de {year} não contém o arquivo da Bahia ({expected})."
    )


def rows_for_barreiras(state_csv: bytes) -> tuple[list[dict], int]:
    """Linhas do município e o total lido, para conferência."""
    text = io.StringIO(state_csv.decode("latin-1"))
    reader = csv.reader(text, delimiter=";")
    try:
        header = next(reader)
    except StopIteration as error:
        raise TseError("O CSV estadual do TSE está vazio.") from error
    index = {column: position for position, column in enumerate(header)}
    missing = [
        column for column in REQUIRED_COLUMNS if column not in index
    ]
    if missing:
        raise TseError(
            f"O layout do TSE mudou: faltam as colunas {missing}."
        )

    found: list[dict] = []
    total = 0
    for row in reader:
        total += 1
        if len(row) <= index["CD_MUNICIPIO"]:
            continue
        if row[index["CD_MUNICIPIO"]].strip() != BARREIRAS_TSE_CODE:
            continue
        found.append(
            {column: row[index[column]].strip() for column in REQUIRED_COLUMNS}
        )
    if not found:
        raise TseError(
            "Nenhuma linha de Barreiras no CSV estadual: o código do "
            f"município ({BARREIRAS_TSE_CODE}) pode ter mudado."
        )
    return found, total


def aggregate_by_candidate(rows: list[dict]) -> list[dict]:
    """Soma os votos das zonas eleitorais por candidatura e turno.

    A fonte publica por zona; o número que interessa ao cidadão é o total
    no município. A soma é feita aqui, por código, nunca por nome.
    """
    grouped: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["SQ_CANDIDATO"], row["NR_TURNO"])
        votes = row["QT_VOTOS_NOMINAIS"]
        if not votes.lstrip("-").isdigit():
            raise TseError(
                f"Votos não numéricos para a candidatura {key[0]}: {votes!r}."
            )
        entry = grouped.get(key)
        if entry is None:
            grouped[key] = {
                "ano": row["ANO_ELEICAO"],
                "turno": row["NR_TURNO"],
                "cargo": row["DS_CARGO"],
                "sq_candidato": row["SQ_CANDIDATO"],
                "numero": row["NR_CANDIDATO"],
                "nome": row["NM_CANDIDATO"],
                "nome_urna": row["NM_URNA_CANDIDATO"],
                "partido": row["SG_PARTIDO"],
                "situacao": row["DS_SIT_TOT_TURNO"],
                "votos_em_barreiras": int(votes),
                "zonas": 1,
            }
            continue
        entry["votos_em_barreiras"] += int(votes)
        entry["zonas"] += 1
    return sorted(
        grouped.values(),
        key=lambda item: (-item["votos_em_barreiras"], item["nome"]),
    )


def fetch_votes(
    year: int,
    *,
    transport: HttpTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> PncpPage | None:
    """Votação de Barreiras num pleito, pronta para persistir."""
    url = package_url(year)
    active_transport = transport or UrllibTransport(ALLOWED_HOSTS)
    policy = retry_policy or RetryPolicy(max_attempts=3)
    log = logger or logging.getLogger(__name__)

    for attempt in range(1, policy.max_attempts + 1):
        requested_at = datetime.now(UTC).isoformat()
        response = active_transport.get(
            url,
            headers={
                "Accept": "application/zip",
                "User-Agent": "BarreirasEmDados-Collector/0.1",
            },
            timeout_seconds=TIMEOUT_SECONDS,
            max_body_bytes=MAX_PACKAGE_BYTES,
        )
        received_at = datetime.now(UTC).isoformat()
        log_event(
            log,
            logging.INFO,
            "collector_http_response",
            source=SOURCE_CODE,
            endpoint=ENDPOINT_CODE,
            status=response.status,
            attempt=attempt,
            body_size_bytes=len(response.body),
        )
        if response.status == 404:
            # Pleito ainda não publicado: fim explícito, não falha.
            return None
        if response.status == 200:
            state_csv = extract_state_csv(response.body, year)
            rows, total = rows_for_barreiras(state_csv)
            candidates = aggregate_by_candidate(rows)
            recorte = json.dumps(
                candidates,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            log_event(
                log,
                logging.INFO,
                "collector_tse_filtered",
                source=SOURCE_CODE,
                year=year,
                state_rows=total,
                barreiras_rows=len(rows),
                candidates=len(candidates),
            )
            return PncpPage(
                schema_name="tse-votacao-barreiras",
                schema_version="1.0.0",
                source_code=SOURCE_CODE,
                endpoint_code=ENDPOINT_CODE,
                idempotency_key=hashlib.sha256(
                    json.dumps(
                        {
                            "url": url,
                            "year": year,
                            "recorte_sha256": hashlib.sha256(
                                recorte
                            ).hexdigest(),
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
                request_url=url,
                final_url=response.final_url,
                requested_at=requested_at,
                received_at=received_at,
                attempts=attempt,
                http_status=response.status,
                collection_status="success",
                body_sha256=hashlib.sha256(recorte).hexdigest(),
                body_size_bytes=len(recorte),
                media_type="application/json",
                response_headers={
                    # Rastreabilidade até a fonte, sem guardar o país todo.
                    "x-package-sha256": hashlib.sha256(
                        response.body
                    ).hexdigest(),
                    "x-state-csv-sha256": hashlib.sha256(
                        state_csv
                    ).hexdigest(),
                },
                cursor={"offset": 0, "size": len(candidates), "ano": year},
                raw_body=recorte,
                window_start=None,
                window_end=None,
                items=tuple(candidates),
                total_paginas=1,
                total_registros=len(candidates),
            )
        if response.status not in RETRYABLE:
            raise TseError(f"O TSE respondeu HTTP {response.status}.")
        if attempt < policy.max_attempts:
            sleep(policy.delay(attempt, 1.0))

    raise TseError("O repositório do TSE ficou indisponível.")
