import unittest

from barreiras_docproc.local_assist import build_local_act_assist


def field(value: str) -> dict[str, str]:
    return {"value": value, "status": "matched", "rule_id": "fixture"}


class LocalAssistTests(unittest.TestCase):
    def test_builds_neutral_summary_from_deterministic_fields(self):
        outcome = build_local_act_assist(
            "nomeacao",
            {
                "excerpt": (
                    "PORTARIA N 10, DE 3 DE JUNHO DE 2026. "
                    "Nomear MARIA SILVA para o cargo de Assessora."
                ),
                "fields": {
                    "person_name": field("MARIA SILVA"),
                    "position": field("Assessora"),
                    "act_number": field("10"),
                    "act_date": field("2026-06-03"),
                },
            },
        )
        self.assertIsNotNone(outcome)
        self.assertIn("nomeação de MARIA SILVA", outcome.summary)
        self.assertEqual(outcome.provider, "local-deterministic")
        self.assertIn("source_excerpt_sha256", outcome.raw_response)

    def test_multiple_people_stay_for_human_review(self):
        outcome = build_local_act_assist(
            "exoneracao",
            {
                "excerpt": "EXONERAR MARIA SILVA e JOANA SOUZA do cargo de Assessora.",
                "fields": {
                    "person_name": field("MARIA SILVA"),
                    "person_names": [field("MARIA SILVA"), field("JOANA SOUZA")],
                    "multiple_persons_detected": True,
                    "position": field("Assessora"),
                    "act_number": field("10"),
                    "act_date": field("2026-06-03"),
                },
            },
        )
        self.assertIsNone(outcome)

    def test_missing_required_field_stays_for_human_review(self):
        self.assertIsNone(
            build_local_act_assist(
                "nomeacao",
                {
                    "excerpt": "Nomear MARIA SILVA.",
                    "fields": {"person_name": field("MARIA SILVA")},
                },
            )
        )


if __name__ == "__main__":
    unittest.main()
