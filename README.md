# Converter

A local image/video converter, built as a learning project: understand the formats first (`learning/`), then build the real thing on mature libraries (`core/`).

- `learning/` — educational implementations (BMP, RLE, Huffman, LZ, DEFLATE, PNG, JPEG, MP4, H.264). Not production code.
- `core/` — the production converter engine. GUI-free, no imports from `learning/`.
- `docs/` — module write-ups. Roadmap: [converter_learning_modules.md](converter_learning_modules.md). Orientation: [CONTEXT.md](CONTEXT.md).
- `examples/sample_data/` — real sample files.
- `desktop/` — the PySide6 desktop app (Module 19). Talks to `core/` only through `ConversionManager`. Run: `python3 desktop/main.py`
- `tests/` — `python3 -m unittest discover -s tests -t .`

Status: Modules 16–18 done (architecture, Pillow images, FFmpeg video). Module 19 (desktop app) is written up in `docs/19_desktop_app.md`. Next: Module 20, testing and validation.
