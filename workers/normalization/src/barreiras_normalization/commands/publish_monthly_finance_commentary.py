"""Publica explicações mensais validadas pela cascata de IA."""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from barreiras_docproc.assist import UrllibJsonCaller

from ..monthly_assist import MonthlyFinanceFacts, run_monthly_assistance


class MonthlyFinanceCommentaryRepository:
    def __init__(self, connection_factory) -> None:
        self.connection_factory = connection_factory

    @classmethod
    def from_dsn(cls, database_url: str) -> MonthlyFinanceCommentaryRepository:
        from barreiras_collectors.persistence.postgres import (
            PostgresCollectionRepository,
        )

        collection = PostgresCollectionRepository.from_dsn(database_url)
        return cls(collection.connection_factory)

    def pending_closures(
        self,
        *,
        limit: int,
        fiscal_year_from: int,
        fiscal_year_to: int,
    ) -> tuple[MonthlyFinanceFacts, ...]:
        connection = self.connection_factory()
        try:
            rows = connection.execute(
                """
                select closure.*
                from api.get_public_monthly_finance_closures(120, null) as closure
                where closure.fiscal_year between %s and %s
                  and not exists (
                    select 1
                    from editorial.monthly_finance_commentaries as commentary
                    where commentary.closure_id = closure.closure_id
                      and commentary.status = 'published'
                  )
                order by closure.period_start desc, closure.public_body_name
                limit %s
                """,
                (fiscal_year_from, fiscal_year_to, limit),
            )
            return tuple(
                MonthlyFinanceFacts(
                    closure_id=str(row["closure_id"]),
                    period_start=_date_text(row["period_start"]),
                    period_end=_date_text(row["period_end"]),
                    public_body_name=str(row["public_body_name"]),
                    closure_status=str(row["closure_status"]),
                    coverage_note=str(row["coverage_note"]),
                    revenue_report_amount=_decimal_text(row["revenue_report_amount"]),
                    expense_paid_amount=_decimal_text(row["expense_paid_amount"]),
                    operational_difference_amount=_decimal_text(
                        row["operational_difference_amount"]
                    ),
                )
                for row in rows.fetchall()
            )
        finally:
            connection.close()

    def persist(
        self,
        facts: MonthlyFinanceFacts,
        outcome,
    ) -> bool:
        if not outcome.provider or not outcome.model:
            raise ValueError("a cascata não informou provedor e modelo")
        connection = self.connection_factory()
        try:
            with connection.transaction():
                connection.execute("set local statement_timeout = '15s'")
                row = connection.execute(
                    """
                    with next_version as (
                      select coalesce(max(version), 0) + 1 as version
                      from editorial.monthly_finance_commentaries
                      where closure_id = %s
                    )
                    insert into editorial.monthly_finance_commentaries (
                      closure_id, public_body_name, fiscal_year,
                      period_start, period_end, facts, commentary,
                      statement_class, provider, model, prompt_version,
                      validator_version, raw_response, version, status
                    )
                    select
                      %s, %s, extract(year from %s::date)::smallint,
                      %s::date, %s::date, %s::jsonb, %s, %s, %s, %s,
                      %s, %s, %s::jsonb, next_version.version, 'published'
                    from next_version
                    on conflict (closure_id, version) do nothing
                    returning id
                    """,
                    (
                        facts.closure_id,
                        facts.closure_id,
                        facts.public_body_name,
                        facts.period_start,
                        facts.period_start,
                        facts.period_end,
                        json.dumps(_facts_dict(facts), ensure_ascii=False),
                        outcome.commentary,
                        outcome.statement_class,
                        outcome.provider,
                        outcome.model,
                        outcome.prompt_version,
                        outcome.validator_version,
                        json.dumps(outcome.raw_response, ensure_ascii=False),
                    ),
                ).fetchone()
                return row is not None
        finally:
            connection.close()


def _date_text(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _decimal_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _facts_dict(facts: MonthlyFinanceFacts) -> dict[str, object]:
    return {
        "period_start": facts.period_start,
        "period_end": facts.period_end,
        "public_body_name": facts.public_body_name,
        "closure_status": facts.closure_status,
        "coverage_note": facts.coverage_note,
        "revenue_report_amount": facts.revenue_report_amount,
        "expense_paid_amount": facts.expense_paid_amount,
        "operational_difference_amount": facts.operational_difference_amount,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publica comentários mensais validados pela cascata de IA."
    )
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--fiscal-year-from", type=int, default=2021)
    parser.add_argument("--fiscal-year-to", type=int, default=date.today().year)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 120:
        parser.error("--limit deve estar entre 1 e 120")
    if not 1900 <= args.fiscal_year_from <= args.fiscal_year_to <= 2200:
        parser.error("intervalo fiscal inválido")
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL é obrigatória")

    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), force=True)
    logger = logging.getLogger(__name__)
    repository = MonthlyFinanceCommentaryRepository.from_dsn(database_url)
    facts_list = repository.pending_closures(
        limit=args.limit,
        fiscal_year_from=args.fiscal_year_from,
        fiscal_year_to=args.fiscal_year_to,
    )
    caller = UrllibJsonCaller(timeout_seconds=60.0)
    published = 0
    rejected = 0
    unavailable = 0
    for facts in facts_list:
        try:
            outcome = run_monthly_assistance(
                caller,
                os.environ,
                facts,
                logger,
            )
            if repository.persist(facts, outcome):
                published += 1
        except Exception as error:  # um mês não bloqueia os demais.
            rejected += 1
            if type(error).__name__ == "CascadeUnavailableError":
                unavailable += 1
            logger.error(
                "monthly_finance_commentary_not_published closure=%s error=%s",
                facts.closure_id,
                str(error)[:500],
            )
    logger.info(
        "monthly_finance_commentary_completed closures=%s published=%s "
        "rejected=%s unavailable=%s",
        len(facts_list),
        published,
        rejected,
        unavailable,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
