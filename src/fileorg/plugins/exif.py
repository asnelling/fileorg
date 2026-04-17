from __future__ import annotations

from pathlib import Path
from typing import Sequence

from fileorg.plugins.base import Clue, CluePlugin

_ACCEPTED_MIMES = {
    "image/jpeg", "image/tiff", "image/png",
    "image/webp", "image/heic", "image/heif",
}


class ExifPlugin(CluePlugin):
    name = "exif"

    def accepts(self, path: Path, mime_type: str | None) -> bool:
        if mime_type in _ACCEPTED_MIMES:
            return True
        return path.suffix.lower() in {".jpg", ".jpeg", ".tiff", ".tif", ".heic", ".heif"}

    def extract(self, path: Path) -> Sequence[Clue]:
        try:
            import piexif
            from PIL import Image

            img = Image.open(path)
            exif_bytes = img.info.get("exif")
            if not exif_bytes:
                return []

            data = piexif.load(exif_bytes)
            clues: list[Clue] = []

            def _str(val: bytes | str | None) -> str | None:
                if val is None:
                    return None
                if isinstance(val, bytes):
                    try:
                        return val.decode("utf-8").strip("\x00").strip()
                    except UnicodeDecodeError:
                        return None
                return str(val).strip()

            ifd0 = data.get("0th", {})
            exif = data.get("Exif", {})
            gps = data.get("GPS", {})

            if make := _str(ifd0.get(piexif.ImageIFD.Make)):
                clues.append(Clue(key="camera_make", value=make, confidence=1.0))
            if model := _str(ifd0.get(piexif.ImageIFD.Model)):
                clues.append(Clue(key="camera_model", value=model, confidence=1.0))
            if dt := _str(exif.get(piexif.ExifIFD.DateTimeOriginal)):
                clues.append(Clue(key="date_taken", value=dt, confidence=1.0))
            if software := _str(ifd0.get(piexif.ImageIFD.Software)):
                clues.append(Clue(key="software", value=software, confidence=0.9))
            if artist := _str(ifd0.get(piexif.ImageIFD.Artist)):
                clues.append(Clue(key="artist", value=artist, confidence=0.9))
            if copy := _str(ifd0.get(piexif.ImageIFD.Copyright)):
                clues.append(Clue(key="copyright", value=copy, confidence=0.9))
            if desc := _str(ifd0.get(piexif.ImageIFD.ImageDescription)):
                clues.append(Clue(key="description", value=desc, confidence=0.8))

            width = ifd0.get(piexif.ImageIFD.ImageWidth) or exif.get(piexif.ExifIFD.PixelXDimension)
            height = ifd0.get(piexif.ImageIFD.ImageLength) or exif.get(piexif.ExifIFD.PixelYDimension)
            if width and height:
                clues.append(Clue(key="image_dimensions", value=f"{width}x{height}", confidence=1.0))

            if gps:
                try:
                    lat_ref = _str(gps.get(piexif.GPSIFD.GPSLatitudeRef)) or "N"
                    lon_ref = _str(gps.get(piexif.GPSIFD.GPSLongitudeRef)) or "E"
                    lat_raw = gps.get(piexif.GPSIFD.GPSLatitude)
                    lon_raw = gps.get(piexif.GPSIFD.GPSLongitude)
                    if lat_raw and lon_raw:
                        def _dms(dms: tuple) -> float:
                            d, m, s = dms
                            return d[0]/d[1] + m[0]/m[1]/60 + s[0]/s[1]/3600
                        lat = _dms(lat_raw) * (-1 if lat_ref == "S" else 1)
                        lon = _dms(lon_raw) * (-1 if lon_ref == "W" else 1)
                        clues.append(Clue(key="gps_coordinates", value=f"{lat:.6f},{lon:.6f}", confidence=1.0))
                except Exception:
                    pass

            return clues
        except Exception as e:
            return [Clue(key="plugin_error", value=str(e)[:200], confidence=0.0)]
