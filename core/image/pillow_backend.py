from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError, features

from core.conversion.errors import ConversionFailedError
from core.conversion.models import CancellationToken, ConversionBackend, ProgressCallback

#pillow-heif is a plugin: once registered, Image.open() reads HEIC and img.save(format="HEIF") writes it
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_READY = True
except ImportError:
    HEIF_READY = False

PILLOW_NAMES = {
    "png": "PNG", "jpeg": "JPEG", "bmp": "BMP",
    "gif": "GIF", "webp": "WEBP", "avif": "AVIF", "tiff": "TIFF", "heic": "HEIF",
}

#formats that need an optional piece. {format id: function that says if it is there}
#if the piece is missing the format simply doesnt show up, same idea as FFmpeg missing
NEEDS_FEATURE = {
    "webp": lambda: features.check("webp"),
    "avif": lambda: features.check("avif"),
    "heic": lambda: HEIF_READY,
}

#formats that can hold many frames (an animation). Only these keep their motion
ANIMATED = {"gif", "webp", "avif"}

#formats with a quality setting (lossy). the same slider drives all of them
LOSSY = {"jpeg", "webp", "avif", "heic"}

JPEG_QUALITY = 90      #default quality for every lossy format, not only JPEG

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


def _save_args(target_format: str, options: Dict[str, Any]) -> Dict[str, Any]:
    #the extra keyword arguments each format wants in img.save()
    args: Dict[str, Any] = {}
    if target_format in LOSSY:
        args["quality"] = options.get("quality", JPEG_QUALITY)
    if target_format == "tiff" and features.check("libtiff"):
        args["compression"] = "tiff_lzw"       #lossless and every viewer opens it. Default is no compression at all
    return args


def _read_frames(img: Image.Image, cancel: CancellationToken) -> Tuple[List[Image.Image], List[int]]:
    #pull every frame (as full RGBA pictures) and how long each one stays on screen, in ms
    frames, durations = [], []
    for frame in ImageSequence.Iterator(img):
        cancel.raise_if_cancelled()
        frames.append(frame.convert("RGBA"))
        durations.append(frame.info.get("duration", 100))
    return frames, durations


class PillowBackend(ConversionBackend):
    name = "Pillow"

    #formats this machine's Pillow can really write
    @staticmethod
    def _available() -> Dict[str, str]:
        return {fid: name for fid, name in PILLOW_NAMES.items()
                if fid not in NEEDS_FEATURE or NEEDS_FEATURE[fid]()}

    def supported_conversions(self) ->Set[Tuple[str, str]]:
        names = self._available()
        pairs = {(a,b) for a in names for b in names if a!=b}
        #same format in, same format out: the COMPRESS tab (lossy formats only, quality slider)
        return pairs | {(f, f) for f in LOSSY if f in names}

    def convert(
        self,
        source: Path,
        destination: Path,
        source_format: str,
        target_format: str,
        progress: ProgressCallback,
        cancel: CancellationToken,
        options: Dict[str, Any],
    ) -> None:
        try:
            with Image.open(source) as img:
                #an animation going to a format that can hold one keeps its motion
                if source_format in ANIMATED and target_format in ANIMATED and getattr(img, "is_animated", False):
                    self._convert_animation(img, destination, target_format, progress, cancel, options)
                    return

                img.load()
                progress(0.5, "Decoded")
                img = ImageOps.exif_transpose(img) #bake in cam rotation
                img = _make_saveable(img)

                save_args = _save_args(target_format, options)
                if target_format == "jpeg":
                    img = _flatten_for_jpeg(img)

                cancel.raise_if_cancelled()
                img.save(destination, format=PILLOW_NAMES[target_format], **save_args)
                
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ConversionFailedError(f"Could not convert {source.name}: {exc}") from exc

    @staticmethod
    def _convert_animation(img: Image.Image, destination: Path, target_format: str,
                           progress: ProgressCallback, cancel: CancellationToken,
                           options: Dict[str, Any]) -> None:
        frames, durations = _read_frames(img, cancel)
        progress(0.5, f"Decoded {len(frames)} frames")

        cancel.raise_if_cancelled()
        frames[0].save(
            destination, format=PILLOW_NAMES[target_format],
            save_all=True, append_images=frames[1:],
            duration=durations, loop=img.info.get("loop", 0),   #loop 0 = forever
            **_save_args(target_format, options),
        )
