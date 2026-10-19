"""Validation tests: lossy formats are never byte-equal, so check the PROPERTIES that must hold.

Two checks per format: the picture still looks like the original (small average pixel error),
and the quality option really trades size for fidelity.
"""
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from core.conversion import ConversionManager
from core.image.pillow_backend import PillowBackend

SAMPLES = Path(__file__).resolve().parents[2] / "examples" / "sample_data" / "images"
PHOTO = SAMPLES / "markScared.jpg"
LOSSY = ["jpeg", "webp", "avif", "heic"]
LOSSLESS = ["tiff", "bmp"]      # png is the reference itself, so it has no png -> png route


def mean_error(a: Path, b: Path) -> float:
    #average absolute difference per channel, 0 (identical) to 255 (opposite)
    with Image.open(a) as x, Image.open(b) as y:
        diff = ImageChops.difference(x.convert("RGB"), y.convert("RGB"))
        return sum(ImageStat.Stat(diff).mean) / 3


class LossyQualityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.manager = ConversionManager([PillowBackend()])
        # a PNG of the photo: the common starting point, and a fair reference for every target
        self.reference = self.dir / "reference.png"
        Image.open(PHOTO).convert("RGB").save(self.reference)

    def tearDown(self):
        self._tmp.cleanup()

    def convert(self, target, quality=None, name="out"):
        options = {} if quality is None else {"quality": quality}
        return self.manager.convert(self.reference, target, output_dir=self.dir / name, overwrite=True,
                                    options=options).output_path

    def test_lossless_formats_are_pixel_exact(self):
        for target in LOSSLESS:
            with self.subTest(target=target):
                self.assertEqual(mean_error(self.reference, self.convert(target)), 0)

    def test_default_quality_stays_close_to_the_original(self):
        for target in LOSSY:
            with self.subTest(target=target):
                self.assertLess(mean_error(self.reference, self.convert(target)), 6)

    def test_lower_quality_means_smaller_file_and_more_error(self):
        for target in LOSSY:
            with self.subTest(target=target):
                low, high = self.convert(target, 20, "low"), self.convert(target, 95, "high")
                self.assertLess(low.stat().st_size, high.stat().st_size)
                self.assertGreater(mean_error(self.reference, low), mean_error(self.reference, high))

    def test_lossy_round_trip_does_not_drift_much(self):
        # convert twice (jpeg -> webp -> jpeg): quality loss is allowed, a different picture is not
        mid = self.convert("webp", name="mid")
        back = self.manager.convert(mid, "jpeg", output_dir=self.dir / "back", overwrite=True).output_path
        self.assertLess(mean_error(self.reference, back), 10)


if __name__ == "__main__":
    unittest.main()
