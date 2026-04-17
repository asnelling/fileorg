from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Sequence

from fileorg.plugins.base import Clue, CluePlugin

_MAGIC_SIGNATURES: list[tuple[int, bytes, str]] = [
    (0, b"\x03\xd9\xa2\x9a", "keepass"),
]

_PGP_HEADER = b"-----BEGIN PGP"
_OPENSSL_HEADER = b"Salted__"


class EncryptionPlugin(CluePlugin):
    name = "encryption"

    def accepts(self, path: Path, mime_type: str | None) -> bool:
        return True

    def extract(self, path: Path) -> Sequence[Clue]:
        try:
            return self._detect(path)
        except Exception as e:
            return [Clue(key="plugin_error", value=str(e)[:200], confidence=0.0)]

    def _detect(self, path: Path) -> list[Clue]:
        if zipfile.is_zipfile(path):
            try:
                with zipfile.ZipFile(path) as zf:
                    if any(info.flag_bits & 0x1 for info in zf.infolist()):
                        return self._encrypted_clues("zip_encrypted")
            except zipfile.BadZipFile:
                pass

        try:
            import py7zr
            with py7zr.SevenZipFile(path, "r") as z:
                if z.needs_password():
                    return self._encrypted_clues("7z_encrypted")
        except Exception:
            pass

        try:
            with open(path, "rb") as f:
                header = f.read(16)
        except OSError:
            return []

        if header[:8] == _OPENSSL_HEADER:
            return self._encrypted_clues("openssl_salted")
        if _PGP_HEADER in header:
            return self._encrypted_clues("pgp")
        for offset, sig, vol_type in _MAGIC_SIGNATURES:
            if header[offset:offset + len(sig)] == sig:
                return self._encrypted_clues(vol_type)

        # VeraCrypt: check for known bootstrap magic
        if len(header) >= 3 and header[:3] == b"\xeb\x52\x90":
            return self._encrypted_clues("veracrypt")

        return []

    def _encrypted_clues(self, volume_type: str) -> list[Clue]:
        return [
            Clue(key="is_encrypted", value="true", confidence=1.0),
            Clue(key="encryption_type", value=volume_type, confidence=1.0),
            Clue(key="_encrypted_volume_type", value=volume_type, confidence=1.0),
        ]
