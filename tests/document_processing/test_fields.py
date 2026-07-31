from __future__ import annotations

import unittest
from pathlib import Path

from barreiras_docproc.candidates import find_candidates
from barreiras_docproc.fields import (
    FIELDSET_VERSION,
    extract_act_fields,
    fields_payload,
)

ROOT = Path(__file__).parents[2]
FIXTURE_PATH = (
    ROOT / "fixtures" / "sources" / "querido_diario" / "gazette-text-sample.txt"
)


def fields_for(text: str, index: int = 0):
    candidate = find_candidates(text)[index]
    return extract_act_fields(
        text,
        match_start=candidate.match_start,
        match_end=candidate.match_end,
    )


class ActFieldExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = FIXTURE_PATH.read_text(encoding="utf-8")

    def test_extracts_all_fields_from_nomination(self) -> None:
        fields = fields_for(self.text, index=0)

        self.assertEqual(fields.person_name.value, "FULANO DE TAL EXEMPLO")
        self.assertEqual(fields.person_name.status, "matched")
        self.assertEqual(fields.position.value, "Assessor de Gabinete")
        self.assertEqual(fields.position_symbol.value, "NH-3")
        self.assertEqual(
            fields.organization.value,
            "Secretaria Municipal de Exemplo",
        )
        self.assertEqual(fields.fieldset_version, FIELDSET_VERSION)

    def test_extracts_exoneration_with_a_pedido_clause(self) -> None:
        fields = fields_for(self.text, index=1)

        self.assertEqual(fields.person_name.value, "BELTRANA DE TAL MODELO")
        self.assertEqual(fields.position.value, "Coordenadora de Exemplo")
        self.assertEqual(fields.position_symbol.value, "NH-2")

    def test_person_name_survives_line_breaks(self) -> None:
        text = "RESOLVE: NOMEAR FULANO DE\nTAL QUEBRADO para o cargo de Chefe,"

        fields = fields_for(text)

        self.assertEqual(fields.person_name.value, "FULANO DE TAL QUEBRADO")

    def test_missing_fields_are_explicit_not_guessed(self) -> None:
        text = "Art. 1° - NOMEAR os candidatos conforme anexo único.\n"

        fields = fields_for(text)

        self.assertEqual(fields.person_name.status, "not_found")
        self.assertIsNone(fields.person_name.value)
        self.assertEqual(fields.position.status, "not_found")
        self.assertEqual(fields.position_symbol.status, "not_found")
        self.assertEqual(fields.organization.status, "not_found")

    def test_extraction_is_deterministic(self) -> None:
        first = fields_for(self.text, index=0)
        second = fields_for(self.text, index=0)

        self.assertEqual(first, second)

    def test_payload_carries_status_and_rule_per_field(self) -> None:
        payload = fields_payload(fields_for(self.text, index=0))

        self.assertEqual(payload["fieldset_version"], FIELDSET_VERSION)
        person = payload["person_name"]
        assert isinstance(person, dict)
        self.assertEqual(person["status"], "matched")
        self.assertEqual(person["rule_id"], "person-uppercase-after-verb")


if __name__ == "__main__":
    unittest.main()
