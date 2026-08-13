"""Recorte mínimo do cadastro oficial de candidaturas do TSE.

Somente candidaturas previamente aprovadas no crosswalk entram no fluxo. O CPF
permanece apenas no objeto privado transitório; a projeção reutilizável não o
contém.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass

from .private_identifiers import InvalidCpfError, normalize_cpf

STATE_CODE = "BA"
SOURCE_URL_TEMPLATE = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/"
    "consulta_cand_{year}.zip"
)
REQUIRED_COLUMNS = (
    "ANO_ELEICAO",
    "SG_UF",
    "DS_CARGO",
    "SQ_CANDIDATO",
    "NR_CPF_CANDIDATO",
    "NM_CANDIDATO",
    "NM_URNA_CANDIDATO",
)


class CandidateRegistryError(RuntimeError):
    """A fonte oficial não satisfaz o contrato privado de identidade."""


@dataclass(frozen=True, slots=True)
class OfficialCandidateIdentity:
    election_year: int
    office: str
    candidate_id: str
    cpf: str | None
    identifier_issue: str | None
    civil_name: str
    ballot_name: str
    public_payload: dict[str, str]
    private_source_payload: bytes


def source_url(year: int) -> str:
    if not 1994 <= year <= 2100:
        raise ValueError("Ano eleitoral fora do intervalo permitido.")
    return SOURCE_URL_TEMPLATE.format(year=year)


def extract_bahia_registry(package: bytes, year: int) -> bytes:
    try:
        archive = zipfile.ZipFile(io.BytesIO(package))
    except zipfile.BadZipFile as error:
        raise CandidateRegistryError("O pacote do TSE não é um ZIP válido.") from error
    expected = f"consulta_cand_{year}_{STATE_CODE}.csv"
    for name in archive.namelist():
        if name.upper().endswith(expected.upper()):
            return archive.read(name)
    raise CandidateRegistryError(
        f"O pacote do TSE não contém o cadastro da Bahia ({expected})."
    )


def candidates_from_registry(
    state_csv: bytes,
    *,
    year: int,
    approved_candidate_ids: set[str],
) -> list[OfficialCandidateIdentity]:
    if not approved_candidate_ids:
        return []
    reader = csv.DictReader(
        io.StringIO(state_csv.decode("latin-1")),
        delimiter=";",
    )
    columns = set(reader.fieldnames or ())
    missing = [column for column in REQUIRED_COLUMNS if column not in columns]
    if missing:
        raise CandidateRegistryError(
            f"O layout do TSE mudou: faltam as colunas {missing}."
        )

    identities: dict[str, OfficialCandidateIdentity] = {}
    for row in reader:
        candidate_id = row["SQ_CANDIDATO"].strip()
        if candidate_id not in approved_candidate_ids:
            continue
        row_year = row["ANO_ELEICAO"].strip()
        if row_year != str(year) or row["SG_UF"].strip().upper() != STATE_CODE:
            raise CandidateRegistryError(
                f"A candidatura {candidate_id} diverge do ano ou UF solicitados."
            )
        private_payload = {
            column.lower(): row[column].strip() for column in REQUIRED_COLUMNS
        }
        public_payload = {
            "ano": row_year,
            "cargo": row["DS_CARGO"].strip(),
            "nome": row["NM_CANDIDATO"].strip(),
            "nome_urna": row["NM_URNA_CANDIDATO"].strip(),
            "sq_candidato": candidate_id,
            "uf": STATE_CODE,
        }
        raw_cpf = row["NR_CPF_CANDIDATO"].strip()
        try:
            cpf = normalize_cpf(raw_cpf)
            identifier_issue = None
        except InvalidCpfError:
            cpf = None
            identifier_issue = (
                "missing_official_value" if not raw_cpf else "invalid_official_value"
            )
        identity = OfficialCandidateIdentity(
            election_year=year,
            office=public_payload["cargo"],
            candidate_id=candidate_id,
            cpf=cpf,
            identifier_issue=identifier_issue,
            civil_name=public_payload["nome"],
            ballot_name=public_payload["nome_urna"],
            public_payload=public_payload,
            private_source_payload=json.dumps(
                private_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        )
        previous = identities.get(candidate_id)
        if (
            previous is not None
            and previous.cpf is not None
            and identity.cpf is not None
            and previous.cpf != identity.cpf
        ):
            raise CandidateRegistryError(
                f"A fonte publicou CPFs divergentes para {candidate_id}."
            )
        if previous is None or previous.cpf is None:
            identities[candidate_id] = identity

    return sorted(identities.values(), key=lambda item: item.candidate_id)
