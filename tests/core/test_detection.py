import tempfile
import unittest
from pathlib import Path

from core.detection import detect_bytes, detect_file, normalize_format

SAMPLES = Path(__file__).resolve().parents[2] / "examples" / "sample_data"


class DetectBytesTests(unittest.TestCase):
    def test_signatures(self):
        cases = {
            b"\x89PNG\r\n\x1a\n" + bytes(8): "png",
            b"\xff\xd8\xff\xe0" + bytes(8): "jpeg",
            b"BM" + bytes(12): "bmp",
            b"GIF89a" + bytes(8): "gif",
            b"RIFF\x00\x00\x00\x00WEBPVP8 ": "webp",
            b"RIFF\x00\x00\x00\x00AVI LIST": "avi",
            b"II*\x00" + bytes(8): "tiff",
            b"MM\x00*" + bytes(8): "tiff",
            b"\x00\x00\x00\x1cftypavif" + bytes(8): "avif",     # must not be mistaken for mp4
            b"\x00\x00\x00\x1cftypavis" + bytes(8): "avif",
            b"\x00\x00\x00\x18ftypheic" + bytes(8): "heic",     # iPhone photos, must not be mistaken for mp4
            b"\x00\x00\x00\x18ftypmif1" + bytes(8): "heic",
            b"\x00\x00\x00\x18ftypmp42" + bytes(8): "mp4",
            b"\x00\x00\x00\x14ftypqt  " + bytes(8): "mov",
            b"\x1a\x45\xdf\xa3" + bytes(8): "mkv",
        }
        for header, expected in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(detect_bytes(header).id, expected)

    def test_unknown_and_empty(self):
        self.assertIsNone(detect_bytes(b""))
        self.assertIsNone(detect_bytes(b"hello world, not a media file"))

    def test_normalize_format(self):
        self.assertEqual(normalize_format(".JPG"), "jpeg")
        self.assertEqual(normalize_format("Tif"), "tiff")
        self.assertEqual(normalize_format("png"), "png")


class DetectFileTests(unittest.TestCase):
    def test_real_samples(self):
        expected = {
            "images/markScared.jpg": "jpeg",
            "images/SmileYay.PNG": "png",
            "images/test_3x3.bmp": "bmp",
            "videos/Speed_lasereyes.MP4": None,  # mp4 or mov: just must be a video
        }
        for rel, fmt in expected.items():
            path = SAMPLES / rel
            if not path.exists():
                self.skipTest(f"missing sample {rel}")
            info = detect_file(path)
            self.assertIsNotNone(info, rel)
            if fmt:
                self.assertEqual(info.id, fmt)
            else:
                self.assertEqual(info.kind, "video")

    def test_extension_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "actually_png.jpg"
            p.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(20))
            self.assertEqual(detect_file(p).id, "png")


if __name__ == "__main__":
    unittest.main()
