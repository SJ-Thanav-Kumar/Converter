from __future__ import annotations

from pathlib import Path
from typing import Set, Tuple

from PIL import Image, ImageOps, UnidentifiedImageError

from core.conversion.errors import ConversionFailedError
from core.conversion.models import CancellationToken, ConversionBackend, ProgressCallback

PILLOW_NAMES = {"png": "PNG", "jpeg": "JPEG", "bmp": "BMP"}

JPEG_QUALITY = 90

def _make_saveable(img: Image.Image) -> Image.Image:
    """Turn uncommon pixel modes into one that every output format can write."""
    if img.mode in ("RGB", "RGBA", "L", "P", "1"):
        return img
    if img.mode.startswith("I"):  # 16-bit grayscale: scale 0-65535 down to 0-255 (convert() would clip)
        return img.point(lambda v: v * (1 / 256)).convert("L")
    if img.mode in ("LA", "PA"):  # grayscale/palette + alpha
        return img.convert("RGBA")
    return img.convert("RGB")     # CMYK, YCbCr, LAB, ...


def _flatten_for_jpeg(img: Image.Image) -> Image.Image:
    """JPEG has no transparency and only stores RGB/grayscale. Paste onto white."""
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    if has_alpha:
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    if img.mode in ("RGB", "L"):
        return img
    return img.convert("RGB")

class PillowBackend(ConversionBackend):
    name = "Pillow"

    def supported_conversions(self) ->Set[Tuple[str, str]]:
        return {(a,b) for a in PILLOW_NAMES for b in PILLOW_NAMES if a!=b}

    def convert(
        self,
        source: Path,
        destination: Path,
        source_format: str,
        target_format: str,
        progress: ProgressCallback,
        cancel: CancellationToken,
    ) -> None:
        try:
            with Image.open(source) as img:
                img.load()
                progress(0.5, "Decoded")
                img = ImageOps.exif_transpose(img) #bake in cam rotation
                img = _make_saveable(img)

                options = {}
                if target_format == "jpeg":
                    img = _flatten_for_jpeg(img)
                    options["quality"] = JPEG_QUALITY

                cancel.raise_if_cancelled()
                img.save(destination, format=PILLOW_NAMES[target_format], **options)
                
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ConversionFailedError(f"Could not convert {source.name}: {exc}") from exc