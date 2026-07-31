from __future__ import annotations

import unittest
from pathlib import Path

from barreiras_docproc.candidates import RULESET_VERSION, find_candidates

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
            self.assertEqual(
                self.text[candidate.excerpt_start : candidate.excerpt_end],
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
