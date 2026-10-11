import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # lets `import core` work from here

from core.conversion import ConversionManager
from core.image.pillow_backend import PillowBackend


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python3 examples/convert_image.py <png|jpeg|bmp> <file> [more files...]")
        return 1

    output_format, files = sys.argv[1], sys.argv[2:]
    manager = ConversionManager([PillowBackend()])

    for r in manager.convert_batch(files, output_format):
        if r.ok:
            print(f"OK    {r.input_path.name} -> {r.output_path}")
        else:
            print(f"FAIL  {r.input_path.name}: {r.error}")
    return 0


if __name__ == "__main__":
    sys.exit(main())