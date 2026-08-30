from __future__ import annotations

import unittest

from barreiras_docproc.processing import PageInput, TextArtifact
from barreiras_docproc.tcm_ba_commitments import (
    TcmBaCommitmentCoverage,
    commitment_candidate_payload,
    find_commitment_candidates,
)


def page(text: str, *, page_number: int = 1) -> PageInput:
    return PageInput(
        page_number=page_number,
        parser_version="fixture/1.0.0",
        text=text,
        sha256="a" * 64,
    )


class TcmBaCommitmentCandidateTests(unittest.TestCase):
    def test_coverage_requires_every_ready_artifact_without_requiring_candidates(
        self,
    ) -> None:
        coverage = TcmBaCommitmentCoverage(
            eligible_artifacts=373,
            processed_artifacts=373,
            candidate_results=0,
            complete_candidates=0,
            incomplete_candidates=0,
            zero_candidate_artifacts=373,
            missing_artifacts=0,
            duplicate_results=0,
            invalid_results=0,
            open_failures=0,
        )

        self.assertTrue(coverage.complete)

    def test_coverage_blocks_missing_duplicate_invalid_or_failed_results(
        self,
    ) -> None:
        baseline = dict(
            eligible_artifacts=10,
            processed_artifacts=10,
            candidate_results=2,
            complete_candidates=1,
            incomplete_candidates=1,
            zero_candidate_artifacts=8,
            missing_artifacts=0,
            duplicate_results=0,
            invalid_results=0,
            open_failures=0,
        )
        variants = (
            {"processed_artifacts": 9, "missing_artifacts": 1},
            {"duplicate_results": 1},
            {"invalid_results": 1},
            {"open_failures": 1},
            {"complete_candidates": 0},
        )

        for overrides in variants:
            with self.subTest(overrides=overrides):
                snapshot = TcmBaCommitmentCoverage(
                    **(baseline | overrides),
                )
                self.assertFalse(snapshot.complete)
    def test_rejects_contract_clause_that_only_mentions_commitment_note(self) -> None:
        candidates = find_commitment_candidates(
            (
                page(
                    "CLÁUSULA QUARTA - O contratado deverá retirar a Nota de "
                    "Empenho no prazo de cinco dias."
                ),
            )
        )

        self.assertEqual(candidates, ())

    def test_rejects_indemnification_text_about_uncommitted_expense(self) -> None:
        candidates = find_commitment_candidates(
            (
                page(
                    "A despesa de aluguel não fora empenhada no exercício "
                    "anterior e integra este pedido de indenização."
                ),
            )
        )

        self.assertEqual(candidates, ())

    def test_extracts_complete_note_from_explicit_heading_and_official_fields(
        self,
    ) -> None:
        candidates = find_commitment_candidates(
            (
                page(
                    "NOTA DE EMPENHO Nº 00123/2021\n"
                    "Data de Emissão: 15/01/2021\n"
                    "Credor: EXEMPLO SERVIÇOS LTDA - CPF 123.456.789-09\n"
                    "Valor do Empenho: R$ 1.234,56\n"
                    "Dotação Orçamentária: 02.05.04.122.001.2001\n"
                ),
            )
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.page_number, 1)
        self.assertEqual(candidate.commitment_number, "00123/2021")
        self.assertEqual(candidate.issue_date, "2021-01-15")
        self.assertEqual(candidate.creditor_name, "EXEMPLO SERVIÇOS LTDA")
        self.assertEqual(candidate.amount_text, "1.234,56")
        self.assertEqual(
            candidate.budget_allocation,
            "02.05.04.122.001.2001",
        )
        self.assertEqual(candidate.missing_fields, ())
        self.assertTrue(candidate.complete)
        self.assertNotIn("123.456.789-09", candidate.evidence_excerpt)
        self.assertIn("***.***.***-**", candidate.evidence_excerpt)

    def test_keeps_incomplete_explicit_note_as_review_candidate(self) -> None:
        candidates = find_commitment_candidates(
            (
                page(
                    "NOTA DE EMPENHO N. 77/2021\n"
                    "Emissão: 31/01/2021\n"
                    "Favorecido: ASSOCIAÇÃO EXEMPLO\n"
                    "Valor: R$ 500,00\n",
                    page_number=7,
                ),
            )
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.page_number, 7)
        self.assertFalse(candidate.complete)
        self.assertEqual(candidate.missing_fields, ("budget_allocation",))

    def test_redacts_spaced_and_unformatted_cpf_from_evidence(self) -> None:
        candidates = find_commitment_candidates(
            (
                page(
                    "NOTA DE EMPENHO Nº 89/2021\n"
                    "Emissão: 31/01/2021\n"
                    "Credor: PESSOA EXEMPLO\n"
                    "CPF: 123 456 789 09\n"
                    "Identificador repetido: 12345678909\n"
                    "Valor: R$ 500,00\n"
                    "Dotação: 02.05.123.456\n"
                ),
            )
        )

        evidence = candidates[0].evidence_excerpt
        self.assertNotIn("123 456 789 09", evidence)
        self.assertNotIn("12345678909", evidence)

    def test_preserves_company_cnpj_for_future_supplier_linking(self) -> None:
        candidates = find_commitment_candidates(
            (
                page(
                    "NOTA DE EMPENHO Nº 88/2021\n"
                    "Emissão: 31/01/2021\n"
                    "Credor: EMPRESA EXEMPLO LTDA - CNPJ 12.345.678/0001-90\n"
                    "Valor: R$ 500,00\n"
                    "Dotação: 02.05.123.456\n"
                ),
            )
        )

        self.assertEqual(candidates[0].creditor_name, "EMPRESA EXEMPLO LTDA")
        self.assertEqual(candidates[0].creditor_cnpj, "12345678000190")
        payload = commitment_candidate_payload(
            candidates[0],
            TextArtifact("artifact-id", "b" * 64, "object-key"),
        )
        self.assertEqual(payload["creditor_cnpj"], "12345678000190")

    def test_extracts_real_tcm_layout_with_number_below_document_banner(
        self,
    ) -> None:
        candidates = find_commitment_candidates(
            (
                page(
                    "PREFEITURA MUNICIPAL - NOTA DE EMPENHO ORDINARIO\n"
                    "R.SOCIAL/NOME: EMPRESA EXEMPLO LTDA\n"
                    "C.N.P.J/CPF: 12.345.678/0001-90\n"
                    "EMPENHO: 123 / 1\n"
                    "DATA DO EMPENHO: 15/01/2021\n"
                    "VALOR BRUTO: 1.234,56\n"
                    "DOTAÇÃO ORÇAMENTÁRIA: 02.05.04.122.001.2001\n"
                ),
            )
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.commitment_number, "123/1")
        self.assertEqual(candidate.issue_date, "2021-01-15")
        self.assertEqual(candidate.creditor_name, "EMPRESA EXEMPLO LTDA")
        self.assertEqual(candidate.creditor_cnpj, "12345678000190")
        self.assertEqual(candidate.amount_text, "1.234,56")
        self.assertEqual(
            candidate.budget_allocation,
            "02.05.04.122.001.2001",
        )
        self.assertTrue(candidate.complete)

    def test_accepts_observed_ocr_label_variants_as_incomplete_review_candidate(
        self,
    ) -> None:
        candidates = find_commitment_candidates(
            (
                page(
                    "NOTA DE EMPENHO\n"
                    "R.SOCLAL/NOME: ASSOCIAÇÃO EXEMPLO\n"
                    "EMPENHO: 77 /\n"
                    "DATA DO EMPANHO: 31/01/2021\n"
                    "VALOR BRUTO: 500,00\n",
                    page_number=9,
                ),
            )
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.commitment_number, "77")
        self.assertEqual(candidate.issue_date, "2021-01-31")
        self.assertEqual(candidate.creditor_name, "ASSOCIAÇÃO EXEMPLO")
        self.assertEqual(candidate.missing_fields, ("budget_allocation",))

    def test_deduplicates_repeated_document_banner_for_same_commitment(self) -> None:
        repeated = (
            "NOTA DE EMPENHO\n"
            "EMPENHO: 45 / 2021\n"
            "DATA DO EMPENHO: 20/01/2021\n"
            "R.SOCIAL/NOME: EMPRESA EXEMPLO LTDA\n"
            "VALOR BRUTO: 2.000,00\n"
            "DOTAÇÃO: 02.05.123.456\n"
        )

        candidates = find_commitment_candidates(
            (page(repeated, page_number=1), page(repeated, page_number=2))
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].page_number, 1)

    def test_keeps_same_number_for_distinct_official_creditors(self) -> None:
        first = (
            "NOTA DE EMPENHO\n"
            "EMPENHO: 45 / 2021\n"
            "DATA DO EMPENHO: 20/01/2021\n"
            "R.SOCIAL/NOME: EMPRESA UM LTDA\n"
            "VALOR BRUTO: 2.000,00\n"
            "DOTAÇÃO: 02.05.123.456\n"
        )
        second = first.replace("EMPRESA UM LTDA", "EMPRESA DOIS LTDA")

        candidates = find_commitment_candidates(
            (page(first, page_number=1), page(second, page_number=2))
        )

        self.assertEqual(len(candidates), 2)
        self.assertEqual(
            [candidate.creditor_name for candidate in candidates],
            ["EMPRESA UM LTDA", "EMPRESA DOIS LTDA"],
        )

    def test_rejects_document_banner_without_labeled_number(self) -> None:
        candidates = find_commitment_candidates(
            (
                page(
                    "NOTA DE EMPENHO\n"
                    "R.SOCIAL/NOME: EMPRESA EXEMPLO LTDA\n"
                    "VALOR BRUTO: 500,00\n"
                ),
            )
        )

        self.assertEqual(candidates, ())

    def test_rejects_heading_without_an_official_number(self) -> None:
        candidates = find_commitment_candidates(
            (page("NOTA DE EMPENHO\nCredor: EXEMPLO\nValor: R$ 10,00\n"),)
        )

        self.assertEqual(candidates, ())


if __name__ == "__main__":
    unittest.main()
