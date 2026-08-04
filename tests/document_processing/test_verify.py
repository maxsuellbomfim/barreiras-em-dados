from __future__ import annotations

import unittest

from barreiras_docproc.verify import (
    VERIFIER_VERSION,
    date_in_excerpt,
    value_in_excerpt,
    verify_candidate,
)

EXCERPT = (
    "PORTARIA Nº 205, DE 03 DE JUNHO DE 2026\n\n"
    "O PREFEITO MUNICIPAL DE BARREIRAS, no uso de suas atribuições,\n"
    "RESOLVE:\n"
    "Art. 1º Exonerar a pedido, a servidora MARIA DAS DORES\nSILVA, "
    "do cargo em comissão de Assessora Técnica, símbolo CC-3, da "
    "Secretaria Municipal de Saúde."
)


def payload(fields: dict) -> dict:
    return {"excerpt": EXCERPT, "fields": fields}


def det(value: str) -> dict:
    return {"value": value, "status": "matched", "rule_id": "regra"}


class LiteralVerificationTests(unittest.TestCase):
    def test_value_matches_across_linebreak_case_and_accents(self) -> None:
        self.assertTrue(
            value_in_excerpt("Maria das Dores Silva", EXCERPT)
        )
        self.assertTrue(value_in_excerpt("secretaria municipal de saúde", EXCERPT))

    def test_value_absent_from_text_is_rejected(self) -> None:
        self.assertFalse(value_in_excerpt("JOSÉ INVENTADO", EXCERPT))
        self.assertFalse(value_in_excerpt("", EXCERPT))

    def test_iso_date_matches_spelled_out_portuguese(self) -> None:
        self.assertTrue(date_in_excerpt("2026-06-03", EXCERPT))
        self.assertFalse(date_in_excerpt("2026-06-04", EXCERPT))
        self.assertFalse(date_in_excerpt("não-é-data", EXCERPT))


class VerifyCandidateTests(unittest.TestCase):
    def test_publishes_when_essentials_verified_and_summary_present(
        self,
    ) -> None:
        outcome = verify_candidate(
            payload(
                {
                    "person_name": det("MARIA DAS DORES SILVA"),
                    "act_number": det("205"),
                    "act_date": det("2026-06-03"),
                }
            ),
            {"position": "Assessora Técnica"},
            "A prefeitura exonerou Maria das Dores Silva a pedido dela.",
            "PORTARIA Nº 205. Exonerar a pedido a servidora Maria das "
            "Dores Silva do cargo de Assessora Técnica.",
        )

        self.assertTrue(outcome.publishable)
        self.assertEqual(
            outcome.verified_fields["person_name"]["source"],
            "deterministic",
        )
        self.assertEqual(
            outcome.verified_fields["position"]["source"],
            "assisted",
        )

    def test_assisted_value_absent_from_text_is_dropped(self) -> None:
        outcome = verify_candidate(
            payload(
                {
                    "person_name": det("MARIA DAS DORES SILVA"),
                    "act_number": det("205"),
                    "act_date": det("2026-06-03"),
                    "position": det("Assessora Técnica"),
                }
            ),
            {"organization": "Secretaria de Obras"},
            "Resumo simples do ato.",
            "Texto do ato recomposto.",
        )

        self.assertTrue(outcome.publishable)
        self.assertNotIn("organization", outcome.verified_fields)

    def test_institutional_name_from_ai_is_refused(self) -> None:
        """'SMS JUSTIFICATIVA' chegou ao site: estar no texto não basta."""
        outcome = verify_candidate(
            {
                "excerpt": "SMS JUSTIFICATIVA da PORTARIA Nº 205 de "
                "03 de junho de 2026, cargo de Diretor.",
                "fields": {},
            },
            {
                "person_name": "SMS JUSTIFICATIVA",
                "act_number": "205",
                "act_date": "2026-06-03",
                "position": "Diretor",
            },
            "Resumo.",
            "Texto recomposto.",
        )

        self.assertFalse(outcome.publishable)
        self.assertIn("person_name", outcome.missing)

    def test_organization_invading_next_block_is_refused(self) -> None:
        excerpt = (
            "Art. 1º Exonerar a servidora Maria das Dores Silva do cargo "
            "de Assessora, da Secretaria Municipal de Assistência Social "
            "e Trabalho BARREIRAS BAHIA CONVOCAÇÃO 003/2026. "
            "PORTARIA Nº 205, DE 03 DE JUNHO DE 2026."
        )
        outcome = verify_candidate(
            {"excerpt": excerpt, "fields": {}},
            {
                "person_name": "Maria das Dores Silva",
                "act_number": "205",
                "act_date": "2026-06-03",
                "position": "Assessora",
                "organization": "Secretaria Municipal de Assistência "
                "Social e Trabalho BARREIRAS BAHIA CONVOCAÇÃO 003/2026",
            },
            "Resumo.",
            "Texto recomposto.",
        )

        self.assertTrue(outcome.publishable)
        self.assertNotIn("organization", outcome.verified_fields)

    def test_missing_clean_text_keeps_candidate_for_humans(self) -> None:
        outcome = verify_candidate(
            payload(
                {
                    "person_name": det("MARIA DAS DORES SILVA"),
                    "act_number": det("205"),
                    "act_date": det("2026-06-03"),
                    "position": det("Assessora Técnica"),
                }
            ),
            None,
            "Resumo presente.",
            None,
        )

        self.assertFalse(outcome.publishable)
        self.assertIn("clean_text", outcome.missing)

    def test_missing_person_keeps_candidate_for_humans(self) -> None:
        outcome = verify_candidate(
            payload(
                {
                    "act_number": det("205"),
                    "act_date": det("2026-06-03"),
                }
            ),
            {"person_name": "JOSÉ INVENTADO"},
            "Resumo simples do ato.",
        )

        self.assertFalse(outcome.publishable)
        self.assertIn("person_name", outcome.missing)

    def test_multiple_people_never_publish_as_one_card(self) -> None:
        outcome = verify_candidate(
            payload(
                {
                    "person_name": det("MARIA DAS DORES SILVA"),
                    "person_names": [
                        det("MARIA DAS DORES SILVA"),
                        det("JOANA PEREIRA SANTOS"),
                    ],
                    "act_number": det("205"),
                    "act_date": det("2026-06-03"),
                    "position": det("Assessora Técnica"),
                }
            ),
            None,
            "Resumo simples do ato.",
            EXCERPT,
        )

        self.assertFalse(outcome.publishable)
        self.assertIn("multiple_persons_requires_split_review", outcome.missing)

    def test_missing_summary_keeps_candidate_for_humans(self) -> None:
        outcome = verify_candidate(
            payload(
                {
                    "person_name": det("MARIA DAS DORES SILVA"),
                    "act_number": det("205"),
                    "act_date": det("2026-06-03"),
                }
            ),
            None,
            None,
        )

        self.assertFalse(outcome.publishable)
        self.assertIn("assisted_summary", outcome.missing)

    def test_verifier_is_versioned(self) -> None:
        self.assertRegex(VERIFIER_VERSION, r"^gazette-act-verifier/\d")


if __name__ == "__main__":
    unittest.main()
