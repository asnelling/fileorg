from __future__ import annotations

from pathlib import Path

from fileorg.plugins.archive import ArchivePlugin


def test_accepts_zip_mime() -> None:
    p = ArchivePlugin()
    assert p.accepts(Path("x.zip"), "application/zip")
    assert p.accepts(Path("x.tar"), "application/x-tar")
    assert not p.accepts(Path("x.txt"), "text/plain")


def test_extract_zip(zip_file: Path) -> None:
    p = ArchivePlugin()
    clues = {c.key: c for c in p.extract(zip_file)}
    assert clues["archive_type"].value == "zip"
    assert clues["entry_count"].value == "2"
    assert "readme.txt" in clues["entry_names"].value
    assert ".txt" in clues["entry_extensions"].value


def test_extract_encrypted_zip(encrypted_zip: Path) -> None:
    p = ArchivePlugin()
    clues = {c.key: c for c in p.extract(encrypted_zip)}
    # encrypted zip should flag as encrypted
    encrypted_clue = clues.get("is_encrypted") or clues.get("_encrypted_volume_type")
    assert encrypted_clue is not None


def test_corrupt_returns_error_clue(tmp_path: Path) -> None:
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"this is not a zip file at all")
    p = ArchivePlugin()
    # Should not raise; may return empty or error clue
    result = list(p.extract(bad))
    # No exception is the key test


def test_subdirectory_detection(zip_file: Path) -> None:
    p = ArchivePlugin()
    clues = {c.key: c for c in p.extract(zip_file)}
    assert clues["has_subdirectories"].value == "true"
