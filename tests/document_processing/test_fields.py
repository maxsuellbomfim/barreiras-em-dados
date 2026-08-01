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
            "Art. 1º Nomear conforme decisão da PREFEITURA MUNICIPAL DE "
            "BARREIRAS e do ESTADO DA BAHIA, NA PROVA OBJETIVA do certame."
        )
        fields = fields_for(text)

        self.assertIsNone(fields.person_name.value)
        self.assertEqual(fields.person_name.status, "not_found")

    def test_digital_signature_block_is_not_a_person(self) -> None:
        text = (
            "Art. 1º Exonerar o servidor conforme documento assinado.\n"
            "OTONIEL NASCIMENTO TEIXEIRA:92731767553\n"
            "Foxit PDF Reader"
        )
        fields = fields_for(text)

        self.assertIsNone(fields.person_name.value)

    def test_mixed_case_name_after_role_marker(self) -> None:
        """Caso real do portal: nome em caixa mista depois de aposto."""
        text = (
            "PORTARIA Nº 205, DE 03 DE JUNHO DE 2026\n\n"
            "Art. 1º Exonerar a pedido, por motivo de aposentadoria, a "
            "servidora Maria\n\nAmélia Gonçalves Mariano, matrícula nº "
            "2250, do cargo de provimento efetivo de\n\nProfessor V, da "
            "Secretaria Municipal de Educação.\n"
        )
        fields = fields_for(text)

        self.assertEqual(
            fields.person_name.value,
            "Maria Amélia Gonçalves Mariano",
        )
        self.assertEqual(fields.person_name.rule_id, "person-after-role-marker")
        # "provimento efetivo de" é fórmula, não cargo.
        self.assertEqual(fields.position.value, "Professor V")
        self.assertEqual(
            fields.organization.value,
            "Secretaria Municipal de Educação",
        )

    def test_name_after_parenthetical_role_marker(self) -> None:
        text = (
            "PORTARIA Nº 207, DE 09 DE JUNHO DE 2026\n\n"
            "Art. 1º Exonerar a pedido o (a) servidor (a) Cleiton Xavier "
            "da Silva, do cargo\n\nde Assistente de Setor da Secretaria "
            "Municipal de Infraestrutura.\n"
        )
        fields = fields_for(text)

        self.assertEqual(fields.person_name.value, "Cleiton Xavier da Silva")
        self.assertEqual(fields.position.value, "Assistente de Setor")

    def test_document_heading_is_not_a_person(self) -> None:
        """'DE NÃO CONTRATAÇÃO' saiu como pessoa na auditoria."""
        from barreiras_docproc.fields import _plausible_person

        self.assertFalse(_plausible_person("DE NÃO CONTRATAÇÃO"))
        self.assertFalse(_plausible_person("SMS JUSTIFICATIVA"))
        self.assertTrue(_plausible_person("Maria Amélia Gonçalves Mariano"))

    def test_position_keeps_abbreviation_in_school_name(self) -> None:
        from barreiras_docproc.fields import (
            _POSITION_PATTERN,
            _extract_position,
        )

        texto = (
            "para o cargo de Diretor da Escola Municipal Dr. Antônio "
            "Balbino, símbolo NH-2"
        )
        cargo = _extract_position(_POSITION_PATTERN.search(texto))

        self.assertEqual(
            cargo.value,
            "Diretor da Escola Municipal Dr. Antônio Balbino",
        )

    def test_position_still_stops_at_sentence_end(self) -> None:
        from barreiras_docproc.fields import (
            _POSITION_PATTERN,
            _extract_position,
        )

        cargo = _extract_position(
            _POSITION_PATTERN.search("para o cargo de Coordenador. Art. 2º")
        )

        self.assertEqual(cargo.value, "Coordenador")

    def test_organization_stops_before_next_gazette_block(self) -> None:
        """Caso real: a captura invadia o ato seguinte da edição."""
        from barreiras_docproc.fields import (
            _ORGANIZATION_PATTERN,
            _extract_organization,
        )

        poluido = (
            "da Secretaria Municipal de Assistência Social e Trabalho "
            "BARREIRAS BAHIA CONVOCAÇÃO 003/2026 A Secretária"
        )
        limpo = _extract_organization(_ORGANIZATION_PATTERN.search(poluido))

        self.assertEqual(
            limpo.value,
            "Secretaria Municipal de Assistência Social e Trabalho",
        )

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
