# Quarry

A local desktop converter for images and video, built with Python, Pillow, FFmpeg and PySide6. Everything runs on your machine: nothing is uploaded.

<!-- TODO: add a screenshot or short GIF of the app here -->

## Features

- **Images:** PNG, JPEG, BMP, GIF, WebP, AVIF, TIFF and HEIC, any to any. A quality slider for the lossy formats (JPEG, WebP, AVIF, HEIC).
- **Video:** MP4, MOV and MKV. Fast remux when only the container changes, re-encode (H.264 / H.265) when it has to.
- **GIF and video:** video to GIF (choose frame rate, width and maximum length) and GIF back to MP4 or MOV.
- **Animations:** animated GIF, WebP and AVIF keep their frames and timing when converted between each other.
- **Preview:** the input and the result are previewed in the window: pictures, animations and video.
- **Compress mode:** smaller files with a quality slider (images) or a CRF value and codec (video).
- **Safe by design:** the original is never overwritten. The result stays in a temporary folder until you press SAVE OUTPUT.
- **Format detection by content:** a file is recognised by its first bytes, not its extension.

## Download

Get the latest build from the [Releases](https://github.com/SJ-Thanav-Kumar/Converter/releases) page:

- **macOS:** `Quarry-macOS.dmg`. Open it and drag Quarry onto Applications.
- **Windows:** `Quarry-Windows.zip`. Unzip the whole folder and run `Quarry.exe`.

The builds are not code-signed, so the first launch shows a warning:

- **macOS:** right-click the app, choose **Open**, then **Open** again (or run `xattr -cr /Applications/Quarry.app`).
- **Windows:** SmartScreen shows "Windows protected your PC". Click **More info**, then **Run anyway**.

### Video needs FFmpeg

FFmpeg is not bundled. Install it once and the video options appear (the top right of the window shows `VIDEO ON`):

- **macOS:** `brew install ffmpeg`
- **Windows:** `winget install ffmpeg`

Without FFmpeg the app still converts images (`VIDEO OFF (NO FFMPEG)`).

## Run from source

Requires Python 3.9 or newer.

```bash
git clone https://github.com/SJ-Thanav-Kumar/Converter.git
cd Converter
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[desktop]"
python3 desktop/main.py
```

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

Tests that need FFmpeg or PySide6 skip themselves when the tool is missing. `pytest -q tests` runs the same suite.

## Project layout

```text
core/       the converter engine (no GUI): format detection, ConversionManager, Pillow and FFmpeg backends
desktop/    the PySide6 app: window, widgets, theme, worker thread, settings
resources/  fonts bundled with the app (Inter Bold)
tests/      unit, integration (real sample files) and validation (lossy quality) tests
examples/   small demo scripts and sample files
```

`desktop/` only talks to `core/` through `ConversionManager`, so the engine could be reused by another front end.

## Build the app yourself

```bash
pip install pyinstaller

# macOS
pyinstaller --noconfirm --windowed --name Quarry --paths . --collect-all pillow_heif \
  --add-data "resources/fonts:resources/fonts" desktop/main.py
mkdir dmgroot && cp -R dist/Quarry.app dmgroot/ && ln -s /Applications dmgroot/Applications
hdiutil create -volname Quarry -srcfolder dmgroot -ov -format UDZO Quarry-macOS.dmg
```

```powershell
# Windows (PowerShell): the source;destination separator is a semicolon
pyinstaller --noconfirm --windowed --name Quarry --paths . --collect-all pillow_heif `
  --add-data "resources/fonts;resources/fonts" desktop\main.py
Compress-Archive -Path dist\Quarry -DestinationPath Quarry-Windows.zip
```

`--collect-all pillow_heif` packs the HEIC libraries and `--add-data` packs the font. PyInstaller cannot cross-compile, so build each platform on its own system.

**Releases are automatic:** pushing a tag that starts with `v` (for example `git tag v0.1.1 && git push origin v0.1.1`) runs `.github/workflows/releases.yml`. It builds the macOS and Windows packages in parallel and publishes both files to a single GitHub Release.

## Licenses

- **Quarry** is released under the [MIT License](LICENSE).
- **Inter** (the bundled font) is licensed under the SIL Open Font License 1.1: see [`resources/fonts/OFL.txt`](resources/fonts/OFL.txt).
- **Pillow** (BSD-style), **PySide6 / Qt** (LGPL) and **pillow-heif** are used as libraries. The HEIC encoder that ships with pillow-heif's wheels is GPL-licensed (x265); check its page if you redistribute a build commercially.
- **FFmpeg** is a separate program that you install yourself. It is not part of this repository or the downloads.

## About

Started as a learning project to understand how image and video formats and compression work, then turned into a real application on top of Pillow and FFmpeg.
