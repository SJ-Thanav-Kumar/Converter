#runs a batch of conversions on a background thread so the window never freezes, pretty neat huh
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any, Dict, List
from PySide6.QtCore import QThread, Signal
from core.conversion import CancellationToken, ConversionManager, ConversionResult, Status

log = logging.getLogger("converter")


class ConversionWorker(QThread):
    #signals are how the worker talks to the window. They are the ONLY safe way
    #bcause widgets must be touched from the GUI thread, never from here
    file_started = Signal(int)            #position of the file in this batch
    file_progress = Signal(int, float)    #osition, fraction 0-1 (-1.0 = unknown)
    file_done = Signal(int, object)       #osition, ConversionResult

    def __init__(self, manager: ConversionManager, paths: List[str], output_format: str, output_dir: Path, options: Dict[str, Any], cancel: CancellationToken,) -> None:
        super().__init__()
        self._manager = manager
        self._paths = paths
        self._output_format = output_format
        self._output_dir = output_dir
        self._options = options
        self._cancel = cancel

    def run(self) -> None:
        #lled by Qt on the new thread after start()
        #when it returns the thread ends
        for position, path in enumerate(self._paths):
            self.file_started.emit(position)

            def report(fraction, message, position=position):
                self.file_progress.emit(position, -1.0 if fraction is None else float(fraction))

            try:
                #convert_batch with one path gives us the managers error -> result mapping
                result = self._manager.convert_batch(
                    [path], self._output_format,
                    output_dir=self._output_dir, options=self._options,
                    progress=report, cancel=self._cancel,
                )[0]
            except Exception as exc:  #bug shouldnt kill thread withoyt notice
                log.exception("Unexpected error converting %s", path)
                result = ConversionResult(Path(path), Status.FAILED, error=f"Unexpected error: {exc}")
            self.file_done.emit(position, result)