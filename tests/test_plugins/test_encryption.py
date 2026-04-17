from __future__ import annotations

from pathlib import Path

from fileorg.plugins.encryption import EncryptionPlugin


def test_accepts_all() -> None:
    p = EncryptionPlugin()
    assert p.accepts(Path("any.bin"), None)


def test_non_encrypted_returns_empty(tmp_path: Path) -> None:
    f = tmp_path / "plain.txt"
    f.write_text("just a plain text file")
    p = EncryptionPlugin()
    clues = list(p.extract(f))
    assert all(c.key == "plugin_error" for c in clues) or clues == []


def test_pgp_detected(tmp_path: Path) -> None:
    f = tmp_path / "msg.asc"
    f.write_bytes(b"-----BEGIN PGP MESSAGE-----\nVersion: GnuPG\n")
    p = EncryptionPlugin()
    clues = {c.key: c for c in p.extract(f)}
    assert clues.get("is_encrypted") is not None
    assert clues["is_encrypted"].value == "true"


def test_openssl_detected(tmp_path: Path) -> None:
    f = tmp_path / "data.enc"
    f.write_bytes(b"Salted__" + b"\x00" * 8)
    p = EncryptionPlugin()
    clues = {c.key: c for c in p.extract(f)}
    assert clues.get("encryption_type") is not None
    assert clues["encryption_type"].value == "openssl_salted"


def test_encrypted_zip_detected(encrypted_zip: Path) -> None:
    p = EncryptionPlugin()
    clues = {c.key: c for c in p.extract(encrypted_zip)}
    assert "_encrypted_volume_type" in clues
    assert clues["_encrypted_volume_type"].value == "zip_encrypted"
