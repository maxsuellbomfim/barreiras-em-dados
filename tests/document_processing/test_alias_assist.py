import json
import unittest

from barreiras_docproc.alias_assist import (
    build_alias_messages,
    normalize_name,
    parse_alias_response,
    rank_candidates,
)

CANDIDATES = [
    {
        "representative_external_id": "cm-barreiras:vereador:allan",
        "candidate_id": "50002071490",
        "canonical_name": "ALLAN KARDEC BOMFIM BACELAR",
        "party": "MDB",
    },
    {
        "representative_external_id": "cm-barreiras:vereador:rider",
        "candidate_id": "50002071541",
        "canonical_name": "RIDER MENDONÇA E CASTRO",
        "party": "União",
    },
]


class AliasAssistTests(unittest.TestCase):
    def test_normalization_is_only_a_triage_key(self):
        self.assertEqual(normalize_name("Silma Rocha Alves"), "SILMA ROCHA ALVES")
        self.assertEqual(normalize_name("SILMA  ROCHA-ALVES"), "SILMA ROCHA ALVES")

    def test_ranking_keeps_all_candidates(self):
        ranked = rank_candidates("Allan do Allanbick", CANDIDATES)
        self.assertEqual(
            {candidate["representative_external_id"] for candidate in ranked},
            {candidate["representative_external_id"] for candidate in CANDIDATES},
        )

    def test_prompt_is_closed_world_and_review_only(self):
        messages = build_alias_messages(
            "Allan do Allanbick",
            CANDIDATES,
            source_context="autoria publicada em dois registros",
        )
        joined = " ".join(message["content"] for message in messages)
        self.assertIn("revisão humana", joined)
        self.assertIn("cm-barreiras:vereador:allan", joined)
        self.assertIn("candidate_external_id deve ser exatamente", joined)

    def test_prompt_does_not_treat_current_roster_as_historical_truth(self):
        messages = build_alias_messages(
            "Vereador histórico",
            CANDIDATES,
            source_context="autoria antiga, fora da legislatura atual",
            historical_candidates=[
                {
                    "election_year": 2016,
                    "candidate_id": "old-1",
                    "canonical_name": "VEREADOR HISTÓRICO",
                    "ballot_name": "HISTÓRICO",
                    "party": "PDT",
                    "office": "Vereador",
                }
            ],
        )
        joined = " ".join(message["content"] for message in messages)
        self.assertIn("ausência na lista eleitoral atual não prova no_match", joined)
        self.assertIn("Candidaturas históricas informativas", joined)

    def test_response_accepts_only_id_from_candidate_list(self):
        result = parse_alias_response(
            json.dumps(
                {
                    "decision": "match",
                    "candidate_external_id": "cm-barreiras:vereador:allan",
                    "alias_kind": "nickname",
                    "confidence": 0.82,
                    "rationale": "O contexto oficial mostra a autoria publicada.",
                    "evidence": ["registro oficial da Câmara"],
                }
            ),
            allowed_external_ids={"cm-barreiras:vereador:allan"},
        )
        self.assertEqual(result["decision"], "match")
        self.assertEqual(result["confidence"], 0.82)

    def test_response_rejects_invented_id_and_match_without_id(self):
        base = {
            "decision": "match",
            "candidate_external_id": "inventado",
            "alias_kind": "other",
            "confidence": 0.99,
            "rationale": "parece igual",
            "evidence": ["sem prova suficiente"],
        }
        with self.assertRaises(ValueError):
            parse_alias_response(json.dumps(base), allowed_external_ids=set())
        base["candidate_external_id"] = None
        with self.assertRaises(ValueError):
            parse_alias_response(json.dumps(base), allowed_external_ids=set())

    def test_response_downgrades_unknown_alias_kind_without_accepting_identity(self):
        result = parse_alias_response(
            json.dumps(
                {
                    "decision": "match",
                    "candidate_external_id": "cm-barreiras:vereador:allan",
                    "alias_kind": "official_name",
                    "confidence": 0.7,
                    "rationale": "Apenas a classificação veio fora da taxonomia.",
                    "evidence": ["registro oficial da Câmara"],
                }
            ),
            allowed_external_ids={"cm-barreiras:vereador:allan"},
        )
        self.assertEqual(result["alias_kind"], "other")


if __name__ == "__main__":
    unittest.main()
