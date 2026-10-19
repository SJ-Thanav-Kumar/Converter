# Quarry

A local desktop converter for images and video, built with Python, Pillow, FFmpeg and PySide6. Everything runs on your machine. Promise!

## About

This little side project started as me just getting wildly curious with file formats. Little did I know how deep this shit hole went, if only i could have the time i lost back....
I was also rather very pissed at all the online converters out there with their clunky ui and ads being shoved in your face every 5 seconds. So i decided, hey why not, im learning it, might as well make something out of it. So here we are!

<!-- TODO: add a screenshot or short GIF of the app here -->

## Features

- **Images:** PNG, JPEG, BMP, GIF, WebP, AVIF, TIFF and HEIC, any to any. A quality slider for the lossy formats (JPEG, WebP, AVIF, HEIC).
- **Video:** MP4, MOV and MKV. Fast remux when only the container changes, re-encode (H.264 / H.265) when it has to.
- **GIF and video:** video to GIF (choose frame rate, width and maximum length) and GIF back to MP4 or MOV.
- **Animations:** animated GIF, WebP and AVIF keep their frames and timing when converted between each other.
- **Compress mode:** smaller files with a quality slider (images) or a CRF value and codec (video).
- **Format detection by content:** a file is recognised by its first bytes, not its extension(cool huh!).

## Download

To get the app, download the build from [Releases](https://github.com/SJ-Thanav-Kumar/Converter/releases)

Just so you know, the app is gonna show you a warning on either platform, its safe i promise. I'm too broke to afford a developer license....

### Video needs FFmpeg

Unfortunately, FFmpeg is not bundled with the .dmg nor .exe, you're gonna have to download FFmpeg on your computer on your own. Heres how:

- **macOS:** `brew install ffmpeg`
- **Windows:** `winget install ffmpeg`

If you do have FFmpeg installed, the right corner of the app should display this: `VIDEO ON`.
FFmpeg is NOT required for image conversion and compression!

## If you're a tech wiz and wanna run from source:

You gotta have Python 3.9 or newer

```bash
git clone https://github.com/SJ-Thanav-Kumar/Converter.git
cd Converter
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[desktop]"
python3 desktop/main.py
```

## Project layout

```text
core/       the converter engine (no GUI): format detection, ConversionManager, Pillow and FFmpeg backends
desktop/    the PySide6 app: window, widgets, theme, worker thread, settings
resources/  fonts bundled with the app (Inter Bold)
tests/      unit, integration (real sample files) and validation (lossy quality) tests
examples/   small demo scripts and sample files
```

`desktop/` only talks to `core/` through `ConversionManager`, so the engine could be reused by another front end!

## Licenses(apparently im required to tell you about this?)

- **Quarry** is released under the [MIT License](LICENSE).
- **Inter** (the bundled font) is licensed under the SIL Open Font License 1.1: see [`resources/fonts/OFL.txt`](resources/fonts/OFL.txt).
- **Pillow** (BSD-style), **PySide6 / Qt** (LGPL) and **pillow-heif** are used as libraries. The HEIC encoder that ships with pillow-heif's wheels is GPL-licensed (x265); check its page if you redistribute a build commercially.
- **FFmpeg** is a separate program that you install yourself. It is not part of this repository or the downloads.
