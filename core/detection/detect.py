"""Content-based format detection (the production version of learning/identify.py).

The file extension is never trusted: we read the leading bytes, as in Module 1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from .formats import FormatInfo, get_format

HEADER_SIZE = 32


def detect_bytes(header: bytes) -> Optional[FormatInfo]:
    """Identify a format from the first bytes of a file; None if unrecognised."""
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return get_format("png")
    if header.startswith(b"\xff\xd8\xff"):
        return get_format("jpeg")
    if header.startswith(b"BM"):
        return get_format("bmp")
    if header.startswith((b"GIF87a", b"GIF89a")):
        return get_format("gif")
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return get_format("tiff")
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return get_format("webp")
    if header[:4] == b"RIFF" and header[8:12] == b"AVI ":
        return get_format("avi")
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return get_format("mkv")
    # AVIF is also an ISO base media file, so its brand ('avif' still, 'avis' animated) is checked first.
    if header[4:8] == b"ftyp" and header[8:12] in (b"avif", b"avis"):
        return get_format("avif")
    # HEIC (iPhone photos) is the same box layout again. Its brands: heic/heix (still), heim/heis, mif1/msf1 (generic HEIF).
    if header[4:8] == b"ftyp" and header[8:12] in (b"heic", b"heix", b"heim", b"heis", b"mif1", b"msf1"):
        return get_format("heic")
    # ISO base media: [size:4]['ftyp'][major brand:4]; 'qt  ' means QuickTime.
    if header[4:8] == b"ftyp":
        return get_format("mov" if header[8:12] == b"qt  " else "mp4")
    return None


def detect_file(path: Union[str, Path]) -> Optional[FormatInfo]:
    """Read the header of `path` and identify it. Raises OSError if unreadable."""
    with open(path, "rb") as f:
        return detect_bytes(f.read(HEADER_SIZE))
