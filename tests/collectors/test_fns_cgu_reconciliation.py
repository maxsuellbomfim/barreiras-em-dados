from __future__ import annotations

import unittest

from barreiras_collectors.connectors.fns_cgu_reconciliation import (
    FNSCGUReconciliationError,
    reconcile_fns_cgu_payment,
)

from tests.collectors.test_cgu_federal_amendment_documents import (
    archive_bytes,
    document_row,
)
from tests.collectors.test_fns_payment_evidence import envelope, order, payment


def cgu_row(**overrides):
    return document_row(
        **{
            "Código da Emenda": "202550410002",
            "Ano da Emenda": "2025",
            "Código do Autor da Emenda": "5041",
            "Nome do Autor da Emenda": "COM. DA SAUDE",
            "Número da emenda": "0002",
            "Tipo de Emenda": "Emenda de comissão",
            "Data Documento": "24/10/2025",
            "Código Documento": "257001000012025OB055607",
            "Fase da despesa": "Pagamento",
            "Valor Empenhado": "0,00",
            "Valor Pago": "5000000,00",
            "Código favorecido": "08595187000125",
            **overrides,
        }
    )


def reconcile(rows=None, *, archive=None):
    return reconcile_fns_cgu_payment(
        payment_body=envelope(payment()),
        order_body=envelope(order()),
        action_id=65061,
        payment_year=2025,
        order_number="055607",
        cgu_archive_body=(
            archive
            if archive is not None
            else archive_bytes(2025, [cgu_row()] if rows is None else rows)
        ),
    )


class FNSCGUReconciliationTests(unittest.TestCase):
    def test_invalid_archive_is_not_reported_as_no_match(self):
        with self.assertRaises(FNSCGUReconciliationError):
            reconcile(archive=b"PRIVATE_SENTINEL invalid archive")

    def test_identical_cgu_lines_are_not_counted_twice(self):
        result = reconcile([cgu_row(), cgu_row()])
        self.assertEqual(result["status"], "unique_candidate")
        self.assertEqual(result["candidate_count"], 1)

    def test_new_archive_invalidates_previous_reconciliation_key(self):
        first = reconcile()
        second = reconcile(
            [
                cgu_row(),
                cgu_row(
                    **{
                        "Código Documento": "257001000012025OB055608",
                    }
                ),
            ]
        )
        self.assertNotEqual(
            first["candidate"]["reconciliation_key"],
            second["candidate"]["reconciliation_key"],
        )

    def test_unique_candidate_keeps_both_authors_and_does_not_publish_or_add_money(
        self,
    ):
        result = reconcile()
        self.assertEqual(result["status"], "unique_candidate")
        self.assertFalse(result["publication_allowed"])
        self.assertEqual(
            result["candidate"]["document_code"], "257001000012025OB055607"
        )
        self.assertEqual(result["candidate"]["cgu_author_name"], "COM. DA SAUDE")
        self.assertEqual(result["candidate"]["fns_author_name"], "COMISSÃO DA SAÚDE")
        self.assertEqual(
            result["candidate"]["requester_name"], "PARLAMENTAR DE EXEMPLO"
        )
        self.assertEqual(result["candidate"]["paid_amount"], "5000000.00")
        self.assertEqual(result["candidate"]["amendment_year"], 2025)
        self.assertEqual(
            result["candidate"]["aggregation_policy"],
            "evidence_only_no_additional_payment",
        )
        self.assertEqual(len(result["candidate"]["cgu_archive_sha256"]), 64)

    def test_missing_document_does_not_mean_no_transfer(self):
        result = reconcile([cgu_row(**{"Código Documento": "257001000012025OB055608"})])
        self.assertEqual(result["status"], "not_found")
        self.assertIsNone(result["candidate"])

    def test_conflicting_fields_block_the_link(self):
        for changes in [
            {"Valor Pago": "4999999,99"},
            {"Data Documento": "25/10/2025"},
            {"Código da Emenda": "202550410001"},
            {"Código do Autor da Emenda": "1234"},
            {"Código UG": "123456"},
            {"Tipo de Emenda": "Emenda Individual"},
        ]:
            with self.subTest(changes=changes):
                result = reconcile([cgu_row(**changes)])
                self.assertEqual(result["status"], "conflict")
                self.assertIsNone(result["candidate"])

    def test_other_beneficiary_or_municipality_never_matches_by_name(self):
        for changes in [
            {"Código favorecido": "13654574000107"},
            {"Código IBGE do município de aplicação do recurso": "2927408"},
        ]:
            result = reconcile([cgu_row(**changes)])
            self.assertEqual(result["status"], "not_found")

    def test_multiple_lines_are_ambiguous_even_if_only_one_amount_matches(self):
        rows = [cgu_row(), cgu_row(**{"Valor Pago": "1,00", "Código Ação": "20AB"})]
        result = reconcile(rows)
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["candidate_count"], 2)
        self.assertIsNone(result["candidate"])

    def test_another_management_with_same_short_ob_is_ambiguous(self):
        result = reconcile(
            [cgu_row(), cgu_row(**{"Código Documento": "257001000022025OB055607"})]
        )
        self.assertEqual(result["status"], "ambiguous")

    def test_old_amendment_year_comes_from_cgu_not_payment_year(self):
        result = reconcile(
            [cgu_row(**{"Código da Emenda": "202350410002", "Ano da Emenda": "2023"})]
        )
        self.assertEqual(result["status"], "unique_candidate")
        self.assertEqual(result["candidate"]["amendment_year"], 2023)

    def test_replay_is_deterministic_and_retains_no_banking_or_cpf_fields(self):
        archive = archive_bytes(2025, [cgu_row()])
        result = reconcile(archive=archive)
        self.assertEqual(result, reconcile(archive=archive))
        self.assertEqual(
            set(result["candidate"]),
            {
                "document_code",
                "amendment_code",
                "amendment_year",
                "document_date",
                "paid_amount",
                "municipality_ibge",
                "cgu_author_name",
                "fns_author_name",
                "requester_name",
                "requester_source_code",
                "proposal_number",
                "payment_sha256",
                "order_sha256",
                "cgu_archive_sha256",
                "source_row_number",
                "aggregation_policy",
                "reconciliation_key",
            },
        )
