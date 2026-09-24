"""Empenhos e liquidações da Prefeitura no sistema Sudoeste/WebRun.

O portal municipal publica despesas por um sistema de terceiro (WebRun 5), sem
API documentada. A consulta observada em 23/09/2026 tem três passos na mesma
sessão: abrir o formulário, executar a regra que fixa o período e pedir a
grade, que chega como JavaScript com todas as linhas do período.

Cada estágio (empenhos, liquidações) é descrito por um ``GridSpec`` com o
formulário, a regra, a grade e os campos observados. A leitura apenas valida
um mês fechado; não converte valores nem persiste: a grade bruta é devolvida
intacta, com SHA-256, para a etapa de preservação. Qualquer divergência do
contrato observado é falha explícita, nunca "zero registros".
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

_PLAIN_FIELD = re.compile(r"'(field\d+)':'((?:[^'\\]|\\.)*)'")
_COLUMN = re.compile(r"\{'name':'(field\d+)','title':'((?:[^'\\]|\\.)*)'")
_SOURCE_FIELD = re.compile(r"d\.c_(\d+)\.field = \\'([^\\']+)\\'")
_HIDDEN_FIELD = re.compile(
    r"new HTMLHidden\(\\'PTP\\', \d+, (\d+), \\'((?:[^\\']|\\\\.)*)\\'\)"
)
_JS_ESCAPE = re.compile(r"\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)", re.DOTALL)
# O- orçamentária, E- extra-orçamentária (retenções de folha e similares).
_KEY = re.compile(r"^[OE]-\d+$")
_AMOUNT = re.compile(r"^-?\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?$|^-?\d+(?:,\d{1,2})?$")


@dataclass(frozen=True)
class GridSpec:
    """Contrato observado de uma grade WebRun de despesa."""

    stage: str
    endpoint_code: str
    form_id: int
    grid_id: int
    grid_name: str
    rule_name: str
    rule_extras: tuple[tuple[str, str], ...]
    row_prefix: str
    date_field: str
    key_field: str
    number_field: str
    amount_field: str
    creditor_field: str
    number_pattern: re.Pattern[str]
    # Campos que a grade só expõe nos valores ocultos do botão de detalhe.
    hidden_fields: tuple[str, ...] = ()
    # Empenho tem chave própria; várias liquidações podem citar o mesmo empenho.
    unique_key: bool = True

    @property
    def required_fields(self) -> tuple[str, ...]:
        return (
            self.date_field,
            self.key_field,
            self.number_field,
            self.amount_field,
            self.creditor_field,
        )


COMMITMENTS = GridSpec(
    stage="empenhos",
    endpoint_code=ENDPOINT_CODE,
    form_id=FORM_ID,
    grid_id=GRID_ID,
    grid_name="DESPESAS",
    rule_name=PERIOD_RULE,
    rule_extras=(("P_6", "P"),),
    row_prefix="{'" + FIELD_DATE + "':",
    date_field=FIELD_DATE,
    key_field=FIELD_KEY,
    number_field=FIELD_NUMBER,
    amount_field=FIELD_AMOUNT,
    creditor_field=FIELD_CREDITOR,
    number_pattern=re.compile(r"^\d+(?:/\d+)?$"),
)

# A liquidação traz a CHAVE do empenho só no botão de detalhe; o número vem
# como "10  16" em vez de "10/16".
LIQUIDATIONS = GridSpec(
    stage="liquidacoes",
    endpoint_code="webrun-liquidacoes",
    form_id=7907,
    grid_id=1089430,
    grid_name="LIQUIDACAO",
    rule_name="TRP_TRANSP_LIQUIDAC_MODIFICAR_CONSULTA",
    rule_extras=(("P_6", "P"),),
    row_prefix="{'field",
    date_field="field1089483",
    key_field="field1089487",
    number_field="field1089486",
    amount_field="field1089488",
    creditor_field="field1144939",
    number_pattern=re.compile(r"^\d+(?:\s+\d+)?$"),
    hidden_fields=("field1089487",),
    unique_key=False,
)
STAGES = {spec.stage: spec for spec in (COMMITMENTS, LIQUIDATIONS)}


class MunicipalExpensesError(RuntimeError):
    """Falha explícita da fonte de despesas."""


class MunicipalExpensesContractError(MunicipalExpensesError):
    """A resposta diverge do contrato observado e não é confiável."""


@dataclass(frozen=True)
class MonthlyGrid:
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
    stage: str = COMMITMENTS.stage


MonthlyCommitments = MonthlyGrid


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
) -> MonthlyGrid:
    return fetch_monthly_grid(
        COMMITMENTS,
        year,
        month,
        today=today,
        transport=transport,
        timeout_seconds=timeout_seconds,
        max_body_bytes=max_body_bytes,
    )


def fetch_monthly_grid(
    spec: GridSpec,
    year: int,
    month: int,
    *,
    today: date,
    transport: TcmBaSessionTransport | None = None,
    timeout_seconds: float = 120.0,
    max_body_bytes: int = 96 * 1024 * 1024,
) -> MonthlyGrid:
    """Consulta um mês fechado de um estágio e valida a grade inteira."""
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
            "formID": spec.form_id,
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
            form=period_rule_form(first, last, spec),
            headers=headers,
            timeout_seconds=timeout_seconds,
            max_body_bytes=1024 * 1024,
        ),
        "fixar período",
    )
    declared_total = parse_declared_total(
        rule.body.decode("iso-8859-1"), spec.grid_name
    )
    if declared_total == 0:
        # Mês fechado sem nenhum registro não é plausível para o Município;
        # tratá-lo como vazio esconderia falha da fonte.
        raise MunicipalExpensesContractError(f"Mês sem {spec.stage} declarados.")

    grid_url = f"{BASE_URL}/navigate.do?" + urlencode(
        {
            "sys": "PTP",
            "formID": spec.form_id,
            "componentID": spec.grid_id,
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
    parsed = parse_grid(spec, grid.body.decode("iso-8859-1"))
    if parsed.page_end != declared_total or len(parsed.rows) != declared_total:
        raise MunicipalExpensesContractError(
            f"Grade com {len(parsed.rows)} linhas (fim de página "
            f"{parsed.page_end}) para {declared_total} declaradas."
        )
    repeated_rows = validate_grid_rows(spec, parsed.rows, first=first, last=last)
    return MonthlyGrid(
        stage=spec.stage,
        source_code=SOURCE_CODE,
        endpoint_code=spec.endpoint_code,
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


def period_rule_form(
    first: date, last: date, spec: GridSpec = COMMITMENTS
) -> dict[str, str]:
    form = {
        "action": "executeRule",
        "pType": "2",
        "ruleName": spec.rule_name,
        "sys": "PTP",
        "formID": str(spec.form_id),
        "parentRID": "-1",
    }
    for index in range(RULE_PARAMETER_COUNT):
        form[f"P_{index}"] = ""
    form["P_0"] = first.strftime("%d/%m/%Y")
    form["P_1"] = last.strftime("%d/%m/%Y")
    # Valores enviados pelo próprio formulário em toda consulta observada.
    form.update(dict(spec.rule_extras))
    return form


def parse_declared_total(rule_script: str, grid_name: str = "DESPESAS") -> int:
    if "interactionError(" in rule_script:
        raise MunicipalExpensesError("A fonte recusou a consulta do período.")
    match = re.search(
        rf"\$c\('{re.escape(grid_name)}'\)\.setTotalRows\((\d+)\)", rule_script
    )
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
    return parse_grid(COMMITMENTS, script)


def parse_grid(spec: GridSpec, script: str) -> ParsedGrid:
    grid_id = spec.grid_id
    if f"d.c_{grid_id}.isLastPage = true;" not in script:
        raise MunicipalExpensesContractError("Grade paginada ou incompleta.")
    page_end = re.search(rf"d\.c_{grid_id}\.setGridPageEnd\((\d+)\);", script)
    if page_end is None:
        raise MunicipalExpensesContractError("Grade sem fim de página.")
    columns = re.search(rf"^cols_{grid_id} = \[(.*)\];$", script, re.MULTILINE)
    if columns is None:
        raise MunicipalExpensesContractError("Grade sem definição de colunas.")
    column_titles = {
        name: _unescape(title) for name, title in _COLUMN.findall(columns.group(1))
    }
    button_marker = f"d.c_{grid_id}.gridButton("
    rows: list[dict[str, str]] = []
    source_field_names: dict[str, str] = {}
    for line in script.split("\n"):
        if not line.startswith(spec.row_prefix):
            continue
        plain, _, button = line.partition(button_marker)
        row = {name: _unescape(value) for name, value in _PLAIN_FIELD.findall(plain)}
        if spec.hidden_fields:
            hidden = {
                f"field{component}": _unescape(value)
                for component, value in _HIDDEN_FIELD.findall(button)
            }
            for field in spec.hidden_fields:
                if field in hidden:
                    row.setdefault(field, hidden[field])
        rows.append(row)
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
    return validate_grid_rows(COMMITMENTS, rows, first=first, last=last)


def validate_grid_rows(
    spec: GridSpec,
    rows: tuple[dict[str, str], ...],
    *,
    first: date,
    last: date,
) -> int:
    """Valida a grade e devolve quantas linhas são repetições idênticas.

    A fonte repete linhas inteiras; a repetição fica preservada no bruto e
    só é aceita quando idêntica. Em estágio de chave única, a mesma chave com
    conteúdo diferente é falha.
    """
    seen_keys: set[str] = set()
    seen_rows: set[tuple[tuple[str, str], ...]] = set()
    repeated = 0
    for position, row in enumerate(rows, start=1):
        missing = [field for field in spec.required_fields if not row.get(field)]
        if missing:
            raise MunicipalExpensesContractError(
                f"Linha {position} sem campos obrigatórios: {', '.join(missing)}."
            )
        key = row[spec.key_field]
        if not _KEY.match(key):
            raise MunicipalExpensesContractError(
                f"Linha {position} com chave fora do padrão."
            )
        identity = tuple(sorted(row.items()))
        if identity in seen_rows:
            repeated += 1
            continue
        if spec.unique_key and key in seen_keys:
            raise MunicipalExpensesContractError(
                f"Linha {position} repete a chave com conteúdo diferente."
            )
        seen_rows.add(identity)
        seen_keys.add(key)
        if not spec.number_pattern.match(row[spec.number_field]):
            raise MunicipalExpensesContractError(
                f"Linha {position} com número fora do padrão."
            )
        parse_amount(row[spec.amount_field])
        issued = datetime.strptime(row[spec.date_field], "%d/%m/%Y").date()
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
