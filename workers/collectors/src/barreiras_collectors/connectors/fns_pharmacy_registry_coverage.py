"""Private snapshot comparison, not payment absence or historical accreditation."""

import json
from datetime import date

from .fns_entity_catalog import inspect_entity_catalog
from .fns_pharmacy_identity import validated_register_rows


def compare_registry_catalog(
    *, register_capture, register_context, catalog_captures, payment_year
):
    """Compare exact identifiers; output only counts and evidence positions.

    Context comes from the trusted operator who observed the export filter.
    The four-column XLSX itself cannot prove the municipality or position date.
    No input or result from this function may authorize publication.
    """
    base = dict(
        publication_allowed=False,
        historical_registration_verified=False,
        payment_presence="not_determined",
        catalog_only_classification="not_performed",
    )
    try:
        if (
            register_context.get("municipality") != "Barreiras"
            or register_context.get("uf") != "BA"
            or register_context.get("method") != "observed_export_filter"
        ):
            raise ValueError("Territorial context required")
        as_of = register_context["as_of"]
        if not isinstance(as_of, str) or date.fromisoformat(as_of).isoformat() != as_of:
            raise ValueError("Invalid register position date")
        rows = validated_register_rows(register_capture)
        registered = {row[0] for row in rows}
        if len(registered) != len(rows):
            raise ValueError("Duplicate register identifier")
        catalog = inspect_entity_catalog(catalog_captures, payment_year=payment_year)
        status = catalog["status"]
        if status not in ("complete", "empty"):
            return dict(
                base,
                status={
                    "not_collected": "not_collected",
                    "partial": "partial_catalog",
                }.get(status, "invalid_evidence"),
            )
        identities = {}
        for capture in catalog_captures:
            data = json.loads(capture["body"])["resultado"]
            for index, row in enumerate(data["dados"], 1):
                identities[row["cpfCnpj"]] = dict(
                    page=data["pagina"] + 1,
                    source_row=index,
                    source_sha256=capture["sha256"],
                )
        found = registered.intersection(identities)
        return dict(
            base,
            status="compared",
            catalog_status=status,
            payment_year=payment_year,
            register_as_of=as_of,
            territorial_evidence="observed_export_filter",
            register_sha256=register_capture["sha256"],
            catalog_sha256s=sorted({c["sha256"] for c in catalog_captures}),
            registered_entities=len(registered),
            catalog_entities=len(identities),
            registered_in_catalog=len(found),
            registered_not_in_catalog=len(registered - identities.keys()),
            catalog_only_entities=len(identities.keys() - registered),
            not_in_catalog_rows=[
                index for index, row in enumerate(rows, 2) if row[0] not in identities
            ],
            matched_rows=[
                dict(register_row=index, **identities[row[0]])
                for index, row in enumerate(rows, 2)
                if row[0] in found
            ],
        )
    except Exception:
        # ZIP/XML/JSON/source errors must not expose original data or filenames.
        return dict(base, status="invalid_evidence")
