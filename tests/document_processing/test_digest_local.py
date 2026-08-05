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

    def test_does_not_invent_non_personnel_items(self):
        self.assertEqual(
            deterministic_digest_items("AVISO de licitação para aquisição de materiais."),
            [],
        )


if __name__ == "__main__":
    unittest.main()
