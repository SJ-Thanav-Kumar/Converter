#remembered user settings (output folder, JPEG quality, video codec)
from __future__ import annotations
from pathlib import Path
from typing import Optional
from PySide6.QtCore import QSettings
from core.conversion.manager import DEFAULT_OUTPUT_DIR


class AppSettings:
    #typed wrapper over qsettings so the rest of the app never sees string keys

    def __init__(self, backend: Optional[QSettings] = None) -> None:
        #QSettings("org", "app") stores to a per-user location chosen by the OS
        #(macOS: ~/Library/Preferences/com.converter.Converter.plist).
        self._store = backend or QSettings("converter", "Converter")

    @property
    def output_dir(self) -> Path:
        return Path(str(self._store.value("output_dir", str(DEFAULT_OUTPUT_DIR))))

    @output_dir.setter
    def output_dir(self, value: Path) -> None:
        self._store.setValue("output_dir", str(value))

    @property
    def jpeg_quality(self) -> int:
        return int(self._store.value("jpeg_quality", 90))

    @jpeg_quality.setter
    def jpeg_quality(self, value: int) -> None:
        self._store.setValue("jpeg_quality", int(value))

    @property
    def video_codec(self) -> str:
        """"keep", "h264" or "h265"."""
        return str(self._store.value("video_codec", "keep"))

    @video_codec.setter
    def video_codec(self, value: str) -> None:
        self._store.setValue("video_codec", value)