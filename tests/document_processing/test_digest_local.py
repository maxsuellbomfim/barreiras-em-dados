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


if __name__ == "__main__":
    unittest.main()
