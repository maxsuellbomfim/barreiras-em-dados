from __future__ import annotations

import unittest
from pathlib import Path

from barreiras_docproc.candidates import (
    RULESET_VERSION,
    clean_excerpt,
    find_candidates,
)

ROOT = Path(__file__).parents[2]
FIXTURE_PATH = (
    ROOT / "fixtures" / "sources" / "querido_diario" / "gazette-text-sample.txt"
)


class ActCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = FIXTURE_PATH.read_text(encoding="utf-8")

    def test_finds_nomeacao_and_exoneracao_with_reproducible_offsets(
        self,
    ) -> None:
        candidates = find_candidates(self.text)

        act_types = [candidate.act_type for candidate in candidates]
        self.assertEqual(act_types, ["nomeacao", "exoneracao"])
        for candidate in candidates:
            self.assertEqual(
                self.text[candidate.match_start : candidate.match_end],
                candidate.match_text,
            )
            # O trecho exibido é a limpeza determinística da fatia bruta:
            # quem tem o texto canônico e os offsets reproduz o mesmo.
            self.assertEqual(
                clean_excerpt(
                    self.text[candidate.excerpt_start : candidate.excerpt_end]
                ),
                candidate.excerpt,
            )
            self.assertEqual(candidate.ruleset_version, RULESET_VERSION)

    def test_matches_are_case_insensitive(self) -> None:
        candidates = find_candidates(self.text)

        self.assertEqual(candidates[1].match_text, "Exonerar")

    def test_excerpt_window_is_bounded_by_text_limits(self) -> None:
        candidates = find_candidates("NOMEAR ALGUÉM")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].excerpt_start, 0)
        self.assertEqual(candidates[0].excerpt_end, len("NOMEAR ALGUÉM"))

    def test_negative_acts_produce_no_candidates(self) -> None:
        text = (
            "Art. 1° - Tornar sem efeito a Portaria n° 900.\n"
            "EXTRATO DE CONTRATO 123/2026 — locação de equipamentos.\n"
        )

        self.assertEqual(find_candidates(text), ())

    def test_one_candidate_per_portaria_not_per_word(self) -> None:
        """Título e dispositivo do MESMO ato não viram dois cartões."""
        text = (
            "PORTARIA Nº 205, DE 03 DE JUNHO DE 2026\n\n"
            "Dispõe sobre exoneração a pedido do servidor.\n\n"
            "RESOLVE:\n\n"
            "Art. 1º Exonerar a pedido, a servidora Maria Amélia "
            "Gonçalves Mariano.\n\n"
            "PORTARIA Nº 207, DE 09 DE JUNHO DE 2026\n\n"
            "Dispõe sobre exoneração de servidor.\n\n"
            "Art. 1º Exonerar a pedido o (a) servidor (a) Cleiton Xavier "
            "da Silva.\n"
        )

        candidates = find_candidates(text)

        self.assertEqual(len(candidates), 2)
        self.assertTrue(
            candidates[0].excerpt.startswith("PORTARIA Nº 205"),
        )
        self.assertTrue(
            candidates[1].excerpt.startswith("PORTARIA Nº 207"),
        )

    def test_mentions_in_considerandos_are_not_candidates(self) -> None:
        text = (
            "PORTARIA Nº 300, DE 01 DE JULHO DE 2026\n\n"
            "CONSIDERANDO a Lei nº 617/2003, que prevê cargos de livre "
            "nomeação e exoneração;\n"
            "CONSIDERANDO a valorização profissional.\n"
        )

        self.assertEqual(find_candidates(text), ())

    def test_excerpt_drops_digital_signature_noise(self) -> None:
        text = (
            "Certificado Digital PF A1, OU=Videoconferencia, CN=\n"
            "OTONIEL NASCIMENTO TEIXEIRA:92731767553\n"
            "Foxit PDF Reader Versão: 2024.3.0\n\n"
            "PORTARIA Nº 205, DE 03 DE JUNHO DE 2026\n\n"
            "Art. 1º Exonerar a pedido a servidora Maria Amélia.\n"
        )

        candidate = find_candidates(text)[0]

        self.assertNotIn("Certificado Digital", candidate.excerpt)
        self.assertNotIn("Foxit", candidate.excerpt)
        self.assertTrue(candidate.excerpt.startswith("PORTARIA"))

    def test_defragments_words_split_by_pdf_extraction(self) -> None:
        """Caso real do portal: o PDF parte a palavra entre linhas."""
        raw = (
            "ESTAD\nO DA BAHIA\nMUN\nICÍPIO DE BA\nRREIRAS\nPORT\n"
            "ARIA Nº 213, DE 16 DE JUNHO DE 2026\nDispõe\n"
            "sobre exoneração de servidor."
        )

        cleaned = clean_excerpt(raw)

        self.assertIn("ESTADO DA BAHIA", cleaned)
        self.assertIn("MUNICÍPIO DE BARREIRAS", cleaned)
        self.assertIn("PORTARIA Nº 213", cleaned)
        # Palavra inteira seguida de minúscula continua separada por espaço.
        self.assertIn("Dispõe sobre exoneração", cleaned)

    def test_ordering_is_deterministic_by_position(self) -> None:
        text = "EXONERAR PRIMEIRO. Depois, NOMEAR SEGUNDO."

        candidates = find_candidates(text)

        self.assertEqual(
            [candidate.act_type for candidate in candidates],
            ["exoneracao", "nomeacao"],
        )
        self.assertEqual(find_candidates(text), candidates)


if __name__ == "__main__":
    unittest.main()
