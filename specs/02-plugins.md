# Spec: Plugin System

## Purpose

Plugins produce "clues" about files — atomic facts that inform the AI categorizer. Each plugin is responsible for one domain of knowledge (filename structure, image metadata, text content, etc.). The plugin system is designed for extensibility: adding a new plugin requires only implementing the base class and registering it.

## Files

### `src/fileorg/plugins/base.py`

Defines the `Clue` dataclass and `CluePlugin` abstract base class that all plugins must implement.

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


@dataclass
class Clue:
    key: str          # snake_case fact name, e.g. 'extension', 'camera_make'
    value: str        # always a string; callers stringify other types
    confidence: float = 1.0   # 0.0–1.0; how reliable this clue is
    raw: dict = field(default_factory=dict)  # optional structured payload; not stored in DB


class CluePlugin(ABC):
    name: str  # class-level; stored as plugin_name in DB

    @abstractmethod
    def accepts(self, path: Path, mime_type: str | None) -> bool:
        """Return True if this plugin can process this file type."""
        ...

    @abstractmethod
    def extract(self, path: Path) -> Sequence[Clue]:
        """
        Extract clues. Must never raise — catch all exceptions internally.
        On error, return [Clue(key='plugin_error', value=str(e), confidence=0.0)].
        """
        ...
```

### `src/fileorg/plugins/registry.py`

Central registry that holds all active plugin instances.

```python
class PluginRegistry:
    def __init__(self) -> None: ...
    def register(self, plugin: CluePlugin) -> None: ...
    def all(self) -> list[CluePlugin]: ...
    def enabled(self, names: list[str] | None = None) -> list[CluePlugin]:
        # If names is None, return all. Otherwise filter to named plugins.
        ...

def build_default_registry() -> PluginRegistry:
    # Instantiates and registers all built-in plugins in priority order:
    # FilenamePlugin, ExifPlugin, ArchivePlugin, OcrPlugin, EncryptionPlugin
    # (CluelessPlugin is NOT in this registry — it runs separately as Stage 4.5)
    ...
```

### `src/fileorg/plugins/filename.py`

**Plugin name:** `filename`

**`accepts()`:** Always returns `True` — every file has a name.

**`extract()`** produces clues:
- `extension`: lowercased file extension without dot (e.g. `pdf`); confidence 1.0. Empty string if no extension.
- `stem`: filename without extension (e.g. `report_q3_2023`); confidence 1.0
- `name_tokens`: space-joined list of words parsed from the stem by splitting on `_`, `-`, `.`, spaces, and camelCase boundaries (e.g. `report q3 2023`); confidence 0.9
- `parent_dirs`: space-joined last 3 path components excluding filename (e.g. `archive 2023 photos`); confidence 0.8
- `depth`: integer depth of path from scan root, stringified; confidence 1.0

Token splitting rules:
- Split on `_`, `-`, `.`, ` `
- Also split on camelCase boundaries (insert space before uppercase letter preceded by lowercase)
- Lowercase all tokens
- Filter out tokens shorter than 2 characters
- Filter out pure numeric tokens that are not year-like (4-digit 1900–2099)

### `src/fileorg/plugins/exif.py`

**Plugin name:** `exif`

**`accepts()`:** Returns `True` for MIME types: `image/jpeg`, `image/tiff`, `image/png`, `image/webp`, `image/heic`, `image/heif`.

**`extract()`** uses `PIL.Image.open()` and `piexif.load()` to read EXIF data. Produces clues for any present EXIF tags:

| EXIF field | Clue key | Confidence |
|------------|----------|------------|
| Make | `camera_make` | 1.0 |
| Model | `camera_model` | 1.0 |
| DateTimeOriginal | `date_taken` | 1.0 |
| GPSLatitude + GPSLongitude | `gps_coordinates` | 1.0 (formatted as `"lat,lon"`) |
| ImageWidth + ImageLength | `image_dimensions` | 1.0 (formatted as `"WxH"`) |
| Software | `software` | 0.9 |
| Artist | `artist` | 0.9 |
| Copyright | `copyright` | 0.9 |
| Description / ImageDescription | `description` | 0.8 |

On `piexif.InvalidImageDataError` or any PIL error: return error clue. On missing EXIF altogether: return empty list (not an error).

### `src/fileorg/plugins/archive.py`

**Plugin name:** `archive`

**`accepts()`:** Returns `True` for MIME types: `application/zip`, `application/x-tar`, `application/gzip`, `application/x-bzip2`, `application/x-7z-compressed`, `application/x-rar`, and any path with extensions `.zip`, `.tar`, `.gz`, `.bz2`, `.7z`, `.rar`, `.tgz`, `.tar.gz`, `.tar.bz2`.

**`extract()`** opens the archive and produces:
- `archive_type`: format string (`zip`, `tar`, `7z`); confidence 1.0
- `entry_count`: number of entries (stringified); confidence 1.0
- `entry_names`: space-joined list of up to 20 entry filenames (truncated with `...` if more); confidence 0.9
- `entry_extensions`: space-joined unique set of extensions found inside; confidence 0.9
- `total_uncompressed_bytes`: sum of uncompressed sizes (stringified); confidence 1.0
- `has_subdirectories`: `"true"` or `"false"`; confidence 1.0

For zip archives: use `zipfile.ZipFile`. Detect password-protection by catching `zipfile.BadZipFile` or checking `entry.flag_bits & 0x1` — if encrypted, also emit `is_encrypted: "true"` with confidence 1.0 and return early (don't try to list contents).

For tar/gz/bz2: use `tarfile.open()`.
For 7z: use `py7zr.SevenZipFile`.

If the archive cannot be opened (corrupted, unsupported): return error clue.

### `src/fileorg/plugins/ocr.py`

**Plugin name:** `ocr`

**`accepts()`:** Returns `True` for MIME types starting with `image/`.

**`extract()`:**
1. Open image with `PIL.Image.open()`
2. Run `pytesseract.image_to_data(image, output_type=Output.DICT)` to get per-word confidence scores
3. Filter words with confidence >= 60 and length >= 3
4. Produce clues:
   - `detected_text`: space-joined filtered words (up to 500 chars, truncated); confidence = mean word confidence / 100
   - `language`: detected language from `pytesseract.image_to_osd()` if available; confidence 0.7
   - `word_count`: count of qualifying words (stringified); confidence 1.0

If `pytesseract.TesseractNotFoundError`: return `[Clue(key='plugin_error', value='tesseract not installed', confidence=0.0)]`.
If image has fewer than 3 qualifying words: return empty list (image is likely non-text).

### `src/fileorg/plugins/encryption.py`

**Plugin name:** `encryption`

**`accepts()`:** Returns `True` for all files — encryption detection is done on file headers.

**`extract()`** checks for known encrypted/protected formats:

| Detection method | `volume_type` value |
|-----------------|---------------------|
| ZIP with `flag_bits & 0x1` set on any entry | `zip_encrypted` |
| 7z with `py7zr` reporting password-protected | `7z_encrypted` |
| VeraCrypt magic bytes at offset 0 (`EB 52 90`) | `veracrypt` |
| PGP armor header (`-----BEGIN PGP`) | `pgp` |
| OpenSSL `Salted__` header | `openssl_salted` |
| Keepass file magic (`03 D9 A2 9A`) | `keepass` |

Produces clues if encryption detected:
- `is_encrypted`: `"true"`; confidence 1.0
- `encryption_type`: the `volume_type` string; confidence 1.0

Returns empty list if no encryption detected (not an error).

Also signals to the pipeline that this file should be recorded in `encrypted_volumes` table. Do this by including a special clue: `Clue(key='_encrypted_volume_type', value=volume_type, confidence=1.0)`. The pipeline checks for this special key and calls `queries.upsert_encrypted_volume()` accordingly. Strip this clue from the list before storing to DB.

### `src/fileorg/plugins/clueless.py`

**Plugin name:** `clueless`

This is a **post-processing plugin** — it does not read the file directly. It reads the accumulated clues from the DB for a file and computes a coverage score.

NOT registered in `PluginRegistry`. Called explicitly by the pipeline at Stage 4.5.

```python
class CluelessPlugin:
    THRESHOLD_PLUGINS = 3
    THRESHOLD_CLUES = 10
    FLAGGED_THRESHOLD = 0.35

    def compute(self, file_id: int, clues: list[sqlite3.Row], mime_type: str | None) -> tuple[float, bool, list[Clue]]:
        """
        Returns (coverage_score, flagged_clueless, extra_clues_to_store).
        extra_clues_to_store contains a 'coverage_score' clue for the AI.
        """
        plugin_count = len({row['plugin_name'] for row in clues})
        clue_count = len(clues)
        total_confidence = sum(row['confidence'] for row in clues)
        avg_confidence = total_confidence / clue_count if clue_count > 0 else 0.0

        score = min(1.0,
            0.5 * min(plugin_count / self.THRESHOLD_PLUGINS, 1.0) +
            0.3 * min(clue_count / self.THRESHOLD_CLUES, 1.0) +
            0.2 * avg_confidence
        )
        flagged = score < self.FLAGGED_THRESHOLD

        hint = self._suggest_plugin(mime_type, {row['plugin_name'] for row in clues})
        extra = [Clue(key='coverage_score', value=f'{score:.2f}', confidence=score)]
        if hint:
            extra.append(Clue(key='missing_plugin_hint', value=hint, confidence=0.5))

        return score, flagged, extra

    def _suggest_plugin(self, mime_type: str | None, active_plugins: set[str]) -> str | None:
        # e.g. image with no 'exif' plugin → suggest exif
        # e.g. image with no 'ocr' plugin → suggest ocr
        # Returns None if no suggestion
        ...
```

## Error Contract

All plugin `extract()` methods must:
1. Catch all exceptions with a broad `except Exception as e`
2. On error, return `[Clue(key='plugin_error', value=str(e)[:200], confidence=0.0)]`
3. Never propagate exceptions to the pipeline

## Testing

Each plugin has its own test file in `tests/test_plugins/`. Tests use real (small) fixture files:
- `tests/fixtures/sample.jpg` — JPEG with EXIF data
- `tests/fixtures/sample.zip` — zip with a few text files
- `tests/fixtures/sample_encrypted.zip` — password-protected zip
- `tests/fixtures/sample.png` — PNG with visible text for OCR
- `tests/fixtures/document.pdf` — PDF

Tests verify:
- `accepts()` returns correct True/False for various MIME types
- `extract()` returns expected clue keys and reasonable values
- `extract()` returns error clue (not raises) when given a corrupt/invalid file
