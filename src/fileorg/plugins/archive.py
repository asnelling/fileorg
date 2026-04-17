from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path
from typing import Sequence

from fileorg.plugins.base import Clue, CluePlugin

_ACCEPTED_MIMES = {
    "application/zip", "application/x-tar", "application/gzip",
    "application/x-bzip2", "application/x-7z-compressed",
    "application/x-rar", "application/x-rar-compressed",
}
_ACCEPTED_EXTS = {
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".tgz", ".tbz2", ".tar.gz", ".tar.bz2",
}


class ArchivePlugin(CluePlugin):
    name = "archive"

    def accepts(self, path: Path, mime_type: str | None) -> bool:
        if mime_type in _ACCEPTED_MIMES:
            return True
        return path.suffix.lower() in _ACCEPTED_EXTS or "".join(path.suffixes[-2:]).lower() in _ACCEPTED_EXTS

    def extract(self, path: Path) -> Sequence[Clue]:
        try:
            if zipfile.is_zipfile(path):
                return self._extract_zip(path)
            if tarfile.is_tarfile(path):
                return self._extract_tar(path)
            try:
                import py7zr
                with py7zr.SevenZipFile(path, "r") as z:
                    return self._extract_7z(z)
            except Exception:
                pass
            return []
        except Exception as e:
            return [Clue(key="plugin_error", value=str(e)[:200], confidence=0.0)]

    def _extract_zip(self, path: Path) -> list[Clue]:
        try:
            with zipfile.ZipFile(path) as zf:
                infos = zf.infolist()
                encrypted = any(info.flag_bits & 0x1 for info in infos)
                if encrypted:
                    return [
                        Clue(key="archive_type", value="zip", confidence=1.0),
                        Clue(key="is_encrypted", value="true", confidence=1.0),
                        Clue(key="_encrypted_volume_type", value="zip_encrypted", confidence=1.0),
                    ]
                names = [i.filename for i in infos]
                exts = {Path(n).suffix.lower() for n in names if Path(n).suffix}
                has_dirs = any(n.endswith("/") or "/" in n for n in names)
                total_uncompressed = sum(i.file_size for i in infos)
                return self._build_clues("zip", names, exts, has_dirs, total_uncompressed)
        except zipfile.BadZipFile as e:
            return [Clue(key="plugin_error", value=str(e)[:200], confidence=0.0)]

    def _extract_tar(self, path: Path) -> list[Clue]:
        with tarfile.open(path) as tf:
            members = tf.getmembers()
            names = [m.name for m in members]
            exts = {Path(n).suffix.lower() for n in names if Path(n).suffix}
            has_dirs = any(m.isdir() for m in members)
            total_uncompressed = sum(m.size for m in members if m.isfile())
            fmt = "tar.gz" if str(path).endswith((".gz", ".tgz")) else "tar"
            return self._build_clues(fmt, names, exts, has_dirs, total_uncompressed)

    def _extract_7z(self, z: object) -> list[Clue]:
        import py7zr
        assert isinstance(z, py7zr.SevenZipFile)
        files = z.list()
        names = [f.filename for f in files]
        exts = {Path(n).suffix.lower() for n in names if Path(n).suffix}
        has_dirs = any(f.is_directory for f in files)
        total_uncompressed = sum(f.uncompressed for f in files if not f.is_directory)
        return self._build_clues("7z", names, exts, has_dirs, total_uncompressed)

    def _build_clues(
        self,
        fmt: str,
        names: list[str],
        exts: set[str],
        has_dirs: bool,
        total_uncompressed: int,
    ) -> list[Clue]:
        sample = names[:20]
        suffix = "..." if len(names) > 20 else ""
        return [
            Clue(key="archive_type", value=fmt, confidence=1.0),
            Clue(key="entry_count", value=str(len(names)), confidence=1.0),
            Clue(key="entry_names", value=" ".join(sample) + suffix, confidence=0.9),
            Clue(key="entry_extensions", value=" ".join(sorted(exts)), confidence=0.9),
            Clue(key="total_uncompressed_bytes", value=str(total_uncompressed), confidence=1.0),
            Clue(key="has_subdirectories", value=str(has_dirs).lower(), confidence=1.0),
        ]
