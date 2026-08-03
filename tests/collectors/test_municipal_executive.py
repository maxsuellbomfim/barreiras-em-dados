import unittest

from barreiras_collectors.connectors.municipal_executive import parse_official_page


class MunicipalExecutiveParserTests(unittest.TestCase):
    def test_parses_prefeito_and_photo_from_official_block(self):
        page = """
        <div class='content'>
          <div class='secretario'>
            <p><img src='https://barreiras.ba.gov.br/wp-content/uploads/prefeito.jpeg' /></p>
            <h2>Prefeito</h2>
            <h2 class='panel-title'><strong>OTONIEL NASCIMENTO TEIXEIRA</strong></h2>
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
        self.assertEqual(profiles[0]["photo_url"], "https://barreiras.ba.gov.br/wp-content/uploads/prefeito.jpeg")

    def test_parses_secretary_from_first_official_paragraph(self):
        page = """
        <div class='content'>
          <p><img src='https://barreiras.ba.gov.br/wp-content/uploads/secretaria.jpeg' />
          GISLAINE CÉSAR DE CARVALHO BARBOSA<br />
          (77) 3614-7104</p>
        </div><div class='clear'></div>
        """
        profiles = parse_official_page(
            role="secretario",
            department="Secretaria Municipal de Administração",
            url="https://barreiras.ba.gov.br/secretaria-municipal-de-administracao",
            page_html=page,
        )
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["display_name"], "GISLAINE CÉSAR DE CARVALHO BARBOSA")

    def test_does_not_invent_profile_when_marker_is_missing(self):
        profiles = parse_official_page(
            role="secretario",
            department="Secretaria Municipal de Educação",
            url="https://barreiras.ba.gov.br/secretaria-municipal-de-educacao",
            page_html="<div class='content'><p>Conteúdo sem responsável.</p></div>",
        )
        self.assertEqual(profiles, ())
