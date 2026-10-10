"""Canonical format ids, their file extensions, and kind (image/video)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FormatInfo:
    id: str            # canonical id, e.g. "jpeg"
    kind: str          # "image" or "video"
    extension: str     # canonical output extension including the dot
    description: str


_FORMATS = {
    f.id: f
    for f in [
        FormatInfo("png", "image", ".png", "PNG image"),
        FormatInfo("jpeg", "image", ".jpg", "JPEG image"),
        FormatInfo("bmp", "image", ".bmp", "BMP image"),
        FormatInfo("gif", "image", ".gif", "GIF image"),
        FormatInfo("webp", "image", ".webp", "WebP image"),
        FormatInfo("tiff", "image", ".tiff", "TIFF image"),
        FormatInfo("mp4", "video", ".mp4", "MP4 container"),
        FormatInfo("mov", "video", ".mov", "QuickTime MOV container"),
        FormatInfo("mkv", "video", ".mkv", "Matroska/WebM container"),
        FormatInfo("avi", "video", ".avi", "AVI container"),
    ]
}

_ALIASES = {"jpg": "jpeg", "jpe": "jpeg", "jfif": "jpeg", "tif": "tiff", "m4v": "mp4", "webm": "mkv"}


def normalize_format(name: str) -> str:
    """'.JPG' / 'jpg' / 'JPEG' -> 'jpeg'. Unknown names come back cleaned, not rejected."""
    cleaned = name.strip().lower().lstrip(".")
    return _ALIASES.get(cleaned, cleaned)


def get_format(format_id: str) -> Optional[FormatInfo]:
    return _FORMATS.get(normalize_format(format_id))
