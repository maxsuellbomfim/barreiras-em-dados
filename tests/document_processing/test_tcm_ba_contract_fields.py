from __future__ import annotations

import unittest

from barreiras_docproc.processing import PageInput, TextArtifact
from barreiras_docproc.tcm_ba_contract_documents import segment_contract_documents
from barreiras_docproc.tcm_ba_contract_fields import (
    TcmBaContractFieldCoverage,
    contract_field_candidate_payload,
    extract_contract_field_candidates,
)


def page(number: int, text: str, marker: str) -> PageInput:
    return PageInput(
        page_number=number,
        parser_version="fixture/1.0.0",
        extraction_method="embedded_text",
        text=text,
        sha256=marker * 64,
    )


def artifact() -> TextArtifact:
    return TextArtifact(
        raw_artifact_id="00000000-0000-0000-0000-000000000902",
        sha256="f" * 64,
        object_key="tcm-ba/monthly-documents/2023/08/source.pdf",
    )


class TcmBaContractFieldTests(unittest.TestCase):
    def test_coverage_requires_every_segment_but_allows_explicit_absence(self) -> None:
        coverage = TcmBaContractFieldCoverage(
            eligible_artifacts=34,
            processed_artifacts=34,
            eligible_segments=449,
            processed_segments=449,
            observed_fields=1200,
            no_fields_observed=3,
            missing_segments=0,
            duplicate_results=0,
            invalid_results=0,
            open_failures=0,
        )

        self.assertTrue(coverage.complete)
        self.assertFalse(
            TcmBaContractFieldCoverage(
                eligible_artifacts=34,
                processed_artifacts=34,
                eligible_segments=449,
                processed_segments=448,
                observed_fields=1200,
                no_fields_observed=3,
                missing_segments=1,
                duplicate_results=0,
                invalid_results=0,
                open_failures=0,
            ).complete
        )


    def test_extracts_conservative_fields_with_exact_source_anchors(self) -> None:
        pages = (
            page(
                4,
                "CONTRATO Nº 17/2023\n"
                "PROCESSO ADMINISTRATIVO Nº 81/2023\n"
                "CONTRATADA: EMPRESA EXEMPLO LTDA - CNPJ 12.345.678/0001-90\n"
                "OBJETO: prestação de serviço de manutenção.\n"
                "VALOR GLOBAL: R$ 12.345,67\n"
                "DATA DA ASSINATURA: 15/08/2023\n"
                "VIGÊNCIA: 12 meses.\n",
                "a",
            ),
        )
        segments = segment_contract_documents(pages)

        candidates = extract_contract_field_candidates(pages, segments)

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.instrument_number, "17/2023")
        self.assertIsNone(candidate.related_contract_number)
        self.assertEqual(candidate.administrative_process_number, "81/2023")
        self.assertEqual(candidate.contracted_party_name, "EMPRESA EXEMPLO LTDA")
        self.assertEqual(candidate.contracted_party_cnpj, "12345678000190")
        self.assertEqual(candidate.amount_text, "12.345,67")
        self.assertEqual(candidate.signature_date, "2023-08-15")
        self.assertEqual(candidate.validity_text, "12 meses.")
        self.assertEqual(candidate.unobserved_fields, ())
        self.assertEqual(candidate.source_anchors["amount_text"].page_number, 4)
        self.assertEqual(candidate.source_anchors["amount_text"].page_sha256, "a" * 64)
        self.assertEqual(
            len(candidate.source_anchors["amount_text"].evidence_sha256),
            64,
        )

    def test_amendment_keeps_own_number_separate_from_related_contract(self) -> None:
        pages = (
            page(
                8,
                "SEGUNDO TERMO ADITIVO Nº 02/2024 AO CONTRATO Nº 17/2023\n"
                "CONTRATADA: EMPRESA EXEMPLO LTDA\n"
                "OBJETO: prorrogação do prazo contratual.\n"
                "VIGÊNCIA: 90 dias.\n",
                "b",
            ),
        )

        candidate = extract_contract_field_candidates(
            pages,
            segment_contract_documents(pages),
        )[0]

        self.assertEqual(candidate.document_kind, "contract_amendment")
        self.assertEqual(candidate.instrument_number, "02/2024")
        self.assertEqual(candidate.related_contract_number, "17/2023")
        self.assertIsNone(candidate.amount_text)
        self.assertIn("amount_text", candidate.unobserved_fields)

    def test_payload_never_contains_cpf_or_raw_evidence(self) -> None:
        pages = (
            page(
                2,
                "CONTRATO Nº 4/2023\n"
                "CONTRATADO: PESSOA EXEMPLO - CPF 123.456.789-09\n"
                "OBJETO: consultoria técnica.\n",
                "c",
            ),
        )
        candidate = extract_contract_field_candidates(
            pages,
            segment_contract_documents(pages),
        )[0]

        payload = contract_field_candidate_payload(candidate, artifact())

        serialized = str(payload)
        self.assertEqual(payload["contracted_party_name"], "PESSOA EXEMPLO")
        self.assertIsNone(payload["contracted_party_cnpj"])
        self.assertNotIn("123.456.789-09", serialized)
        self.assertNotIn("CPF", serialized)
        self.assertNotIn("raw_text", serialized)
        self.assertEqual(payload["source_segment_ordinal"], 1)
        self.assertEqual(payload["source_artifact_sha256"], "f" * 64)

    def test_unlabelled_values_are_not_guessed(self) -> None:
        pages = (
            page(
                1,
                "CONTRATO\n"
                "A empresa prestará serviços durante doze meses pelo preço acordado.\n",
                "d",
            ),
        )

        candidate = extract_contract_field_candidates(
            pages,
            segment_contract_documents(pages),
        )[0]

        self.assertIsNone(candidate.instrument_number)
        self.assertIsNone(candidate.object_text)
        self.assertIsNone(candidate.amount_text)
        self.assertEqual(len(candidate.source_anchors), 0)
        self.assertEqual(candidate.candidate_status, "no_fields_observed")


if __name__ == "__main__":
    unittest.main()
