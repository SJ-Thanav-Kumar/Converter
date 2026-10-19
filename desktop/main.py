"""Entry point:  python3 desktop/main.py"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # lets `import core` / `import desktop` work

# A macOS app started from Finder gets a minimal PATH (no Homebrew), so FFmpeg would look
# "missing". Append the usual install folders before any backend calls shutil.which().
for extra in ("/opt/homebrew/bin", "/usr/local/bin"):
    if extra not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + extra

from PySide6.QtWidgets import QApplication

from core.conversion import ConversionManager
from core.image.pillow_backend import PillowBackend
from core.video.ffmpeg_backend import FFmpegBackend
from desktop.gui.main_window import MainWindow
from desktop.gui.theme import build_stylesheet, load_bundled_fonts
from desktop.settings.store import AppSettings


def main() -> int:
    app = QApplication(sys.argv)
    load_bundled_fonts()          # the Inter file in resources/fonts/, before the stylesheet names it
    app.setStyleSheet(build_stylesheet())

    manager = ConversionManager([PillowBackend(), FFmpegBackend()])
    window = MainWindow(manager, AppSettings())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())