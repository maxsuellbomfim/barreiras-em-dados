from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from barreiras_docproc.anydoc_adapter import (
    ANYDOC_PARSER_VERSION,
    MAX_INPUT_BYTES,
    AnyDocConversionError,
    AnyDocUnavailable,
    convert_to_markdown,
)


class AnyDocAdapterTests(unittest.TestCase):
    def test_output_has_input_and_derived_hashes(self) -> None:
        fake = types.SimpleNamespace(
            format_from_bytes=lambda body: "docx",
            to_markdown_bytes=lambda body: "# Edital\n\nConteúdo",
        )
        with patch.dict(sys.modules, {"anydoc": fake}):
            result = convert_to_markdown(b"PK\x03\x04")

        self.assertEqual(result.detected_format, "docx")
        self.assertEqual(result.parser_version, ANYDOC_PARSER_VERSION)
        self.assertEqual(result.input_bytes, 4)
        self.assertEqual(len(result.input_sha256), 64)
        self.assertEqual(len(result.output_sha256), 64)

    def test_format_hint_is_forwarded_for_csv(self) -> None:
        calls: list[str | None] = []
        fake = types.SimpleNamespace(
            format_from_bytes=lambda body: None,
            to_markdown_bytes=lambda body, hint=None: calls.append(hint)
            or "| valor |\n| --- |\n| 1 |",
        )
        with patch.dict(sys.modules, {"anydoc": fake}):
            convert_to_markdown(b"valor\n1\n", format_hint="csv")

        self.assertEqual(calls, ["csv"])

    def test_missing_optional_dependency_is_explicit(self) -> None:
        with patch.dict(sys.modules, {"anydoc": None}):
            with self.assertRaises(AnyDocUnavailable):
                convert_to_markdown(b"document")

    def test_oversized_document_is_rejected_before_import(self) -> None:
        with self.assertRaises(AnyDocConversionError):
            convert_to_markdown(b"x" * (MAX_INPUT_BYTES + 1))
