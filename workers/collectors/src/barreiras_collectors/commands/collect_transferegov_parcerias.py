"""Preserva propostas, distribuicoes e parcerias do Transferegov."""

from __future__ import annotations

import argparse
import logging
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from zoneinfo import ZoneInfo

from ..collection_control import (
    CollectionControl,
    CollectionOutcome,
    build_execution_idempotency_key,
)
from ..connectors.transferegov import (
    DEFAULT_PAGE_SIZE,
    MAX_FINANCIAL_PAGE_SIZE,
    SOURCE_CODE,
    TransferegovError,
    TransferegovPage,
    fetch_commitments_page,
    fetch_partnerships_page,
    fetch_payable_documents_page,
    fetch_payment_orders_page,
    fetch_proposals_page,
    fetch_resource_distributions_page,
)
from ..logging import log_event
from ..persistence.models import RawRecordEvidence
from ..persistence.postgres import PostgresCollectionRepository
from ..persistence.service import (
    TRANSFEREGOV_COLLECTOR_VERSION,
    TRANSFEREGOV_PARSER_VERSION,
    TransferegovPersistenceService,
)
from ..resilience import CircuitBreaker
from ..settings import CollectorSettings, PersistenceSettings
from .pncp_runtime import build_authenticated_object_store

MUNICIPAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
MAX_PAGES_PER_RESOURCE = 100
MIN_FISCAL_YEAR = 2021
RELATED_ENDPOINT_NAMESPACES = {
    "distribuicoes-proposta": "tgov-distribuicoes",
    "parcerias-proposta": "tgov-parcerias",
    "empenhos-parceria": "tgov-empenhos",
    "documentos-habeis-parceria": "tgov-documentos",
    "ordens-pagamento-documento": "tgov-pagamentos",
}


@dataclass(frozen=True)
class TransferegovCollectionSummary:
    proposal_records: int
    related_records: int
    preserved_pages: int
    inserted_records: int
    existing_records: int
    manifest_records: int
    snapshot_fingerprint: str
    snapshot_records: tuple[RawRecordEvidence, ...]
    commitment_records: int = 0
    payable_document_records: int = 0
    payment_order_records: int = 0
    bank_order_records: int = 0
    distribution_records: int = 0
    partnership_records: int = 0

    def __post_init__(self) -> None:
        if self.manifest_records != self.observed_records:
            raise ValueError(
                "A contagem do manifesto diverge dos registros observados."
            )
        if re.fullmatch(r"[0-9a-f]{64}", self.snapshot_fingerprint) is None:
            raise ValueError("A impressão do snapshot deve ser SHA-256 hexadecimal.")
        expected_fingerprint = build_transferegov_snapshot_fingerprint(
            tuple(
                (
                    evidence.record_type,
                    evidence.source_record_key,
                    evidence.payload_sha256,
                )
                for evidence in self.snapshot_records
            )
        )
        if len(self.snapshot_records) != self.manifest_records:
            raise ValueError(
                "A evidência do snapshot diverge da contagem do manifesto."
            )
        if expected_fingerprint != self.snapshot_fingerprint:
            raise ValueError("A evidência do snapshot diverge da impressão declarada.")

    @property
    def observed_records(self) -> int:
        return (
            self.proposal_records
            + self.related_records
            + self.commitment_records
            + self.payable_document_records
            + self.payment_order_records
            + self.bank_order_records
        )

    @property
    def outcome(self) -> CollectionOutcome:
        if self.proposal_records == 0:
            return CollectionOutcome.EMPTY
        return CollectionOutcome.COMPLETE

    def records_for_endpoint(self, endpoint_code: str) -> int:
        """Retorna a contagem observada no endpoint oficial correspondente."""
        records_by_endpoint = {
            "propostas-barreiras": self.proposal_records,
            "distribuicoes-proposta": self.distribution_records,
            "parcerias-proposta": self.partnership_records,
            "empenhos-parceria": self.commitment_records,
            "documentos-habeis-parceria": self.payable_document_records,
            "ordens-pagamento-documento": self.payment_order_records,
        }
        try:
            return records_by_endpoint[endpoint_code]
        except KeyError as error:
            raise ValueError(
                f"Endpoint Transferegov sem contagem controlada: {endpoint_code}."
            ) from error


def execute_controlled_transferegov(
    *,
    control: CollectionControl,
    related_controls: Mapping[str, CollectionControl] | None = None,
    fiscal_year: int,
    operation: Callable[[], TransferegovCollectionSummary],
    snapshot_stager: Callable[[str, int, Sequence[RawRecordEvidence], str], object],
) -> TransferegovCollectionSummary:
    """Registra a tentativa antes de autenticar ou consultar a fonte."""
    with ExitStack() as stack:
        stack.enter_context(control)
        active_related_controls = {
            endpoint_code: stack.enter_context(related_control)
            for endpoint_code, related_control in (related_controls or {}).items()
        }
        summary = operation()
        snapshot_stager(
            control.run_id,
            fiscal_year,
            summary.snapshot_records,
            summary.snapshot_fingerprint,
        )
        for endpoint_code, related_control in active_related_controls.items():
            observed_records = summary.records_for_endpoint(endpoint_code)
            related_control.complete(
                outcome=(
                    CollectionOutcome.EMPTY
                    if observed_records == 0
                    else CollectionOutcome.COMPLETE
                ),
                observed_records=observed_records,
                checkpoint={
                    "fiscal_year": fiscal_year,
                    "parent_endpoint": "propostas-barreiras",
                    "proposal_records": summary.proposal_records,
                    "coverage_derivation": "full_parent_traversal",
                },
                metrics={
                    "fiscal_year": fiscal_year,
                    "observed_records": observed_records,
                    "proposal_records": summary.proposal_records,
                },
            )
        control.complete(
            outcome=summary.outcome,
            observed_records=summary.observed_records,
            checkpoint={
                "fiscal_year": fiscal_year,
                "preserved_pages": summary.preserved_pages,
                "proposal_records": summary.proposal_records,
                "manifest_records": summary.manifest_records,
                "snapshot_fingerprint": summary.snapshot_fingerprint,
            },
            metrics={
                "fiscal_year": fiscal_year,
                "proposal_records": summary.proposal_records,
                "related_records": summary.related_records,
                "distribution_records": summary.distribution_records,
                "partnership_records": summary.partnership_records,
                "preserved_pages": summary.preserved_pages,
                "inserted_records": summary.inserted_records,
                "existing_records": summary.existing_records,
                "commitment_records": summary.commitment_records,
                "payable_document_records": summary.payable_document_records,
                "payment_order_records": summary.payment_order_records,
                "bank_order_records": summary.bank_order_records,
                "manifest_records": summary.manifest_records,
                "snapshot_fingerprint": summary.snapshot_fingerprint,
            },
        )
    return summary


def validate_fiscal_year_range(
    year_from: int,
    year_to: int,
    *,
    current_year: int,
) -> tuple[int, ...]:
    """Valida o intervalo retroativo sem aceitar anos futuros ou anteriores a 2021."""
    values = (year_from, year_to, current_year)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError("Os anos fiscais devem ser inteiros.")
    if year_from < MIN_FISCAL_YEAR:
        raise ValueError(f"O ano inicial não pode ser anterior a {MIN_FISCAL_YEAR}.")
    if year_from > year_to:
        raise ValueError("O ano inicial não pode ser posterior ao ano final.")
    if year_to > current_year:
        raise ValueError("O ano final não pode estar no futuro.")
    return tuple(range(year_from, year_to + 1))


def execute_yearly_backfill(
    *,
    fiscal_years: Sequence[int],
    control_factory: Callable[[int], CollectionControl],
    operation_factory: Callable[[int], Callable[[], TransferegovCollectionSummary]],
    logger: logging.Logger,
    snapshot_stager: Callable[[str, int, Sequence[RawRecordEvidence], str], object],
    related_control_factory: (
        Callable[[int], Mapping[str, CollectionControl]] | None
    ) = None,
) -> tuple[tuple[int, TransferegovCollectionSummary], ...]:
    """Tenta cada ano isoladamente e só então reporta falhas agregadas."""
    completed: list[tuple[int, TransferegovCollectionSummary]] = []
    failures: list[tuple[int, Exception]] = []
    for fiscal_year in fiscal_years:
        try:
            summary = execute_controlled_transferegov(
                control=control_factory(fiscal_year),
                related_controls=(
                    related_control_factory(fiscal_year)
                    if related_control_factory is not None
                    else None
                ),
                fiscal_year=fiscal_year,
                operation=operation_factory(fiscal_year),
                snapshot_stager=snapshot_stager,
            )
        except Exception as error:
            failures.append((fiscal_year, error))
            log_event(
                logger,
                logging.ERROR,
                "collector_transferegov_year_failed",
                source=SOURCE_CODE,
                fiscal_year=fiscal_year,
                error_type=type(error).__name__,
            )
            continue
        completed.append((fiscal_year, summary))
        _log_year_completed(logger, fiscal_year=fiscal_year, summary=summary)

    if failures:
        failed_years = ", ".join(str(year) for year, _error in failures)
        raise TransferegovError(
            f"A coleta anual do Transferegov falhou em: {failed_years}."
        ) from failures[0][1]
    return tuple(completed)


def _log_year_completed(
    logger: logging.Logger,
    *,
    fiscal_year: int,
    summary: TransferegovCollectionSummary,
) -> None:
    log_event(
        logger,
        logging.INFO,
        "collector_transferegov_year_completed",
        source=SOURCE_CODE,
        fiscal_year=fiscal_year,
        coverage_status=summary.outcome.value,
        proposal_records=summary.proposal_records,
        related_records=summary.related_records,
        distribution_records=summary.distribution_records,
        partnership_records=summary.partnership_records,
        preserved_pages=summary.preserved_pages,
        inserted_records=summary.inserted_records,
        existing_records=summary.existing_records,
        commitment_records=summary.commitment_records,
        payable_document_records=summary.payable_document_records,
        payment_order_records=summary.payment_order_records,
        bank_order_records=summary.bank_order_records,
        manifest_records=summary.manifest_records,
        snapshot_fingerprint=summary.snapshot_fingerprint,
    )


def build_transferegov_snapshot_fingerprint(
    records: Sequence[tuple[str, str, str]],
) -> str:
    """Resume chaves e hashes normalizados sem expor o conteúdo coletado."""
    canonical_lines: list[str] = []
    for record_type, source_record_key, payload_sha256 in records:
        if not record_type or not source_record_key:
            raise ValueError("O manifesto exige tipo e chave de origem.")
        if re.fullmatch(r"[0-9a-f]{64}", payload_sha256) is None:
            raise ValueError("O manifesto exige hash de payload válido.")
        canonical_lines.append(
            "\x1f".join((record_type, source_record_key, payload_sha256))
        )
    return sha256("\n".join(sorted(canonical_lines)).encode("utf-8")).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preserva o retrato oficial das propostas destinadas a Barreiras "
            "e seus recursos relacionados, sem calcular totais financeiros."
        )
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help="Quantidade solicitada por pagina da API oficial.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=MAX_PAGES_PER_RESOURCE,
        help="Limite de seguranca por recurso e proposta.",
    )
    current_year = datetime.now(MUNICIPAL_TIMEZONE).year
    parser.add_argument(
        "--year-from",
        type=int,
        default=MIN_FISCAL_YEAR,
        help=f"Primeiro ano fiscal a consultar (minimo: {MIN_FISCAL_YEAR}).",
    )
    parser.add_argument(
        "--year-to",
        type=int,
        default=current_year,
        help="Ultimo ano fiscal a consultar (padrao: ano municipal atual).",
    )
    arguments = parser.parse_args(argv)
    if arguments.page_size < 1:
        parser.error("--page-size deve ser positivo.")
    if arguments.max_pages < 1:
        parser.error("--max-pages deve ser positivo.")
    try:
        fiscal_years = validate_fiscal_year_range(
            arguments.year_from,
            arguments.year_to,
            current_year=current_year,
        )
    except ValueError as error:
        parser.error(str(error))

    collector_settings = CollectorSettings.from_env()
    persistence_settings = PersistenceSettings.from_env()
    logging.basicConfig(
        level=getattr(logging, collector_settings.log_level),
        format="%(message)s",
        force=True,
    )
    if persistence_settings.mode != "postgres-supabase":
        raise RuntimeError(
            "A coleta Transferegov requer PERSISTENCE_MODE=postgres-supabase."
        )
    if persistence_settings.database_url is None:
        raise RuntimeError("Configuracao de banco incompleta.")

    repository = PostgresCollectionRepository.from_dsn(
        persistence_settings.database_url
    )
    logger = logging.getLogger(__name__)

    def control_factory(fiscal_year: int) -> CollectionControl:
        return CollectionControl(
            repository=repository,
            source_code=SOURCE_CODE,
            endpoint_code="propostas-barreiras",
            idempotency_key=build_execution_idempotency_key(
                f"transferegov-parcerias-{fiscal_year}"
            ),
            collector_version=TRANSFEREGOV_COLLECTOR_VERSION,
            parser_version=TRANSFEREGOV_PARSER_VERSION,
            partition_key=f"fiscal-year:{fiscal_year}",
            period_start=date(fiscal_year, 1, 1),
            period_end=date(fiscal_year, 12, 31),
        )

    def operation_factory(
        fiscal_year: int,
    ) -> Callable[[], TransferegovCollectionSummary]:
        def operation() -> TransferegovCollectionSummary:
            service = TransferegovPersistenceService(
                object_store=build_authenticated_object_store(persistence_settings),
                repository=repository,
            )
            return _collect_snapshot(
                service=service,
                fiscal_year=fiscal_year,
                page_size=arguments.page_size,
                max_pages=arguments.max_pages,
                logger=logger,
            )

        return operation

    def related_control_factory(
        fiscal_year: int,
    ) -> Mapping[str, CollectionControl]:
        return {
            endpoint_code: CollectionControl(
                repository=repository,
                source_code=SOURCE_CODE,
                endpoint_code=endpoint_code,
                idempotency_key=build_execution_idempotency_key(
                    f"{namespace}-{fiscal_year}"
                ),
                collector_version=TRANSFEREGOV_COLLECTOR_VERSION,
                parser_version=TRANSFEREGOV_PARSER_VERSION,
                partition_key=f"fiscal-year:{fiscal_year}",
                period_start=date(fiscal_year, 1, 1),
                period_end=date(fiscal_year, 12, 31),
            )
            for endpoint_code, namespace in RELATED_ENDPOINT_NAMESPACES.items()
        }

    execute_yearly_backfill(
        fiscal_years=fiscal_years,
        control_factory=control_factory,
        operation_factory=operation_factory,
        logger=logger,
        related_control_factory=related_control_factory,
        snapshot_stager=repository.stage_transferegov_snapshot,
    )
    return 0


def _collect_snapshot(
    *,
    service: TransferegovPersistenceService,
    fiscal_year: int,
    page_size: int,
    max_pages: int,
    logger: logging.Logger,
) -> TransferegovCollectionSummary:
    breaker = CircuitBreaker(failure_threshold=4)
    proposal_records = related_records = 0
    distribution_records = partnership_records = 0
    commitment_records = payable_document_records = 0
    payment_order_records = bank_order_records = 0
    preserved_pages = inserted_records = existing_records = 0
    record_evidence: list[RawRecordEvidence] = []
    proposal_ids: set[int] = set()
    partnership_ids: set[int] = set()
    document_ids: set[int] = set()

    def preserve(page: TransferegovPage) -> None:
        nonlocal preserved_pages, inserted_records, existing_records
        result = service.persist(page)
        preserved_pages += 1
        inserted_records += result.inserted_records
        existing_records += result.existing_records
        record_evidence.extend(result.record_evidence)
        log_event(
            logger,
            logging.INFO,
            "collector_transferegov_page_persisted",
            source=SOURCE_CODE,
            endpoint=page.endpoint_code,
            page=page.cursor["page"],
            records=len(page.items),
            artifact_hash=page.body_sha256,
            inserted_records=result.inserted_records,
            existing_records=result.existing_records,
        )

    proposal_pages = _fetch_all_pages(
        fetch=lambda number: fetch_proposals_page(
            page=number,
            page_size=page_size,
            fiscal_year=fiscal_year,
            circuit_breaker=breaker,
            logger=logger,
        ),
        max_pages=max_pages,
        resource="propostas",
    )
    for page in proposal_pages:
        preserve(page)
        proposal_records += len(page.items)
        for item in page.items:
            identifier = item["id_proposta"]
            if identifier in proposal_ids:
                raise TransferegovError(
                    f"A proposta {identifier} apareceu mais de uma vez no retrato."
                )
            proposal_ids.add(identifier)

    validated_ids = frozenset(proposal_ids)
    for proposal_id in sorted(validated_ids):
        distribution_pages = _fetch_all_pages(
            fetch=lambda number, proposal_id=proposal_id: (
                fetch_resource_distributions_page(
                    proposal_id=proposal_id,
                    validated_proposal_ids=validated_ids,
                    page=number,
                    page_size=page_size,
                    circuit_breaker=breaker,
                    logger=logger,
                )
            ),
            max_pages=max_pages,
            resource=f"distribuicoes:{proposal_id}",
        )
        for page in distribution_pages:
            preserve(page)
            related_records += len(page.items)
            distribution_records += len(page.items)

        partnership_pages = _fetch_all_pages(
            fetch=lambda number, proposal_id=proposal_id: fetch_partnerships_page(
                proposal_id=proposal_id,
                validated_proposal_ids=validated_ids,
                page=number,
                page_size=page_size,
                circuit_breaker=breaker,
                logger=logger,
            ),
            max_pages=max_pages,
            resource=f"parcerias:{proposal_id}",
        )
        for page in partnership_pages:
            preserve(page)
            related_records += len(page.items)
            partnership_records += len(page.items)
            for item in page.items:
                identifier = item["id_parceria"]
                if identifier in partnership_ids:
                    raise TransferegovError(
                        f"A parceria {identifier} apareceu mais de uma vez."
                    )
                partnership_ids.add(identifier)

    validated_partnership_ids = frozenset(partnership_ids)
    financial_page_size = min(page_size, MAX_FINANCIAL_PAGE_SIZE)
    for partnership_id in sorted(validated_partnership_ids):
        commitment_pages = _fetch_all_pages(
            fetch=lambda number, partnership_id=partnership_id: fetch_commitments_page(
                partnership_id=partnership_id,
                validated_partnership_ids=validated_partnership_ids,
                page=number,
                page_size=financial_page_size,
                circuit_breaker=breaker,
                logger=logger,
            ),
            max_pages=max_pages,
            resource=f"empenhos:{partnership_id}",
        )
        for page in commitment_pages:
            preserve(page)
            commitment_records += len(page.items)

        document_pages = _fetch_all_pages(
            fetch=lambda number, partnership_id=partnership_id: (
                fetch_payable_documents_page(
                    partnership_id=partnership_id,
                    validated_partnership_ids=validated_partnership_ids,
                    page=number,
                    page_size=financial_page_size,
                    circuit_breaker=breaker,
                    logger=logger,
                )
            ),
            max_pages=max_pages,
            resource=f"documentos-habeis:{partnership_id}",
        )
        for page in document_pages:
            preserve(page)
            payable_document_records += len(page.items)
            for item in page.items:
                identifier = item["id_documento_habil"]
                if identifier in document_ids:
                    raise TransferegovError(
                        f"O documento hábil {identifier} apareceu mais de uma vez."
                    )
                document_ids.add(identifier)

    validated_document_ids = frozenset(document_ids)
    for document_id in sorted(validated_document_ids):
        order_pages = _fetch_all_pages(
            fetch=lambda number, document_id=document_id: fetch_payment_orders_page(
                document_id=document_id,
                validated_document_ids=validated_document_ids,
                page=number,
                page_size=financial_page_size,
                circuit_breaker=breaker,
                logger=logger,
            ),
            max_pages=max_pages,
            resource=f"ordens-pagamento:{document_id}",
        )
        for page in order_pages:
            preserve(page)
            payment_order_records += len(page.items)
            bank_order_records += sum(
                isinstance(item.get("nr_ordem_bancaria"), str)
                and bool(item["nr_ordem_bancaria"].strip())
                for item in page.items
            )

    manifest_records = len(record_evidence)
    observed_records = (
        proposal_records
        + related_records
        + commitment_records
        + payable_document_records
        + payment_order_records
        + bank_order_records
    )
    if manifest_records != observed_records:
        raise TransferegovError(
            "O manifesto normalizado diverge dos registros observados."
        )
    return TransferegovCollectionSummary(
        proposal_records=proposal_records,
        related_records=related_records,
        preserved_pages=preserved_pages,
        inserted_records=inserted_records,
        existing_records=existing_records,
        manifest_records=manifest_records,
        snapshot_fingerprint=build_transferegov_snapshot_fingerprint(
            tuple(
                (
                    evidence.record_type,
                    evidence.source_record_key,
                    evidence.payload_sha256,
                )
                for evidence in record_evidence
            )
        ),
        snapshot_records=tuple(record_evidence),
        commitment_records=commitment_records,
        payable_document_records=payable_document_records,
        payment_order_records=payment_order_records,
        bank_order_records=bank_order_records,
        distribution_records=distribution_records,
        partnership_records=partnership_records,
    )


def _fetch_all_pages(
    *,
    fetch: Callable[[int], TransferegovPage],
    max_pages: int,
    resource: str,
) -> Iterator[TransferegovPage]:
    page_number = 1
    while page_number <= max_pages:
        page = fetch(page_number)
        yield page
        if page.total_pages == 0 or page_number >= page.total_pages:
            return
        page_number += 1
    raise TransferegovError(
        f"A paginacao de {resource} excedeu o limite seguro de {max_pages}."
    )


if __name__ == "__main__":
    raise SystemExit(main())
