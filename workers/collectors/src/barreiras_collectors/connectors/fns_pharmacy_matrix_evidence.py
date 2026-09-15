"""Private establishment/matrix evidence; never a municipal payment allocation."""

from .fns_pharmacy_identity import _valid_cnpj, validated_register_rows
from .fns_pharmacy_renewal import validated_renewal_rows


def inspect_registry_renewal_link(*, register_capture, register_row, renewal_capture):
    """Locate an exact XLSX establishment in the second column of the 2025 PDF.

    Both captures must come from trusted preservation, not web-client input.
    The XLSX has no intrinsic municipality/date; neither snapshot establishes
    a historical link or payment to a branch. Return only document references.
    This investigation is intentionally separate from the publishing matcher.
    """
    base = dict(
        publication_allowed=False,
        historical_registration_verified=False,
        payment_presence="not_determined",
        municipal_payment_attribution="not_determined",
    )
    try:
        registered = validated_register_rows(register_capture)
        if (
            type(register_row) is not int
            or not 2 <= register_row <= len(registered) + 1
        ):
            raise ValueError("Invalid registry row")
        if len({row[0] for row in registered}) != len(registered):
            return dict(base, status="ambiguous_evidence")
        identifier = registered[register_row - 2][0]
        rows = validated_renewal_rows(renewal_capture)
        matches = [row for row in rows if row["identifier"] == identifier]
        references = dict(
            register_row=register_row,
            register_sha256=register_capture["sha256"],
            renewal_sha256=renewal_capture["sha256"],
            renewal_year=2025,
        )
        if not matches:
            return dict(base, **references, status="not_located_in_renewal")
        if len(matches) != 1:
            return dict(base, status="ambiguous_evidence")
        match = matches[0]
        if not _valid_cnpj(match["matrix"]) or not _valid_cnpj(match["identifier"]):
            raise ValueError("Invalid renewal identifier")
        return dict(
            base,
            **references,
            status="link_documented",
            renewal_page=match["page"],
            renewal_row=match["row"],
            matrix_is_different=match["matrix"] != identifier,
        )
    except Exception:
        # Do not leak source identifiers, names, addresses or exception contents.
        return dict(base, status="invalid_evidence")
