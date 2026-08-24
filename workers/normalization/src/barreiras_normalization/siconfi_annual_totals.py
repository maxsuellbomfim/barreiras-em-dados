"""Normalização determinística dos totais anuais literais da DCA/SICONFI."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

SICONFI_ANNUAL_TOTALS_PARSER_VERSION = "siconfi-annual-totals/1.0.0"
SICONFI_ANNUAL_TOTALS_VALIDATOR_VERSION = (
    "siconfi-annual-totals-deterministic/1.0.0"
)
SICONFI_ANNUAL_TOTALS_JOB_TYPE = "siconfi_annual_totals_v1"
BARREIRAS_IBGE_CODE = 2903201
BARREIRAS_INSTITUTION = "Prefeitura Municipal de Barreiras - BA"
SICONFI_DCA_URL_PREFIX = (
    "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca"
)

_DECIMAL = re.compile(r"^-?\d{1,18}(?:\.\d{1,2})?$")


class SiconfiAnnualTotalsError(ValueError):
    """O retrato anual não satisfaz o contrato estrito de publicação."""


@dataclass(frozen=True)
class MetricSelector:
    metric_key: str
    annex: str
    label: str
    column_label: str
    account_code: str
    account_label: str

    @property
    def identity(self) -> tuple[str, str, str, str, str]:
        return (
            self.annex,
            self.label,
            self.column_label,
            self.account_code,
            self.account_label,
        )


REVENUE_ACCOUNT = "TOTAL DAS RECEITAS (III) = (I + II)"
EXPENSE_ACCOUNT = "Total Geral da Despesa"

METRIC_SELECTORS = (
    MetricSelector(
        "gross_revenue_realized",
        "DCA-Anexo I-C",
        "Padrão",
        "Receitas Brutas Realizadas",
        "TotalReceitas",
        REVENUE_ACCOUNT,
    ),
    MetricSelector(
        "fundeb_deductions",
        "DCA-Anexo I-C",
        "Padrão",
        "Deduções - FUNDEB",
        "TotalReceitas",
        REVENUE_ACCOUNT,
    ),
    MetricSelector(
        "expense_committed",
        "DCA-Anexo I-D",
        "Padrão",
        "Despesas Empenhadas",
        "TotalDespesas",
        EXPENSE_ACCOUNT,
    ),
    MetricSelector(
        "expense_liquidated",
        "DCA-Anexo I-D",
        "Padrão",
        "Despesas Liquidadas",
        "TotalDespesas",
        EXPENSE_ACCOUNT,
    ),
    MetricSelector(
        "expense_paid",
        "DCA-Anexo I-D",
        "Padrão",
        "Despesas Pagas",
        "TotalDespesas",
        EXPENSE_ACCOUNT,
    ),
    MetricSelector(
        "nonprocessed_payables_registered",
        "DCA-Anexo I-D",
        "Padrão",
        "Inscrição de Restos a Pagar Não Processados",
        "TotalDespesas",
        EXPENSE_ACCOUNT,
    ),
    MetricSelector(
        "processed_payables_registered",
        "DCA-Anexo I-D",
        "Padrão",
        "Inscrição de Restos a Pagar Processados",
        "TotalDespesas",
        EXPENSE_ACCOUNT,
    ),
)

_SELECTOR_BY_IDENTITY = {selector.identity: selector for selector in METRIC_SELECTORS}


@dataclass(frozen=True)
class SiconfiAnnualRawLine:
    raw_record_id: str
    payload: Mapping[str, object]


@dataclass(frozen=True)
class SiconfiAnnualSnapshot:
    fiscal_year: int
    raw_artifact_id: str
    artifact_sha256: str
    source_url: str
    retrieved_at: str
    rows: tuple[SiconfiAnnualRawLine, ...]


@dataclass(frozen=True)
class SiconfiAnnualTotal:
    raw_record_id: str
    raw_artifact_id: str
    fiscal_year: int
    metric_key: str
    amount: Decimal
    official_annex: str
    official_label: str
    official_column_label: str
    official_account_code: str
    official_account_label: str
    evidence_text: str
    evidence_sha256: str
    methodology_version: str = SICONFI_ANNUAL_TOTALS_PARSER_VERSION


def normalize_siconfi_annual_snapshot(
    snapshot: SiconfiAnnualSnapshot,
) -> tuple[SiconfiAnnualTotal, ...]:
    """Seleciona sete linhas oficiais exatas, sem somar ou inferir valores."""
    if snapshot.fiscal_year < 1988 or snapshot.fiscal_year > 2200:
        raise SiconfiAnnualTotalsError("Exercício SICONFI fora do intervalo.")
    if not re.fullmatch(r"[0-9a-f]{64}", snapshot.artifact_sha256):
        raise SiconfiAnnualTotalsError("Hash do artefato SICONFI inválido.")
    if not snapshot.source_url.startswith(SICONFI_DCA_URL_PREFIX):
        raise SiconfiAnnualTotalsError("URL não pertence à API oficial do SICONFI.")

    matched: dict[str, SiconfiAnnualTotal] = {}
    for row in snapshot.rows:
        payload = row.payload
        identity = tuple(
            _required_text(payload, key)
            for key in ("anexo", "rotulo", "coluna", "cod_conta", "conta")
        )
        selector = _SELECTOR_BY_IDENTITY.get(identity)
        if selector is None:
            continue

        year = _required_int(payload, "exercicio")
        ibge_code = _required_int(payload, "cod_ibge")
        institution = _required_text(payload, "instituicao")
        if year != snapshot.fiscal_year:
            raise SiconfiAnnualTotalsError(
                "A linha total diverge do exercício do artefato."
            )
        if ibge_code != BARREIRAS_IBGE_CODE or institution != BARREIRAS_INSTITUTION:
            raise SiconfiAnnualTotalsError(
                "A linha total não pertence à Prefeitura de Barreiras."
            )
        if selector.metric_key in matched:
            raise SiconfiAnnualTotalsError(
                f"A fonte repetiu a métrica anual {selector.metric_key}."
            )

        amount_text = _required_text(payload, "valor")
        if not _DECIMAL.fullmatch(amount_text):
            raise SiconfiAnnualTotalsError("Valor anual SICONFI inválido.")
        try:
            amount = Decimal(amount_text)
        except InvalidOperation as error:
            raise SiconfiAnnualTotalsError(
                "Valor anual SICONFI não é decimal."
            ) from error

        evidence_payload = {
            "anexo": selector.annex,
            "rotulo": selector.label,
            "coluna": selector.column_label,
            "cod_conta": selector.account_code,
            "conta": selector.account_label,
            "valor": amount_text,
            "exercicio": year,
            "cod_ibge": ibge_code,
        }
        evidence_text = json.dumps(
            evidence_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        matched[selector.metric_key] = SiconfiAnnualTotal(
            raw_record_id=row.raw_record_id,
            raw_artifact_id=snapshot.raw_artifact_id,
            fiscal_year=year,
            metric_key=selector.metric_key,
            amount=amount,
            official_annex=selector.annex,
            official_label=selector.label,
            official_column_label=selector.column_label,
            official_account_code=selector.account_code,
            official_account_label=selector.account_label,
            evidence_text=evidence_text,
            evidence_sha256=hashlib.sha256(evidence_text.encode("utf-8")).hexdigest(),
        )

    missing = [
        selector.metric_key
        for selector in METRIC_SELECTORS
        if selector.metric_key not in matched
    ]
    if missing:
        raise SiconfiAnnualTotalsError(
            "O exercício não contém todas as sete métricas anuais: "
            + ", ".join(missing)
        )
    return tuple(matched[selector.metric_key] for selector in METRIC_SELECTORS)


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SiconfiAnnualTotalsError(f"Campo obrigatório inválido: {key}.")
    return value.strip()


def _required_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool):
        raise SiconfiAnnualTotalsError(f"Campo inteiro inválido: {key}.")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"\d+", value):
        return int(value)
    raise SiconfiAnnualTotalsError(f"Campo inteiro inválido: {key}.")
