import tempfile
import unittest
from pathlib import Path

from core.conversion import (
    CancellationToken,
    ConversionBackend,
    ConversionCancelledError,
    ConversionFailedError,
    ConversionManager,
    InvalidInputError,
    OutputExistsError,
    Status,
    UnsupportedFormatError,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"fake png body"
BMP = b"BM" + b"fake bmp body"


class FakeBackend(ConversionBackend):
    """Pretends to convert png -> jpeg/bmp by writing a marker file."""

    name = "fake"

    def __init__(self, mode="ok"):
        self.mode = mode
        self.calls = []

    def supported_conversions(self):
        return {("png", "jpeg"), ("png", "bmp")}

    def convert(self, source, destination, source_format, target_format, progress, cancel):
        self.calls.append((source, destination, source_format, target_format))
        progress(0.5, "halfway")
        if self.mode == "fail":
            destination.write_bytes(b"partial")
            raise ConversionFailedError("boom")
        if self.mode == "cancel":
            cancel.cancel()
            cancel.raise_if_cancelled()
        if self.mode == "empty":
            destination.write_bytes(b"")
            return
        destination.write_bytes(b"converted:" + target_format.encode())


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.src = self.dir / "photo.png"
        self.src.write_bytes(PNG)
        self.backend = FakeBackend()
        self.manager = ConversionManager([self.backend])

    def tearDown(self):
        self._tmp.cleanup()

    def test_convert_ok(self):
        r = self.manager.convert(self.src, "jpg")  # alias accepted
        self.assertTrue(r.ok)
        self.assertEqual(r.output_path, self.dir / "photo.jpg")
        self.assertEqual(r.input_format, "png")
        self.assertEqual(r.output_format, "jpeg")
        self.assertEqual(r.output_path.read_bytes(), b"converted:jpeg")
        self.assertEqual([p.name for p in self.dir.iterdir() if "partial" in p.name], [])

    def test_output_dir_created(self):
        out = self.dir / "nested" / "out"
        r = self.manager.convert(self.src, "bmp", output_dir=out)
        self.assertEqual(r.output_path, out / "photo.bmp")

    def test_progress_reported(self):
        events = []
        self.manager.convert(self.src, "bmp", progress=lambda f, m: events.append(f))
        self.assertEqual(events[0], 0.0)
        self.assertEqual(events[-1], 1.0)
        self.assertIn(0.5, events)

    def test_refuses_overwrite_by_default(self):
        existing = self.dir / "photo.jpg"
        existing.write_bytes(b"keep me")
        with self.assertRaises(OutputExistsError):
            self.manager.convert(self.src, "jpeg")
        self.assertEqual(existing.read_bytes(), b"keep me")
        self.assertEqual(self.backend.calls, [])

    def test_overwrite_allowed_on_request(self):
        (self.dir / "photo.jpg").write_bytes(b"old")
        r = self.manager.convert(self.src, "jpeg", overwrite=True)
        self.assertEqual(r.output_path.read_bytes(), b"converted:jpeg")

    def test_never_overwrites_input(self):
        class SameFormat(FakeBackend):
            def supported_conversions(self):
                return {("png", "png")}

        m = ConversionManager([SameFormat()])
        with self.assertRaises(OutputExistsError):
            m.convert(self.src, "png", overwrite=True)
        self.assertEqual(self.src.read_bytes(), PNG)

    def test_invalid_inputs(self):
        with self.assertRaises(InvalidInputError):
            self.manager.convert(self.dir / "missing.png", "jpeg")
        with self.assertRaises(InvalidInputError):
            self.manager.convert(self.dir, "jpeg")
        empty = self.dir / "empty.png"
        empty.write_bytes(b"")
        with self.assertRaises(InvalidInputError):
            self.manager.convert(empty, "jpeg")

    def test_unsupported(self):
        text = self.dir / "notes.png"
        text.write_bytes(b"just text pretending to be a png")
        with self.assertRaises(UnsupportedFormatError):
            self.manager.convert(text, "jpeg")  # content, not extension, decides
        with self.assertRaises(UnsupportedFormatError):
            self.manager.convert(self.src, "mp4")  # no route
        with self.assertRaises(UnsupportedFormatError):
            self.manager.convert(self.src, "nonsense")

    def test_backend_failure_leaves_no_partial_file(self):
        m = ConversionManager([FakeBackend("fail")])
        with self.assertRaises(ConversionFailedError):
            m.convert(self.src, "jpeg")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["photo.png"])

    def test_empty_backend_output_is_a_failure(self):
        m = ConversionManager([FakeBackend("empty")])
        with self.assertRaises(ConversionFailedError):
            m.convert(self.src, "jpeg")

    def test_cancel_before_start(self):
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(ConversionCancelledError):
            self.manager.convert(self.src, "jpeg", cancel=token)
        self.assertEqual(self.backend.calls, [])

    def test_cancel_during_conversion(self):
        m = ConversionManager([FakeBackend("cancel")])
        with self.assertRaises(ConversionCancelledError):
            m.convert(self.src, "jpeg")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["photo.png"])

    def test_batch_continues_after_failure(self):
        bad = self.dir / "bad.png"
        bad.write_bytes(b"nope")
        good2 = self.dir / "other.png"
        good2.write_bytes(PNG)
        results = self.manager.convert_batch([self.src, bad, good2], "jpeg")
        self.assertEqual([r.status for r in results], [Status.OK, Status.FAILED, Status.OK])
        self.assertIn("Unrecognised", results[1].error)

    def test_supported_targets(self):
        self.assertEqual(self.manager.supported_targets("PNG"), ["bmp", "jpeg"])
        self.assertEqual(self.manager.supported_targets("mp4"), [])


if __name__ == "__main__":
    unittest.main()
