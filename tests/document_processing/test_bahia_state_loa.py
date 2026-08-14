from __future__ import annotations

import hashlib
import unittest
from decimal import Decimal

from barreiras_docproc.bahia_state_loa import (
    LOA_BARREIRAS_PARSER_VERSION,
    LoaPage,
    LoaParseError,
    parse_barreiras_loa_pages,
    parse_loa_2026_scope_pages,
)


class BahiaStateLoaParserTests(unittest.TestCase):
    def test_parses_pre_2026_rows_with_multiline_author_and_literal_evidence(
        self,
    ) -> None:
        page = LoaPage(
            page_number=17,
            text="""Governo do Estado da Bahia
Orçamento 2024
Município Nº da Emenda Parlamentar Órgão Unidade Orçamentária Objeto da Emenda Valor
Barreiras 4724 Antônio Henrique
Júnior
SECULT APG/SECULT Apoio técnico e financeiro à Academia Barreirense de Letras
- ABL para a
execução de ações de estímulo à cultura do município
50.000
Barreiras 4727 Antônio Henrique
Júnior
SDR CAR Aquisição de caixa d'água de 500 litros de polietileno 36.000
Barro Alto 2329 Laerte do Vando SETRE SUDESB Apoio financeiro a entidades 22.000
""",
        )

        rows = parse_barreiras_loa_pages(
            fiscal_year=2024,
            annex_code="III",
            pages=(page,),
        )

        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(first.amendment_number, "4724")
        self.assertEqual(first.author_name, "Antônio Henrique Júnior")
        self.assertIsNone(first.author_external_code)
        self.assertEqual(first.agency_code, "SECULT")
        self.assertEqual(first.budget_unit_code, "APG/SECULT")
        self.assertIsNone(first.action_code)
        self.assertEqual(first.authorized_amount, Decimal("50000"))
        self.assertEqual(first.municipality, "Barreiras")
        self.assertEqual(first.page_number, 17)
        self.assertIn("Academia Barreirense de Letras", first.official_description)
        self.assertEqual(
            first.evidence_sha256,
            hashlib.sha256(first.evidence_text.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(first.parser_version, LOA_BARREIRAS_PARSER_VERSION)

    def test_pre_2026_does_not_use_a_barreiras_mention_as_territorial_key(
        self,
    ) -> None:
        page = LoaPage(
            page_number=9,
            text="""Município Nº da Emenda Parlamentar Órgão Unidade Objeto Valor
Baianópolis 100 José da Silva SEC FAED Apoio a estudantes que viajam para
Barreiras 20.000
Barreiras 101 Maria Souza SESAB FESBA Aquisição de equipamento hospitalar 30.000
Barro Alto 102 Outro Autor SEC FAED Material escolar 10.000
""",
        )

        rows = parse_barreiras_loa_pages(
            fiscal_year=2023,
            annex_code="III",
            pages=(page,),
        )

        self.assertEqual([row.amendment_number for row in rows], ["101"])

    def test_pre_2026_amount_does_not_absorb_cnpj_from_the_object(self) -> None:
        page = LoaPage(
            page_number=17,
            text="""Barreiras 4315 Jurailton Santos SESAB FESBA Aquisição de kit
consultório
odontológico para a Unidade de Saúde da Família do CAIC, CNPJ 36.410.571/0001-41
45.000
Barreiras 4724 Antônio Henrique Júnior SECULT APG/SECULT Apoio cultural 50.000
Barro Alto 2329 Laerte do Vando SETRE SUDESB Apoio esportivo 22.000
""",
        )

        rows = parse_barreiras_loa_pages(
            fiscal_year=2024,
            annex_code="III",
            pages=(page,),
        )

        self.assertEqual(rows[0].authorized_amount, Decimal("45000"))
        self.assertIn("36.410.571/0001-41", rows[0].official_description)

    def test_pre_2026_does_not_treat_cpf_suffix_as_amount(self) -> None:
        page = LoaPage(
            page_number=18,
            text=(
                "Barreiras 4316 Autor Teste SESAB FESBA Apoio a entidade "
                "representada por CPF 123.456.789-10\n"
                "Barro Alto 10 Outro Autor SEC FAED Apoio 20.000"
            ),
        )

        with self.assertRaisesRegex(LoaParseError, "valor autorizado"):
            parse_barreiras_loa_pages(
                fiscal_year=2024,
                annex_code="III",
                pages=(page,),
            )

    def test_pre_2026_does_not_treat_spaced_cpf_suffix_as_amount(self) -> None:
        page = LoaPage(
            page_number=18,
            text=(
                "Barreiras 4316 Autor Teste SESAB FESBA Apoio a entidade "
                "representada por CPF 123.456.789 - 10\n"
                "Barro Alto 10 Outro Autor SEC FAED Apoio 20.000"
            ),
        )

        with self.assertRaisesRegex(LoaParseError, "valor autorizado"):
            parse_barreiras_loa_pages(
                fiscal_year=2024,
                annex_code="III",
                pages=(page,),
            )

    def test_pre_2026_refuses_one_unrecognized_barreiras_row(self) -> None:
        page = LoaPage(
            page_number=19,
            text="""Barreiras 4317 Autor Teste SESAB FESBA Objeto 45.000
Barreiras - 4318 Outro Autor SESAB FESBA Formato alterado 50.000
Barro Alto 10 Outro Autor SEC FAED Apoio 20.000
""",
        )

        with self.assertRaisesRegex(LoaParseError, "territorial"):
            parse_barreiras_loa_pages(
                fiscal_year=2024,
                annex_code="III",
                pages=(page,),
            )

    def test_pre_2026_refuses_pipe_separator_layout_drift(self) -> None:
        page = LoaPage(
            page_number=19,
            text="""Barreiras 4317 Autor Teste SESAB FESBA Objeto 45.000
Barreiras | 4318 Outro Autor SESAB FESBA Formato alterado 50.000
Barro Alto 10 Outro Autor SEC FAED Apoio 20.000
""",
        )

        with self.assertRaisesRegex(LoaParseError, "territorial"):
            parse_barreiras_loa_pages(
                fiscal_year=2024,
                annex_code="III",
                pages=(page,),
            )

    def test_pre_2026_refuses_separator_without_spaces(self) -> None:
        for separator in (":", "|", "-"):
            with self.subTest(separator=separator):
                page = LoaPage(
                    page_number=19,
                    text=(
                        "Barreiras 4317 Autor Teste SESAB FESBA Objeto 45.000\n"
                        f"Barreiras{separator}4318 Outro Autor SESAB FESBA "
                        "Formato alterado 50.000\n"
                        "Barro Alto 10 Outro Autor SEC FAED Apoio 20.000"
                    ),
                )

                with self.assertRaisesRegex(LoaParseError, "territorial"):
                    parse_barreiras_loa_pages(
                        fiscal_year=2024,
                        annex_code="III",
                        pages=(page,),
                    )

    def test_tracks_2026_author_across_pages_and_keeps_authorized_stage_only(
        self,
    ) -> None:
        pages = (
            LoaPage(
                page_number=21,
                text="""Antonio Henrique Júnior - 500069          10.324.979
Total da Área de Saúde 5.162.490
3027 SESAB FESBA 2875 Gerenciamento do Serviço Hospitalar
Apoio financeiro para custeio hospitalar
Salvador 52.490
""",
            ),
            LoaPage(
                page_number=22,
                text="""3030 SESAB FESBA 5607 Aparelhamento de Unidade de Saúde
Aquisição para cessão de uso de Kit Odontológico para o
Colégio da Polícia Militar Professor Alexandre Leal Costa
Barreiras 80.000
3031 SESAB FESBA 3354 Apoio Financeiro para a Melhoria da Assistência à Saúde
Apoio financeiro para o custeio da assistência à saúde
Luís Eduardo Magalhães 1.000.000
""",
            ),
            LoaPage(
                page_number=25,
                text="""3020 MPE FMMP 5092 Construção de Unidade do Ministério Público
Apoio financeiro à Construção da Promotoria Regional de Barreiras (MPBA)
Barreiras 200 .000
""",
            ),
        )

        rows = parse_barreiras_loa_pages(
            fiscal_year=2026,
            annex_code="I",
            pages=pages,
        )

        self.assertEqual([row.amendment_number for row in rows], ["3030", "3020"])
        self.assertTrue(
            all(row.author_name == "Antonio Henrique Júnior" for row in rows)
        )
        self.assertTrue(all(row.author_external_code == "500069" for row in rows))
        self.assertEqual(rows[0].action_code, "5607")
        self.assertEqual(rows[0].authorized_amount, Decimal("80000"))
        self.assertEqual(rows[1].authorized_amount, Decimal("200000"))
        self.assertEqual(rows[1].page_number, 25)

    def test_2026_scope_keeps_every_structured_row_not_only_barreiras(self) -> None:
        pages = (
            LoaPage(
                page_number=21,
                text="""Autor Teste - 500069 10.324.979
3030 SESAB FESBA 5607 Aparelhamento de Unidade de Saude
Aquisição de equipamento
Barreiras 80.000
3031 SESAB FESBA 5607 Aparelhamento de Unidade de Saude
Aquisição de outro equipamento
Salvador 90.000
""",
            ),
        )

        scope = parse_loa_2026_scope_pages(annex_code="I", pages=pages)
        barreiras = parse_barreiras_loa_pages(
            fiscal_year=2026,
            annex_code="I",
            pages=pages,
        )

        self.assertEqual([row.amendment_number for row in scope], ["3030", "3031"])
        self.assertEqual(len(barreiras), 1)
        self.assertEqual(
            {
                (
                    row.author_external_code,
                    row.agency_code,
                    row.budget_unit_code,
                    row.action_code,
                )
                for row in scope
            },
            {("500069", "SESAB", "FESBA", "5607")},
        )

    def test_2026_scope_preserves_author_and_row_page_evidence(self) -> None:
        pages = (
            LoaPage(
                page_number=21,
                text="""Autor Teste - 500069 10.324.979
Total da Área de Saúde 5.162.490
""",
            ),
            LoaPage(
                page_number=22,
                text="""3030 SESAB FESBA 5607 Aparelhamento de Unidade de Saude
Aquisição de equipamento
Luís Eduardo Ma-
galhães
1.000.000
""",
            ),
        )

        scope = parse_loa_2026_scope_pages(annex_code="I", pages=pages)

        self.assertEqual(len(scope), 1)
        self.assertEqual(scope[0].author_page_number, 21)
        self.assertEqual(scope[0].page_number, 22)
        self.assertEqual(
            scope[0].author_evidence_text,
            "Autor Teste - 500069 10.324.979",
        )
        self.assertTrue(scope[0].evidence_text.startswith("3030 SESAB FESBA 5607"))

    def test_2026_scope_rejects_any_structured_row_without_proven_author(self) -> None:
        page = LoaPage(
            page_number=1,
            text="""3030 SESAB FESBA 5607 Aparelhamento de Unidade de Saude
Salvador 80.000
""",
        )

        with self.assertRaisesRegex(LoaParseError, "autor"):
            parse_loa_2026_scope_pages(annex_code="I", pages=(page,))

    def test_2026_refuses_barreiras_row_without_proven_author(self) -> None:
        page = LoaPage(
            page_number=1,
            text="""3030 SESAB FESBA 5607 Aparelhamento de Unidade de Saúde
Aquisição de equipamento
Barreiras 80.000
""",
        )

        with self.assertRaisesRegex(LoaParseError, "autor"):
            parse_barreiras_loa_pages(
                fiscal_year=2026,
                annex_code="I",
                pages=(page,),
            )

    def test_2026_refuses_partial_layout_drift_with_one_valid_row(self) -> None:
        page = LoaPage(
            page_number=1,
            text="""Autor Teste - 500069 10.324.979
3030 SESAB FESBA 5607 Aparelhamento de Unidade de Saúde
Aquisição de equipamento
Barreiras 80.000
3031 SESAB FESBA 5607 Aparelhamento de Unidade de Saúde
Aquisição de outro equipamento
Barreiras R$ 50.000
""",
        )

        with self.assertRaisesRegex(LoaParseError, "territorial"):
            parse_barreiras_loa_pages(
                fiscal_year=2026,
                annex_code="I",
                pages=(page,),
            )

    def test_2026_refuses_colon_separator_layout_drift(self) -> None:
        page = LoaPage(
            page_number=24,
            text="""Autor Comprovado - 500001 100.000
1 SESAB FESBA 1000 Objeto valido
Barreiras 50.000
2 SESAB FESBA 1001 Objeto com layout alterado
Barreiras: 50.000
Total 100.000
""",
        )

        with self.assertRaisesRegex(LoaParseError, "territorial"):
            parse_barreiras_loa_pages(
                fiscal_year=2026,
                annex_code="I",
                pages=(page,),
            )

    def test_rejects_duplicate_author_and_amendment_number(self) -> None:
        page = LoaPage(
            page_number=17,
            text="""Barreiras 860 José de Arimateia SETUR APG Apoio a evento
cultural 100.000
Barreiras 860 José de Arimateia SETUR APG Apoio a evento cultural 100.000
Barro Alto 923 Laerte do Vando SESAB FESBA Aquisição de kit 55.000
""",
        )

        with self.assertRaisesRegex(LoaParseError, "duplicada"):
            parse_barreiras_loa_pages(
                fiscal_year=2025,
                annex_code="III",
                pages=(page,),
            )


if __name__ == "__main__":
    unittest.main()
