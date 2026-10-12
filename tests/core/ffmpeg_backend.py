import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.conversion import ConversionFailedError, ConversionManager
from core.detection import detect_file
from core.video.ffmpeg_backend import FFmpegBackend, probe_media

HAVE_FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


def make_video(path, video_codec="libx264", audio_codec="aac"):
    """Generate a 1-second test video (picture + beep) with FFmpeg itself."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
         "-f", "lavfi", "-i", "sine=duration=1",
         "-c:v", video_codec, "-pix_fmt", "yuv420p", "-c:a", audio_codec, "-shortest", str(path)],
        check=True,
    )


def codecs(path):
    streams = probe_media(Path(path))["streams"]
    return {s["codec_type"]: s["codec_name"] for s in streams}


@unittest.skipUnless(HAVE_FFMPEG, "FFmpeg/ffprobe not installed")
class FFmpegBackendTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.out = self.dir / "out"
        self.manager = ConversionManager([FFmpegBackend()])
        self.mp4 = self.dir / "clip.mp4"
        make_video(self.mp4)

    def tearDown(self):
        self._tmp.cleanup()

    def convert(self, src, fmt, **kw):
        return self.manager.convert(src, fmt, output_dir=self.out, **kw)

    def test_mp4_to_mov_is_remux(self):
        result = self.convert(self.mp4, "mov")
        self.assertEqual(detect_file(result.output_path).id, "mov")
        self.assertEqual(codecs(result.output_path), {"video": "h264", "audio": "aac"})  # untouched

    def test_mov_to_mp4_roundtrip(self):
        mov = self.convert(self.mp4, "mov").output_path
        back = self.manager.convert(mov, "mp4", output_dir=self.dir / "back").output_path
        self.assertEqual(detect_file(back).id, "mp4")
        self.assertEqual(codecs(back)["video"], "h264")

    def test_h264_to_h265_transcodes(self):
        result = self.convert(self.mp4, "mp4", options={"video_codec": "h265"})
        self.assertEqual(codecs(result.output_path)["video"], "hevc")

    def test_incompatible_audio_triggers_transcode_of_audio_only(self):
        mkv = self.dir / "clip.mkv"
        make_video(mkv, audio_codec="libopus")           # Opus audio is not allowed in our mp4 table
        result = self.convert(mkv, "mp4")
        found = codecs(result.output_path)
        self.assertEqual(found["video"], "h264")         # video was copied
        self.assertEqual(found["audio"], "aac")          # audio was re-encoded

    def test_duration_is_preserved(self):
        result = self.convert(self.mp4, "mov")
        before = float(probe_media(self.mp4)["format"]["duration"])
        after = float(probe_media(result.output_path)["format"]["duration"])
        self.assertAlmostEqual(before, after, delta=0.2)

    def test_progress_reaches_the_end(self):
        events = []
        self.convert(self.mp4, "mov", progress=lambda f, m: events.append(f))
        self.assertEqual(events[0], 0.0)
        self.assertEqual(events[-1], 1.0)

    def test_corrupt_video_fails_cleanly(self):
        bad = self.dir / "bad.mp4"
        bad.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"garbage" * 50)
        with self.assertRaises(ConversionFailedError):
            self.convert(bad, "mov")
        self.assertEqual(list(self.out.glob("*")), [])

    def test_bad_codec_option(self):
        with self.assertRaises(ConversionFailedError):
            self.convert(self.mp4, "mov", options={"video_codec": "h266"})

    def test_missing_ffmpeg_hides_video_conversions(self):
        with mock.patch("shutil.which", return_value=None):
            self.assertEqual(FFmpegBackend().supported_conversions(), set())


if __name__ == "__main__":
    unittest.main()