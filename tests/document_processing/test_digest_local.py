import unittest

from barreiras_docproc.digest import deterministic_digest_items


class DeterministicDigestTests(unittest.TestCase):
    def test_reads_multiple_personnel_acts_from_one_text(self):
        text = (
            "PORTARIA N 10, DE 3 DE JUNHO DE 2026. "
            "Nomear MARIA SILVA para o cargo de Assessora.\n\n"
            "PORTARIA N 11, DE 4 DE JUNHO DE 2026. "
            "Exonerar JOANA SOUZA do cargo de Diretora."
        )
        items = deterministic_digest_items(text)
        self.assertEqual(len(items), 2)
        self.assertEqual({item.item_type for item in items}, {"nomeacao", "exoneracao"})
        self.assertTrue(all(item.anchor for item in items))

    def test_reads_multiple_budget_decrees_without_ai(self):
        text = (
            "Decreto Nº 118\n"
            "Lei 1704 / 2026\n"
            "De 27 de Julho de 2026\n"
            "O PREFEITO MUNICIPAL, no uso de suas atribuições legais.\n"
            "DECRETA:\n"
            "Artigo 1º - Fica alterado o Quadro de Detalhamento de Despesa.\n"
            "Programação das Despesas das Secretarias Municipais.\n"
            "Altera o Orçamento Analítico (QDD) do exercício financeiro de "
            "2026 e dá outras providências.\n\n"
            "Decreto Nº 119\n"
            "27/07/2026\n"
            "Abre Crédito Suplementar no valor total de R$ 290.000,00, "
            "para fins que se especifica e dá outras providências."
        )

        items = deterministic_digest_items(text)

        self.assertEqual(len(items), 2)
        self.assertEqual([item.item_type for item in items], ["decreto", "decreto"])
        self.assertIn("118", items[0].title)
        self.assertIn("119", items[1].title)
        self.assertIn("Orçamento Analítico", items[0].summary)
        self.assertIn("Crédito Suplementar", items[1].summary)
        self.assertTrue(all(item.anchor in text for item in items))

    def test_reads_explicit_procurement_notice_without_ai(self):
        text = (
            "AVISO DE LICITAÇÃO\n"
            "Pregão Eletrônico nº 012/2026. Objeto: aquisição de "
            "gêneros alimentícios para a merenda escolar."
        )

        items = deterministic_digest_items(text)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].item_type, "licitacao")
        self.assertEqual(items[0].title, "Aviso de licitação")
        self.assertIn("aquisição de gêneros", items[0].summary)
        self.assertIn(items[0].anchor, text)

    def test_keeps_general_and_personnel_acts_in_document_order(self):
        text = (
            "Decreto Nº 118\n"
            "Altera o Orçamento Analítico do exercício de 2026.\n\n"
            "PORTARIA Nº 205, DE 03 DE JUNHO DE 2026\n"
            "Nomear MARIA SILVA para o cargo de Assessora."
        )

        items = deterministic_digest_items(text)

        self.assertEqual(
            [item.item_type for item in items],
            ["decreto", "nomeacao"],
        )

    def test_does_not_invent_item_without_official_heading(self):
        self.assertEqual(
            deterministic_digest_items(
                "A administração pretende adquirir materiais no futuro."
            ),
            [],
        )

    def test_ignores_legal_references_and_signing_portarias(self):
        text = (
            "PORTARIA Nº 261, DE 29 DE JULHO DE 2026.\n"
            "Designa servidor responsável pela fiscalização do contrato.\n"
            "Decreto nº 45/2024 e nos termos do art. 117 da Lei nº 14.133/2021.\n"
            "Larissa Gomes Barbosa\n"
            "Secretária Municipal de Saúde\n"
            "Portaria 34/2025\n\n"
            "PORTARIA Nº 262, DE 29 DE JULHO DE 2026.\n"
            "Designa servidor responsável pela fiscalização de outra ata."
        )

        items = deterministic_digest_items(text)

        self.assertEqual(
            [item.title for item in items],
            ["Portaria nº 261", "Portaria nº 262"],
        )

    def test_reads_numbered_heading_with_trailing_punctuation(self):
        text = (
            "DECRETO Nº 123.\n"
            "Constitui Comissão Especial para acompanhamento das execuções."
        )

        items = deterministic_digest_items(text)

        self.assertEqual([item.title for item in items], ["Decreto nº 123."])

    def test_reads_bare_decree_heading_followed_by_budget_structure(self):
        text = (
            "PREFEITURA MUNICIPAL DE BARREIRAS\n"
            "Decreto Nº 118\n"
            "Lei 1704 / 2026\n"
            "De 27 de Julho de 2026\n"
            "O(a) PREFEITO(A) MUNICIPAL, no uso de suas atribuições legais.\n"
            "D E C R E T A :\n"
            "Artigo 1º - Fica alterado o Quadro de Detalhamento de Despesa."
        )

        items = deterministic_digest_items(text)

        self.assertEqual([item.title for item in items], ["Decreto nº 118"])

    def test_reads_numbered_editals_contract_errata_and_dispensa(self):
        text = (
            "EDITAL DE NOTIFICAÇÃO Nº 695/2026\n"
            "Procedimento de regularização fundiária destinado a Tereza Silva.\n\n"
            "ERRATA\n"
            "REPUBLICAÇÃO\n"
            "PREGÃO ELETRÔNICO Nº 028/2026\n"
            "Republica a sessão de abertura para 18/08/2026.\n\n"
            "EXTRATO DO CONTRATO Nº 152/2026\n"
            "Contratada MOVTERRA CONSTRUTORA LTDA. Valor R$ 13.269.960,00.\n\n"
            "AVISO DE DISPENSA DE LICITAÇÃO Nº 009/2026\n"
            "Aquisição de vestuários para o Serviço de Convivência."
        )

        items = deterministic_digest_items(text)

        self.assertEqual(len(items), 4)
        self.assertEqual(
            [item.item_type for item in items],
            ["aviso", "licitacao", "contrato", "licitacao"],
        )
        self.assertIn("695/2026", items[0].title)
        self.assertIn("152/2026", items[2].title)

    def test_reads_decision_environmental_extract_and_contract_amendment(self):
        text = (
            "DECISÃO SOBRE IMPUGNAÇÃO AO EDITAL\n"
            "PREGÃO ELETRÔNICO Nº 031/2026\n"
            "A impugnação foi conhecida e indeferida.\n\n"
            "EXTRATO DA PORTARIA SEMMAS Nº 000049/2026\n"
            "Concede Licença de Operação à SEMENTES OILEMA LTDA.\n\n"
            "EXTRATO DO TERCEIRO TERMO ADITIVO AO CONTRATO Nº 006-FMS/2023\n"
            "Prorroga o prazo e acrescenta 25% ao valor contratado."
        )

        items = deterministic_digest_items(text)

        self.assertEqual(len(items), 3)
        self.assertEqual(
            [item.item_type for item in items],
            ["licitacao", "portaria", "contrato"],
        )

    def test_deduplicates_identical_publication_repeated_in_the_pdf(self):
        edital = (
            "EDITAL DE INTIMAÇÃO\nGERALDO RIBEIRO NEVES - TIAF 67/2026 e 68/2026.\n"
        )

        items = deterministic_digest_items(f"{edital}\n{edital}")

        self.assertEqual(len(items), 1)

    def test_ignores_edital_reference_inside_contract_fiscal_portaria(self):
        text = (
            "PORTARIA Nº 023, DE 30 DE JULHO DE 2026.\n"
            "Designa servidor responsável pela fiscalização do contrato.\n"
            "Edital de Pregão Eletrônico para Registro de Preços nº 040/2025 e/ou "
            "no Termo\n"
            "responsável pelo acompanhamento e fiscalização da execução."
        )

        items = deterministic_digest_items(text)

        self.assertEqual([item.title for item in items], ["Portaria nº 023"])

    def test_classifies_ocr_damaged_price_registry_notice_as_procurement(self):
        text = (
            "Aviso de Republicação de Ata de Regist111 de Preços Compartilhada "
            "Estadual\n"
            "Processo Administrativo Nº 12248/2026. Contratada: CM HOSPITALAR S.A."
        )

        items = deterministic_digest_items(text)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].item_type, "licitacao")


if __name__ == "__main__":
    unittest.main()
