"""keyring backend for Windows: secrets encrypted with DPAPI and stored as files.

Windows Credential Manager caps a secret at 2,560 bytes. Snowflake OAuth access tokens are
larger, so the default backend fails with "CredWrite: The stub received bad data" (WinError 1783)
and the connector can't cache the login. DPAPI ties the ciphertext to the current Windows user.

Enabled for the exploration venv only, via .venv/Lib/site-packages/exploration-keyring.pth
(see README.md). Files live in %LOCALAPPDATA%/exploration-keyring/.
"""
import ctypes
import ctypes.wintypes as wt
import hashlib
import os
from pathlib import Path

from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

STORE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "exploration-keyring"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(fn, data: bytes) -> bytes:
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    if not fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _path(service: str, username: str) -> Path:
    return STORE / (hashlib.sha256(f"{service}\0{username}".encode()).hexdigest() + ".bin")


class DpapiKeyring(KeyringBackend):
    priority = 10

    def set_password(self, service, username, password):
        STORE.mkdir(parents=True, exist_ok=True)
        _path(service, username).write_bytes(_dpapi(ctypes.windll.crypt32.CryptProtectData, password.encode()))

    def get_password(self, service, username):
        p = _path(service, username)
        if not p.exists():
            return None
        return _dpapi(ctypes.windll.crypt32.CryptUnprotectData, p.read_bytes()).decode()

    def delete_password(self, service, username):
        p = _path(service, username)
        if not p.exists():
            raise PasswordDeleteError("No such password")
        p.unlink()
