"""Totalizadores determinísticos da relação municipal de servidores.

O parser recebe texto já extraído do PDF oficial e devolve somente agregados.
Nomes, matrículas, cargos, lotações e descontos individuais não atravessam
esta fronteira. O total geral só é aceito quando fecha aritmeticamente e
coincide com a soma de todos os subtotais declarados no documento.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

PAYROLL_REPORT_PARSER_VERSION = "payroll-report-aggregate/1.4.0"
PAYROLL_REGIME_PARSER_VERSION = "payroll-regime-breakdown/1.0.0"
PAYROLL_COMPENSATION_PARSER_VERSION = "payroll-compensation-bands/1.0.0"
PayrollCycle = Literal[
    "regular",
    "thirteenth_advance",
    "thirteenth_final",
]
PayrollRegimeCode = Literal[
    "statutory",
    "commissioned",
    "selection_process",
    "ceded",
    "political_agent",
    "guardianship_council",
    "pensioner",
    "temporary_worker",
]


class PayrollReportContractError(ValueError):
    """O documento não atende ao leiaute agregado comprovado."""


@dataclass(frozen=True)
class PayrollReportAggregate:
    employee_count: int
    gross_amount: Decimal
    deduction_amount: Decimal
    net_amount: Decimal
    subtotal_count: int
    payroll_cycle: PayrollCycle
    parser_version: str = PAYROLL_REPORT_PARSER_VERSION


@dataclass(frozen=True)
class PayrollRegimeAggregate:
    regime_code: PayrollRegimeCode
    regime_label: str
    employee_count: int
    gross_amount: Decimal
    deduction_amount: Decimal
    net_amount: Decimal


@dataclass(frozen=True)
class PayrollRegimeBreakdown:
    employee_count: int
    gross_amount: Decimal
    deduction_amount: Decimal
    net_amount: Decimal
    payroll_cycle: PayrollCycle
    categories: tuple[PayrollRegimeAggregate, ...]
    parser_version: str = PAYROLL_REGIME_PARSER_VERSION


@dataclass(frozen=True)
class PayrollCompensationBand:
    band_code: str
    band_label: str
    employee_count: int
    gross_amount: Decimal


@dataclass(frozen=True)
class PayrollCompensationDistribution:
    employee_count: int
    gross_amount: Decimal
    maximum_gross_amount: Decimal
    payroll_cycle: PayrollCycle
    bands: tuple[PayrollCompensationBand, ...]
    parser_version: str = PAYROLL_COMPENSATION_PARSER_VERSION


@dataclass(frozen=True)
class _DeclaredTotal:
    employee_count: int
    gross_amount: Decimal
    deduction_amount: Decimal
    net_amount: Decimal


_AMOUNT = r"(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}"
_REQUIRED_HEADER_FIELDS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bMat\.",
        r"\bNome\b",
        r"\bCargo\b",
        r"\bProvento\b",
        r"\bDesconto\b",
        r"\bL\S*quido\b",
    )
)
_TOTAL_ROW = re.compile(
    rf"^Total\s+de\s+Funcion\S*rios(?P<grand>\s+Geral)?\s*:\s*"
    rf"(?P<count>\d+)\s+"
    rf"(?P<gross>{_AMOUNT})\s+"
    rf"(?P<deduction>{_AMOUNT})\s+"
    rf"(?P<net>{_AMOUNT})\s*$",
    re.IGNORECASE,
)
_PAYROLL_HEADER = re.compile(
    r"Listagem\s+Sint\S*tica\s+E-TCM(?P<label>.*)",
    re.IGNORECASE,
)
_PAYROLL_FIELD = re.compile(
    r"(?P<before>.*?)FOLHA\s*\.{3,}\s*:\s*(?P<after>.*)",
    re.IGNORECASE,
)
_EMPLOYEE_AMOUNTS = re.compile(
    rf"(?P<gross>{_AMOUNT})\s+"
    rf"(?P<deduction>{_AMOUNT})\s+"
    rf"(?P<net>{_AMOUNT})\s*$"
)
_EMPLOYEE_IDENTIFIER = re.compile(r"^\s*(?:\d+|\([A-Z]\))\s+")
_REGIME_LABELS: dict[PayrollRegimeCode, str] = {
    "statutory": "Estatutários",
    "commissioned": "Cargos em comissão",
    "selection_process": "Processo seletivo",
    "ceded": "Cedidos",
    "political_agent": "Agentes políticos",
    "guardianship_council": "Conselho tutelar",
    "pensioner": "Pensionistas",
    "temporary_worker": "Trabalhadores temporários",
}
_COMPENSATION_BANDS: tuple[tuple[str, str, Decimal | None], ...] = (
    ("up_to_1500", "Até R$ 1.500", Decimal("1500.00")),
    ("from_1500_01_to_3000", "De R$ 1.500,01 a R$ 3 mil", Decimal("3000.00")),
    ("from_3000_01_to_5000", "De R$ 3.000,01 a R$ 5 mil", Decimal("5000.00")),
    ("from_5000_01_to_10000", "De R$ 5.000,01 a R$ 10 mil", Decimal("10000.00")),
    ("from_10000_01_to_20000", "De R$ 10.000,01 a R$ 20 mil", Decimal("20000.00")),
    ("above_20000", "Acima de R$ 20 mil", None),
)


def _amount(value: str) -> Decimal:
    try:
        return Decimal(value.replace(".", "").replace(",", ".")).quantize(
            Decimal("0.01")
        )
    except InvalidOperation as error:
        raise PayrollReportContractError(
            "total monetário inválido no documento"
        ) from error


def _declared_total(match: re.Match[str]) -> _DeclaredTotal:
    total = _DeclaredTotal(
        employee_count=int(match.group("count")),
        gross_amount=_amount(match.group("gross")),
        deduction_amount=_amount(match.group("deduction")),
        net_amount=_amount(match.group("net")),
    )
    if total.employee_count < 1:
        raise PayrollReportContractError("total de vínculos deve ser positivo")
    if total.gross_amount - total.deduction_amount != total.net_amount:
        raise PayrollReportContractError(
            "aritmética declarada de provento, desconto e líquido não fecha"
        )
    return total


def _has_validated_header(text: str) -> bool:
    return any(
        all(field.search(line) is not None for field in _REQUIRED_HEADER_FIELDS)
        for line in text.splitlines()
    )


def _payroll_cycle(text: str) -> PayrollCycle:
    observed: set[PayrollCycle] = set()
    unknown_header = False
    header_found = False
    labels: list[str] = []
    for line in text.splitlines():
        header = _PAYROLL_HEADER.search(line)
        if header is not None:
            header_found = True
            header_label = header.group("label").strip()
            if header_label:
                labels.append(header_label)
        payroll_field = _PAYROLL_FIELD.search(line)
        if payroll_field is not None:
            labels.append(
                " ".join(
                    part.strip()
                    for part in (
                        payroll_field.group("before"),
                        payroll_field.group("after"),
                    )
                    if part.strip()
                )
            )
    for label in labels:
        matched = False
        if re.search(r"\b1\s*-\s*Normal", label, re.IGNORECASE) or re.search(
            r"<\s*Todos\s*>", label, re.IGNORECASE
        ):
            observed.add("regular")
            matched = True
        if re.search(r"\b4\s*-\s*Adiant", label, re.IGNORECASE):
            observed.add("thirteenth_advance")
            matched = True
        if re.search(r"\b6\s*-\s*13\S*\s+Final", label, re.IGNORECASE):
            observed.add("thirteenth_final")
            matched = True
        if not matched:
            unknown_header = True
    if not header_found or unknown_header or len(observed) != 1:
        raise PayrollReportContractError(
            "processamento da folha ausente, desconhecido ou misto"
        )
    return observed.pop()


def parse_payroll_report_aggregate(text: str) -> PayrollReportAggregate:
    """Valida subtotais e retorna apenas o total geral reconciliado."""

    if not isinstance(text, str) or not text.strip():
        raise PayrollReportContractError("texto do relatório vazio")
    if not _has_validated_header(text):
        raise PayrollReportContractError(
            "cabeçalho da relação de servidores não reconhecido"
        )
    payroll_cycle = _payroll_cycle(text)

    subtotals: list[_DeclaredTotal] = []
    grand_totals: list[_DeclaredTotal] = []
    for line in text.splitlines():
        match = _TOTAL_ROW.match(line.strip())
        if match is None:
            continue
        total = _declared_total(match)
        if match.group("grand"):
            grand_totals.append(total)
        else:
            subtotals.append(total)

    if not subtotals:
        raise PayrollReportContractError("nenhum subtotal de lotação reconhecido")
    if len(grand_totals) != 1:
        raise PayrollReportContractError(
            "documento deve conter exatamente um total geral"
        )

    grand = grand_totals[0]
    subtotal_sum = _DeclaredTotal(
        employee_count=sum(row.employee_count for row in subtotals),
        gross_amount=sum(
            (row.gross_amount for row in subtotals),
            start=Decimal("0.00"),
        ),
        deduction_amount=sum(
            (row.deduction_amount for row in subtotals),
            start=Decimal("0.00"),
        ),
        net_amount=sum(
            (row.net_amount for row in subtotals),
            start=Decimal("0.00"),
        ),
    )
    if subtotal_sum != grand:
        raise PayrollReportContractError(
            "soma dos subtotais diverge do total geral declarado"
        )

    return PayrollReportAggregate(
        employee_count=grand.employee_count,
        gross_amount=grand.gross_amount,
        deduction_amount=grand.deduction_amount,
        net_amount=grand.net_amount,
        subtotal_count=len(subtotals),
        payroll_cycle=payroll_cycle,
    )


def _normalized_regime_label(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character) and character != "�"
    )
    return re.sub(r"[^a-z0-9]+", " ", without_marks).strip()


def _regime_code(value: str) -> PayrollRegimeCode:
    normalized = _normalized_regime_label(value)
    candidates: list[PayrollRegimeCode] = []
    known_regimes: tuple[tuple[str, PayrollRegimeCode], ...] = (
        ("estatut", "statutory"),
        ("cargo em comiss", "commissioned"),
        ("processo seletivo", "selection_process"),
        ("cedid", "ceded"),
        ("agente politico", "political_agent"),
        ("conselho tutelar", "guardianship_council"),
        ("pensionista", "pensioner"),
        ("trabalhador tempor", "temporary_worker"),
    )
    for prefix, code in known_regimes:
        if normalized.startswith(prefix):
            candidates.append(code)
    if len(candidates) != 1:
        raise PayrollReportContractError(
            "regime/vínculo ausente, desconhecido ou ambíguo"
        )
    return candidates[0]


def parse_payroll_report_regime_breakdown(
    text: str,
) -> PayrollRegimeBreakdown:
    """Agrupa linhas por vínculo somente quando fecha com o total oficial."""

    overall = parse_payroll_report_aggregate(text)
    header_positions: tuple[int, int] | None = None
    grouped: dict[PayrollRegimeCode, list[Decimal | int]] = defaultdict(
        lambda: [
            0,
            Decimal("0.00"),
            Decimal("0.00"),
            Decimal("0.00"),
        ]
    )

    for line in text.splitlines():
        if "Regime/V" in line and "Local de Trabalho" in line:
            regime_start = line.index("Regime/V")
            local_start = line.index("Local de Trabalho")
            if regime_start >= local_start:
                raise PayrollReportContractError(
                    "colunas de regime/vínculo não reconhecidas"
                )
            header_positions = (regime_start, local_start)
            continue

        amounts = _EMPLOYEE_AMOUNTS.search(line)
        if amounts is None or "Total de Funcion" in line:
            continue
        if _EMPLOYEE_IDENTIFIER.match(line[: amounts.start()]) is None:
            continue
        if header_positions is None:
            raise PayrollReportContractError(
                "linha funcional encontrada antes do cabeçalho de regime/vínculo"
            )
        regime_start, local_start = header_positions
        if len(line) < local_start:
            raise PayrollReportContractError(
                "linha funcional truncada antes do regime/vínculo"
            )
        code = _regime_code(line[regime_start:local_start])
        gross = _amount(amounts.group("gross"))
        deduction = _amount(amounts.group("deduction"))
        net = _amount(amounts.group("net"))
        if gross - deduction != net:
            raise PayrollReportContractError(
                "aritmética individual não fecha para agregar regime/vínculo"
            )
        aggregate = grouped[code]
        aggregate[0] += 1
        aggregate[1] += gross
        aggregate[2] += deduction
        aggregate[3] += net

    categories = tuple(
        PayrollRegimeAggregate(
            regime_code=code,
            regime_label=_REGIME_LABELS[code],
            employee_count=int(values[0]),
            gross_amount=Decimal(values[1]),
            deduction_amount=Decimal(values[2]),
            net_amount=Decimal(values[3]),
        )
        for code, values in sorted(grouped.items())
    )
    reconciled = _DeclaredTotal(
        employee_count=sum(item.employee_count for item in categories),
        gross_amount=sum(
            (item.gross_amount for item in categories),
            start=Decimal("0.00"),
        ),
        deduction_amount=sum(
            (item.deduction_amount for item in categories),
            start=Decimal("0.00"),
        ),
        net_amount=sum(
            (item.net_amount for item in categories),
            start=Decimal("0.00"),
        ),
    )
    expected = _DeclaredTotal(
        employee_count=overall.employee_count,
        gross_amount=overall.gross_amount,
        deduction_amount=overall.deduction_amount,
        net_amount=overall.net_amount,
    )
    if not categories or reconciled != expected:
        raise PayrollReportContractError(
            "soma dos regimes/vínculos diverge do total geral declarado"
        )
    return PayrollRegimeBreakdown(
        employee_count=reconciled.employee_count,
        gross_amount=reconciled.gross_amount,
        deduction_amount=reconciled.deduction_amount,
        net_amount=reconciled.net_amount,
        payroll_cycle=overall.payroll_cycle,
        categories=categories,
    )


def _compensation_band(gross_amount: Decimal) -> tuple[str, str]:
    for code, label, upper_bound in _COMPENSATION_BANDS:
        if upper_bound is None or gross_amount <= upper_bound:
            return code, label
    raise AssertionError("faixa de remuneração sem cobertura")


def parse_payroll_report_compensation_distribution(
    text: str,
) -> PayrollCompensationDistribution:
    """Agrupa proventos brutos da folha regular sem conservar pessoas."""

    overall = parse_payroll_report_aggregate(text)
    if overall.payroll_cycle != "regular":
        raise PayrollReportContractError("faixas de remuneração exigem folha regular")

    grouped: dict[str, list[object]] = {}
    row_count = 0
    row_gross = Decimal("0.00")
    row_deduction = Decimal("0.00")
    row_net = Decimal("0.00")
    maximum_gross = Decimal("0.00")
    for line in text.splitlines():
        amounts = _EMPLOYEE_AMOUNTS.search(line)
        if amounts is None or "Total de Funcion" in line:
            continue
        if _EMPLOYEE_IDENTIFIER.match(line[: amounts.start()]) is None:
            continue
        gross = _amount(amounts.group("gross"))
        deduction = _amount(amounts.group("deduction"))
        net = _amount(amounts.group("net"))
        if gross - deduction != net:
            raise PayrollReportContractError(
                "aritmética individual não fecha para agregar faixas"
            )
        code, label = _compensation_band(gross)
        aggregate = grouped.setdefault(
            code,
            [label, 0, Decimal("0.00")],
        )
        aggregate[1] = int(aggregate[1]) + 1
        aggregate[2] = Decimal(aggregate[2]) + gross
        row_count += 1
        row_gross += gross
        row_deduction += deduction
        row_net += net
        maximum_gross = max(maximum_gross, gross)

    if (
        row_count != overall.employee_count
        or row_gross != overall.gross_amount
        or row_deduction != overall.deduction_amount
        or row_net != overall.net_amount
    ):
        raise PayrollReportContractError(
            "soma das faixas diverge do total geral declarado"
        )

    bands = tuple(
        PayrollCompensationBand(
            band_code=code,
            band_label=label,
            employee_count=int(grouped[code][1]),
            gross_amount=Decimal(grouped[code][2]),
        )
        for code, label, _upper_bound in _COMPENSATION_BANDS
        if code in grouped
    )
    return PayrollCompensationDistribution(
        employee_count=row_count,
        gross_amount=row_gross,
        maximum_gross_amount=maximum_gross,
        payroll_cycle=overall.payroll_cycle,
        bands=bands,
    )
