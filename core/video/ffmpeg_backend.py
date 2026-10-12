from __future__ import annotations
import json, shutil, subprocess, tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from core.conversion.errors import ConversionCancelledError, ConversionFailedError
from core.conversion.models import CancellationToken, ConversionBackend, ProgressCallback

VIDEO_FORMATS = {"mp4", "mov", "mkv"}

#codecs that each container can hold, so no need to reenocode
#none means "accepts anything". This is a deliberately safe, simplified subset
COPYABLE = {
    "mp4": {"video": {"h264", "hevc", "av1", "mpeg4"}, 
            "audio": {"aac", "mp3", "ac3", "alac"}
            },
    "mov": {"video": {"h264", "hevc", "mpeg4", "prores", "mjpeg"}, 
            "audio": {"aac", "alac", "mp3", "pcm_s16le", "pcm_s24le"}
            },
    "mkv": {"video": None, "audio": None},
}

VIDEO_ENCODERS = {"h264": ("libx264", 23), "h265": ("libx265", 28)}

def probe_media(path: Path) -> Dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise ConversionFailedError("ffprobe was not found. Install FFmpeg and make sure it is on PATH.")

    try:
        done = subprocess.run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], 
                              capture_output= True, text = True, timeout= 30,)
    except subprocess.TimeoutExpired as exc:
        raise ConversionFailedError(f"ffprobe timed out reading {path.name}") from exc
    if done.returncode != 0:
        raise ConversionFailedError(f"Not a readable media file: {path.name}")
    
    return json.loads(done.stdout)

def _codecs(info: Dict[str, Any], kind: str) -> List[str]:
    #codec names of all streams of one kind ("video" or "audio")
    arr = []
    for s in info.get("streams", []):
        if s.get("codec_type") == kind:
            arr.append(s.get("codec_name", ""))

    return arr

def _can_copy(container: str, kind: str, codecs: List[str]) -> bool:
    allowed = COPYABLE[container][kind]
    return allowed is None or all(codec in allowed for codec in codecs)

def build_command(
        ffmpeg: str, source: Path, destination: Path, target_format: str,
        info: Dict[str, Any], options: Dict[str, Any]
) -> Tuple[List[str], str]:
    #return argv_list, "remux" or "transcode"
    #each stream copied when it can be
    wanted = options.get("video_codec")     #None, h264, or h265

    if wanted is not None and wanted not in VIDEO_ENCODERS:
        raise ConversionFailedError(f"Unsupported video codec option: {wanted!r}")

    copy_video = wanted is None and _can_copy(target_format, "video", _codecs(info, "video")[:1])
    copy_audio = _can_copy(target_format, "audio", _codecs(info, "audio"))

    command = [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
        "-i", str(source),
        "-map", "0:v:0", "-map", "0:a?",             #first video stream+any audio streams
    ]

    if copy_video:
        command += ["-c:v", "copy"]
    else:
        encoder, default_crf = VIDEO_ENCODERS[wanted or "h264"]
        command += ["-c:v", encoder, "-crf", str(options.get("crf", default_crf)),
                    "-preset", "medium", "-pix_fmt", "yuv420p"]
        
        if encoder == "libx265" and target_format in ("mp4", "mov"):
            command += ["-tag:v", "hvc1"]            #lets apple players open HEVC

    command += ["-c:a", "copy"] if copy_audio else ["-c:a", "aac", "-b:a", "160k"]

    if target_format in ("mp4", "mov"):
        command += ["-movflags", "+faststart"] #put index(moov) in front

    command += ["-progress", "pipe:1", "-nostats", str(destination)]
    mode = "remux" if (copy_video and copy_audio) else "transcode"
    return command, mode

class FFmpegBackend(ConversionBackend):
    name = "FFmpeg"

    def supported_conversions(self) -> Set[Tuple[str, str]]:
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            return set()                             #no FFmpeg: no video options
        return {(a, b) for a in VIDEO_FORMATS for b in VIDEO_FORMATS}

    def convert(
        self,
        source: Path,
        destination: Path,
        source_format: str,
        target_format: str,
        progress: ProgressCallback,
        cancel: CancellationToken,
        options: Dict[str, Any],
    ) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise ConversionFailedError("FFmpeg was not found. Install it and make sure it is on PATH.")

        info = probe_media(source)
        if not _codecs(info, "video"):
            raise ConversionFailedError(f"{source.name} has no video stream")

        duration = float(info.get("format", {}).get("duration") or 0)

        command, mode = build_command(ffmpeg, source.resolve(),
                                      destination.resolve(), target_format, info, options)
        verb = "Remuxing" if mode == "remux" else "Transcoding"
        progress(0.0, f"{verb} {source.name}")
        self._run(command, duration, progress, cancel)


    @staticmethod
    def _run(command: List[str], duration: float,
                progress: ProgressCallback, cancel: CancellationToken) ->None:
        with tempfile.TemporaryFile() as error_log:
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=error_log, text=True) as process:
                try:
                    #With "-progress pipe:1" FFmpeg prints key=value lines almost twice a second
                    for line in process.stdout:
                        if cancel.cancelled:
                            process.terminate()
                            raise ConversionCancelledError("Conversion cancelled")
                        key, _, value = line.strip().partition("=")

                        if key == "out_time_us" and value.isdigit() and duration > 0:
                            done = int(value) / 1_000_000 / duration
                            progress(min(done, 0.99), "Converting")
                    return_code = process.wait()

                finally:
                    if process.poll() is None:       #cancelled or crashed: kill ffmpeg so it doesnt keep running
                        process.kill()

            if return_code != 0:
                error_log.seek(0)
                lines = error_log.read().decode(errors="replace").strip().splitlines()
                raise ConversionFailedError("FFmpeg failed: " + (lines[-1] if lines else f"exit code {return_code}"))