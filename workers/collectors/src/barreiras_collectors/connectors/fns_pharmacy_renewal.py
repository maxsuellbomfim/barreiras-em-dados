"""Restricted reader for the official 2025 renewal list; identity, not tenure."""

import hashlib
import io
import re
from functools import lru_cache

BASE = "https://www.gov.br/saude/pt-br/composicao/sectics/farmacia-popular/"
RENEWAL_PATHS = tuple(
    BASE + part + "/empresas-credenciadas-para-realizar-a-renovacao-2025"
    for part in (
        "renovacao-de-estabelecimentos-participantes",
        "renovacao-de-credenciamento",
    )
)
HEADER = "CNPJ_MATRIZ CNPJ_ESTABELECIMENTO RAZAO_SOCIAL_MATRIZ_RFB"
TITLES = {
    "MINISTÉRIO DA SAÚDE",
    "Secretaria de Ciência, Tecnologia, Inovação e do Complexo "
    "Econômico-Industrial da Saúde - SECTICS",
    "Departamento de Assistência Farmacêutica e Insumos Estratégicos - DAF",
    "Lista de Farmácias Credenciadas que devem realizar a "
    "Renovação Cadastral anual Obrigatória",
    "Período de 17/04/2025 a 30/05/2025",
}


def parse_renewal_pages(pages):
    if not 1 <= len(pages) <= 500:
        raise ValueError("Invalid renewal page count")
    rows, header_seen = [], False
    for number, text in enumerate(pages, 1):
        if not isinstance(text, str) or len(text) > 40000:
            raise ValueError("Invalid renewal page")
        page_rows, name_column = [], None
        for line in text.splitlines():
            normalized = " ".join(line.split())
            if not normalized:
                continue
            if number == 1 and not page_rows and normalized in TITLES:
                continue
            if number == 1 and not page_rows and normalized == HEADER:
                header_seen = True
                continue
            match = re.fullmatch(r"\s*([0-9]{14})\s+([0-9]{14})\s+(.+?)\s*", line)
            if match and header_seen:
                name_column = match.start(3)
                page_rows.append(
                    dict(
                        matrix=match[1],
                        identifier=match[2],
                        name=match[3],
                        page=number,
                        row=len(page_rows) + 1,
                    )
                )
            elif (
                page_rows
                and len(line) - len(line.lstrip()) >= name_column - 2
                and not re.search(r"[0-9]{14}", line)
            ):
                page_rows[-1]["name"] += " " + normalized
            else:
                raise ValueError("Unexpected renewal line")
        if not page_rows or len(page_rows) > 1000:
            raise ValueError("Empty or oversized renewal page")
        rows.extend(page_rows)
    return rows


def match_renewal_rows(rows, beneficiary):
    from .fns_pharmacy_identity import _valid_cnpj

    matches = [r for r in rows if r["identifier"] == beneficiary]
    if not _valid_cnpj(beneficiary) or len(matches) != 1:
        return None
    row = matches[0]
    # This source names the matrix. Do not invent a branch name from that field.
    if row["matrix"] != beneficiary:
        return None
    name = row["name"]
    if (
        not 2 <= len(name) <= 180
        or name != name.strip()
        or re.search(r"[<>\x00-\x1f\x7f]|[0-9]{11}", name)
    ):
        raise ValueError("Invalid institutional name")
    return dict(establishment=name, register_page=row["page"], register_row=row["row"])


@lru_cache(maxsize=2)
def _pdf_rows(raw):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw), strict=True)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 500:
        raise ValueError("Unsupported renewal PDF")
    return parse_renewal_pages(
        [page.extract_text(extraction_mode="layout") for page in reader.pages]
    )


def inspect_renewal_register(capture, beneficiary):
    try:
        raw = capture["body"]
        if (
            not isinstance(raw, bytes)
            or not raw.startswith(b"%PDF-")
            or not 0 < len(raw) <= 8_000_000
        ):
            raise ValueError("Invalid renewal bytes")
        if (
            type(capture["byte_size"]) is not int
            or capture["byte_size"] != len(raw)
            or capture["sha256"] != hashlib.sha256(raw).hexdigest()
        ):
            raise ValueError("Invalid renewal integrity")
        if (
            capture.get("http_status") != 200
            or capture["source_url"]
            not in tuple(p + "/@@download/file" for p in RENEWAL_PATHS)
            or capture["referrer_url"] not in tuple(p + "/view" for p in RENEWAL_PATHS)
        ):
            raise ValueError("Invalid renewal origin")
        match = match_renewal_rows(_pdf_rows(raw), beneficiary)
        if match is None:
            return dict(status="review_required", publication_allowed=False)
        return dict(
            status="institution_matched",
            **match,
            register_sha256=capture["sha256"],
            historical_registration_verified=False,
            reconciliation="pending",
            publication_allowed=False,
        )
    except Exception:
        return dict(status="invalid_evidence", publication_allowed=False)
