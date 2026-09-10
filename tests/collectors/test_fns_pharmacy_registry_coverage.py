import json
import unittest

from barreiras_collectors.connectors.fns_pharmacy_registry_coverage import (
    compare_registry_catalog,
)

from tests.collectors.test_fns_entity_catalog import capture
from tests.collectors.test_fns_pharmacy_identity import CNPJ, register

OTHER = "11444777000161"


class RegistryCoverageTests(unittest.TestCase):
    def compare(self, *, reg=None, catalogs=None, context=None):
        return compare_registry_catalog(
            register_capture=reg or register(),
            register_context=context
            if context is not None
            else dict(
                municipality="Barreiras",
                uf="BA",
                method="observed_export_filter",
                as_of="2026-09-04",
            ),
            catalog_captures=catalogs
            if catalogs is not None
            else [capture(ids=[CNPJ])],
            payment_year=2025,
        )

    def test_exact_comparison_returns_references_not_names_or_identifiers(self):
        reg = register(
            [
                [CNPJ, "PRIVATE_NAME", "ADDRESS", "NEIGHBORHOOD"],
                [OTHER, "PRIVATE_OTHER", "ADDRESS", "NEIGHBORHOOD"],
            ]
        )
        result = self.compare(reg=reg)
        self.assertEqual(result["status"], "compared")
        self.assertEqual(result["registered_entities"], 2)
        self.assertEqual(result["registered_in_catalog"], 1)
        self.assertEqual(result["registered_not_in_catalog"], 1)
        self.assertEqual(result["not_in_catalog_rows"], [3])
        self.assertFalse(result["publication_allowed"])
        self.assertFalse(result["historical_registration_verified"])
        self.assertEqual(result["payment_presence"], "not_determined")
        self.assertEqual(result["catalog_only_classification"], "not_performed")
        for value in (CNPJ, OTHER, "PRIVATE_NAME", "ADDRESS"):
            self.assertNotIn(value, json.dumps(result))

    def test_empty_not_collected_and_partial_are_distinct(self):
        self.assertEqual(self.compare(catalogs=[])["status"], "not_collected")
        partial = self.compare(
            catalogs=[capture(total=11, ids=[str(i) for i in range(10)])]
        )
        self.assertEqual(partial["status"], "partial_catalog")
        self.assertNotIn("registered_not_in_catalog", partial)
        empty = self.compare(catalogs=[capture(total=0, ids=[])])
        self.assertEqual(empty["catalog_status"], "empty")
        self.assertEqual(empty["registered_not_in_catalog"], 1)
        self.assertEqual(empty["payment_presence"], "not_determined")

    def test_catalog_only_is_not_assumed_pharmacy_or_invalid_identity(self):
        result = self.compare(catalogs=[capture(total=2, ids=[CNPJ, "12345678901"])])
        self.assertEqual(result["catalog_only_entities"], 1)
        self.assertEqual(result["catalog_only_classification"], "not_performed")
        self.assertNotIn("12345678901", json.dumps(result))

    def test_complete_pages_in_any_order_keep_exact_evidence_positions(self):
        first = capture(total=11, ids=[CNPJ, *[str(i) for i in range(9)]])
        last = capture(page=2, total=11, ids=[OTHER])
        reg = register([[CNPJ, "A", "R", "B"], [OTHER, "Z", "R", "B"]])
        result = self.compare(reg=reg, catalogs=[last, first])
        self.assertEqual(result, self.compare(reg=reg, catalogs=[first, last]))
        self.assertEqual(result["catalog_entities"], 11)
        self.assertEqual(result["registered_in_catalog"], 2)
        self.assertEqual(result["not_in_catalog_rows"], [])
        self.assertEqual(
            result["matched_rows"],
            [
                dict(
                    register_row=2, page=1, source_row=1, source_sha256=first["sha256"]
                ),
                dict(
                    register_row=3, page=2, source_row=1, source_sha256=last["sha256"]
                ),
            ],
        )

    def test_duplicates_tampering_and_wrong_territory_block(self):
        reg = register([[CNPJ, "A", "R", "B"], [CNPJ, "A", "R", "B"]])
        self.assertEqual(self.compare(reg=reg)["status"], "invalid_evidence")
        reg = register()
        reg["sha256"] = "0" * 64
        self.assertEqual(self.compare(reg=reg)["status"], "invalid_evidence")
        self.assertEqual(self.compare(context={})["status"], "invalid_evidence")
        bad = dict(
            municipality="Salvador",
            uf="BA",
            method="observed_export_filter",
            as_of="2026-09-04",
        )
        self.assertEqual(self.compare(context=bad)["status"], "invalid_evidence")
        self.assertEqual(
            self.compare(catalogs=[capture(year=2024)])["status"], "invalid_evidence"
        )

    def test_register_date_does_not_become_historical_accreditation(self):
        result = self.compare()
        self.assertEqual(result["register_as_of"], "2026-09-04")
        self.assertEqual(result["payment_year"], 2025)
        self.assertEqual(result["territorial_evidence"], "observed_export_filter")
        self.assertFalse(result["historical_registration_verified"])
