import os
import shutil
import subprocess
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
        return {("png", "jpeg"), ("png", "bmp"), ("jpeg", "png"), ("jpeg", "jpeg")}

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

    def test_compress_keeps_the_format_and_hides_the_format_picker(self):
        jpg = self.dir / "photo.jpg"
        jpg.write_bytes(JPEG)
        window = self.make_window()
        window._load_file(jpg)
        self.assertEqual(self.targets(window), ["png"])      # CONVERT never offers the same format
        window._set_mode("compress")
        self.assertEqual(self.targets(window), ["jpeg"])
        self.assertTrue(window._target_combo.isHidden())
        self.assertTrue(window._quality_row.isVisibleTo(window))
        window._set_mode("convert")
        self.assertFalse(window._target_combo.isHidden())

    def test_compress_has_no_route_for_a_png_source(self):
        window = self.make_window()
        window._load_file(self.src)
        window._set_mode("compress")
        self.assertEqual(self.targets(window), [])
        self.assertFalse(window._run_button.isEnabled())

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


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class PreviewAndOptionTests(unittest.TestCase):
    """The window with the REAL backends: previews are decoded by Pillow/Qt, so a fake backend would prove nothing."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PIL import Image
        from core.image.pillow_backend import PillowBackend
        from core.video.ffmpeg_backend import FFmpegBackend
        from desktop.settings.store import AppSettings

        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.settings = AppSettings(QSettings(str(self.dir / "s.ini"), QSettings.Format.IniFormat))
        self.manager = ConversionManager([PillowBackend(), FFmpegBackend()])
        self.png = self.dir / "photo.png"
        Image.new("RGB", (60, 40), (200, 30, 30)).save(self.png)
        frames = [Image.new("RGB", (20, 10), c) for c in ("red", "green", "blue")]
        self.gif = self.dir / "anim.gif"
        frames[0].save(self.gif, save_all=True, append_images=frames[1:], duration=[100, 200, 300], loop=0)

    def tearDown(self):
        self._tmp.cleanup()

    def make_window(self):
        from desktop.gui.main_window import MainWindow

        return MainWindow(self.manager, self.settings)

    def convert_to(self, window, target):
        window._target_combo.setCurrentIndex(window._target_combo.findData(target))
        window._start()
        wait_until(lambda: window._worker is None)

    def shows_picture(self, window):
        return window._preview._label.pixmap() is not None and not window._preview._label.pixmap().isNull()

    def test_only_convert_and_compress_tabs_exist(self):
        self.assertEqual(list(self.make_window()._mode_buttons), ["convert", "compress"])

    def test_every_still_output_format_is_previewed(self):
        window = self.make_window()
        window._load_file(self.png)
        for target in ("webp", "avif", "heic", "tiff", "gif", "jpeg", "bmp"):
            with self.subTest(target=target):
                self.convert_to(window, target)
                self.assertIsNotNone(window._result, target)
                self.assertTrue(self.shows_picture(window), target)

    def test_loaded_input_is_previewed_in_the_drop_zone(self):
        window = self.make_window()
        window._load_file(self.png)
        self.assertTrue(window._drop._preview.isVisibleTo(window))
        window._clear()
        self.assertFalse(window._drop._preview.isVisibleTo(window))

    def test_animated_output_plays(self):
        window = self.make_window()
        window._load_file(self.gif)
        self.convert_to(window, "webp")
        preview = window._preview
        self.assertIsNotNone(preview._animation)
        preview._next_frame()
        self.assertEqual(preview._frame, 1)
        window._discard()
        self.assertIsNone(preview._animation)          # discarding stops it and lets go of the file

    def test_default_button_resets_every_option(self):
        window = self.make_window()
        window._load_file(self.png)
        window._target_combo.setCurrentIndex(window._target_combo.findData("bmp"))
        self.assertFalse(window._default_button.isVisibleTo(window))      # png -> bmp has no options to reset
        window._target_combo.setCurrentIndex(window._target_combo.findData("webp"))
        self.assertTrue(window._default_button.isVisibleTo(window))
        window._quality_slider.setValue(20)
        window._gif_fps_slider.setValue(30)
        window._crf_slider.setValue(40)
        window._default_button.click()
        self.assertEqual(window._quality_slider.value(), 90)
        self.assertEqual(window._gif_fps_slider.value(), 12)
        self.assertEqual(window._crf_slider.value(), 28)
        self.assertEqual(window._codec_combo.currentData(), "keep")

    def test_gif_sliders_only_for_video_to_gif(self):
        window = self.make_window()
        window._load_file(self.png)
        window._target_combo.setCurrentIndex(window._target_combo.findData("gif"))
        self.assertFalse(window._gif_fps_row.isVisibleTo(window))
        self.assertNotIn("gif_fps", window._collect_options())

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg not installed")
    def test_video_to_gif_options_and_previews(self):
        mp4 = self.dir / "clip.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mp4)], check=True)
        window = self.make_window()
        window._load_file(mp4)
        window._target_combo.setCurrentIndex(window._target_combo.findData("gif"))
        self.assertTrue(window._gif_fps_row.isVisibleTo(window))
        window._gif_width_slider.setValue(80)
        window._gif_seconds_slider.setValue(1)
        options = window._collect_options()
        self.assertEqual((options["gif_width"], options["gif_seconds"]), (80, 1))
        window._start()
        wait_until(lambda: window._worker is None, 15000)
        self.assertIsNotNone(window._result)
        self.assertIsNotNone(window._preview._animation)           # the GIF plays in the preview
        self.convert_to(window, "mov")                              # and a video output goes to the player
        self.assertIsNotNone(window._result)
        window._discard()


if __name__ == "__main__":
    unittest.main()