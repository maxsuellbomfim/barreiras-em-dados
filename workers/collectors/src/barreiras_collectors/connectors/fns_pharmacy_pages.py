"""Bounded private Farmacia Popular inspection, never publication approval."""

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal
from urllib.parse import parse_qsl, urlsplit

from .fns_payment_evidence import (
    MAX_RESPONSE_BYTES,
    _money,
    _reject_constant,
    _require,
    _unique_object,
)


def inspect_pharmacy_capture(
    capture: dict, *, beneficiary: str, payment_year: int
) -> dict:
    """Inspect a single complete page bound to trusted acquisition metadata.

    Beneficiary is an opaque request identifier, NOT a verified legal entity.
    Do not publish it, infer nature from its length, or reuse municipal CGU
    reconciliation. Multi-page responses require a future pagination adapter.
    Originals/metadata stay private; matching hashes do not authenticate a source.
    """
    try:
        _require(
            isinstance(beneficiary, str) and re.fullmatch(r"[0-9]{1,14}", beneficiary)
        )
        _require(type(payment_year) is int and 2021 <= payment_year <= 2100)
        raw = capture["body"]
        _require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_RESPONSE_BYTES)
        _require(type(capture["http_status"]) is int and capture["http_status"] == 200)
        _require(type(capture["byte_size"]) is int and capture["byte_size"] == len(raw))
        sha = hashlib.sha256(raw).hexdigest()
        _require(sha == capture["sha256"])
        url = capture["request_url"]
        _require(isinstance(url, str) and not any(c.isspace() for c in url))
        _require(url == capture["final_url"])
        parsed = urlsplit(url)
        _require(
            parsed.scheme == "https" and parsed.netloc == "consultafns.saude.gov.br"
        )
        _require(parsed.path == "/recursos/consulta-detalhada/detalhe-pagamento")
        _require(not parsed.fragment)
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        query = dict(pairs)
        expected = dict(
            ano=str(payment_year),
            tipoConsulta="3",
            estado="BA",
            municipio="290320",
            page="1",
            count="25",
            cpfCnpjUg=beneficiary,
        )
        _require(len(pairs) == len(query) and query == expected)
        data = json.loads(
            raw,
            parse_float=Decimal,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )["resultado"]
        _require(
            all(
                type(data[k]) is int
                for k in ("pagina", "total", "totalPaginas", "itensPorPagina")
            )
        )
        rows = data["dados"]
        _require(isinstance(rows, list) and 0 < len(rows) <= 25)
        _require(data["pagina"] == 0 and data["totalPaginas"] == 1)
        _require(data["total"] == len(rows) and data["itensPorPagina"] == 25)
        _require(all(isinstance(r, dict) for r in rows))
        if any(r.get("nomeComponente") != "FARMACIA POPULAR" for r in rows):
            return dict(status="unsupported_program", publication_allowed=False)
        totals = dict(gross=Decimal(0), discount=Decimal(0), net=Decimal(0))
        fields = dict(
            gross="valorTotal", discount="valorDescontoTotal", net="valorLiquido"
        )
        general = dict(
            gross="valorTotalGeral",
            discount="valorDescontoTotalGeral",
            net="valorLiquidoGeral",
        )
        records, keys, reasons = [], set(), set()
        for position, row in enumerate(rows, 1):
            _require(
                row["uf"] == "BA" and str(row["anoPagamento"]) == str(payment_year)
            )
            _require(row["id"]["esferaAdministrativa"] == "PRIVADA")
            action = row["id"]["programaFundo"]["id"]
            _require(type(action) is int and action > 0)
            date = datetime.strptime(row["dataCriacaoSiafi"], "%d/%m/%Y").date()
            _require(
                date.year == payment_year and row["mesPagamento"] == f"{date.month:02}"
            )
            document = row["numeroDocumentoSiafi"]
            _require(isinstance(document, str) and re.fullmatch(r"[0-9]{6}", document))
            _require(row["tipoDocumentoPagamento"] == "OB")
            # Only a private documentary key; no cross-source identity assertion.
            key = hashlib.sha256(
                json.dumps(
                    [beneficiary, payment_year, document, date.isoformat(), action]
                ).encode()
            ).hexdigest()
            if key in keys:
                reasons.add("repeated_document_key")
            keys.add(key)
            amounts = {k: _money(row[f]) for k, f in fields.items()}
            if amounts["gross"] - amounts["discount"] != amounts["net"]:
                reasons.add("unbalanced_amounts")
            if _money(row["valorAnulacao"]):
                reasons.add("source_annulment")
            _require(isinstance(row["motivoRejeicao"], str))
            if row["motivoRejeicao"]:
                reasons.add("source_rejection")
            records.append(
                dict(
                    document_key=key,
                    document_date=date.isoformat(),
                    source_row=position,
                    source_sha256=sha,
                    amounts={k: f"{v:.2f}" for k, v in amounts.items()},
                )
            )
            for k, value in amounts.items():
                totals[k] += value
        for key, field in general.items():
            declared = {_money(r[field]) for r in rows if r.get(field) is not None}
            if declared != {totals[key]}:
                reasons.add("source_total_mismatch")
        return dict(
            status="review_required" if reasons else "documentary_consistent",
            records=records,
            review_reasons=sorted(reasons),
            publication_allowed=False,
            identity_verification="pending",
            reconciliation="pending",
            document_totals={k: f"{v:.2f}" for k, v in totals.items()},
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        ArithmeticError,
        RecursionError,
        AttributeError,
    ):
        return dict(status="invalid_capture", publication_allowed=False)
