"""ConversionManager: the single entry point for converting files.

    manager = ConversionManager([PillowBackend(), FFmpegBackend()])   # Modules 17-18
    result = manager.convert("photo.png", "jpeg")

The manager owns everything that is *not* codec work: input validation, format
detection, backend lookup, output naming, overwrite protection, temp-file-then-rename,
progress, cancellation and logging. Backends only convert bytes.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

from core.detection import detect_file, get_format, normalize_format

from .errors import (
    ConversionCancelledError,
    ConversionFailedError,
    ConverterError,
    InvalidInputError,
    OutputExistsError,
    UnsupportedFormatError,
)
from .models import (
    CancellationToken,
    ConversionBackend,
    ConversionResult,
    ProgressCallback,
    Status,
)

log = logging.getLogger("converter")

PathLike = Union[str, Path]


def _ignore_progress(fraction: Optional[float], message: str) -> None:
    pass


class ConversionManager:
    def __init__(self, backends: Iterable[ConversionBackend] = ()) -> None:
        self._routes: Dict[Tuple[str, str], ConversionBackend] = {}
        for backend in backends:
            self.register(backend)

    # ---- backend registry -------------------------------------------------

    def register(self, backend: ConversionBackend) -> None:
        """Add a backend. If two backends claim the same pair, the later one wins."""
        for source, target in backend.supported_conversions():
            self._routes[(normalize_format(source), normalize_format(target))] = backend

    def supported_targets(self, source_format: str) -> List[str]:
        """Formats `source_format` can be converted to (for a GUI's dropdown)."""
        source = normalize_format(source_format)
        return sorted(t for (s, t) in self._routes if s == source)

    # ---- conversion -------------------------------------------------------

    def convert(
        self,
        input_path: PathLike,
        output_format: str,
        *,
        output_dir: Optional[PathLike] = None,
        overwrite: bool = False,
        progress: Optional[ProgressCallback] = None,
        cancel: Optional[CancellationToken] = None,
    ) -> ConversionResult:
        """Convert one file. Raises a ConverterError subclass on any failure."""
        source = Path(input_path)
        progress = progress or _ignore_progress
        cancel = cancel or CancellationToken()

        self._validate_input(source)
        detected = detect_file(source)
        if detected is None:
            raise UnsupportedFormatError(f"Unrecognised file format: {source.name}")

        target = get_format(output_format)
        if target is None:
            raise UnsupportedFormatError(f"Unknown output format: {output_format!r}")

        backend = self._routes.get((detected.id, target.id))
        if backend is None:
            raise UnsupportedFormatError(
                f"No converter registered for {detected.id} -> {target.id}"
            )

        destination = self.plan_output_path(source, target.id, output_dir)
        if destination.resolve() == source.resolve():
            raise OutputExistsError(f"Output would overwrite the input file: {destination}")
        if destination.exists() and not overwrite:
            raise OutputExistsError(f"Output already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)

        # The backend writes to a temp file next to the destination (same extension,
        # so tools that infer format from the name still work). A failed or cancelled
        # run therefore never leaves a half-written output or clobbers an old one.
        temp = destination.with_name(f"{destination.stem}.partial-{os.getpid()}{destination.suffix}")

        log.info("Converting %s (%s -> %s) via %s", source, detected.id, target.id, backend.name)
        progress(0.0, f"Converting {source.name}")
        try:
            cancel.raise_if_cancelled()
            backend.convert(source, temp, detected.id, target.id, progress, cancel)
            cancel.raise_if_cancelled()
            if not temp.exists() or temp.stat().st_size == 0:
                raise ConversionFailedError(f"{backend.name} produced no output")
            os.replace(temp, destination)
        finally:
            if temp.exists():
                temp.unlink()
        progress(1.0, f"Finished {destination.name}")
        log.info("Wrote %s", destination)

        return ConversionResult(
            input_path=source,
            status=Status.OK,
            output_path=destination,
            input_format=detected.id,
            output_format=target.id,
        )

    def convert_batch(
        self,
        input_paths: Iterable[PathLike],
        output_format: str,
        *,
        output_dir: Optional[PathLike] = None,
        overwrite: bool = False,
        progress: Optional[ProgressCallback] = None,
        cancel: Optional[CancellationToken] = None,
    ) -> List[ConversionResult]:
        """Convert many files. One bad file does not stop the rest; each gets a result.
        Cancelling stops the batch (remaining files are reported as cancelled)."""
        cancel = cancel or CancellationToken()
        results: List[ConversionResult] = []
        for path in input_paths:
            try:
                results.append(
                    self.convert(
                        path, output_format,
                        output_dir=output_dir, overwrite=overwrite,
                        progress=progress, cancel=cancel,
                    )
                )
            except ConversionCancelledError as exc:
                results.append(ConversionResult(Path(path), Status.CANCELLED, error=str(exc)))
            except ConverterError as exc:
                log.warning("Failed to convert %s: %s", path, exc)
                results.append(ConversionResult(Path(path), Status.FAILED, error=str(exc)))
        return results

    # ---- helpers ----------------------------------------------------------

    @staticmethod
    def plan_output_path(source: Path, target_format: str, output_dir: Optional[PathLike]) -> Path:
        """Predictable naming: <output_dir or source dir>/<source stem><canonical ext>."""
        info = get_format(target_format)
        extension = info.extension if info else "." + normalize_format(target_format)
        directory = Path(output_dir) if output_dir is not None else source.parent
        return directory / (source.stem + extension)

    @staticmethod
    def _validate_input(source: Path) -> None:
        if not source.exists():
            raise InvalidInputError(f"File not found: {source}")
        if not source.is_file():
            raise InvalidInputError(f"Not a file: {source}")
        if source.stat().st_size == 0:
            raise InvalidInputError(f"File is empty: {source}")
        if not os.access(source, os.R_OK):
            raise InvalidInputError(f"File is not readable: {source}")
