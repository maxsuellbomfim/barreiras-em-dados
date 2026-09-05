"""Validated FNS evidence; intentionally not a publication or identity resolver."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

MAX_RESPONSE_BYTES = 128 * 1024
_OBSERVATION = re.compile(
    r"PAGAMENTO DA PROPOSTA (?P<proposal>[0-9]{17}) - UF BA - "
    r"EMENDA: \((?P<amendment>[0-9]{8})\) (?P<author>[^:()\n\r]+?)"
    r"(?: - SOLICITANTE: \((?P<requester_code>[0-9]{4})\) "
    r"(?P<requester>[^:()\n\r]+))?"
)


class FNSPaymentEvidenceError(ValueError):
    """The response cannot safely be interpreted by this bounded reader."""


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("Unsupported FNS evidence")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("Nonfinite JSON number")


def _single_row(body: bytes) -> dict:
    _require(isinstance(body, bytes) and 0 < len(body) <= MAX_RESPONSE_BYTES)
    result = json.loads(
        body,
        parse_float=Decimal,
        parse_constant=_reject_constant,
        object_pairs_hook=_unique_object,
    )["resultado"]
    # A bounded pilot reader, not a pagination/coverage engine. Never accept
    # a partial page or an empty response as evidence of a completed payment.
    for key in ("total", "totalPaginas"):
        _require(type(result[key]) is int and result[key] == 1)
    _require(type(result["pagina"]) is int and result["pagina"] in (0, 1))
    _require(type(result["itensPorPagina"]) is int and result["itensPorPagina"] > 0)
    rows = result["dados"]
    _require(isinstance(rows, list) and len(rows) == 1)
    _require(isinstance(rows[0], dict))
    return rows[0]


def _money(value: object) -> Decimal:
    _require(type(value) in (int, str, Decimal))
    text = str(value)
    # Bound precision, avoid nonfinite values and reject fractional centavos.
    _require(re.fullmatch(r"[0-9]{1,15}(?:\.[0-9]{1,2})?", text) is not None)
    return Decimal(text)


def _digits(value: object, width: int) -> str:
    _require(isinstance(value, str))
    _require(re.fullmatch(rf"[0-9]{{{width}}}", value) is not None)
    return value


def _name(value: str) -> str:
    _require(2 <= len(value) <= 120 and value == value.strip())
    _require(all(char.isalpha() or char in " '-" for char in value))
    _require(any(char.isalpha() for char in value))
    return value


def parse_fns_payment_evidence(
    payment_body: bytes,
    order_body: bytes,
    *,
    action_id: int,
    payment_year: int,
    order_number: str,
) -> dict:
    """Read one municipal FAF payment and its corresponding OB response.

    The caller supplies responses from the exact payment/OB request scope.
    Raw bytes may contain bank data and must stay in private storage. This
    function emits only allowlisted evidence, never raw fields or exception
    details. An unsupported response must be retained for review, not dropped.

    The OB endpoint does not report UG/gestao; its number is not a global key.
    No CGU match, person ID, amendment year or publication decision is inferred.
    """
    try:
        return _parse(payment_body, order_body, action_id, payment_year, order_number)
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        RecursionError,
        InvalidOperation,
        OverflowError,
    ):
        # Do not let source text, JSON decoder excerpts or bank data escape.
        raise FNSPaymentEvidenceError(
            "Evidência FNS incompatível com o escopo ou formato validado; "
            "revisão necessária."
        ) from None


def _parse(
    payment_body: bytes,
    order_body: bytes,
    action_id: int,
    payment_year: int,
    order_number: str,
) -> dict:
    _require(type(action_id) is int and action_id > 0)
    _require(type(payment_year) is int and 2021 <= payment_year <= 2100)
    _digits(order_number, 6)
    payment, order = _single_row(payment_body), _single_row(order_body)
    identity = payment["id"]
    _require(identity["esferaAdministrativa"] == "MUNICIPAL")
    _require(identity["indicadorFundoAFundo"] == "S")
    _require(type(identity["programaFundo"]["id"]) is int)
    _require(identity["programaFundo"]["id"] == action_id)
    _require(payment["numeroDocumentoSiafi"] == order_number)
    _require(payment["tipoDocumentoPagamento"] == "OB")
    _require(payment["uf"] == order["uf"] == "BA")
    _require(order["codigoIBGE"] == "290320")
    _require(order["municipio"] == "BARREIRAS")
    _require(payment["motivoRejeicao"] == order["motivoRejeicao"] == "")
    _require(_money(payment["valorAnulacao"]) == 0)
    year = str(payment_year)
    _require(payment["anoPagamento"] == order["anoExercicio"] == year)
    # Cross-year/competence variants have not been validated by this pilot.
    _require(identity["ano"] == year)
    month = _digits(payment["mesPagamento"], 2)
    _require(order["mesExercicio"] == identity["mes"] == month)
    competence = f"Única em {payment_year}"
    _require(payment["competencia"] == competence)
    # Reproduced on the official OB endpoint even with a correct UTF-8 query:
    # this one echoed field is decoded as Latin-1. Accept the exact observed
    # variant only; never repair arbitrary names, observations or source bytes.
    _require(
        order["competencia"]
        in (competence, competence.encode("utf-8").decode("latin-1"))
    )
    raw_date = payment["dataCriacaoSiafi"]
    _require(isinstance(raw_date, str))
    date = datetime.strptime(raw_date, "%d/%m/%Y").date()
    _require(date.strftime("%d/%m/%Y") == raw_date)
    _require(date.year == payment_year and date.month == int(month))
    gross = _money(payment["valorTotal"])
    deduction = _money(payment["valorDescontoTotal"])
    paid = _money(payment["valorLiquido"])
    _require(gross - deduction == paid and paid > 0)
    _require(_money(order["valor"]) == _money(order["valorTotal"]) == paid)
    proposal = _digits(
        identity["processoEntidadePrograma"]["projeto"]["numeroSubprojeto"], 17
    )
    observation = order["dsObservacao"]
    _require(isinstance(observation, str) and len(observation) <= 500)
    match = _OBSERVATION.fullmatch(observation)
    if match is None:
        raise ValueError("Unsupported observation")
    _require(match["proposal"] == proposal)
    author = _name(match["author"])
    requester = _name(match["requester"]) if match["requester"] else None
    return {
        "schema_version": "fns-payment-evidence-v1",
        "action_id": action_id,
        "payment_year": payment_year,
        "order_number": order_number,
        "document_date": date.isoformat(),
        "proposal_number": proposal,
        "amendment_number": match["amendment"],
        "amendment_year": None,
        "author_name": author,
        "requester_name": requester,
        "requester_source_code": match["requester_code"],
        # Explicit official FNS-to-IBGE mapping, never a generic truncation.
        "municipality_ibge": "2903201",
        "paid_amount": f"{paid:.2f}",
        "gross_amount": f"{gross:.2f}",
        "deduction_amount": f"{deduction:.2f}",
        "payment_sha256": hashlib.sha256(payment_body).hexdigest(),
        "order_sha256": hashlib.sha256(order_body).hexdigest(),
        "link_status": "unlinked",
    }
