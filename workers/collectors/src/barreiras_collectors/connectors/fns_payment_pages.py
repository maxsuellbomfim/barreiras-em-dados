"""Private normalized observations, not confirmed transfers or amendments."""

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal

from .fns_payment_evidence import (
    MAX_RESPONSE_BYTES,
    _money,
    _reject_constant,
    _require,
    _unique_object,
)


def normalize_payment_pages(
    pages: list[bytes], *, action_id: int, payment_year: int
) -> dict:
    """Caller must bind originals to the same action/year/municipality request.

    Keeps every observation and its position/hash. Documentary sums are not
    paid totals: rejected rows stay present. No author or person is inferred.
    """
    try:
        _require(type(action_id) is int and action_id > 0)
        _require(type(payment_year) is int and 2021 <= payment_year <= 2100)
        _require(isinstance(pages, list) and 0 < len(pages) <= 100)
        records, hashes = [], []
        totals = dict(gross=Decimal(0), discount=Decimal(0), net=Decimal(0))
        metadata = None
        for index, raw in enumerate(pages):
            _require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_RESPONSE_BYTES)
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
            total, count = data["total"], data["itensPorPagina"]
            _require(total > 0 and count > 0 and data["pagina"] == index)
            _require(data["totalPaginas"] == len(pages) == (total + count - 1) // count)
            current = (total, count)
            if metadata is None:
                metadata = current
            _require(metadata == current)
            rows = data["dados"]
            _require(
                isinstance(rows, list)
                and len(rows) == min(count, total - index * count)
            )
            sha = hashlib.sha256(raw).hexdigest()
            _require(sha not in hashes)
            hashes.append(sha)
            for position, row in enumerate(rows):
                _require(isinstance(row, dict) and row["uf"] == "BA")
                _require(str(row["anoPagamento"]) == str(payment_year))
                document = row["numeroDocumentoSiafi"]
                _require(
                    isinstance(document, str)
                    and re.fullmatch(r"[0-9]{6}", document) is not None
                )
                _require(row["tipoDocumentoPagamento"] == "OB")
                date = datetime.strptime(row["dataCriacaoSiafi"], "%d/%m/%Y").date()
                _require(
                    date.year == payment_year
                    and row["mesPagamento"] == f"{date.month:02}"
                )
                identity = row["id"]
                _require(identity["esferaAdministrativa"] == "MUNICIPAL")
                _require(identity["indicadorFundoAFundo"] == "S")
                _require(
                    type(identity["programaFundo"]["id"]) is int
                    and identity["programaFundo"]["id"] == action_id
                )
                year, month = str(identity["ano"]), identity["mes"]
                _require(re.fullmatch(r"[0-9]{4}", year) is not None)
                _require(
                    isinstance(month, str)
                    and re.fullmatch(r"0[1-9]|1[0-2]", month) is not None
                )
                process = identity["processoFormatado"]
                _require(
                    isinstance(process, str)
                    and re.fullmatch(r"[0-9]{5}\.[0-9]{6}/[0-9]{4}-[0-9]{2}", process)
                    is not None
                )
                competence = row["competencia"]
                _require(isinstance(competence, str) and 0 < len(competence) <= 80)
                reason = row["motivoRejeicao"]
                _require(isinstance(reason, str))
                money = {
                    k: _money(row[f])
                    for k, f in [
                        ("gross", "valorTotal"),
                        ("discount", "valorDescontoTotal"),
                        ("net", "valorLiquido"),
                    ]
                }
                annulment = _money(row["valorAnulacao"])
                reasons = []
                if reason:
                    reasons.append("source_rejection")
                if annulment:
                    reasons.append("source_annulment")
                if money["gross"] - money["discount"] != money["net"]:
                    reasons.append("unbalanced_amounts")
                scope = dict(
                    anoPagamento=str(payment_year),
                    ano=year,
                    mes=month,
                    competencia=competence,
                    uf="BA",
                    numeroDocumentoSiafi=document,
                    tipoDocumentoPagamento="OB",
                )
                key = hashlib.sha256(
                    json.dumps(
                        [action_id, scope, process, date.isoformat()], sort_keys=True
                    ).encode()
                ).hexdigest()
                records.append(
                    dict(
                        document_key=key,
                        action_id=action_id,
                        document_date=date.isoformat(),
                        process_number=process,
                        order_scope=scope,
                        source_sha256=sha,
                        source_page=index + 1,
                        source_row=position + 1,
                        amounts={k: f"{v:.2f}" for k, v in money.items()},
                        annulment=f"{annulment:.2f}",
                        review_reasons=reasons,
                        order_verification="pending",
                        publication_allowed=False,
                    )
                )
                for k, v in money.items():
                    totals[k] += v
        counts = Counter(r["document_key"] for r in records)
        for record in records:
            if counts[record["document_key"]] > 1:
                record["review_reasons"].append("repeated_document_key")
        return dict(
            status="review_required"
            if any(r["review_reasons"] for r in records)
            else "normalized",
            records=records,
            page_sha256=hashes,
            document_totals={k: f"{v:.2f}" for k, v in totals.items()},
            publication_allowed=False,
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
        return dict(status="invalid_pages", publication_allowed=False)
