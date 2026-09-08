import hashlib
import io
import unittest
import zipfile
from xml.sax.saxutils import escape

from barreiras_collectors.connectors.fns_pharmacy_identity import (
    inspect_pharmacy_identity,
)

from tests.collectors.test_fns_pharmacy_pages import capture

CNPJ = "11222333000181"
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def register(rows=None):
    rows = rows if rows is not None else [[CNPJ, "FARMACIA TESTE", "RUA", "BAIRRO"]]
    rows = [["CNPJ", "Farmácia", "Endereço", "Bairro"], *rows]
    xml = "".join(
        f'<row r="{i}">'
        + "".join(
            f'<c r="{col}{i}" t="inlineStr"><is><t>{escape(v)}</t></is></c>'
            for col, v in zip("ABCD", row, strict=True)
        )
        + "</row>"
        for i, row in enumerate(rows, 1)
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{NS}"><sheetData>{xml}</sheetData></worksheet>',
        )
    body = out.getvalue()
    return dict(
        body=body,
        sha256=hashlib.sha256(body).hexdigest(),
        byte_size=len(body),
        source_url="https://infoms.saude.gov.br/tempcontent/export/register.xlsx",
        referrer_url="https://infoms.saude.gov.br/extensions/SEIDIGI_DEMAS_PFPB_ENDERECOS/index.html",
    )


def payment():
    result = capture()
    result["request_url"] = result["final_url"] = result["request_url"].replace(
        "00000000000000", CNPJ
    )
    return result


class PharmacyIdentityTests(unittest.TestCase):
    def inspect(self, reg=None, pay=None, beneficiary=CNPJ):
        return inspect_pharmacy_identity(
            register_capture=reg if reg is not None else register(),
            payment_capture=pay if pay is not None else payment(),
            beneficiary=beneficiary,
            payment_year=2025,
        )

    def test_exact_institution_with_two_evidence_hashes_not_publication(self):
        reg = register()
        result = self.inspect(reg)
        self.assertEqual(result["status"], "institution_matched")
        self.assertEqual(result["establishment"], "FARMACIA TESTE")
        self.assertEqual(result["register_sha256"], reg["sha256"])
        self.assertEqual(result["payment_sha256"], payment()["sha256"])
        self.assertFalse(result["historical_registration_verified"])
        self.assertFalse(result["publication_allowed"])
        self.assertNotIn(CNPJ, str(result))
        self.assertNotIn("DO_NOT_EXPOSE", str(result))

    def test_names_never_override_identifier_and_repetitions_need_review(self):
        for rows in (
            [["11444777000161", "FARMACIA TESTE", "R", "B"]],
            [[CNPJ, "NOME A", "R", "B"], [CNPJ, "NOME A", "R", "B"]],
            [[CNPJ, "NOME A", "R", "B"], [CNPJ, "NOME B", "R", "B"]],
        ):
            self.assertEqual(self.inspect(register(rows))["status"], "review_required")

    def test_invalid_identifiers_are_not_institutional_evidence(self):
        for identifier in ("00000000000000", "12345678901", "11222333000182"):
            self.assertEqual(
                self.inspect(beneficiary=identifier)["status"], "invalid_evidence"
            )

    def test_tampering_wrong_source_and_wrong_payment_fail_closed(self):
        for field, value in (
            ("sha256", "a" * 64),
            ("byte_size", 1),
            ("source_url", "https://example.org/register.xlsx"),
        ):
            reg = register()
            reg[field] = value
            self.assertEqual(self.inspect(reg)["status"], "invalid_evidence")
        pay = payment()
        pay["sha256"] = "a" * 64
        self.assertEqual(self.inspect(pay=pay)["status"], "invalid_evidence")

    def test_register_names_with_private_payload_are_rejected(self):
        reg = register([[CNPJ, "FARMACIA\nCPF 12345678901", "R", "B"]])
        result = self.inspect(reg)
        self.assertEqual(result["status"], "invalid_evidence")
        self.assertNotIn("12345678901", str(result))

    def test_formula_xml_entities_duplicate_members_and_extra_sheets_blocked(self):
        for mode in ("formula", "entity", "duplicate", "sheet", "broken"):
            reg = register()
            with zipfile.ZipFile(io.BytesIO(reg["body"])) as original:
                xml = original.read("xl/worksheets/sheet1.xml")
            if mode == "formula":
                xml = xml.replace(b"<is>", b'<f>HYPERLINK("private")</f><is>', 1)
            if mode == "entity":
                xml = b'<!DOCTYPE x [<!ENTITY e "bad">]>' + xml
            if mode == "broken":
                xml = b"not xml"
            out = io.BytesIO()
            with zipfile.ZipFile(out, "w") as archive:
                archive.writestr("xl/worksheets/sheet1.xml", xml)
                if mode == "duplicate":
                    with self.assertWarns(UserWarning):
                        archive.writestr("xl/worksheets/sheet1.xml", xml)
                if mode == "sheet":
                    archive.writestr("xl/worksheets/sheet2.xml", xml)
            reg["body"] = out.getvalue()
            reg["byte_size"] = len(reg["body"])
            reg["sha256"] = hashlib.sha256(reg["body"]).hexdigest()
            self.assertEqual(self.inspect(reg)["status"], "invalid_evidence", mode)
