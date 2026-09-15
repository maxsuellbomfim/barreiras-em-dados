import hashlib
import io
import json
import unittest

from barreiras_collectors.connectors.fns_pharmacy_identity import (
    inspect_pharmacy_identity,
)
from barreiras_collectors.connectors.fns_pharmacy_matrix_evidence import (
    inspect_registry_renewal_link,
)
from barreiras_collectors.connectors.fns_pharmacy_renewal import (
    HEADER,
    RENEWAL_PATHS,
    inspect_renewal_register,
    validated_renewal_rows,
)
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from tests.collectors.test_fns_pharmacy_identity import CNPJ, payment, register

MATRIX = "11444777000161"


def renewal(pages=None):
    pages = (
        pages if pages is not None else [[HEADER, f"{MATRIX}  {CNPJ}  PRIVATE_MATRIX"]]
    )
    writer = PdfWriter()
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Courier"),
            }
        )
    )
    for lines in pages:
        page = writer.add_blank_page(900, 600)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(
            (
                "BT /F1 10 Tf 40 560 Td "
                + " 0 -15 Td ".join(f"({line}) Tj" for line in lines)
                + " ET"
            ).encode("ascii")
        )
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    raw = output.getvalue()
    return dict(
        body=raw,
        byte_size=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        source_url=RENEWAL_PATHS[0] + "/@@download/file",
        referrer_url=RENEWAL_PATHS[0] + "/view",
        http_status=200,
    )


class MatrixEvidenceTests(unittest.TestCase):
    def inspect(self, *, reg=None, row=2, pdf=None):
        result = inspect_registry_renewal_link(
            register_capture=register() if reg is None else reg,
            register_row=row,
            renewal_capture=renewal() if pdf is None else pdf,
        )
        self.assertFalse(result["publication_allowed"])
        self.assertFalse(result["historical_registration_verified"])
        self.assertEqual(result["payment_presence"], "not_determined")
        self.assertEqual(result["municipal_payment_attribution"], "not_determined")
        for private in (
            CNPJ,
            MATRIX,
            "PRIVATE_MATRIX",
            "FARMACIA TESTE",
            "RUA",
            "BAIRRO",
        ):
            self.assertNotIn(private, json.dumps(result))
        return result

    def test_link_returns_only_document_positions_and_no_publication(self):
        reg, pdf = register(), renewal()
        result = self.inspect(reg=reg, pdf=pdf)
        self.assertEqual(
            result,
            dict(
                status="link_documented",
                register_row=2,
                register_sha256=reg["sha256"],
                renewal_sha256=pdf["sha256"],
                renewal_page=1,
                renewal_row=1,
                renewal_year=2025,
                matrix_is_different=True,
                publication_allowed=False,
                historical_registration_verified=False,
                payment_presence="not_determined",
                municipal_payment_attribution="not_determined",
            ),
        )
        self.assertEqual(result, self.inspect(reg=reg, pdf=pdf))
        # A matrix/branch pair must not become a match in the public identity path.
        self.assertEqual(
            inspect_renewal_register(pdf, CNPJ)["status"], "review_required"
        )

    def test_same_matrix_stays_distinct_from_payment_confirmation(self):
        pdf = renewal([[HEADER, f"{CNPJ}  {CNPJ}  PRIVATE_MATRIX"]])
        self.assertFalse(self.inspect(pdf=pdf)["matrix_is_different"])
        self.assertEqual(
            inspect_renewal_register(pdf, CNPJ)["status"], "institution_matched"
        )

    def test_investigation_does_not_resolve_branch_through_identity_facade(self):
        pdf = renewal()
        self.assertEqual(self.inspect(pdf=pdf)["status"], "link_documented")
        result = inspect_pharmacy_identity(
            register_capture={**pdf, "format": "renewal_pdf"},
            payment_capture=payment(),
            beneficiary=CNPJ,
            payment_year=2025,
        )
        self.assertEqual(result["status"], "review_required")
        self.assertFalse(result["publication_allowed"])
        self.assertNotIn("establishment", result)

    def test_matrix_column_alone_is_not_an_establishment_match(self):
        pdf = renewal([[HEADER, f"{CNPJ}  {MATRIX}  PRIVATE_MATRIX"]])
        result = self.inspect(pdf=pdf)
        self.assertEqual(result["status"], "not_located_in_renewal")
        self.assertNotIn("renewal_page", result)

    def test_repeated_matrix_for_distinct_establishments_is_allowed(self):
        pdf = renewal(
            [
                [HEADER, f"{MATRIX}  {MATRIX}  PRIVATE_MATRIX"],
                [f"{MATRIX}  {CNPJ}  PRIVATE_MATRIX", " " * 32 + "CONTINUED"],
            ]
        )
        result = self.inspect(pdf=pdf)
        self.assertEqual(result["status"], "link_documented")
        self.assertEqual((result["renewal_page"], result["renewal_row"]), (2, 1))

    def test_physical_xlsx_row_selects_exact_full_identifier(self):
        reg = register(
            [
                [MATRIX, "OTHER", "RUA", "BAIRRO"],
                [CNPJ, "FARMACIA TESTE", "RUA", "BAIRRO"],
            ]
        )
        self.assertEqual(
            self.inspect(reg=reg, row=2)["status"], "not_located_in_renewal"
        )
        self.assertEqual(self.inspect(reg=reg, row=3)["status"], "link_documented")

    def test_invalid_row_positions_are_rejected(self):
        for row in (True, False, None, "2", 2.0, -1, 0, 1, 3):
            with self.subTest(row=row):
                self.assertEqual(self.inspect(row=row)["status"], "invalid_evidence")

    def test_duplicate_register_identifiers_are_ambiguous(self):
        for name in ("FARMACIA TESTE", "CONFLICT"):
            reg = register(
                [
                    [CNPJ, "FARMACIA TESTE", "RUA", "BAIRRO"],
                    [CNPJ, name, "RUA", "BAIRRO"],
                ]
            )
            self.assertEqual(self.inspect(reg=reg)["status"], "ambiguous_evidence")

    def test_duplicate_establishment_in_pdf_blocks_even_across_pages(self):
        for matrix in (MATRIX, CNPJ):
            pdf = renewal(
                [
                    [HEADER, f"{MATRIX}  {CNPJ}  PRIVATE_MATRIX"],
                    [f"{matrix}  {CNPJ}  PRIVATE_MATRIX"],
                ]
            )
            self.assertEqual(self.inspect(pdf=pdf)["status"], "ambiguous_evidence")

    def test_invalid_check_digits_block(self):
        for matrix in ("00000000000000", "11444777000160"):
            pdf = renewal([[HEADER, f"{matrix}  {CNPJ}  PRIVATE_MATRIX"]])
            self.assertEqual(self.inspect(pdf=pdf)["status"], "invalid_evidence")
        reg = register([["11222333000180", "PRIVATE", "RUA", "BAIRRO"]])
        self.assertEqual(self.inspect(reg=reg)["status"], "invalid_evidence")

    def test_integrity_and_origin_of_both_captures_are_required(self):
        for key, original in (("reg", register()), ("pdf", renewal())):
            mutations = [
                ("sha256", "0" * 64),
                ("byte_size", 1),
                ("byte_size", True),
                ("body", b"invalid"),
                ("source_url", "https://example.org/private"),
                ("referrer_url", "https://example.org/private"),
            ]
            if key == "pdf":
                mutations.append(("http_status", 500))
            for field, value in mutations:
                with self.subTest(key=key, field=field):
                    self.assertEqual(
                        self.inspect(**{key: {**original, field: value}})["status"],
                        "invalid_evidence",
                    )

    def test_inverted_header_and_malformed_later_page_block_entire_pdf(self):
        for pages in (
            [
                [
                    "CNPJ_ESTABELECIMENTO CNPJ_MATRIZ RAZAO_SOCIAL_MATRIZ_RFB",
                    f"{MATRIX}  {CNPJ}  PRIVATE_MATRIX",
                ]
            ],
            [[HEADER, f"{MATRIX}  {CNPJ}  PRIVATE_MATRIX"], ["BROKEN ROW"]],
        ):
            self.assertEqual(
                self.inspect(pdf=renewal(pages))["status"], "invalid_evidence"
            )

    def test_validated_rows_do_not_expose_mutable_parser_cache(self):
        pdf = renewal()
        rows = validated_renewal_rows(pdf)
        rows[0]["matrix"] = CNPJ
        rows.clear()
        self.assertTrue(self.inspect(pdf=pdf)["matrix_is_different"])
        self.assertEqual(
            inspect_renewal_register(pdf, CNPJ)["status"], "review_required"
        )
