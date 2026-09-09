import hashlib
import io
import unittest

from barreiras_collectors.connectors.fns_pharmacy_renewal import (
    RENEWAL_PATHS,
    inspect_renewal_register,
    match_renewal_rows,
    parse_renewal_pages,
)
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

CNPJ = "11222333000181"
HEADER = "CNPJ_MATRIZ  CNPJ_ESTABELECIMENTO  RAZAO_SOCIAL_MATRIZ_RFB"


class RenewalTests(unittest.TestCase):
    def test_pdf_integrity_origin_and_wrapped_name(self):
        writer = PdfWriter()
        page = writer.add_blank_page(900, 600)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Courier"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        stream = DecodedStreamObject()
        stream.set_data(
            (
                "BT /F1 10 Tf 40 560 Td ("
                + HEADER
                + ") Tj 0 -15 Td ("
                + CNPJ
                + "  "
                + CNPJ
                + "  FARMACIA TESTE) Tj ET"
            ).encode()
        )
        page[NameObject("/Contents")] = writer._add_object(stream)
        output = io.BytesIO()
        writer.write(output)
        raw = output.getvalue()
        capture = dict(
            body=raw,
            byte_size=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            http_status=200,
            source_url=RENEWAL_PATHS[0] + "/@@download/file",
            referrer_url=RENEWAL_PATHS[0] + "/view",
        )
        result = inspect_renewal_register(capture, CNPJ)
        self.assertEqual(result["status"], "institution_matched")
        self.assertFalse(result["historical_registration_verified"])
        self.assertFalse(result["publication_allowed"])
        for field, value in [
            ("http_status", None),
            ("sha256", "0" * 64),
            ("source_url", "https://example.org/a.pdf"),
        ]:
            self.assertEqual(
                inspect_renewal_register({**capture, field: value}, CNPJ)["status"],
                "invalid_evidence",
            )
        rows = parse_renewal_pages(
            [HEADER + "\n" + CNPJ + "  " + CNPJ + "  FARMACIA\n" + " " * 32 + "TESTE"]
        )
        self.assertEqual(rows[0]["name"], "FARMACIA TESTE")

    def test_exact_establishment_with_page_and_row_not_historical_accreditation(self):
        rows = parse_renewal_pages([HEADER + "\n" + f"{CNPJ}  {CNPJ}  FARMACIA TESTE"])
        result = match_renewal_rows(rows, CNPJ)
        self.assertEqual(
            result,
            dict(establishment="FARMACIA TESTE", register_page=1, register_row=1),
        )
        self.assertNotIn(CNPJ, str(result))

    def test_matrix_or_duplicate_or_partial_name_never_resolves(self):
        for body in [
            f"{CNPJ}  11444777000161  FARMACIA TESTE",
            f"11444777000161  {CNPJ}  FARMACIA TESTE",
            f"{CNPJ}  {CNPJ}  FARMACIA TESTE\n{CNPJ}  {CNPJ}  FARMACIA TESTE",
        ]:
            self.assertIsNone(
                match_renewal_rows(parse_renewal_pages([HEADER + "\n" + body]), CNPJ)
            )
        with self.assertRaises(ValueError):
            parse_renewal_pages([HEADER + "\n" + "LINHA SEM IDENTIFICADORES"])
        with self.assertRaises(ValueError):
            parse_renewal_pages([f"{CNPJ}  {CNPJ}  FARMACIA TESTE"])
