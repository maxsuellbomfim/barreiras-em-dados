"""Private exact institutional match against a preserved Infoms XLSX export.

Acquisition URLs/hashes must be supplied by trusted transport, not web clients.
This bounded reader supports the observed four-column export, not arbitrary
Excel workbooks. Current registration does not prove historical accreditation.
"""

import hashlib
import io
import re
import zipfile
from urllib.parse import urlsplit
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from .fns_payment_evidence import _require
from .fns_pharmacy_pages import inspect_pharmacy_capture

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
MAX_BYTES = 2_000_000
MAX_EXPANDED_BYTES = 8_000_000
REGISTER_PAGE = (
    "https://infoms.saude.gov.br/extensions/SEIDIGI_DEMAS_PFPB_ENDERECOS/index.html"
)


def _valid_cnpj(value: str) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{14}", value):
        return False
    if len(set(value)) == 1:
        return False
    digits = [int(c) for c in value]
    for size in (12, 13):
        weights = list(range(size - 7, 1, -1)) + list(range(9, 1, -1))
        remainder = sum(a * b for a, b in zip(digits[:size], weights, strict=True)) % 11
        if digits[size] != (0 if remainder < 2 else 11 - remainder):
            return False
    return True


def _register_rows(body: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        entries = archive.infolist()
        names = [e.filename for e in entries]
        _require(len(names) == len(set(names)) and len(names) <= 30)
        _require(sum(e.file_size for e in entries) <= MAX_EXPANDED_BYTES)
        _require(not any(e.flag_bits & 1 for e in entries))
        sheets = [n for n in names if n.startswith("xl/worksheets/")]
        _require(sheets == ["xl/worksheets/sheet1.xml"])
        _require(not any("externalLink" in n or "vbaProject" in n for n in names))
        strings = []
        if "xl/sharedStrings.xml" in names:
            shared = fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(s.itertext()) for s in shared.findall(f"{NS}si")]
        sheet = fromstring(archive.read(sheets[0]))
        _require(not list(sheet.iter(f"{NS}f")))
        _require(not list(sheet.iter(f"{NS}mergeCell")))
        rows = sheet.findall(f"{NS}sheetData/{NS}row")
        _require(2 <= len(rows) <= 1001)
        result = []
        for index, row in enumerate(rows, 1):
            _require(row.get("r") == str(index))
            cells = row.findall(f"{NS}c")
            _require(len(cells) == 4)
            values = []
            for column, cell in zip("ABCD", cells, strict=True):
                _require(cell.get("r") == f"{column}{index}")
                if cell.get("t") == "s":
                    ref = cell.findtext(f"{NS}v", "")
                    _require(bool(re.fullmatch(r"[0-9]+", ref)))
                    value = strings[int(ref)]
                else:
                    _require(cell.get("t") == "inlineStr")
                    value = "".join(t.text or "" for t in cell.findall(f"{NS}is/{NS}t"))
                _require(0 < len(value) <= 500)
                values.append(value)
            result.append(values)
        _require(result[0] == ["CNPJ", "Farmácia", "Endereço", "Bairro"])
        return result[1:]


def inspect_pharmacy_identity(
    *,
    register_capture: dict,
    payment_capture: dict,
    beneficiary: str,
    payment_year: int,
) -> dict:
    """Match CNPJ exactly; never resolve identity by a similar name or amount.

    No identifier/address/account is returned. No cross-source money total is
    created. A repeated identifier, even identical rows, remains reviewable.
    """
    blocked = dict(status="invalid_evidence", publication_allowed=False)
    try:
        _require(_valid_cnpj(beneficiary))
        payment = inspect_pharmacy_capture(
            payment_capture, beneficiary=beneficiary, payment_year=payment_year
        )
        _require(payment["status"] == "documentary_consistent")
        raw = register_capture["body"]
        _require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_BYTES)
        _require(type(register_capture["byte_size"]) is int)
        _require(register_capture["byte_size"] == len(raw))
        sha = hashlib.sha256(raw).hexdigest()
        _require(register_capture["sha256"] == sha)
        _require(register_capture["referrer_url"] == REGISTER_PAGE)
        url = register_capture["source_url"]
        _require(isinstance(url, str) and not any(c.isspace() for c in url))
        parsed = urlsplit(url)
        _require(parsed.scheme == "https" and parsed.netloc == "infoms.saude.gov.br")
        _require(
            parsed.path.startswith("/tempcontent/") and parsed.path.endswith(".xlsx")
        )
        _require(not parsed.fragment)
        rows = _register_rows(raw)
        _require(all(_valid_cnpj(row[0]) for row in rows))
        matches = [row for row in rows if row[0] == beneficiary]
        if len(matches) != 1:
            return dict(status="review_required", publication_allowed=False)
        name = matches[0][1]
        _require(2 <= len(name) <= 180 and name == name.strip())
        _require(not re.search(r"[<>\x00-\x1f\x7f]|[0-9]{11}", name))
        return dict(
            status="institution_matched",
            establishment=name,
            register_sha256=sha,
            register_row=rows.index(matches[0]) + 2,
            payment_sha256=payment_capture["sha256"],
            historical_registration_verified=False,
            reconciliation="pending",
            publication_allowed=False,
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        OSError,
        zipfile.BadZipFile,
        ParseError,
        DefusedXmlException,
    ):
        return blocked
