from __future__ import annotations

import hashlib
import unittest

from barreiras_docproc.canonical import (
    CanonicalTextError,
    derive_canonical_text,
)


class CanonicalTextTests(unittest.TestCase):
    def test_normalizes_line_endings_and_hashes_normalized_text(self) -> None:
        raw = "PORTARIA N° 1\r\nRESOLVE:\rArt. 1°\n".encode()

        canonical = derive_canonical_text(raw)

        self.assertEqual(canonical.text, "PORTARIA N° 1\nRESOLVE:\nArt. 1°\n")
        self.assertEqual(
            canonical.sha256,
            hashlib.sha256(canonical.text.encode("utf-8")).hexdigest(),
        )

    def test_is_deterministic_for_same_bytes(self) -> None:
        raw = "NOMEAR ALGUÉM\n".encode()

        self.assertEqual(
            derive_canonical_text(raw),
            derive_canonical_text(raw),
        )

    def test_rejects_empty_and_invalid_utf8(self) -> None:
        with self.assertRaises(CanonicalTextError):
            derive_canonical_text(b"")
        with self.assertRaises(CanonicalTextError):
            derive_canonical_text(b"\xff\xfe invalido")


if __name__ == "__main__":
    unittest.main()
