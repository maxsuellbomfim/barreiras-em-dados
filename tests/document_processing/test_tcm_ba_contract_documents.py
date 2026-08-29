from __future__ import annotations

import unittest

from barreiras_docproc.processing import PageInput, TextArtifact
from barreiras_docproc.tcm_ba_contract_documents import (
    TcmBaContractDocumentCoverage,
    contract_document_payload,
    segment_contract_documents,
)


def page(number: int, text: str, marker: str) -> PageInput:
    return PageInput(
        page_number=number,
        parser_version="pypdf/fixture",
        extraction_method="embedded_text",
        text=text,
        sha256=marker * 64,
    )


class TcmBaContractDocumentTests(unittest.TestCase):
    def test_coverage_blocks_empty_missing_or_unknown_only_artifacts(self) -> None:
        complete = TcmBaContractDocumentCoverage(
            eligible_artifacts=34,
            processed_artifacts=34,
            identified_segments=700,
            unknown_segments=0,
            missing_artifacts=0,
            unknown_only_artifacts=0,
            duplicate_results=0,
            invalid_results=0,
            open_failures=0,
        )

        self.assertTrue(complete.complete)
        self.assertFalse(
            TcmBaContractDocumentCoverage(
                eligible_artifacts=0,
                processed_artifacts=0,
                identified_segments=0,
                unknown_segments=0,
                missing_artifacts=0,
                unknown_only_artifacts=0,
                duplicate_results=0,
                invalid_results=0,
                open_failures=0,
            ).complete
        )
        self.assertFalse(
            TcmBaContractDocumentCoverage(
                eligible_artifacts=34,
                processed_artifacts=33,
                identified_segments=699,
                unknown_segments=1,
                missing_artifacts=1,
                unknown_only_artifacts=1,
                duplicate_results=0,
                invalid_results=0,
                open_failures=0,
            ).complete
        )

    def test_amendment_heading_takes_priority_over_contract_reference(self) -> None:
        segments = segment_contract_documents(
            (
                page(
                    1,
                    "PRIMEIRO TERMO ADITIVO AO CONTRATO Nº 10/2021\n"
                    "Cláusula primeira.\n",
                    "a",
                ),
            )
        )

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].document_kind, "contract_amendment")
        self.assertEqual(segments[0].start_page, 1)
        self.assertEqual(segments[0].end_page, 1)

    def test_continuation_page_stays_with_previous_document(self) -> None:
        segments = segment_contract_documents(
            (
                page(1, "CONTRATO Nº 1/2021\nCláusula primeira.\n", "a"),
                page(2, "Continuação da cláusula.\n", "b"),
                page(3, "EXTRATO DE CONTRATO Nº 2/2021\nObjeto.\n", "c"),
            )
        )

        self.assertEqual(len(segments), 2)
        self.assertEqual((segments[0].start_page, segments[0].end_page), (1, 2))
        self.assertEqual((segments[1].start_page, segments[1].end_page), (3, 3))

    def test_multiple_headings_on_one_page_create_distinct_segments(self) -> None:
        segments = segment_contract_documents(
            (
                page(
                    7,
                    "CONTRATO Nº 1/2021\nObjeto A.\n"
                    "TERMO DE RESCISÃO DO CONTRATO Nº 1/2021\nObjeto B.\n",
                    "d",
                ),
            )
        )

        self.assertEqual(
            [segment.document_kind for segment in segments],
            ["contract", "contract_termination"],
        )
        self.assertLess(segments[0].end_offset, segments[1].end_offset)

    def test_payload_keeps_lineage_without_raw_text_or_personal_data(self) -> None:
        source = TextArtifact(
            raw_artifact_id="00000000-0000-0000-0000-000000000902",
            sha256="e" * 64,
            object_key="tcm-ba/monthly-documents/2021/01/source.pdf",
        )
        text = (
            "CONTRATO Nº 1/2021\n"
            "Contratada: PESSOA EXEMPLO CPF 123.456.789-09\n"
            "Valor: R$ 1.000,00\n"
        )
        segment = segment_contract_documents((page(1, text, "f"),))[0]

        payload = contract_document_payload(segment, source)

        serialized = str(payload)
        self.assertNotIn("PESSOA EXEMPLO", serialized)
        self.assertNotIn("123.456.789-09", serialized)
        self.assertNotIn("1.000,00", serialized)
        self.assertEqual(payload["source_artifact_sha256"], "e" * 64)
        self.assertEqual(payload["source_page_numbers"], [1])
        self.assertEqual(len(str(payload["segment_text_sha256"])), 64)

    def test_artifact_without_known_heading_is_explicitly_unknown(self) -> None:
        segments = segment_contract_documents(
            (page(1, "Documento sem cabeçalho reconhecido.\n", "a"),)
        )

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].document_kind, "unknown")
        self.assertEqual(segments[0].classification_status, "needs_review")


if __name__ == "__main__":
    unittest.main()
