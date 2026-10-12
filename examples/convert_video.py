import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # lets `import core` work from here

from core.conversion import ConversionManager
from core.video.ffmpeg_backend import FFmpegBackend, probe_media


def describe(path: Path) -> str:
    """One-line summary of a video file, read with ffprobe."""
    info = probe_media(path)
    codecs = ", ".join(f"{s['codec_type']}={s['codec_name']}" for s in info["streams"])
    return f"{path.name}: {codecs}, {float(info['format']['duration']):.1f}s"


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python3 examples/convert_video.py <mp4|mov|mkv> <file> [h264|h265]")
        return 1

    output_format, source = sys.argv[1], Path(sys.argv[2])
    options = {"video_codec": sys.argv[3]} if len(sys.argv) > 3 else {}

    manager = ConversionManager([FFmpegBackend()])
    if not manager.supported_targets("mp4"):
        print("FFmpeg was not found, so video conversion is unavailable.")
        return 1

    def show_progress(fraction, message):
        if fraction is not None:
            print(f"\r{message}: {fraction:5.0%}", end="", flush=True)

    result = manager.convert(source, output_format, options=options, progress=show_progress)
    print()
    print("before:", describe(source))
    print("after: ", describe(result.output_path))
    print("saved to:", result.output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())