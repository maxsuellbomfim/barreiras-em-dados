import os
import tempfile
import unittest
from pathlib import Path

from barreiras_collectors.commands.collect_fns_other_payments_local import PrivateStore


@unittest.skipUnless(os.name == "nt", "Windows DPAPI required")
class PrivateStoreTests(unittest.TestCase):
    def test_encrypted_roundtrip_lock_and_immutable_capture(self):
        with tempfile.TemporaryDirectory() as root:
            with PrivateStore(Path(root)) as store:
                value = dict(body=b"PRIVATE ORIGINAL", sha256="test")
                store.save("a" * 64, value)
                self.assertEqual(store.load("a" * 64), value)
                self.assertNotIn(
                    b"PRIVATE ORIGINAL",
                    (Path(root) / ("a" * 64 + ".dpapi")).read_bytes(),
                )
                with self.assertRaises(ValueError):
                    store.save("a" * 64, dict(body=b"changed"))
                with self.assertRaises(OSError):
                    with PrivateStore(Path(root)):
                        pass
                with self.assertRaises(ValueError):
                    store.load("../escape")
            with PrivateStore(Path(root)) as reopened:
                self.assertEqual(reopened.load("a" * 64), value)
