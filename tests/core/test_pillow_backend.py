import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        self.assertEqual(self.manager.supported_targets("png"), ["avif", "bmp", "gif", "heic", "jpeg", "tiff", "webp"])
        self.assertEqual(self.manager.supported_targets("jpeg"), ["avif", "bmp", "gif", "heic", "jpeg", "png", "tiff", "webp"])

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

    def test_uncommon_modes_convert(self):
        # (mode, fill, source ext, targets that previously failed or are most likely)
        cases = [
            ("CMYK", (0, 100, 100, 0), "jpg", ["png", "bmp"]),  # print-style JPEGs
            ("LA", (100, 255), "png", ["bmp", "jpeg"]),
            ("I;16", 3000, "png", ["bmp", "jpeg"]),
        ]
        for mode, fill, ext, targets in cases:
            src = self.dir / f"{mode.replace(';', '_')}.{ext}"
            Image.new(mode, (8, 6), fill).save(src)
            for target in targets:
                with self.subTest(mode=mode, target=target):
                    out = self.manager.convert(src, target, output_dir=self.out, overwrite=True)
                    with Image.open(out.output_path) as img:
                        self.assertEqual(img.size, (8, 6))

    def test_16bit_grayscale_is_scaled_not_clipped(self):
        src = self.dir / "deep.png"
        Image.new("I;16", (4, 4), 3000).save(src)
        with Image.open(self.convert(src, "bmp").output_path) as img:
            self.assertEqual(img.convert("L").getpixel((0, 0)), 11)  # 3000 / 256, not 255

    def test_exif_rotation_applied(self):
        src = self.dir / "rot.jpg"
        exif = Image.Exif()
        exif[0x0112] = 6                      # "rotate 90 degrees to display"
        Image.new("RGB", (40, 20), "red").save(src, exif=exif)
        with Image.open(self.convert(src, "png").output_path) as img:
            self.assertEqual(img.size, (20, 40))

    def test_new_formats_keep_dimensions_and_transparency(self):
        src = self.dir / "t.png"
        Image.new("RGBA", (30, 20), (255, 0, 0, 100)).save(src)
        for target, name in (("webp", "WEBP"), ("avif", "AVIF"), ("tiff", "TIFF"), ("heic", "HEIF")):
            with self.subTest(target=target):
                out = self.manager.convert(src, target, output_dir=self.out, overwrite=True).output_path
                with Image.open(out) as img:
                    self.assertEqual((img.format, img.size, img.mode), (name, (30, 20), "RGBA"))

    def test_new_formats_roundtrip_back_to_png(self):
        src = self.dir / "a.png"
        Image.new("RGB", (16, 16), (10, 200, 30)).save(src)
        for target in ("webp", "avif", "tiff", "gif", "heic"):
            with self.subTest(target=target):
                mid = self.manager.convert(src, target, output_dir=self.out, overwrite=True).output_path
                back = self.manager.convert(mid, "png", output_dir=self.dir / "back", overwrite=True).output_path
                with Image.open(back) as img:
                    self.assertEqual(img.size, (16, 16))

    def test_tiff_is_lossless(self):
        original = Image.new("RGB", (6, 6))
        original.putdata([(x * 40, y * 40, 7) for y in range(6) for x in range(6)])
        src = self.dir / "a.png"
        original.save(src)
        with Image.open(self.convert(src, "tiff").output_path) as img:
            self.assertEqual(img.convert("RGB").tobytes(), original.tobytes())

    def test_quality_option_changes_lossy_size(self):
        src = self.dir / "noise.png"
        Image.effect_noise((64, 64), 60).convert("RGB").save(src)
        for target in ("jpeg", "webp", "avif", "heic"):
            with self.subTest(target=target):
                low = self.manager.convert(src, target, output_dir=self.dir / "low", options={"quality": 10}).output_path
                high = self.manager.convert(src, target, output_dir=self.dir / "high", options={"quality": 95}).output_path
                self.assertLess(low.stat().st_size, high.stat().st_size)

    def _make_animated_gif(self, path):
        frames = [Image.new("RGB", (20, 10), c) for c in ("red", "green", "blue")]
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=[100, 200, 300], loop=0)

    def test_animation_survives_between_animated_formats(self):
        src = self.dir / "a.gif"
        self._make_animated_gif(src)
        for target in ("webp", "avif"):
            with self.subTest(target=target):
                mid = self.manager.convert(src, target, output_dir=self.out, overwrite=True).output_path
                with Image.open(mid) as img:
                    self.assertEqual(img.n_frames, 3)
                back = self.manager.convert(mid, "gif", output_dir=self.dir / "back", overwrite=True).output_path
                with Image.open(back) as img:
                    self.assertEqual(img.n_frames, 3)
                    durations = []
                    for i in range(img.n_frames):
                        img.seek(i)
                        durations.append(img.info["duration"])
                    self.assertEqual(durations, [100, 200, 300])

    def test_animation_to_still_format_uses_first_frame(self):
        src = self.dir / "a.gif"
        self._make_animated_gif(src)
        with Image.open(self.convert(src, "png").output_path) as img:
            self.assertEqual(getattr(img, "n_frames", 1), 1)

    def test_missing_heif_plugin_hides_heic(self):
        with mock.patch("core.image.pillow_backend.HEIF_READY", False):
            targets = {b for _, b in PillowBackend().supported_conversions()}
        self.assertNotIn("heic", targets)
        self.assertIn("webp", targets)

    def test_missing_webp_support_hides_it(self):
        with mock.patch("core.image.pillow_backend.features.check", return_value=False):
            targets = {b for _, b in PillowBackend().supported_conversions()}
        self.assertNotIn("webp", targets)
        self.assertNotIn("avif", targets)
        self.assertIn("tiff", targets)

    def test_corrupt_image_fails_cleanly(self):
        src = self.dir / "bad.png"
        src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"not really image data" * 5)
        with self.assertRaises(ConversionFailedError):
            self.convert(src, "jpeg")
        self.assertEqual(list(self.out.glob("*")), [])


if __name__ == "__main__":
    unittest.main()