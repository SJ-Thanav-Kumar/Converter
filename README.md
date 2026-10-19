# Quarry — A Local Media Converter

A desktop image and video converter built with Python, Pillow, FFmpeg and PySide6. Convert between formats, compress videos, preview animations and videos, all on your machine.

## Features

- **Images:** PNG, JPEG, BMP, GIF, WebP, AVIF, TIFF, HEIC — any to any
- **Video:** MP4, MOV, MKV — remux (fast) or transcode with H.264/H.265
- **GIF <-> Video:** convert videos to GIF with frame rate and width controls
- **Animations:** GIF, WebP and AVIF keep their frames and timing
- **Previews:** live picture, animation and video preview in the app
- **Quality:** JPEG/WebP/AVIF/HEIC quality slider; video CRF control
- **Staging:** converted files are held until you explicitly save them (never overwrites the original)

## Install

### macOS / Windows (prebuilt)

Download `Quarry.dmg` (macOS) or `Quarry-Windows.zip` (Windows) from the [Releases](https://github.com/SJ-Thanav-Kumar/Converter/releases) page.

**First time only:** macOS will show "cannot be opened because the developer cannot be verified". Right-click the app, choose "Open", and click "Open" again. Windows may show a SmartScreen warning; click "More info" and "Run anyway".

### For video (MP4, MOV, MKV)

FFmpeg is not bundled. Install it:

- **macOS:** `brew install ffmpeg`
- **Windows:** `winget install ffmpeg`

Without FFmpeg, the app converts images only (video options are hidden).

## From source

```bash
git clone https://github.com/SJ-Thanav-Kumar/Converter.git
cd Converter
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[desktop]"
python3 desktop/main.py
```

Requires Python 3.9+, FFmpeg (optional, for video), and Pillow with AVIF/HEIC support.

## Building a release

```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed --name Quarry --paths . --collect-all pillow_heif desktop/main.py

# macOS: create a disk image
mkdir dmgroot && cp -R dist/Quarry.app dmgroot/ && ln -s /Applications dmgroot/Applications
hdiutil create -volname Quarry -srcfolder dmgroot -ov -format UDZO Quarry.dmg

# Windows: zip the folder
Compress-Archive -Path dist\Quarry -DestinationPath Quarry-Windows.zip
```

See [`docs/22_final_map.md`](docs/22_final_map.md) for details and the GitHub Actions workflow.

## License

This project is licensed under the **MIT License** — see [`LICENSE`](LICENSE) for details.

**Note on dependencies:** Pillow-HEIF bundles x265 (GPL-licensed). If you bundle this project with FFmpeg/libx264/libx265, those are also GPL, so you must release under GPL v2+ instead. For personal use, this is fine.

## Learning

This started as a learning project to understand file formats, compression and media processing. See [`converter_learning_modules.md`](converter_learning_modules.md) for the roadmap and [`docs/`](docs/) for module write-ups.
