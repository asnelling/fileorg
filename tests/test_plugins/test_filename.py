from __future__ import annotations

from pathlib import Path

from fileorg.plugins.filename import FilenamePlugin


def test_accepts_all() -> None:
    p = FilenamePlugin()
    assert p.accepts(Path("/any/file.xyz"), None)
    assert p.accepts(Path("/file"), "text/plain")


def test_extension_and_stem() -> None:
    p = FilenamePlugin()
    clues = {c.key: c for c in p.extract(Path("/home/user/report_q3_2023.pdf"))}
    assert clues["extension"].value == "pdf"
    assert clues["stem"].value == "report_q3_2023"
    assert "report" in clues["name_tokens"].value
    assert "2023" in clues["name_tokens"].value


def test_no_extension() -> None:
    p = FilenamePlugin()
    clues = {c.key: c for c in p.extract(Path("/bin/bash"))}
    assert clues["extension"].value == ""


def test_parent_dirs() -> None:
    p = FilenamePlugin()
    clues = {c.key: c for c in p.extract(Path("/home/alice/photos/vacation.jpg"))}
    assert "parent_dirs" in clues
    assert "photos" in clues["parent_dirs"].value


def test_camel_case_split() -> None:
    p = FilenamePlugin()
    clues = {c.key: c for c in p.extract(Path("/tmp/myProjectFile.ts"))}
    tokens = clues["name_tokens"].value
    assert "my" in tokens or "project" in tokens
