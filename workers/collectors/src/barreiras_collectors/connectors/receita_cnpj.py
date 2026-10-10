"""Cadastro oficial de CNPJ (dados abertos da Receita Federal), filtrado.

A Receita publica a base completa todo mês num compartilhamento público do
próprio domínio (`arquivos.receitafederal.gov.br`, WebDAV do Nextcloud). A
base tem ~7 GB comprimidos; o portal só precisa dos CNPJs que aparecem nos
contratos de Barreiras. Cada ZIP oficial é baixado para o disco, tem o SHA-256
calculado durante o download, é lido em fluxo e descartado; ficam só as linhas
dos CNPJs pedidos, sem telefone, e-mail ou endereço.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import re
import urllib.request
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlparse
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

SOURCE_CODE = "receita-federal-cnpj"
ENDPOINT_CODE = "dados-abertos-cnpj"
WEBDAV_URL = "https://arquivos.receitafederal.gov.br/public.php/webdav"
# Token público do compartilhamento de dados abertos do CNPJ (usuário do
# WebDAV, senha vazia). Não é segredo: é o identificador do link público.
SHARE_TOKEN = "YggdBLfdninEJX9"  # noqa: S105 - link público, não é credencial.
OFFICIAL_HOST = "arquivos.receitafederal.gov.br"
EMPRESAS_FILES = tuple(f"Empresas{index}.zip" for index in range(10))
ESTABELECIMENTOS_FILES = tuple(f"Estabelecimentos{index}.zip" for index in range(10))
NATUREZAS_FILE = "Naturezas.zip"
REQUIRED_FILES = frozenset((*EMPRESAS_FILES, *ESTABELECIMENTOS_FILES, NATUREZAS_FILE))
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
CNPJ = re.compile(r"^\d{14}$")
CHUNK_BYTES = 4 * 1024 * 1024
TIMEOUT_SECONDS = 120.0


class ReceitaCnpjError(RuntimeError):
    """A base oficial não permite afirmar o cadastro com segurança."""


@dataclass(frozen=True)
class RemoteFile:
    month: str
    name: str
    size: int
    last_modified: str

    @property
    def url(self) -> str:
        return f"{WEBDAV_URL}/{self.month}/{quote(self.name)}"


@dataclass(frozen=True)
class DownloadedFile:
    remote: RemoteFile
    path: Path
    sha256: str


def _authorization() -> str:
    token = base64.b64encode(f"{SHARE_TOKEN}:".encode()).decode()
    return f"Basic {token}"


def _check_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != OFFICIAL_HOST:
        raise ReceitaCnpjError("URL fora do host oficial da Receita.")


def _propfind(url: str, *, opener: Callable = urllib.request.urlopen) -> bytes:
    _check_url(url)
    request = urllib.request.Request(  # noqa: S310 - host HTTPS da Receita conferido.
        url,
        method="PROPFIND",
        headers={
            "Depth": "1",
            "Authorization": _authorization(),
            "User-Agent": "Barreiras360-Collector/0.1",
        },
    )
    with opener(request, timeout=TIMEOUT_SECONDS) as response:
        if response.status != 207:
            raise ReceitaCnpjError(
                f"Listagem da Receita respondeu HTTP {response.status}."
            )
        return response.read(8 * 1024 * 1024)


def parse_propfind(body: bytes) -> list[tuple[str, int | None, str | None]]:
    """(caminho, tamanho, última modificação) de cada item da listagem."""
    namespace = {"d": "DAV:"}
    try:
        root = fromstring(body)
    except (ParseError, DefusedXmlException) as error:
        raise ReceitaCnpjError("Listagem da Receita não é XML válido.") from error
    items = []
    for response in root.findall("d:response", namespace):
        href = response.findtext("d:href", default="", namespaces=namespace)
        size = response.findtext(
            ".//d:getcontentlength", default="", namespaces=namespace
        )
        modified = response.findtext(
            ".//d:getlastmodified", default="", namespaces=namespace
        )
        items.append((href, int(size) if size.isdigit() else None, modified or None))
    return items


def latest_complete_month(
    *, opener: Callable = urllib.request.urlopen
) -> dict[str, RemoteFile]:
    """Pasta mensal mais recente que tem todos os arquivos necessários."""
    months = sorted(
        {
            href.rstrip("/").rsplit("/", 1)[-1]
            for href, _size, _modified in parse_propfind(
                _propfind(f"{WEBDAV_URL}/", opener=opener)
            )
            if href.endswith("/") and MONTH.match(href.rstrip("/").rsplit("/", 1)[-1])
        },
        reverse=True,
    )
    for month in months[:3]:
        files: dict[str, RemoteFile] = {}
        for href, size, modified in parse_propfind(
            _propfind(f"{WEBDAV_URL}/{month}/", opener=opener)
        ):
            name = href.rsplit("/", 1)[-1]
            if name in REQUIRED_FILES and size and modified:
                files[name] = RemoteFile(
                    month=month,
                    name=name,
                    size=size,
                    last_modified=parsedate_to_datetime(modified).isoformat(),
                )
        if frozenset(files) == REQUIRED_FILES:
            return files
    raise ReceitaCnpjError("Nenhuma das pastas mensais recentes está completa.")


def download(
    remote: RemoteFile,
    directory: Path,
    *,
    opener: Callable = urllib.request.urlopen,
) -> DownloadedFile:
    """Baixa para o disco calculando o SHA-256; confere o tamanho anunciado."""
    _check_url(remote.url)
    request = urllib.request.Request(  # noqa: S310 - host HTTPS da Receita conferido.
        remote.url,
        headers={
            "Authorization": _authorization(),
            "User-Agent": "Barreiras360-Collector/0.1",
        },
    )
    digest = hashlib.sha256()
    target = directory / remote.name
    size = 0
    with (
        opener(request, timeout=TIMEOUT_SECONDS) as response,
        target.open("wb") as output,
    ):
        if response.status != 200:
            raise ReceitaCnpjError(f"{remote.name}: HTTP {response.status}.")
        _check_url(response.geturl())
        while chunk := response.read(CHUNK_BYTES):
            digest.update(chunk)
            output.write(chunk)
            size += len(chunk)
    if size != remote.size:
        target.unlink(missing_ok=True)
        raise ReceitaCnpjError(f"{remote.name}: {size} bytes, esperado {remote.size}.")
    return DownloadedFile(remote=remote, path=target, sha256=digest.hexdigest())


def _rows(path: Path) -> Iterable[list[str]]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != 1:
            raise ReceitaCnpjError(f"{path.name}: esperado um CSV, há {len(names)}.")
        with archive.open(names[0]) as raw:
            text = io.TextIOWrapper(raw, encoding="latin-1", newline="")
            yield from csv.reader(text, delimiter=";", quotechar='"')


def scan_empresas(path: Path, bases: frozenset[str]) -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    for row in _rows(path):
        if row and row[0] in bases:
            if len(row) < 6:
                raise ReceitaCnpjError(f"{path.name}: linha de empresa incompleta.")
            found[row[0]] = {
                "cnpj_basico": row[0],
                "razao_social": row[1].strip(),
                "natureza_juridica": row[2].strip(),
                "porte": row[5].strip(),
            }
    return found


def scan_estabelecimentos(
    path: Path, cnpjs: frozenset[str]
) -> dict[str, dict[str, str]]:
    bases = frozenset(cnpj[:8] for cnpj in cnpjs)
    found: dict[str, dict[str, str]] = {}
    for row in _rows(path):
        if not row or row[0] not in bases:
            continue
        if len(row) < 21:
            raise ReceitaCnpjError(f"{path.name}: linha de estabelecimento incompleta.")
        cnpj = f"{row[0]}{row[1]}{row[2]}"
        if cnpj in cnpjs:
            # Sem telefone, e-mail ou endereço: só o que identifica o CNPJ.
            found[cnpj] = {
                "cnpj": cnpj,
                "matriz_filial": row[3].strip(),
                "nome_fantasia": row[4].strip(),
                "situacao_cadastral": row[5].strip(),
                "data_situacao_cadastral": row[6].strip(),
                # 1.1.0: abertura e atividade principal (dados públicos da
                # empresa, sem dado pessoal) para a verificação de empresa
                # recém-aberta (ADR 0097).
                "data_inicio_atividade": row[10].strip(),
                "cnae_fiscal_principal": row[11].strip(),
                "uf": row[19].strip(),
                "municipio_receita": row[20].strip(),
            }
    return found


def read_naturezas(path: Path) -> dict[str, str]:
    return {row[0]: row[1].strip() for row in _rows(path) if len(row) >= 2}


def build_registry(
    targets: frozenset[str],
    empresas: dict[str, dict[str, str]],
    estabelecimentos: dict[str, dict[str, str]],
    naturezas: dict[str, str],
) -> tuple[list[dict[str, str]], list[str]]:
    """Uma linha por CNPJ encontrado; os ausentes voltam em lista própria."""
    if any(not CNPJ.match(cnpj) for cnpj in targets):
        raise ValueError("Alvos devem ser CNPJs de 14 dígitos.")
    registry = []
    missing = []
    for cnpj in sorted(targets):
        establishment = estabelecimentos.get(cnpj)
        company = empresas.get(cnpj[:8])
        if establishment is None or company is None:
            missing.append(cnpj)
            continue
        registry.append(
            {
                **establishment,
                "razao_social": company["razao_social"],
                "natureza_juridica": company["natureza_juridica"],
                "natureza_juridica_descricao": naturezas.get(
                    company["natureza_juridica"], ""
                ),
                "porte": company["porte"],
            }
        )
    return registry, missing
