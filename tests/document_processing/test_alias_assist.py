import json
import unittest
from unittest.mock import patch

from barreiras_docproc.alias_assist import (
    build_alias_messages,
    classify_alias_deterministically,
    name_match_signals,
    normalize_name,
    parse_alias_response,
    rank_candidates,
    run_alias_assistance,
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

    def test_parenthetical_name_is_a_signal_not_published_text(self):
        signals = name_match_signals(
            "Allan Kardec (Allan do Allanbick)",
            CANDIDATES[0],
        )
        self.assertTrue(signals["first_and_surname"])
        self.assertIn("KARDEC", signals["surname_overlap"])
        result = classify_alias_deterministically(
            "Allan Kardec (Allan do Allanbick)",
            CANDIDATES,
        )
        self.assertEqual(result["decision"], "match")
        self.assertEqual(
            result["candidate_external_id"],
            "cm-barreiras:vereador:allan",
        )
        self.assertEqual(result["alias_kind"], "ballot_name")
        self.assertLess(result["confidence"], 0.8)

    def test_nickname_without_name_base_does_not_identify_a_person(self):
        result = classify_alias_deterministically("Allan do Allanbick", CANDIDATES)
        self.assertEqual(result["decision"], "ambiguous")
        self.assertIsNone(result["candidate_external_id"])

    def test_case_variants_are_classified_without_accepting_them(self):
        result = classify_alias_deterministically(
            "silma rocha alves",
            [
                {
                    "representative_external_id": "cm-barreiras:vereador:silma",
                    "canonical_name": "SILMA ROCHA ALVES",
                }
            ],
        )
        self.assertEqual(result["decision"], "match")
        self.assertEqual(result["alias_kind"], "case_variant")
        self.assertEqual(
            result["validator_version"],
            "representative-alias-literal-safe/1.0.0",
        )

    def test_equal_first_and_surname_remains_ambiguous(self):
        result = classify_alias_deterministically(
            "Maria Silva",
            [
                {
                    "representative_external_id": "cm-barreiras:vereador:one",
                    "canonical_name": "MARIA SILVA SOUZA",
                },
                {
                    "representative_external_id": "cm-barreiras:vereador:two",
                    "canonical_name": "MARIA SILVA SANTOS",
                },
            ],
        )
        self.assertEqual(result["decision"], "ambiguous")
        self.assertIsNone(result["candidate_external_id"])

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

    def test_cascade_quarantines_invented_id_as_ambiguous(self):
        class Logger:
            def warning(self, *_args):
                return None

        invalid = json.dumps(
            {
                "decision": "match",
                "candidate_external_id": "tse-historical:2016:old-1",
                "alias_kind": "nickname",
                "confidence": 0.95,
                "rationale": "nome parecido",
                "evidence": ["candidatura histórica"],
            }
        )
        with patch(
            "barreiras_docproc.alias_assist.run_cascade_content",
            return_value=("groq", "model", invalid),
        ):
            _provider, _model, result, _raw = run_alias_assistance(
                None,
                {},
                "Vereador histórico",
                CANDIDATES,
                source_context="registro antigo",
                logger=Logger(),
                attempts=[],
            )
        self.assertEqual(result["decision"], "ambiguous")
        self.assertIsNone(result["candidate_external_id"])

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
