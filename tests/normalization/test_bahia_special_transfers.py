from __future__ import annotations

import csv
import io
import unittest
import zipfile
from decimal import Decimal

from barreiras_collectors.connectors.bahia_special_transfers import (
    EXPECTED_MEMBER_COLUMNS,
    PAYMENT_MEMBER_NAME,
)

CENTRALIZATION_MEMBER = (
    "VW_PAINEL_TRANSFERENCIA_ESPECIAL_CENTRALIZACAO_DESCENTRALIZACAO.csv"
)
EXPENSE_MEMBER = "VW_PAINEL_TRANSFERENCIA_ESPECIAL_DESPESA.csv"


def _csv_bytes(columns: tuple[str, ...], rows: list[tuple[str, ...]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def _archive(
    *,
    centralization_rows: list[tuple[str, ...]],
    expense_rows: list[tuple[str, ...]],
    payment_rows: list[tuple[str, ...]],
    break_object_quotes: bool = False,
) -> bytes:
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for member, columns in EXPECTED_MEMBER_COLUMNS.items():
            rows: list[tuple[str, ...]] = []
            if member == CENTRALIZATION_MEMBER:
                rows = centralization_rows
            elif member == EXPENSE_MEMBER:
                rows = expense_rows
            elif member == PAYMENT_MEMBER_NAME:
                rows = payment_rows
            content = _csv_bytes(columns, rows)
            if member == PAYMENT_MEMBER_NAME and break_object_quotes:
                content = content.replace(b'""kits""', b'"kits"')
            package.writestr(member, content)
    return body.getvalue()


def _centralization(
    *,
    expense_code: str = "2022.3.20.60101.414.3054.4072.5",
    execution_code: str = "2022.3.20.60101.414.3054.4072.5",
    liquidation_code: str = "2022.500001.60101.1.4072.414.3054.51511.5",
) -> tuple[str, ...]:
    return (
        expense_code,
        execution_code,
        liquidation_code,
        "Secretaria de Infraestrutura Hídrica",
    )


def _expense(
    *,
    expense_code: str = "2022.3.20.60101.414.3054.4072.5",
) -> tuple[str, ...]:
    return (
        "2022",
        "Secretaria de Infraestrutura Hídrica",
        "SIHS",
        "Coordenação de Recursos Hídricos",
        "CRH",
        "Ministério do Desenvolvimento Regional",
        "40720003",
        "2021",
        "Tito",
        "Implantação de Infraestrutura Hídrica",
        "4072",
        expense_code,
        "594841,25",
        "594841,25",
        "594841,25",
        "594841,25",
        "594841,25",
    )


def _payment(
    *,
    payment_id: str = "1234567890123456789",
    object_text: str = 'Aquisição de "kits"; peças para poços em Barreiras/BA',
    execution_code: str = "2022.3.20.60101.414.3054.4072.5",
    payment_date: str = "05/10/2022",
    gcv_amount: str = "0,00",
) -> tuple[str, ...]:
    return (
        payment_id,
        "2022.0001.00001",
        "98765432100",
        "CREDOR QUE NÃO DEVE SER PUBLICADO",
        payment_date,
        "594841,25",
        gcv_amount,
        object_text,
        "2022.60101.00001",
        "2022",
        execution_code,
        "Sim",
        "https://www.transparencia.ba.gov.br/Pagamentos/Detalhe/123",
    )


class BahiaSpecialTransferNormalizationTests(unittest.TestCase):
    def test_counts_every_payment_by_year_without_exposing_creditor_data(
        self,
    ) -> None:
        try:
            from barreiras_normalization.bahia_special_transfers import (
                analyze_special_transfer_payments,
            )
        except ImportError:
            self.fail("a cobertura anual das transferências especiais não existe")
        archive = _archive(
            centralization_rows=[_centralization()],
            expense_rows=[_expense()],
            payment_rows=[
                _payment(),
                _payment(
                    payment_id="2234567890123456789",
                    object_text="Perfuração de poços em Barreirinhas/MA",
                ),
            ],
        )

        analysis = analyze_special_transfer_payments(archive)

        self.assertEqual(len(analysis.candidates), 1)
        self.assertEqual(len(analysis.annual_coverage), 1)
        coverage = analysis.annual_coverage[0]
        self.assertEqual(coverage.fiscal_year, 2022)
        self.assertEqual(coverage.source_payment_count, 2)
        self.assertEqual(coverage.territorial_payment_count, 1)
        self.assertNotIn("98765432100", str(coverage))
        self.assertNotIn("CREDOR QUE NÃO DEVE SER PUBLICADO", str(coverage))

    def test_joins_official_keys_and_keeps_only_literal_barreiras_candidate(
        self,
    ) -> None:
        try:
            from barreiras_normalization.bahia_special_transfers import (
                parse_special_transfer_payment_candidates,
            )
        except ImportError:
            self.fail("o normalizador de transferências especiais ainda não existe")
        archive = _archive(
            centralization_rows=[_centralization()],
            expense_rows=[_expense()],
            payment_rows=[
                _payment(),
                _payment(
                    payment_id="2234567890123456789",
                    object_text="Perfuração de poços em Barreirinhas/MA",
                ),
            ],
            break_object_quotes=True,
        )

        candidates = parse_special_transfer_payment_candidates(archive)

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.amendment_number, "40720003")
        self.assertEqual(candidate.amendment_year, 2021)
        self.assertEqual(candidate.author_name, "Tito")
        self.assertEqual(candidate.payment_amount, Decimal("594841.25"))
        self.assertEqual(candidate.payment_status, "Sim")
        self.assertEqual(candidate.payment_date.isoformat(), "2022-10-05")
        self.assertIn('"kits"; peças', candidate.object_text)
        self.assertEqual(
            candidate.territorial_scope,
            "payment_object_literal_barreiras",
        )
        self.assertEqual(len(candidate.evidence_sha256), 64)

    def test_payload_never_contains_creditor_identifier_or_name(self) -> None:
        try:
            from barreiras_normalization.bahia_special_transfers import (
                parse_special_transfer_payment_candidates,
                special_transfer_payload,
            )
        except ImportError:
            self.fail("o normalizador de transferências especiais ainda não existe")
        archive = _archive(
            centralization_rows=[_centralization()],
            expense_rows=[_expense()],
            payment_rows=[_payment()],
        )

        candidate = parse_special_transfer_payment_candidates(archive)[0]
        payload = special_transfer_payload(
            candidate,
            source_url="https://dados.ba.gov.br/dataset/transferencias-especiais",
            source_artifact_sha256="a" * 64,
            source_collected_at="2026-08-21T04:32:47+00:00",
        )
        serialized = str(payload)

        self.assertNotIn("98765432100", serialized)
        self.assertNotIn("CREDOR QUE NÃO DEVE SER PUBLICADO", serialized)
        self.assertNotIn("CNPJ_CPF_CREDOR_PAGAMENTO", serialized)
        self.assertEqual(payload["payment_id"], "1234567890123456789")
        self.assertEqual(payload["source_artifact_sha256"], "a" * 64)

    def test_masks_personal_identifiers_embedded_in_payment_object(self) -> None:
        try:
            from barreiras_normalization.bahia_special_transfers import (
                parse_special_transfer_payment_candidates,
                special_transfer_payload,
            )
        except ImportError:
            self.fail("o normalizador de transferências especiais ainda não existe")
        archive = _archive(
            centralization_rows=[_centralization()],
            expense_rows=[_expense()],
            payment_rows=[
                _payment(
                    object_text=(
                        "Apoio em Barreiras ao CPF 987.654.321-00 e ao "
                        "CNPJ 12.345.678/0001-99"
                    )
                )
            ],
        )

        candidate = parse_special_transfer_payment_candidates(archive)[0]
        payload = special_transfer_payload(
            candidate,
            source_url="https://dados.ba.gov.br/dataset/transferencias-especiais",
            source_artifact_sha256="a" * 64,
            source_collected_at="2026-08-21T04:32:47+00:00",
        )
        serialized = str(payload)

        self.assertNotIn("987.654.321-00", serialized)
        self.assertNotIn("12.345.678/0001-99", serialized)
        self.assertIn("[documento ocultado]", candidate.object_text)

    def test_rejects_non_unique_official_relationship(self) -> None:
        try:
            from barreiras_normalization.bahia_special_transfers import (
                SpecialTransferNormalizationError,
                parse_special_transfer_payment_candidates,
            )
        except ImportError:
            self.fail("o normalizador de transferências especiais ainda não existe")
        archive = _archive(
            centralization_rows=[
                _centralization(),
                _centralization(expense_code="2022.3.20.60101.414.3054.4072.6"),
            ],
            expense_rows=[
                _expense(),
                _expense(expense_code="2022.3.20.60101.414.3054.4072.6"),
            ],
            payment_rows=[_payment()],
        )

        with self.assertRaises(SpecialTransferNormalizationError):
            parse_special_transfer_payment_candidates(archive)

    def test_accepts_midnight_suffix_published_by_official_payment_view(self) -> None:
        try:
            from barreiras_normalization.bahia_special_transfers import (
                parse_special_transfer_payment_candidates,
            )
        except ImportError:
            self.fail("o normalizador de transferências especiais ainda não existe")
        archive = _archive(
            centralization_rows=[_centralization()],
            expense_rows=[_expense()],
            payment_rows=[_payment(payment_date="05/10/2022 00:00:00")],
        )

        try:
            candidate = parse_special_transfer_payment_candidates(archive)[0]
        except Exception as error:
            self.fail(
                f"a data oficial com meia-noite foi rejeitada: {type(error).__name__}"
            )

        self.assertEqual(candidate.payment_date.isoformat(), "2022-10-05")

    def test_preserves_missing_gcv_as_unknown_instead_of_zero(self) -> None:
        try:
            from barreiras_normalization.bahia_special_transfers import (
                parse_special_transfer_payment_candidates,
            )
        except ImportError:
            self.fail("o normalizador de transferências especiais ainda não existe")
        archive = _archive(
            centralization_rows=[_centralization()],
            expense_rows=[_expense()],
            payment_rows=[_payment(gcv_amount="")],
        )

        try:
            candidate = parse_special_transfer_payment_candidates(archive)[0]
        except Exception as error:
            self.fail(f"GCV ausente foi rejeitado: {type(error).__name__}")

        self.assertIsNone(candidate.gcv_amount)

    def test_allows_multiple_liquidations_for_one_unique_expense(self) -> None:
        try:
            from barreiras_normalization.bahia_special_transfers import (
                parse_special_transfer_payment_candidates,
            )
        except ImportError:
            self.fail("o normalizador de transferências especiais ainda não existe")
        archive = _archive(
            centralization_rows=[
                _centralization(),
                _centralization(
                    liquidation_code="2022.500002.60101.1.4072.414.3054.51511.5"
                ),
            ],
            expense_rows=[_expense()],
            payment_rows=[_payment()],
        )

        try:
            candidate = parse_special_transfer_payment_candidates(archive)[0]
        except Exception as error:
            self.fail(
                f"liquidações da mesma despesa foram rejeitadas: {type(error).__name__}"
            )

        self.assertEqual(
            candidate.liquidation_codes,
            (
                "2022.500001.60101.1.4072.414.3054.51511.5",
                "2022.500002.60101.1.4072.414.3054.51511.5",
            ),
        )


if __name__ == "__main__":
    unittest.main()
