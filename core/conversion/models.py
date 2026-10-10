"""Data types shared by the manager, the backends, and any front end."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Set, Tuple

from .errors import ConversionCancelledError

# progress(fraction 0.0-1.0 or None if unknown, human-readable message)
ProgressCallback = Callable[[Optional[float], str], None]


class Status(Enum):
    OK = "ok"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CancellationToken:
    """Thread-safe flag. The GUI calls cancel(); backends poll raise_if_cancelled()."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise ConversionCancelledError("Conversion cancelled")


@dataclass(frozen=True)
class ConversionResult:
    input_path: Path
    status: Status
    output_path: Optional[Path] = None
    input_format: Optional[str] = None
    output_format: Optional[str] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status is Status.OK


class ConversionBackend(ABC):
    """One production tool (Pillow, FFmpeg, ...) behind a stable interface.

    The manager has already validated the input, detected its format, and chosen a
    safe temporary `destination`; the backend only does the conversion.
    It must raise ConversionFailedError on failure and call
    cancel.raise_if_cancelled() at sensible points during long work.
    """

    name: str = "backend"

    @abstractmethod
    def supported_conversions(self) -> Set[Tuple[str, str]]:
        """Set of (source_format, target_format) pairs, using canonical format ids."""

    @abstractmethod
    def convert(
        self,
        source: Path,
        destination: Path,
        source_format: str,
        target_format: str,
        progress: ProgressCallback,
        cancel: CancellationToken,
    ) -> None:
        """Read `source`, write the converted file to `destination`."""
