from __future__ import annotations

import hashlib
import unittest

from barreiras_docproc.bahia_state_loa_processing import (
    BahiaStateLoaArtifact,
    BahiaStateLoaExtractionBatch,
    BahiaStateLoaExtractionService,
    LoaArtifactMismatchError,
    LoaIncompleteTextError,
)

from tests.document_processing.test_pdf_processing import build_pdf


class FakeReader:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def read(self, object_key: str) -> bytes:
        return self.objects[object_key]


class FakeRepository:
    def __init__(self) -> None:
        self.batches: list[BahiaStateLoaExtractionBatch] = []

    def persist_extraction(self, batch: BahiaStateLoaExtractionBatch):
        self.batches.append(batch)
        return type(
            "Result",
            (),
            {
                "job_created": True,
                "results_inserted": len(batch.amendments),
                "scope_rows_inserted": len(batch.scope_rows),
            },
        )()


def artifact_for(body: bytes, *, year: int = 2024) -> BahiaStateLoaArtifact:
    sha256 = hashlib.sha256(body).hexdigest()
    return BahiaStateLoaArtifact(
        raw_artifact_id="00000000-0000-0000-0000-000000000901",
        raw_record_id="00000000-0000-0000-0000-000000000902",
        sha256=sha256,
        object_key=f"bahia/loa-emendas-estaduais/{year}/{sha256}.pdf",
        fiscal_year=year,
        annex_code="I" if year == 2026 else "III",
        source_url=f"https://www.ba.gov.br/seplan/loa-{year}.pdf",
    )


class BahiaStateLoaExtractionServiceTests(unittest.TestCase):
    def test_verifies_pdf_and_persists_literal_authorized_rows(self) -> None:
        body = build_pdf(
            [
                "Barreiras 4315 Jurailton Santos SESAB FESBA "
                "Aquisicao de kit odontologico CNPJ 36.410.571/0001-41 "
                "45.000\nBarro Alto 10 Outro Autor SEC FAED Apoio 20.000"
            ]
        )
        artifact = artifact_for(body)
        repository = FakeRepository()
        service = BahiaStateLoaExtractionService(
            object_reader=FakeReader({artifact.object_key: body}),
            repository=repository,
        )

        result = service.process(artifact)

        self.assertTrue(result.job_created)
        self.assertEqual(result.results_inserted, 1)
        batch = repository.batches[0]
        self.assertEqual(len(batch.pages), 1)
        self.assertEqual(len(batch.amendments), 1)
        amendment = batch.amendments[0]
        self.assertEqual(str(amendment.authorized_amount), "45000")
        self.assertIn("36.410.571/0001-41", amendment.official_description)
        self.assertEqual(batch.artifact.sha256, hashlib.sha256(body).hexdigest())

    def test_refuses_restored_bytes_with_a_different_hash(self) -> None:
        body = build_pdf(["Barreiras 1 Autor SEC FAED Objeto 10.000"])
        artifact = artifact_for(body)
        service = BahiaStateLoaExtractionService(
            object_reader=FakeReader({artifact.object_key: body + b"tampered"}),
            repository=FakeRepository(),
        )

        with self.assertRaises(LoaArtifactMismatchError):
            service.process(artifact)

    def test_refuses_partial_pdf_instead_of_publishing_partial_totals(self) -> None:
        body = build_pdf(
            ["Barreiras 1 Autor SEC FAED Objeto 10.000", None]
        )
        artifact = artifact_for(body)
        repository = FakeRepository()
        service = BahiaStateLoaExtractionService(
            object_reader=FakeReader({artifact.object_key: body}),
            repository=repository,
        )

        with self.assertRaises(LoaIncompleteTextError):
            service.process(artifact)
        self.assertEqual(repository.batches, [])

    def test_refuses_zero_target_rows_as_parser_drift(self) -> None:
        body = build_pdf(["Salvador 1 Autor SEC FAED Objeto 10.000"])
        artifact = artifact_for(body)
        service = BahiaStateLoaExtractionService(
            object_reader=FakeReader({artifact.object_key: body}),
            repository=FakeRepository(),
        )

        with self.assertRaisesRegex(LoaIncompleteTextError, "Barreiras"):
            service.process(artifact)

    def test_2026_persists_statewide_scope_alongside_barreiras_projection(self) -> None:
        body = build_pdf(
            [
                "Autor Teste - 500069 10.324.979\n"
                "3030 SESAB FESBA 5607 Aparelhamento de Unidade de Saude\n"
                "Barreiras 80.000\n"
                "3031 SESAB FESBA 5607 Aparelhamento de Unidade de Saude\n"
                "Salvador 90.000"
            ]
        )
        artifact = artifact_for(body, year=2026)
        repository = FakeRepository()
        service = BahiaStateLoaExtractionService(
            object_reader=FakeReader({artifact.object_key: body}),
            repository=repository,
        )

        result = service.process(artifact)

        self.assertEqual(result.results_inserted, 1)
        self.assertEqual(result.scope_rows_inserted, 2)
        self.assertEqual(len(repository.batches[0].scope_rows), 2)


if __name__ == "__main__":
    unittest.main()
