import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # no real window needed

try:
    from PySide6.QtCore import QEventLoop, QSettings, QTimer
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

from core.conversion import CancellationToken, ConversionBackend, ConversionManager, Status

PNG = b"\x89PNG\r\n\x1a\n" + b"fake png body"
JPEG = b"\xff\xd8\xff\xe0" + b"fake jpeg body"
SAVE_DIALOG = "desktop.gui.main_window.QFileDialog.getSaveFileName"


class FakeBackend(ConversionBackend):
    name = "fake"

    def supported_conversions(self):
        return {("png", "jpeg"), ("png", "bmp"), ("jpeg", "png")}

    def convert(self, source, destination, source_format, target_format, progress, cancel, options):
        progress(0.5, "halfway")
        cancel.raise_if_cancelled()
        destination.write_bytes(b"converted:" + target_format.encode())


def wait_until(condition, timeout_ms=5000):
    """Spin the Qt event loop until condition() is true (queued signals need it)."""
    loop, timer = QEventLoop(), QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: loop.quit() if condition() else None)
    timer.start()
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    timer.stop()


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.settings.store import AppSettings

        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.src = self.dir / "photo.png"
        self.src.write_bytes(PNG)
        self.settings = AppSettings(QSettings(str(self.dir / "s.ini"), QSettings.Format.IniFormat))
        self.settings.output_dir = self.dir / "saved"
        self.manager = ConversionManager([FakeBackend()])

    def tearDown(self):
        self._tmp.cleanup()

    # --- settings ---------------------------------------------------------
    def test_settings_roundtrip_and_defaults(self):
        self.assertEqual(self.settings.jpeg_quality, 90)
        self.assertEqual(self.settings.video_codec, "keep")
        self.settings.jpeg_quality = 55
        self.settings.video_codec = "h265"
        self.assertEqual((self.settings.jpeg_quality, self.settings.video_codec), (55, "h265"))

    # --- worker -----------------------------------------------------------
    def _run_worker(self, paths, cancel=None):
        from desktop.workers.conversion_worker import ConversionWorker

        results = {}
        worker = ConversionWorker(self.manager, [str(p) for p in paths], "jpeg",
                                  self.dir / "stage", {}, cancel or CancellationToken())
        worker.file_done.connect(lambda position, result: results.__setitem__(position, result))
        worker.start()
        wait_until(lambda: worker.isFinished())
        worker.wait()
        wait_until(lambda: len(results) == len(paths))   # queued signals arrive via the event loop
        return results

    def test_worker_reports_every_file_and_keeps_going_after_a_failure(self):
        missing = self.dir / "missing.png"
        results = self._run_worker([missing, self.src])
        self.assertEqual(results[0].status, Status.FAILED)
        self.assertTrue(results[1].ok)
        self.assertEqual(results[1].output_path.parent, self.dir / "stage")

    def test_worker_marks_everything_cancelled_when_token_is_set(self):
        token = CancellationToken()
        token.cancel()
        results = self._run_worker([self.src, self.src], cancel=token)
        self.assertEqual([r.status for r in results.values()], [Status.CANCELLED, Status.CANCELLED])

    # --- window -----------------------------------------------------------
    def make_window(self):
        from desktop.gui.main_window import MainWindow

        return MainWindow(self.manager, self.settings)

    def convert_to(self, window, target):
        window._target_combo.setCurrentIndex(window._target_combo.findData(target))
        window._start()
        wait_until(lambda: window._worker is None)

    def targets(self, window):
        combo = window._target_combo
        return [combo.itemData(i) for i in range(combo.count())]

    def test_loading_a_file_fills_the_workspace(self):
        window = self.make_window()
        self.assertFalse(window._run_button.isEnabled())
        window._load_file(self.src)
        self.assertEqual(window._file_name.text(), "photo.png")
        self.assertTrue(window._file_meta.text().startswith("PNG"))
        self.assertEqual(self.targets(window), ["bmp", "jpeg"])
        self.assertTrue(window._run_button.isEnabled())

    def test_unrecognised_file_is_refused_with_a_message(self):
        junk = self.dir / "notes.txt"
        junk.write_text("hello")
        window = self.make_window()
        window._load_file(junk)
        self.assertIsNone(window._input)
        self.assertIn("ERROR", window._status.text())

    def test_compress_mode_offers_only_jpeg_for_images(self):
        window = self.make_window()
        window._load_file(self.src)
        window._set_mode("compress")
        self.assertEqual(self.targets(window), ["jpeg"])
        self.assertTrue(window._quality_row.isVisibleTo(window))
        window._set_mode("convert")
        self.assertEqual(self.targets(window), ["bmp", "jpeg"])

    def test_compress_has_no_route_for_a_jpeg_source(self):
        jpg = self.dir / "photo.jpg"
        jpg.write_bytes(JPEG)
        window = self.make_window()
        window._load_file(jpg)
        window._set_mode("compress")
        self.assertEqual(self.targets(window), [])
        self.assertFalse(window._run_button.isEnabled())

    def test_restore_tab_shows_the_placeholder_page(self):
        window = self.make_window()
        window._set_mode("restore")
        self.assertEqual(window._stack.currentIndex(), 1)
        window._set_mode("convert")
        self.assertEqual(window._stack.currentIndex(), 0)

    def test_output_stays_staged_until_save_and_original_is_untouched(self):
        window = self.make_window()
        window._load_file(self.src)
        self.convert_to(window, "jpeg")

        staged = window._result.output_path
        self.assertTrue(staged.exists())
        self.assertFalse((self.dir / "saved").exists())     # nothing saved yet
        self.assertTrue(window._save_button.isEnabled())

        final = self.dir / "saved" / "photo.jpg"
        with patch(SAVE_DIALOG, return_value=(str(final), "")):
            window._save()
        self.assertFalse(staged.exists())
        self.assertTrue(final.exists())
        self.assertEqual(self.src.read_bytes(), PNG)

    def test_save_refuses_to_replace_the_original(self):
        window = self.make_window()
        window._load_file(self.src)
        self.convert_to(window, "jpeg")
        with patch(SAVE_DIALOG, return_value=(str(self.src), "")):
            window._save()
        self.assertEqual(self.src.read_bytes(), PNG)
        self.assertIsNotNone(window._result)          # still staged, user can pick another name

    def test_discard_removes_staged_file(self):
        window = self.make_window()
        window._load_file(self.src)
        self.convert_to(window, "jpeg")
        staged = window._result.output_path
        window._discard()
        self.assertFalse(staged.exists())
        self.assertIsNone(window._staging)


if __name__ == "__main__":
    unittest.main()