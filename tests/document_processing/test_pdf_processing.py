from __future__ import annotations

import hashlib
import io
import unittest

from barreiras_docproc import pdf_text
from barreiras_docproc.canonical import CanonicalTextError
from barreiras_docproc.pdf_text import PDF_PARSER_VERSION, derive_pdf_text
from barreiras_docproc.processing import (
    ExtractionBatch,
    ExtractionPersistResult,
    GazetteActExtractionService,
    TextArtifact,
)


def build_pdf(page_texts: list[str | None]) -> bytes:
    """Gera um PDF real em memória; página None fica sem texto embutido."""
    from pypdf import PdfWriter
    from pypdf.generic import (
        DecodedStreamObject,
        DictionaryObject,
        NameObject,
    )

    writer = PdfWriter()
    for text in page_texts:
        page = writer.add_blank_page(width=612, height=792)
        if text is None:
            continue
        content = DecodedStreamObject()
        escaped = text.replace("(", r"\(").replace(")", r"\)")
        content.set_data(
            f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
        )
        page[NameObject("/Contents")] = writer._add_object(content)
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {
                        NameObject("/F1"): DictionaryObject(
                            {
                                NameObject("/Type"): NameObject("/Font"),
                                NameObject("/Subtype"): NameObject("/Type1"),
                                NameObject("/BaseFont"): NameObject(
                                    "/Helvetica"
                                ),
                            }
                        )
                    }
                )
            }
        )
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class FakeReader:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def read(self, object_key: str) -> bytes:
        return self.objects[object_key]


class FakeRepository:
    def __init__(self) -> None:
        self.batches: list[ExtractionBatch] = []
        self.failures: list[str] = []
        self.deferred_pages: list[tuple] = []
        self.supplemental: dict[int, str] = {}

    def persist_extraction(
        self,
        batch: ExtractionBatch,
    ) -> ExtractionPersistResult:
        self.batches.append(batch)
        return ExtractionPersistResult(
            job_created=True,
            results_inserted=len(batch.candidates),
        )

    def persist_extraction_failure(self, artifact, **kwargs) -> None:
        self.failures.append(kwargs["error_code"])

    def persist_pages(self, artifact, pages) -> None:
        self.deferred_pages.append((artifact.raw_artifact_id, pages))

    def supplemental_page_texts(self, raw_artifact_id: str) -> dict[int, str]:
        return dict(self.supplemental)


def make_service(body: bytes) -> tuple[GazetteActExtractionService, ...]:
    sha = hashlib.sha256(body).hexdigest()
    artifact = TextArtifact(
        raw_artifact_id="00000000-0000-0000-0000-000000000801",
        sha256=sha,
        object_key=(
            "barreiras-diario/gazettes/documents/sha256/"
            f"{sha[:2]}/{sha}.pdf"
        ),
    )
    repository = FakeRepository()
    service = GazetteActExtractionService(
        object_reader=FakeReader({artifact.object_key: body}),
        repository=repository,
    )
    return service, artifact, repository


class PdfTextTests(unittest.TestCase):
    def test_extracts_text_pages_and_marks_scanned_pages(self) -> None:
        body = build_pdf(
            ["NOMEAR FULANO DE TAL para o cargo de Chefe", None]
        )

        canonical = derive_pdf_text(body)

        self.assertEqual(len(canonical.pages), 2)
        self.assertEqual(canonical.pages_with_text, 1)
        self.assertIn("NOMEAR FULANO DE TAL", canonical.pages[0].text or "")
        self.assertIsNone(canonical.pages[1].text)
        self.assertIsNone(canonical.pages[1].sha256)
        self.assertEqual(canonical.parser_version, PDF_PARSER_VERSION)

    def test_fully_scanned_pdf_has_empty_canonical_text(self) -> None:
        canonical = derive_pdf_text(build_pdf([None, None]))

        self.assertEqual(canonical.pages_with_text, 0)
        self.assertEqual(canonical.text, "")

    def test_unreadable_pdf_raises_explicit_error(self) -> None:
        with self.assertRaises(CanonicalTextError):
            derive_pdf_text(b"%PDF-1.7 truncado e invalido")
        with self.assertRaises(CanonicalTextError):
            derive_pdf_text(b"nao eh pdf")

    def test_extracts_layout_text_with_distinct_version(self) -> None:
        self.assertTrue(hasattr(pdf_text, "derive_pdf_layout_text"))
        self.assertTrue(hasattr(pdf_text, "PDF_LAYOUT_TEXT_VERSION"))
        canonical = pdf_text.derive_pdf_layout_text(
            build_pdf(["RESTOS A PAGAR", "Total 0,00 1,00 1,00"])
        )

        self.assertEqual(
            canonical.parser_version,
            pdf_text.PDF_LAYOUT_TEXT_VERSION,
        )
        self.assertEqual(canonical.pages_with_text, 2)
        self.assertIn("RESTOS A PAGAR", canonical.pages[0].text or "")


class PdfExtractionServiceTests(unittest.TestCase):
    def test_processes_fully_texted_pdf_into_candidates(self) -> None:
        body = build_pdf(
            [
                "NOMEAR FULANO DE TAL para o cargo de Assessor,",
                "EXTRATO DE CONTRATO 9/2026 sem ato de pessoal.",
            ]
        )
        service, artifact, repository = make_service(body)

        result = service.process(artifact)

        self.assertTrue(result.job_created)
        self.assertFalse(result.deferred_awaiting_ocr)
        self.assertEqual(result.results_inserted, 1)
        batch = repository.batches[0]
        self.assertEqual(len(batch.pages), 2)
        candidate = batch.candidates[0]
        self.assertEqual(
            batch.canonical.text[
                candidate.match_start : candidate.match_end
            ],
            candidate.match_text,
        )

    def test_pdf_with_scanned_pages_is_deferred_awaiting_ocr(self) -> None:
        body = build_pdf(
            ["NOMEAR FULANO DE TAL para o cargo de Assessor,", None]
        )
        service, artifact, repository = make_service(body)

        result = service.process(artifact)

        self.assertFalse(result.job_created)
        self.assertTrue(result.deferred_awaiting_ocr)
        self.assertEqual(result.results_inserted, 0)
        self.assertEqual(repository.batches, [])
        artifact_id, pages = repository.deferred_pages[0]
        self.assertEqual(artifact_id, artifact.raw_artifact_id)
        self.assertEqual(len(pages), 2)
        self.assertIsNone(pages[1].text)

    def test_ocr_supplement_completes_pdf_and_extracts_candidates(
        self,
    ) -> None:
        body = build_pdf(
            ["PORTARIA N 10. RESOLVE: nada de pessoal aqui.", None]
        )
        service, artifact, repository = make_service(body)
        repository.supplemental = {
            2: "Art. 1° - EXONERAR BELTRANA DE TAL do cargo de Chefe,"
        }

        result = service.process(artifact)

        self.assertTrue(result.job_created)
        self.assertFalse(result.deferred_awaiting_ocr)
        self.assertEqual(result.results_inserted, 1)
        batch = repository.batches[0]
        self.assertEqual(
            batch.canonical.parser_version,
            "gazette-merged-text/1.0.0",
        )
        self.assertIn("EXONERAR BELTRANA", batch.canonical.text)
        candidate = batch.candidates[0]
        self.assertEqual(candidate.act_type, "exoneracao")
        self.assertEqual(
            batch.canonical.text[
                candidate.match_start : candidate.match_end
            ],
            candidate.match_text,
        )

    def test_fully_scanned_pdf_is_deferred_not_half_processed(self) -> None:
        service, artifact, repository = make_service(build_pdf([None]))

        result = service.process(artifact)

        self.assertTrue(result.deferred_awaiting_ocr)
        self.assertEqual(repository.batches, [])
        self.assertEqual(len(repository.deferred_pages), 1)


if __name__ == "__main__":
    unittest.main()
