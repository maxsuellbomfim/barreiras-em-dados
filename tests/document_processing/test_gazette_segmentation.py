from __future__ import annotations

import json
import unittest
from pathlib import Path

from barreiras_docproc.gazette_documents import DocumentBlock
from barreiras_docproc.gazette_segmentation import (
    build_document_drafts,
    propose_boundaries,
)

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "sources"
    / "querido_diario"
    / "edition-4706-pages.json"
)


def load_blocks() -> tuple[DocumentBlock, ...]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return tuple(
        DocumentBlock.create(
            page_number=page["page_number"],
            block_order=raw["block_order"],
            text=raw["text"],
        )
        for page in payload["pages"]
        for raw in page["blocks"]
    )


class GazetteSegmentationTests(unittest.TestCase):
    def test_finds_heading_after_repeated_municipal_header(self) -> None:
        blocks = (
            DocumentBlock.create(
                page_number=1,
                block_order=0,
                text=(
                    "PREFEITURA MUNICIPAL DE BARREIRAS\n"
                    "Rua Edigar de Deus Pitta\n"
                    "BARREIRAS - BA\n"
                    "CNPJ: 13.654.405/0001-95\n"
                    "PORTARIA NÂº 263, DE 03 DE AGOSTO DE 2026.\n"
                    "Designa servidor responsável."
                ),
            ),
            DocumentBlock.create(
                page_number=2,
                block_order=0,
                text=(
                    "PREFEITURA MUNICIPAL DE BARREIRAS\n"
                    "Rua Edigar de Deus Pitta\n"
                    "PORTARIA NÂº 264, DE 03 DE AGOSTO DE 2026.\n"
                    "Designa outra servidora."
                ),
            ),
        )

        proposals = propose_boundaries(blocks)
        documents = build_document_drafts(blocks, proposals)

        self.assertEqual([proposal.start_block for proposal in proposals], [0, 1])
        self.assertEqual([document.literal_title for document in documents], [
            "PORTARIA NÂº 263, DE 03 DE AGOSTO DE 2026.",
            "PORTARIA NÂº 264, DE 03 DE AGOSTO DE 2026.",
        ])

    def test_separates_only_complete_headings_at_structural_page_starts(self) -> None:
        blocks = load_blocks()

        proposals = propose_boundaries(blocks)
        documents = build_document_drafts(blocks, proposals)

        self.assertEqual(
            [proposal.start_block for proposal in proposals],
            [0, 2, 4],
        )
        self.assertEqual(len(documents), 3)
        self.assertEqual(
            documents[0].literal_title,
            "PORTARIA Nº 261, DE 29 DE JULHO DE 2026.",
        )
        self.assertIn("acompanhamento e fiscalização", documents[0].full_text)
        self.assertTrue(documents[0].full_text.endswith("data de sua publicação."))
        self.assertEqual(documents[0].document_type, "portaria")
        self.assertEqual(documents[2].document_type, "edital")

    def test_keeps_page_continuation_inside_previous_document(self) -> None:
        blocks = (
            DocumentBlock.create(
                page_number=1,
                block_order=0,
                text=(
                    "DECRETO Nº 123, DE 1º DE AGOSTO DE 2026.\n"
                    "Art. 1º Institui comissão."
                ),
            ),
            DocumentBlock.create(
                page_number=2,
                block_order=0,
                text=(
                    "Art. 2º A comissão terá cinco integrantes.\n"
                    "Art. 3º Este Decreto entra em vigor."
                ),
            ),
        )

        documents = build_document_drafts(blocks, propose_boundaries(blocks))

        self.assertEqual(len(documents), 1)
        self.assertIn("Art. 3º Este Decreto entra em vigor.", documents[0].full_text)

    def test_does_not_split_uppercase_text_without_complete_heading(self) -> None:
        blocks = (
            DocumentBlock.create(
                page_number=1,
                block_order=0,
                text="EDITAL Nº 20/2026\nConvoca os interessados.",
            ),
            DocumentBlock.create(
                page_number=2,
                block_order=0,
                text="RELAÇÃO DE DOCUMENTOS\nDocumento de identidade.\nComprovante.",
            ),
        )

        proposals = propose_boundaries(blocks)

        self.assertEqual([proposal.start_block for proposal in proposals], [0])

    def test_body_text_before_heading_blocks_boundary(self) -> None:
        """Página de continuação com citação legal não vira documento novo."""
        blocks = (
            DocumentBlock.create(
                page_number=1,
                block_order=0,
                text=(
                    "PREFEITURA MUNICIPAL DE BARREIRAS\n"
                    "ESTADO DA BAHIA\n"
                    "EDITAL DE NOTIFICAÇÃO Nº 900/2026\n"
                    "AO SENHOR NOTIFICADO."
                ),
            ),
            DocumentBlock.create(
                page_number=2,
                block_order=0,
                text=(
                    "PREFEITURA MUNICIPAL DE BARREIRAS\n"
                    "ESTADO DA BAHIA\n"
                    "Artigo 4º As eventuais impugnações deverão ser apresentadas"
                    " no prazo de trinta dias, com as devidas justificativas\n"
                    "plausíveis que serão analisadas pelos setores, conforme a\n"
                    "Lei Federal nº 13.465/2017 e art. 24 do Decreto Federal nº"
                    " 9.310/2018."
                ),
            ),
        )

        proposals = propose_boundaries(blocks)
        documents = build_document_drafts(blocks, proposals)

        self.assertEqual([proposal.start_block for proposal in proposals], [0])
        self.assertEqual(len(documents), 1)
        self.assertEqual(
            documents[0].literal_title, "EDITAL DE NOTIFICAÇÃO Nº 900/2026"
        )

    def test_federal_citation_after_masthead_is_not_a_heading(self) -> None:
        """"Lei Federal nº …" no Diário municipal é citação, nunca título."""
        blocks = (
            DocumentBlock.create(
                page_number=1,
                block_order=0,
                text="EDITAL DE NOTIFICAÇÃO Nº 901/2026\nAo interessado.",
            ),
            DocumentBlock.create(
                page_number=2,
                block_order=0,
                text=(
                    "PREFEITURA MUNICIPAL DE BARREIRAS\n"
                    "Lei Federal nº 13.465/2017 e art. 24, §7º, do Decreto"
                    " Federal nº 9.310/2018.\n"
                    "Segue o texto do edital."
                ),
            ),
        )

        proposals = propose_boundaries(blocks)

        self.assertEqual([proposal.start_block for proposal in proposals], [0])

    def test_lowercase_and_dangling_lines_are_not_headings(self) -> None:
        blocks = (
            DocumentBlock.create(
                page_number=1,
                block_order=0,
                text="PORTARIA Nº 90/2026\nArt. 1º Designa equipe.",
            ),
            DocumentBlock.create(
                page_number=2,
                block_order=0,
                text=(
                    "justificativas plausíveis que serão analisadas, priorizando o\n"
                    "restante do procedimento administrativo em curso."
                ),
            ),
            DocumentBlock.create(
                page_number=3,
                block_order=0,
                text=(
                    "Decreto nº 9.310/2018);\n"
                    "Decreto nº 9.310/2018. Essa modalidade dispensa apresentação"
                    " do projeto de\n"
                    "regularização previsto no procedimento."
                ),
            ),
        )

        proposals = propose_boundaries(blocks)

        self.assertEqual([proposal.start_block for proposal in proposals], [0])

    def test_joins_ocr_broken_heading_and_keeps_literal_title(self) -> None:
        blocks = (
            DocumentBlock.create(
                page_number=1,
                block_order=0,
                text=(
                    "ESTA\n"
                    "DO DA BAHIA \n"
                    "MUNICÍPIO DE BARREIRAS \n"
                    "CNPJ nº 13.654.405/0001-95 \n"
                    "DECR\n"
                    "ETO Nº 140, DE 17 DE AGOSTO DE 2026. \n"
                    "O PREFEITO MUNICIPAL, no exercício de suas atribuições,"
                    " decreta as medidas adiante."
                ),
            ),
        )

        documents = build_document_drafts(blocks, propose_boundaries(blocks))

        self.assertEqual(len(documents), 1)
        self.assertEqual(
            documents[0].literal_title,
            "DECR\nETO Nº 140, DE 17 DE AGOSTO DE 2026.",
        )
        self.assertEqual(documents[0].document_type, "decreto")
        self.assertIn(documents[0].literal_title, documents[0].full_text)

    def test_fallback_title_skips_masthead_fragments(self) -> None:
        blocks = (
            DocumentBlock.create(
                page_number=1,
                block_order=0,
                text=(
                    "P\n"
                    "REFEITURA MUNICIPAL DE BARREIRAS \n"
                    "ESTADO DA BAHIA \n"
                    "(77) 3614-7100 / www.barreiras.ba.gov.br \n"
                    "ORDEM DE SERVIÇO N° 10/2026 \n"
                    "O Secretário define a escala do plantão fiscal para o mês"
                    " em referência, conforme programação."
                ),
            ),
        )

        documents = build_document_drafts(blocks, propose_boundaries(blocks))

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].literal_title, "ORDEM DE SERVIÇO N° 10/2026")

    def test_ato_de_convocacao_after_short_department_lines_is_heading(self) -> None:
        blocks = (
            DocumentBlock.create(
                page_number=1,
                block_order=0,
                text="PORTARIA Nº 91/2026\nArt. 1º Nomeia comissão.",
            ),
            DocumentBlock.create(
                page_number=2,
                block_order=0,
                text=(
                    "PREFEITURA MUNICIPAL DE BARREIRAS\n"
                    "SECRETARIA DE ADMINISTRAÇÃO\n"
                    "DIRETORIA DE GESTÃO DE PESSOAS\n"
                    "ATO DE CONVOCAÇÃO Nº 02/2026\n"
                    "O Prefeito Municipal, no uso de suas atribuições legais e"
                    " nos termos do edital vigente, convoca os aprovados."
                ),
            ),
        )

        proposals = propose_boundaries(blocks)
        documents = build_document_drafts(blocks, proposals)

        self.assertEqual([proposal.start_block for proposal in proposals], [0, 1])
        self.assertEqual(
            documents[1].literal_title, "ATO DE CONVOCAÇÃO Nº 02/2026"
        )
        self.assertEqual(documents[1].document_type, "convocacao")

    def test_keeps_multiple_people_in_the_same_official_act(self) -> None:
        blocks = (
            DocumentBlock.create(
                page_number=1,
                block_order=0,
                text=(
                    "PORTARIA Nº 80/2026\nArt. 1º Designar ANA SILVA e "
                    "BRUNO SOUZA para compor a comissão."
                ),
            ),
        )

        documents = build_document_drafts(blocks, propose_boundaries(blocks))

        self.assertEqual(len(documents), 1)
        self.assertIn("ANA SILVA e BRUNO SOUZA", documents[0].full_text)


if __name__ == "__main__":
    unittest.main()
