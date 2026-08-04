import unittest

from barreiras_collectors.connectors.municipal_executive import parse_official_page
from barreiras_collectors.persistence.service import (
    executive_record_idempotency_key,
)


class MunicipalExecutiveParserTests(unittest.TestCase):
    def test_profile_idempotency_is_stable_per_snapshot(self):
        first = executive_record_idempotency_key(
            profile_key="prefeito:https://barreiras.ba.gov.br/prefeito-e-vice/:otoniel",
            payload_sha256="a" * 64,
            page_body_sha256="b" * 64,
            parser_version="barreiras-executive-pages/1.1.1",
        )
        replay = executive_record_idempotency_key(
            profile_key="prefeito:https://barreiras.ba.gov.br/prefeito-e-vice/:otoniel",
            payload_sha256="a" * 64,
            page_body_sha256="b" * 64,
            parser_version="barreiras-executive-pages/1.1.1",
        )
        next_snapshot = executive_record_idempotency_key(
            profile_key="prefeito:https://barreiras.ba.gov.br/prefeito-e-vice/:otoniel",
            payload_sha256="a" * 64,
            page_body_sha256="c" * 64,
            parser_version="barreiras-executive-pages/1.1.1",
        )

        self.assertEqual(first, replay)
        self.assertNotEqual(first, next_snapshot)

        next_parser = executive_record_idempotency_key(
            profile_key="prefeito:https://barreiras.ba.gov.br/prefeito-e-vice/:otoniel",
            payload_sha256="a" * 64,
            page_body_sha256="b" * 64,
            parser_version="barreiras-executive-pages/1.1.2",
        )
        self.assertNotEqual(first, next_parser)

    def test_parses_prefeito_and_photo_from_official_block(self):
        page = """
        <div class='content'>
          <div class='secretario'>
            <p>
              <img
                src='https://barreiras.ba.gov.br/wp-content/uploads/prefeito.jpeg'
              />
            </p>
            <h2>Prefeito</h2>
            <h2 class='panel-title'>
              <strong>OTONIEL NASCIMENTO TEIXEIRA</strong>
            </h2>
          </div>
        </div><div class='clear'></div>
        """
        profiles = parse_official_page(
            role="prefeito",
            department="",
            url="https://barreiras.ba.gov.br/prefeito-e-vice/",
            page_html=page,
        )
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["display_name"], "OTONIEL NASCIMENTO TEIXEIRA")
        self.assertEqual(
            profiles[0]["photo_url"],
            "https://barreiras.ba.gov.br/wp-content/uploads/prefeito.jpeg",
        )

    def test_parses_secretary_from_first_official_paragraph(self):
        page = """
        <div class='content'>
          <p>
            <img
              src='https://barreiras.ba.gov.br/wp-content/uploads/secretaria.jpeg'
            />
            GISLAINE CÉSAR DE CARVALHO BARBOSA<br />
            (77) 3614-7104
          </p>
        </div><div class='clear'></div>
        """
        profiles = parse_official_page(
            role="secretario",
            department="Secretaria Municipal de Administração",
            url="https://barreiras.ba.gov.br/secretaria-municipal-de-administracao",
            page_html=page,
        )
        self.assertEqual(len(profiles), 1)
        self.assertEqual(
            profiles[0]["display_name"],
            "GISLAINE CÉSAR DE CARVALHO BARBOSA",
        )

    def test_does_not_invent_profile_when_marker_is_missing(self):
        profiles = parse_official_page(
            role="secretario",
            department="Secretaria Municipal de Educação",
            url="https://barreiras.ba.gov.br/secretaria-municipal-de-educacao",
            page_html="<div class='content'><p>Conteúdo sem responsável.</p></div>",
        )
        self.assertEqual(profiles, ())

    def test_separates_prefeito_and_vice_biographies(self):
        page = """
        <div class='content'>
          <h2>Prefeito</h2>
          <h2 class='panel-title'><strong>OTONIEL NASCIMENTO TEIXEIRA</strong></h2>
          <p>Biografia do prefeito.</p>
          <h2>Vice-prefeito</h2>
          <h2 class='panel-title'><strong>TÚLIO MACHADO VIANA</strong></h2>
          <p>Biografia do vice.</p>
        </div><div class='clear'></div>
        """
        prefeito = parse_official_page(
            role="prefeito",
            department="",
            url="https://barreiras.ba.gov.br/prefeito-e-vice/",
            page_html=page,
        )[0]
        vice = parse_official_page(
            role="vice-prefeito",
            department="",
            url="https://barreiras.ba.gov.br/prefeito-e-vice/",
            page_html=page,
        )[0]
        self.assertIn("Biografia do prefeito", prefeito["source_excerpt"])
        self.assertNotIn("Biografia do vice", prefeito["source_excerpt"])
        self.assertIn("Biografia do vice", vice["source_excerpt"])
        self.assertNotIn("Biografia do prefeito", vice["source_excerpt"])

    def test_associates_portraits_with_the_following_executive_heading(self):
        page = """
        <div class='content'>
          <div class='portrait'><img src='https://barreiras.ba.gov.br/wp-content/uploads/otoniel-scaled.jpeg'></div>
          <h2>Prefeito</h2>
          <h2 class='panel-title'><strong>OTONIEL NASCIMENTO TEIXEIRA</strong></h2>
          <p>Biografia do prefeito.</p>
          <div class='portrait'><img src='https://barreiras.ba.gov.br/wp-content/uploads/tulio.jpeg'></div>
          <h2>Vice-prefeito</h2>
          <h2 class='panel-title'><strong>TÚLIO MACHADO VIANA</strong></h2>
          <p>Biografia do vice.</p>
        </div><div class='clear'></div>
        """
        prefeito = parse_official_page(
            role="prefeito",
            department="",
            url="https://barreiras.ba.gov.br/prefeito-e-vice/",
            page_html=page,
        )[0]
        vice = parse_official_page(
            role="vice-prefeito",
            department="",
            url="https://barreiras.ba.gov.br/prefeito-e-vice/",
            page_html=page,
        )[0]
        self.assertTrue(prefeito["photo_url"].endswith("otoniel-scaled.jpeg"))
        self.assertTrue(vice["photo_url"].endswith("tulio.jpeg"))
