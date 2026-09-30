from __future__ import annotations

import unittest
from datetime import date

from barreiras_collectors.commands.collect_siconfi_rgf import closed_periods
from barreiras_collectors.connectors.siconfi import (
    SiconfiContractError,
    fetch_siconfi_rgf_annex2,
    parse_siconfi_rgf_page,
)
from barreiras_collectors.persistence.service import SiconfiDcaPersistenceService
from barreiras_collectors.resilience import RetryPolicy

from tests.collectors.test_siconfi_dca import (
    CountingLimiter,
    SequenceTransport,
    page_body,
    response,
)
from tests.collectors.test_siconfi_dca_persistence import (
    FakeObjectStore,
    FakeRepository,
)

RGF_URL = (
    "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rgf?an_exercicio=2024"
    "&in_periodicidade=Q&nr_periodo=3&co_tipo_demonstrativo=RGF"
    "&no_anexo=RGF-Anexo+02&co_esfera=M&co_poder=E&id_ente=2903201"
    "&limit=5000&offset=0"
)


def rgf_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "exercicio": 2024,
        "periodo": 3,
        "periodicidade": "Q",
        "instituicao": "Prefeitura Municipal de Barreiras - BA",
        "cod_ibge": 2903201,
        "uf": "BA",
        "co_poder": "E",
        "populacao": 165413,
        "anexo": "RGF-Anexo 02",
        "esfera": "M",
        "rotulo": "Padrão",
        "coluna": "Até o 3º Quadrimestre",
        "cod_conta": "DividaConsolidadaLiquida",
        "conta": "DÍVIDA CONSOLIDADA LÍQUIDA (DCL) (III) = (I - II)",
        "valor": 837492964.58,
    }
    item.update(overrides)
    return item


def parse(items):
    return parse_siconfi_rgf_page(
        page_body(items),
        expected_year=2024,
        expected_period=3,
        expected_offset=0,
        expected_limit=5000,
    )


class SiconfiRgfContractTests(unittest.TestCase):
    def test_keeps_declared_values_as_decimal_text(self) -> None:
        parsed = parse([rgf_item(), rgf_item(coluna="SALDO DO EXERCÍCIO ANTERIOR")])
        self.assertEqual(parsed.items[0]["valor"], "837492964.58")
        self.assertEqual(parsed.items[0]["periodo"], 3)

    def test_rejects_other_period_annex_power_or_missing_fields(self) -> None:
        for broken, message in (
            (rgf_item(periodo=2), "Período"),
            (rgf_item(anexo="RGF-Anexo 01"), "Anexo 02"),
            (rgf_item(co_poder="L"), "Anexo 02"),
            (rgf_item(periodicidade="S"), "Anexo 02"),
        ):
            with (
                self.subTest(broken=broken),
                self.assertRaisesRegex(SiconfiContractError, message),
            ):
                parse([broken])
        missing = rgf_item()
        del missing["esfera"]
        with self.assertRaisesRegex(SiconfiContractError, "contrato oficial"):
            parse([missing])

    def test_rejects_duplicate_source_identity(self) -> None:
        with self.assertRaisesRegex(SiconfiContractError, "duplicada"):
            parse([rgf_item(), rgf_item()])


class SiconfiRgfDownloadTests(unittest.TestCase):
    def fetch(self, final_url: str = RGF_URL):
        transport = SequenceTransport(
            [response(page_body([rgf_item()]), final_url=final_url)]
        )
        pages = fetch_siconfi_rgf_annex2(
            year=2024,
            period=3,
            transport=transport,
            rate_limiter=CountingLimiter(),
            retry_policy=RetryPolicy(max_attempts=1),
            sleep=lambda _seconds: None,
        )
        return pages, transport

    def test_requests_executive_annex2_of_the_quadrimester(self) -> None:
        pages, transport = self.fetch()
        self.assertEqual(transport.requests, [RGF_URL])
        page = pages[0]
        self.assertEqual(page.endpoint_code, "rgf-anexo-02")
        self.assertEqual(page.schema_name, "siconfi-rgf-annex2-page")
        self.assertEqual(
            (page.window_start, page.window_end), ("2024-01-01", "2024-12-31")
        )
        self.assertEqual(page.cursor["period"], 3)

    def test_rejects_redirect_to_another_period(self) -> None:
        with self.assertRaisesRegex(SiconfiContractError, "URL final"):
            self.fetch(RGF_URL.replace("nr_periodo=3", "nr_periodo=2"))

    def test_persists_under_its_own_corridor_and_record_type(self) -> None:
        pages, _transport = self.fetch()
        repository = FakeRepository()
        result = SiconfiDcaPersistenceService(
            object_store=FakeObjectStore(), repository=repository
        ).persist(pages[0])
        self.assertTrue(result.object_key.startswith("siconfi/rgf/2024/q3/sha256/"))
        record = repository.batches[0].records[0]
        self.assertEqual(record.record_type, "siconfi_rgf_annex2_line")
        self.assertEqual(record.parser_version, "siconfi-rgf-annex2-page/1.0.0")
        self.assertTrue(
            record.source_record_key.startswith("siconfi:rgf-anexo-02:2024:3:")
        )
        self.assertEqual(
            repository.batches[0].collector_version,
            "siconfi-rgf-annex2-collector/1.0.0",
        )


class ClosedPeriodTests(unittest.TestCase):
    def test_only_finished_quadrimesters_are_requested(self) -> None:
        self.assertEqual(
            closed_periods(2025, 2026, collected_on=date(2026, 9, 30)),
            ((2025, 1), (2025, 2), (2025, 3), (2026, 1), (2026, 2)),
        )
        with self.assertRaises(ValueError):
            closed_periods(2014, 2026, collected_on=date(2026, 9, 30))


if __name__ == "__main__":
    unittest.main()
