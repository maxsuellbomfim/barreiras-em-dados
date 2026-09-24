"""Empenhos individuais da Prefeitura no sistema Sudoeste/WebRun.

O portal municipal publica despesas por um sistema de terceiro (WebRun 5), sem
API documentada. A consulta observada em 23/09/2026 tem três passos na mesma
sessão: abrir o formulário, executar a regra que fixa o período e pedir a
grade, que chega como JavaScript com todas as linhas do período.

Esta sonda apenas lê e valida um mês fechado. Ela não converte valores nem
persiste: a grade bruta é devolvida intacta, com SHA-256, para a etapa de
preservação. Qualquer divergência do contrato observado é falha explícita,
nunca "zero empenhos".
"""

from __future__ import annotations

import calendar
import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from ..http import HttpResponse
from .tcm_ba import TcmBaSessionTransport, UrllibSessionTransport

SOURCE_CODE = "prefeitura-barreiras-despesas-webrun"
ENDPOINT_CODE = "webrun-empenhos"
HOST = "portaldatransparencia.sudoesteinformatica.com.br"
ALLOWED_HOSTS = frozenset({HOST})
BASE_URL = f"https://{HOST}/webrun5"
FORM_ID = 7901
GRID_ID = 1082469
PERIOD_RULE = "TRP_TRANSP_DESPESDA_MODIFICAR_CONSULTA"
RULE_PARAMETER_COUNT = 25
# A série histórica anterior a 2024 falha na própria fonte (SQLException
# "Invalid column name 'NUMERO_DESPESA_2'"); o sistema atual só tem parte
# desses meses. Mês anterior a esta data é cobertura parcial, não completa.
FULL_COVERAGE_START = date(2024, 1, 1)

FIELD_DATE = "field1082407"
FIELD_KEY = "field1144631"
FIELD_NUMBER = "field1082410"
FIELD_AMOUNT = "field1082412"
FIELD_HISTORY = "field1144634"
FIELD_CREDITOR = "field1144629"
REQUIRED_FIELDS = (FIELD_DATE, FIELD_KEY, FIELD_NUMBER, FIELD_AMOUNT, FIELD_CREDITOR)
# A sessão WebRun devolve cookie; só estes cabeçalhos podem ser preservados.
PRESERVED_HEADERS = frozenset(
    {"content-type", "content-length", "date", "etag", "last-modified"}
)

_ROW_PREFIX = "{'" + FIELD_DATE + "':"
_PLAIN_FIELD = re.compile(r"'(field\d+)':'((?:[^'\\]|\\.)*)'")
_COLUMN = re.compile(r"\{'name':'(field\d+)','title':'((?:[^'\\]|\\.)*)'")
_SOURCE_FIELD = re.compile(r"d\.c_(\d+)\.field = \\'([^\\']+)\\'")
_JS_ESCAPE = re.compile(r"\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)", re.DOTALL)
# O- orçamentária, E- extra-orçamentária (retenções de folha e similares).
_KEY = re.compile(r"^[OE]-\d+$")
_NUMBER = re.compile(r"^\d+(?:/\d+)?$")
_AMOUNT = re.compile(r"^-?\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?$|^-?\d+(?:,\d{1,2})?$")


class MunicipalExpensesError(RuntimeError):
    """Falha explícita da fonte de despesas."""


class MunicipalExpensesContractError(MunicipalExpensesError):
    """A resposta diverge do contrato observado e não é confiável."""


@dataclass(frozen=True)
class MonthlyCommitments:
    source_code: str
    endpoint_code: str
    year: int
    month: int
    coverage: str
    declared_total: int
    repeated_rows: int
    open_url: str
    rule_url: str
    grid_url: str
    requested_at: str
    received_at: str
    grid_body: bytes
    grid_sha256: str
    grid_headers: Mapping[str, str]
    rows: tuple[dict[str, str], ...]
    column_titles: Mapping[str, str]
    source_field_names: Mapping[str, str]


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def coverage_for(year: int, month: int) -> str:
    if date(year, month, 1) < FULL_COVERAGE_START:
        return "partial_source_history_unavailable"
    return "complete"


def fetch_monthly_commitments(
    year: int,
    month: int,
    *,
    today: date,
    transport: TcmBaSessionTransport | None = None,
    timeout_seconds: float = 120.0,
    max_body_bytes: int = 96 * 1024 * 1024,
) -> MonthlyCommitments:
    """Consulta um mês fechado de empenhos e valida a grade inteira."""
    first, last = month_bounds(year, month)
    if last >= today:
        raise ValueError("Somente meses fechados podem ser coletados.")
    active = transport or UrllibSessionTransport(ALLOWED_HOSTS)
    active.reset_session()
    requested_at = datetime.now(UTC).isoformat()
    headers = {"Accept": "text/html,application/javascript,*/*"}

    open_url = f"{BASE_URL}/openform.do?" + urlencode(
        {
            "sys": "PTP",
            "action": "openform",
            "formID": FORM_ID,
            "dataConnection": "PM_Barreiras",
            "numerotc": 39,
        }
    )
    _expect_ok(
        active.get(
            open_url,
            headers=headers,
            timeout_seconds=timeout_seconds,
            max_body_bytes=4 * 1024 * 1024,
        ),
        "abrir formulário",
    )

    rule_url = f"{BASE_URL}/executeRule.do"
    rule = _expect_ok(
        active.post(
            rule_url,
            form=period_rule_form(first, last),
            headers=headers,
            timeout_seconds=timeout_seconds,
            max_body_bytes=1024 * 1024,
        ),
        "fixar período",
    )
    declared_total = parse_declared_total(rule.body.decode("iso-8859-1"))
    if declared_total == 0:
        # Mês fechado sem nenhum empenho não é plausível para o Município;
        # tratá-lo como vazio esconderia falha da fonte.
        raise MunicipalExpensesContractError("Mês sem empenhos declarados.")

    grid_url = f"{BASE_URL}/navigate.do?" + urlencode(
        {
            "sys": "PTP",
            "formID": FORM_ID,
            "componentID": GRID_ID,
            "action": "navigate",
            "param": "first",
            "inner": "true",
            "gt": 0,
        }
    )
    grid = _expect_ok(
        active.get(
            grid_url,
            headers=headers,
            timeout_seconds=timeout_seconds,
            max_body_bytes=max_body_bytes,
        ),
        "ler grade",
    )
    received_at = datetime.now(UTC).isoformat()
    parsed = parse_commitment_grid(grid.body.decode("iso-8859-1"))
    if parsed.page_end != declared_total or len(parsed.rows) != declared_total:
        raise MunicipalExpensesContractError(
            f"Grade com {len(parsed.rows)} linhas (fim de página "
            f"{parsed.page_end}) para {declared_total} declaradas."
        )
    repeated_rows = validate_rows(parsed.rows, first=first, last=last)
    return MonthlyCommitments(
        source_code=SOURCE_CODE,
        endpoint_code=ENDPOINT_CODE,
        year=year,
        month=month,
        coverage=coverage_for(year, month),
        declared_total=declared_total,
        repeated_rows=repeated_rows,
        open_url=open_url,
        rule_url=rule_url,
        grid_url=grid_url,
        requested_at=requested_at,
        received_at=received_at,
        grid_body=grid.body,
        grid_sha256=hashlib.sha256(grid.body).hexdigest(),
        grid_headers={
            name.lower(): value
            for name, value in grid.headers.items()
            if name.lower() in PRESERVED_HEADERS
        },
        rows=parsed.rows,
        column_titles=parsed.column_titles,
        source_field_names=parsed.source_field_names,
    )


def period_rule_form(first: date, last: date) -> dict[str, str]:
    form = {
        "action": "executeRule",
        "pType": "2",
        "ruleName": PERIOD_RULE,
        "sys": "PTP",
        "formID": str(FORM_ID),
        "parentRID": "-1",
    }
    for index in range(RULE_PARAMETER_COUNT):
        form[f"P_{index}"] = ""
    form["P_0"] = first.strftime("%d/%m/%Y")
    form["P_1"] = last.strftime("%d/%m/%Y")
    # Valor enviado pelo próprio formulário em toda consulta observada.
    form["P_6"] = "P"
    return form


def parse_declared_total(rule_script: str) -> int:
    if "interactionError(" in rule_script:
        raise MunicipalExpensesError("A fonte recusou a consulta do período.")
    match = re.search(r"\$c\('DESPESAS'\)\.setTotalRows\((\d+)\)", rule_script)
    if match is None:
        raise MunicipalExpensesContractError("Regra sem total declarado.")
    return int(match.group(1))


@dataclass(frozen=True)
class ParsedGrid:
    rows: tuple[dict[str, str], ...]
    page_end: int
    column_titles: Mapping[str, str]
    source_field_names: Mapping[str, str]


def parse_commitment_grid(script: str) -> ParsedGrid:
    if f"d.c_{GRID_ID}.isLastPage = true;" not in script:
        raise MunicipalExpensesContractError("Grade paginada ou incompleta.")
    page_end = re.search(rf"d\.c_{GRID_ID}\.setGridPageEnd\((\d+)\);", script)
    if page_end is None:
        raise MunicipalExpensesContractError("Grade sem fim de página.")
    columns = re.search(rf"^cols_{GRID_ID} = \[(.*)\];$", script, re.MULTILINE)
    if columns is None:
        raise MunicipalExpensesContractError("Grade sem definição de colunas.")
    column_titles = {
        name: _unescape(title) for name, title in _COLUMN.findall(columns.group(1))
    }
    button_marker = f"d.c_{GRID_ID}.gridButton("
    rows: list[dict[str, str]] = []
    source_field_names: dict[str, str] = {}
    for line in script.split("\n"):
        if not line.startswith(_ROW_PREFIX):
            continue
        plain, _, button = line.partition(button_marker)
        rows.append(
            {name: _unescape(value) for name, value in _PLAIN_FIELD.findall(plain)}
        )
        if not source_field_names and button:
            source_field_names = {
                f"field{component}": name
                for component, name in _SOURCE_FIELD.findall(button)
            }
    return ParsedGrid(
        rows=tuple(rows),
        page_end=int(page_end.group(1)),
        column_titles=column_titles,
        source_field_names=source_field_names,
    )


def validate_rows(rows: tuple[dict[str, str], ...], *, first: date, last: date) -> int:
    """Valida a grade e devolve quantas linhas são repetições idênticas.

    A fonte repete linhas inteiras; a repetição fica preservada no bruto e
    só é aceita quando idêntica. Mesma chave com conteúdo diferente é falha.
    """
    seen: dict[str, dict[str, str]] = {}
    repeated = 0
    for position, row in enumerate(rows, start=1):
        missing = [field for field in REQUIRED_FIELDS if not row.get(field)]
        if missing:
            raise MunicipalExpensesContractError(
                f"Linha {position} sem campos obrigatórios: {', '.join(missing)}."
            )
        key = row[FIELD_KEY]
        if not _KEY.match(key):
            raise MunicipalExpensesContractError(
                f"Linha {position} com chave fora do padrão."
            )
        if key in seen:
            if seen[key] != row:
                raise MunicipalExpensesContractError(
                    f"Linha {position} repete a chave com conteúdo diferente."
                )
            repeated += 1
            continue
        seen[key] = row
        if not _NUMBER.match(row[FIELD_NUMBER]):
            raise MunicipalExpensesContractError(
                f"Linha {position} com número de empenho fora do padrão."
            )
        parse_amount(row[FIELD_AMOUNT])
        issued = datetime.strptime(row[FIELD_DATE], "%d/%m/%Y").date()
        if not first <= issued <= last:
            raise MunicipalExpensesContractError(
                f"Linha {position} fora do período consultado."
            )
    return repeated


def parse_amount(text: str) -> Decimal:
    if not _AMOUNT.match(text):
        raise MunicipalExpensesContractError("Valor fora do formato observado.")
    try:
        return Decimal(text.replace(".", "").replace(",", "."))
    except InvalidOperation as error:
        raise MunicipalExpensesContractError("Valor inválido.") from error


def _expect_ok(response: HttpResponse, stage: str) -> HttpResponse:
    if response.status != 200:
        raise MunicipalExpensesError(f"HTTP {response.status} ao {stage}.")
    return response


def _unescape(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token[0] in "ux" and len(token) > 1:
            return chr(int(token[1:], 16))
        return {"n": "\n", "r": "\r", "t": "\t"}.get(token, token)

    return _JS_ESCAPE.sub(replace, value)
