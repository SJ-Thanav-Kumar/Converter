"""Integration tests: the REAL backends on the REAL sample files in examples/sample_data."""
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from PIL import Image

from core.conversion import CancellationToken, ConversionFailedError, ConversionManager, Status
from core.detection import detect_file
from core.image.pillow_backend import PillowBackend
from core.video.ffmpeg_backend import FFmpegBackend, probe_media

SAMPLES = Path(__file__).resolve().parents[2] / "examples" / "sample_data"
IMAGES = [SAMPLES / "images" / n for n in ("SmileYay.PNG", "markScared.jpg", "test_3x3.bmp")]
VIDEO = SAMPLES / "videos" / "Speed_lasereyes.MP4"
CORRUPT = SAMPLES / "corrupted" / "Calc_CIA1.png"
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


class RealImageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name) / "out"
        self.manager = ConversionManager([PillowBackend()])

    def tearDown(self):
        self._tmp.cleanup()

    def test_every_sample_converts_to_every_target_with_right_size_and_format(self):
        for src in IMAGES:
            with Image.open(src) as original:
                size = original.size
            source_format = detect_file(src).id
            for target in self.manager.supported_targets(source_format):
                with self.subTest(sample=src.name, target=target):
                    result = self.manager.convert(src, target, output_dir=self.out, overwrite=True)
                    self.assertEqual(detect_file(result.output_path).id, target)     # detected by content, not by name
                    with Image.open(result.output_path) as converted:
                        self.assertEqual(converted.size, size)

    def test_corrupted_sample_is_refused_and_leaves_nothing_behind(self):
        with self.assertRaises(Exception):
            self.manager.convert(CORRUPT, "jpeg", output_dir=self.out)
        self.assertEqual(list(self.out.glob("*")) if self.out.exists() else [], [])

    def test_real_batch_mixes_good_and_bad_files(self):
        batch = [IMAGES[0], CORRUPT, IMAGES[1]]
        results = self.manager.convert_batch(batch, "webp", output_dir=self.out)
        self.assertEqual([r.status for r in results], [Status.OK, Status.FAILED, Status.OK])

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can write anywhere")
    def test_unwritable_output_folder_fails_cleanly(self):
        locked = Path(self._tmp.name) / "locked"
        locked.mkdir()
        locked.chmod(0o500)                                    # read + enter, no write
        try:
            with self.assertRaises(Exception):
                self.manager.convert(IMAGES[0], "jpeg", output_dir=locked / "sub")
        finally:
            locked.chmod(0o700)


@unittest.skipUnless(HAVE_FFMPEG and VIDEO.exists(), "FFmpeg or the sample video is missing")
class RealVideoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name) / "out"
        self.manager = ConversionManager([FFmpegBackend()])

    def tearDown(self):
        self._tmp.cleanup()

    def test_containers_keep_duration_and_streams(self):
        before = probe_media(VIDEO)
        duration = float(before["format"]["duration"])
        for target in ("mov", "mkv"):
            with self.subTest(target=target):
                out = self.manager.convert(VIDEO, target, output_dir=self.out).output_path
                after = probe_media(out)
                self.assertAlmostEqual(float(after["format"]["duration"]), duration, delta=0.3)
                kinds = sorted(s["codec_type"] for s in after["streams"])
                self.assertEqual(kinds, sorted(s["codec_type"] for s in before["streams"]))

    def test_video_to_gif_respects_the_length_cap(self):
        out = self.manager.convert(VIDEO, "gif", output_dir=self.out, options={"gif_seconds": 2}).output_path
        self.assertLess(float(probe_media(out)["format"]["duration"]), 2.5)

    def test_real_ffmpeg_run_can_be_cancelled_and_leaves_no_output(self):
        token = CancellationToken()
        # the sample is short, so cancel on the very first progress report
        def on_progress(fraction, message):
            if fraction is not None and fraction > 0:
                token.cancel()
        with self.assertRaises(Exception):
            self.manager.convert(VIDEO, "mp4", output_dir=self.out, options={"video_codec": "h265"},
                                 progress=on_progress, cancel=token)
        self.assertEqual([p for p in self.out.glob("*")] if self.out.exists() else [], [])


if __name__ == "__main__":
    unittest.main()
