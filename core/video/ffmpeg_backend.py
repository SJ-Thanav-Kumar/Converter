from __future__ import annotations
import json, shutil, subprocess, tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from core.conversion.errors import ConversionCancelledError, ConversionFailedError
from core.conversion.models import CancellationToken, ConversionBackend, ProgressCallback

#container ids this backend handles
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

#containers that can go to and from gif. mkv is left out on purpose
GIF_VIDEO_FORMATS = {"mp4", "mov"}

#gif defaults: a gif is huge, so it is made small and low-fps unless the caller asks otherwise
GIF_FPS = 12
GIF_WIDTH = 480

#mapping option names to ffmpegs encoder name and a default crf(const rate factor)
VIDEO_ENCODERS = {"h264": ("libx264", 23), "h265": ("libx265", 28)}


#asks ffprobe about the file given
def probe_media(path: Path) -> Dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise ConversionFailedError("ffprobe was not found. Install FFmpeg and make sure it is on PATH.")

    #subprocess collects its output as text, gives up after given timeout
    try:
        done = subprocess.run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], 
                              capture_output= True, text = True, timeout= 30,)
    except subprocess.TimeoutExpired as exc:
        raise ConversionFailedError(f"ffprobe timed out reading {path.name}") from exc

    #checks if the media file is readable
    if done.returncode != 0:
        raise ConversionFailedError(f"Not a readable media file: {path.name}")

    return json.loads(done.stdout)


'''a list comprehension: loop over every stream, keep whose codec_type
matches kind, collect their codec_name'''
def _codecs(info: Dict[str, Any], kind: str) -> List[str]:
    #codec names of all streams of one kind ("video" or "audio")
    arr = []
    for s in info.get("streams", []):
        if s.get("codec_type") == kind:
            arr.append(s.get("codec_name", ""))

    return arr


#either anything is allowed, or every codec in the list must be in the set
#a video with audio is fine
def _can_copy(container: str, kind: str, codecs: List[str]) -> bool:
    allowed = COPYABLE[container][kind]
    return allowed is None or all(codec in allowed for codec in codecs)


#says if its remux or transcode, return argv_list, "remux" or "transcode"
#each stream copied when it can be
def build_command(
        ffmpeg: str, source: Path, destination: Path, target_format: str,
        info: Dict[str, Any], options: Dict[str, Any]
) -> Tuple[List[str], str]:

    wanted = options.get("video_codec")     #users option: None, h264, or h265

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
        command += ["-c:v", "copy"] #copy video
    else:
        encoder, default_crf = VIDEO_ENCODERS[wanted or "h264"]
        command += ["-c:v", encoder, "-crf", str(options.get("crf", default_crf)),
                    "-preset", "medium", "-pix_fmt", "yuv420p"]                         #if not just copy, then we get the crf to to override the quality
        
        if encoder == "libx265" and target_format in ("mp4", "mov"):
            command += ["-tag:v", "hvc1"]            #lets apple players open HEVC

    command += ["-c:a", "copy"] if copy_audio else ["-c:a", "aac", "-b:a", "160k"]      #self explanatory

    if target_format in ("mp4", "mov"):                 #only these containers have faststart
        command += ["-movflags", "+faststart"] #put index(moov) in front

    command += ["-progress", "pipe:1", "-nostats", str(destination)]
    mode = "remux" if (copy_video and copy_audio) else "transcode"

    return command, mode



#gif is not a video container, so it gets its own command builder
#returns the same (argv_list, mode) pair as build_command. mode is "gif" here
def build_gif_command(
        ffmpeg: str, source: Path, destination: Path, source_format: str, target_format: str,
        options: Dict[str, Any]
) -> Tuple[List[str], str]:

    command = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-i", str(source), "-an"]   #-an: gifs have no sound

    if target_format == "gif":
        fps = int(options.get("gif_fps", GIF_FPS))
        width = int(options.get("gif_width", GIF_WIDTH))
        seconds = float(options.get("gif_seconds", 0))         #0 = the whole video
        if fps < 1 or width < 16 or seconds < 0:
            raise ConversionFailedError("gif_fps must be at least 1, gif_width at least 16 and gif_seconds not negative")
        if seconds > 0:
            command += ["-t", str(seconds)]                    #stop after this many seconds. Placed after -i so it limits the output

        #a gif can only hold 256 colours. paletteGEN picks the best 256 for this clip,
        #paletteUSE maps every frame onto them. Without this the colours look dirty.
        #min(width, iw) so a small video is never stretched bigger
        command += ["-vf", f"fps={fps},scale='min({width},iw)':-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse",
                    "-loop", "0"]                                #0 = loop forever
    else:
        wanted = options.get("video_codec") or "h264"
        if wanted not in VIDEO_ENCODERS:
            raise ConversionFailedError(f"Unsupported video codec option: {wanted!r}")
        encoder, default_crf = VIDEO_ENCODERS[wanted]

        #h264/h265 with yuv420p need even width and height, gifs often are odd. so round down to even
        command += ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                    "-c:v", encoder, "-crf", str(options.get("crf", default_crf)),
                    "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        if encoder == "libx265":
            command += ["-tag:v", "hvc1"]

    command += ["-progress", "pipe:1", "-nostats", str(destination)]
    return command, "gif"


class FFmpegBackend(ConversionBackend):
    name = "FFmpeg"

    #if either tool is missing, return an empty set so managers target is empty
    def supported_conversions(self) -> Set[Tuple[str, str]]:
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            return set()                             #no FFmpeg: so no video options in ui
        pairs = {(a, b) for a in VIDEO_FORMATS for b in VIDEO_FORMATS}
        for container in GIF_VIDEO_FORMATS:        #gif both ways: video -> gif and gif -> video
            pairs |= {(container, "gif"), ("gif", container)}
        return pairs

    #orchestration
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
        #check if ffmpeg exists
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise ConversionFailedError("FFmpeg was not found. Install it and make sure it is on PATH.")

        info = probe_media(source)
        if not _codecs(info, "video"):
            raise ConversionFailedError(f"{source.name} has no video stream")

        #handles missing keys and None. Needed to turn seconds encoded to %
        duration = float(info.get("format", {}).get("duration") or 0)

        if "gif" in (source_format, target_format):
            command, mode = build_gif_command(ffmpeg, source.resolve(), destination.resolve(),
                                              source_format, target_format, options)
        else:
            command, mode = build_command(ffmpeg, source.resolve(),
                                          destination.resolve(), target_format, info, options)
        verb = {"remux": "Remuxing", "transcode": "Transcoding", "gif": "Converting"}[mode]
        progress(0.0, f"{verb} {source.name}")

        self._run(command, duration, progress, cancel)


    @staticmethod
    #runs ffmpeg and monitor
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

                        #splits into key:value
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