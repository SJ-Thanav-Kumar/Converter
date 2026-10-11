import tempfile
import unittest
from pathlib import Path

from PIL import Image

from core.conversion import ConversionFailedError, ConversionManager
from core.image.pillow_backend import PillowBackend


class PillowBackendTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.out = self.dir / "out"
        self.manager = ConversionManager([PillowBackend()])

    def tearDown(self):
        self._tmp.cleanup()

    def convert(self, src, fmt):
        return self.manager.convert(src, fmt, output_dir=self.out)

    def test_all_pairs_registered(self):
        self.assertEqual(self.manager.supported_targets("png"), ["bmp", "jpeg"])
        self.assertEqual(self.manager.supported_targets("jpeg"), ["bmp", "png"])

    def test_png_to_jpeg_keeps_dimensions(self):
        src = self.dir / "a.png"
        Image.new("RGB", (30, 20), (10, 200, 30)).save(src)
        result = self.convert(src, "jpeg")
        with Image.open(result.output_path) as img:
            self.assertEqual(img.format, "JPEG")
            self.assertEqual(img.size, (30, 20))

    def test_lossless_roundtrip_bmp_png_bmp(self):
        original = Image.new("RGB", (5, 7))
        original.putdata([(x * 20 % 256, y * 30 % 256, (x + y) * 10) for y in range(7) for x in range(5)])
        src = self.dir / "a.bmp"
        original.save(src)
        png = self.convert(src, "png").output_path
        back = self.manager.convert(png, "bmp", output_dir=self.dir / "back").output_path
        with Image.open(back) as img:
            self.assertEqual(img.convert("RGB").tobytes(), original.tobytes())

    def test_transparency_flattened_onto_white(self):
        src = self.dir / "t.png"
        Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(src)
        with Image.open(self.convert(src, "jpeg").output_path) as img:
            self.assertEqual(img.mode, "RGB")
            self.assertTrue(all(c > 240 for c in img.getpixel((0, 0))))

    def test_palette_png_to_jpeg(self):
        src = self.dir / "p.png"
        Image.new("RGB", (6, 6), (200, 10, 10)).convert("P").save(src)
        with Image.open(self.convert(src, "jpeg").output_path) as img:
            self.assertEqual(img.size, (6, 6))

    def test_exif_rotation_applied(self):
        src = self.dir / "rot.jpg"
        exif = Image.Exif()
        exif[0x0112] = 6                      # "rotate 90 degrees to display"
        Image.new("RGB", (40, 20), "red").save(src, exif=exif)
        with Image.open(self.convert(src, "png").output_path) as img:
            self.assertEqual(img.size, (20, 40))

    def test_corrupt_image_fails_cleanly(self):
        src = self.dir / "bad.png"
        src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"not really image data" * 5)
        with self.assertRaises(ConversionFailedError):
            self.convert(src, "jpeg")
        self.assertEqual(list(self.out.glob("*")), [])


if __name__ == "__main__":
    unittest.main()