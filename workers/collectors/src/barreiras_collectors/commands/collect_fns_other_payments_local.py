"""Private Windows acquisition. No upload, normalization or public writes."""

import argparse
import base64
import ctypes
import json
import os
import re
from pathlib import Path
from uuid import uuid4

from barreiras_collectors.connectors.fns_collection_resume import collect_year
from barreiras_collectors.http import UrllibTransport


def _crypt(raw, *, decrypt=False):
    if os.name != "nt":
        raise OSError("Windows protection required")

    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.c_void_p)]

    buffer = ctypes.create_string_buffer(raw)
    incoming, outgoing = Blob(len(raw), ctypes.cast(buffer, ctypes.c_void_p)), Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    operation.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(Blob),
    ]
    operation.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    try:
        if not operation(
            ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)
        ):
            raise OSError("Local protection failed")
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        ctypes.memset(buffer, 0, len(raw))
        if outgoing.data:
            ctypes.memset(outgoing.data, 0, outgoing.size)
            kernel32.LocalFree(outgoing.data)


class PrivateStore:
    """DPAPI CurrentUser, exclusive process lock, atomic encrypted writes.

    Captures are immutable. Only the non-sensitive run checkpoint is replaced.
    The 128 MiB acquisition budget is deliberately independent of request count.
    """

    def __init__(self, directory):
        if os.name != "nt":
            raise OSError("Windows protection required")
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = None

    def __enter__(self):
        import msvcrt

        self.lock = (self.directory / "acquisition.lock").open("a+b")
        try:
            self.lock.seek(0)
            msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.lock.close()
            raise OSError("Acquisition already running") from None
        return self

    def __exit__(self, *_):
        self.lock.close()

    def _path(self, key):
        if key != "run" and not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("Invalid capture key")
        path = self.directory / (key + ".dpapi")
        if path.is_symlink():
            raise ValueError("Unexpected capture link")
        return path

    def load(self, key):
        path = self._path(key)
        if not path.exists():
            return None
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Capture size limit")
        value = json.loads(_crypt(path.read_bytes(), decrypt=True))
        if "body" in value:
            value["body"] = base64.b64decode(value["body"], validate=True)
        return value

    def save(self, key, value):
        path = self._path(key)
        if key != "run" and path.exists():
            if self.load(key) != value:
                raise ValueError("Immutable capture conflict")
            return
        payload = dict(value)
        if "body" in payload:
            payload["body"] = base64.b64encode(payload["body"]).decode("ascii")
        encrypted = _crypt(json.dumps(payload, separators=(",", ":")).encode())
        if (
            len(encrypted) > 2 * 1024 * 1024
            or sum(p.stat().st_size for p in self.directory.iterdir() if p.is_file())
            + len(encrypted)
            > 128 * 1024 * 1024
        ):
            raise ValueError("Private acquisition storage limit")
        temporary = self.directory / (uuid4().hex + ".tmp")
        with temporary.open("xb") as output:
            output.write(encrypted)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
        if self.load(key) != value:
            raise ValueError("Private read-back mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--max-requests", type=int, default=20)
    args = parser.parse_args()
    try:
        with PrivateStore(args.directory) as store:
            result = collect_year(
                args.year,
                store,
                UrllibTransport(frozenset({"consultafns.saude.gov.br"})),
                max_requests=args.max_requests,
            )
        print(json.dumps(result))
        return 0 if result["status"] in ("complete", "empty") else 2
    except Exception:
        print('{"status":"failed","publication_allowed":false}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
