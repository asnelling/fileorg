from __future__ import annotations

from pathlib import Path
from typing import Sequence

from fileorg.plugins.base import Clue, CluePlugin


class OcrPlugin(CluePlugin):
    name = "ocr"

    def accepts(self, path: Path, mime_type: str | None) -> bool:
        if mime_type and mime_type.startswith("image/"):
            return True
        return path.suffix.lower() in {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}

    def extract(self, path: Path) -> Sequence[Clue]:
        try:
            import pytesseract
            from PIL import Image
            from pytesseract import Output

            img = Image.open(path)

            data = pytesseract.image_to_data(img, output_type=Output.DICT)
            words = []
            confidences = []
            for word, conf in zip(data["text"], data["conf"]):
                try:
                    conf_float = float(conf)
                except (ValueError, TypeError):
                    continue
                if conf_float >= 60 and len(word.strip()) >= 3:
                    words.append(word.strip())
                    confidences.append(conf_float)

            if len(words) < 3:
                return []

            detected_text = " ".join(words)
            if len(detected_text) > 500:
                detected_text = detected_text[:497] + "..."
            avg_conf = sum(confidences) / len(confidences) / 100

            clues: list[Clue] = [
                Clue(key="detected_text", value=detected_text, confidence=avg_conf),
                Clue(key="word_count", value=str(len(words)), confidence=1.0),
            ]

            try:
                osd = pytesseract.image_to_osd(img, output_type=Output.DICT)
                if lang := osd.get("script"):
                    clues.append(Clue(key="language", value=lang, confidence=0.7))
            except Exception:
                pass

            return clues

        except pytesseract.TesseractNotFoundError:
            return [Clue(key="plugin_error", value="tesseract not installed", confidence=0.0)]
        except Exception as e:
            return [Clue(key="plugin_error", value=str(e)[:200], confidence=0.0)]
