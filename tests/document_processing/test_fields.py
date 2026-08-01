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
        self.assertEqual(fields.act_number.value, "901")
        self.assertEqual(fields.act_date.value, "2026-06-15")
        self.assertEqual(fields.fieldset_version, FIELDSET_VERSION)

    def test_extracts_exoneration_with_a_pedido_clause(self) -> None:
        fields = fields_for(self.text, index=1)

        self.assertEqual(fields.person_name.value, "BELTRANA DE TAL MODELO")
        self.assertEqual(fields.position.value, "Coordenadora de Exemplo")
        self.assertEqual(fields.position_symbol.value, "NH-2")
        # O cabeçalho mais próximo antes do verbo é a Portaria 902.
        self.assertEqual(fields.act_number.value, "902")
        self.assertEqual(fields.act_date.value, "2026-06-15")

    def test_person_found_after_filler_text_between_verb_and_name(self) -> None:
        # Forma real dos diários: preposições e apostos antes do nome.
        text = (
            "PORTARIA Nº 210, DE 10 DE JUNHO DE 2026\n"
            "RESOLVE: Art. 1º Nomear a candidata habilitada no concurso "
            "público, MARIA DAS DORES SILVA, para o cargo de Professora."
        )
        fields = fields_for(text)

        self.assertEqual(fields.person_name.value, "MARIA DAS DORES SILVA")
        self.assertEqual(
            fields.person_name.rule_id,
            "person-uppercase-in-window",
        )

    def test_institutional_uppercase_is_not_a_person(self) -> None:
        text = (
            "prevê cargos de livre nomeação e exoneração conforme a "
            "PREFEITURA MUNICIPAL DE BARREIRAS e o ESTADO DA BAHIA, "
            "NA PROVA OBJETIVA do certame."
        )
        fields = fields_for(text)

        self.assertIsNone(fields.person_name.value)
        self.assertEqual(fields.person_name.status, "not_found")

    def test_digital_signature_block_is_not_a_person(self) -> None:
        text = (
            "Dispõe sobre exoneração de servidor.\n"
            "OTONIEL NASCIMENTO TEIXEIRA:92731767553\n"
            "Foxit PDF Reader"
        )
        fields = fields_for(text)

        self.assertIsNone(fields.person_name.value)

    def test_act_heading_missing_or_invalid_is_explicit(self) -> None:
        no_heading = fields_for("RESOLVE: NOMEAR FULANO DE TAL para o cargo,")
        self.assertEqual(no_heading.act_number.status, "not_found")
        self.assertEqual(no_heading.act_date.status, "not_found")

        invalid_date = fields_for(
            "PORTARIA N° 77, DE 31 DE FEVEREIRO DE 2026.\n"
            "RESOLVE: NOMEAR FULANO DE TAL para o cargo,"
        )
        self.assertEqual(invalid_date.act_number.value, "77")
        self.assertEqual(invalid_date.act_date.status, "not_found")
        self.assertIsNone(invalid_date.act_date.value)

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
