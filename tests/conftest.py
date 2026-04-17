from __future__ import annotations

import struct
import zipfile
import zlib
from pathlib import Path

import pytest

from fileorg.db.connection import get_connection


def _make_encrypted_zip_bytes() -> bytes:
    """Build a minimal ZIP file with the encryption flag set (0x0001) on the entry."""
    fname = b"secret.txt"
    data = b"secret content"
    crc = zlib.crc32(data) & 0xFFFFFFFF

    lfh = struct.pack(
        "<4sHHHHHIIIHH",
        b"PK\x03\x04", 20, 0x0001, 0, 0, 0,
        crc, len(data), len(data), len(fname), 0,
    ) + fname + data

    cdfh = struct.pack(
        "<4sHHHHHHIIIHHHHHII",
        b"PK\x01\x02", 20, 20, 0x0001, 0, 0, 0,
        crc, len(data), len(data), len(fname), 0, 0, 0, 0, 0, 0,
    ) + fname

    eocd = struct.pack(
        "<4sHHHHIIH",
        b"PK\x05\x06", 0, 0, 1, 1, len(cdfh), len(lfh), 0,
    )
    return lfh + cdfh + eocd


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture()
def conn(db_path: Path):
    c = get_connection(db_path)
    yield c
    c.close()


@pytest.fixture()
def source_dir(tmp_path: Path) -> Path:
    d = tmp_path / "source"
    d.mkdir()
    (d / "report_q3_2023.txt").write_text("Quarterly financial report EBITDA revenue")
    (d / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # minimal JPEG header
    sub = d / "docs"
    sub.mkdir()
    (sub / "contract_draft.pdf").write_bytes(b"%PDF-1.4 dummy content here")
    return d


@pytest.fixture()
def zip_file(tmp_path: Path) -> Path:
    p = tmp_path / "sample.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("readme.txt", "hello world")
        zf.writestr("data/records.csv", "name,age\nAlice,30")
    return p


@pytest.fixture()
def encrypted_zip(tmp_path: Path) -> Path:
    p = tmp_path / "secret.zip"
    p.write_bytes(_make_encrypted_zip_bytes())
    return p
