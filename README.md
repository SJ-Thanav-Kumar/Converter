# Converter

A local image/video converter, built as a learning project: understand the formats first (`learning/`), then build the real thing on mature libraries (`core/`).

- `learning/` — educational implementations (BMP, RLE, Huffman, LZ, DEFLATE, PNG, JPEG, MP4, H.264). Not production code.
- `core/` — the production converter engine. GUI-free, no imports from `learning/`.
- `docs/` — module write-ups. Roadmap: [converter_learning_modules.md](converter_learning_modules.md). Orientation: [CONTEXT.md](CONTEXT.md).
- `examples/sample_data/` — real sample files.
- `tests/` — `python3 -m unittest discover -s tests -t .`

Status: Module 16 (architecture) done. Next: Module 17, Pillow image backend.
