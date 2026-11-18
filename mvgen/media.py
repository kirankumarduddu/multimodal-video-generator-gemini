"""ffmpeg helpers (the binary comes from imageio-ffmpeg, so nothing else to install)."""
from __future__ import annotations

import pathlib
import re
import subprocess
import wave

import imageio_ffmpeg

from .project import FPS

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def run(args: list[str]) -> None:
    result = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()[-2000:]}")


def duration(path: pathlib.Path) -> float:
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as handle:
            return handle.getnframes() / handle.getframerate()
    probe = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    match = re.search(r"Duration: (\d+):(\d+):([\d.]+)", probe.stderr)
    if not match:
        raise RuntimeError(f"cannot read the duration of {path}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def write_wav(path: pathlib.Path, pcm: bytes, rate: int = 24000) -> float:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)
    return len(pcm) / (2 * rate)


def silence(path: pathlib.Path, seconds: float) -> None:
    write_wav(path, b"\x00\x00" * int(24000 * seconds))


def animatic(source: pathlib.Path | None, out: pathlib.Path, seconds: float, size: tuple[int, int],
             color: str = "#222222") -> None:
    """A slow push-in on a still (the keyframe), or a plain brand-colored clip when there is no still."""
    width, height = size
    frames = max(1, round(seconds * FPS))
    if source and source.exists():
        zoom = f"zoompan=z='min(1+0.10*on/{frames},1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={FPS}"
        run(["-loop", "1", "-i", str(source), "-vf",
             f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,crop={width * 2}:{height * 2},{zoom},format=yuv420p",
             "-frames:v", str(frames), "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", str(out)])
    else:
        run(["-f", "lavfi", "-i", f"color=c=0x{color.lstrip('#')}:s={width}x{height}:r={FPS}:d={seconds:.2f}",
             "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", str(out)])
