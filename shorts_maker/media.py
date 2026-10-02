"""ffmpeg discovery, probing and subprocess helpers."""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Tuple


class MediaError(RuntimeError):
    """Raised when ffmpeg is missing or a media operation fails."""


def find_ffmpeg() -> str:
    """Return a usable ffmpeg executable.

    Order: $FFMPEG_BINARY, ffmpeg on PATH, then the static build bundled with
    the ``imageio-ffmpeg`` package (so ``pip install`` alone is enough).
    """
    env = os.environ.get("FFMPEG_BINARY")
    if env and Path(env).is_file():
        return env
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - depends on the environment
        raise MediaError(
            "ffmpeg was not found. Install it from https://ffmpeg.org or run: pip install imageio-ffmpeg"
        ) from exc


def run_ffmpeg(
    args: Sequence[object],
    *,
    cwd=None,
    loglevel: str = "error",
) -> subprocess.CompletedProcess:
    """Run ffmpeg and return the finished process (stdout/stderr are bytes)."""
    cmd = [find_ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", loglevel] + [str(a) for a in args]
    proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip()[-2500:]
        raise MediaError(f"ffmpeg failed (exit {proc.returncode}):\n{tail}")
    return proc


@dataclass
class MediaInfo:
    duration: float
    width: int  # display size: rotation metadata and pixel aspect ratio already applied
    height: int
    fps: float
    has_audio: bool

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 16 / 9


def _display_size(path: Path) -> Tuple[int, int]:
    """Size of the first frame exactly as ffmpeg will see it (auto-rotation and SAR applied)."""
    proc = run_ffmpeg(
        ["-i", path, "-vf", "scale=trunc(iw*sar):ih", "-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "-"]
    )
    data = proc.stdout
    if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
        raise MediaError(f"Could not decode a video frame from {path}")
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def probe(path) -> MediaInfo:
    """Read duration / size / fps / audio presence of a media file."""
    path = Path(path)
    if not path.is_file():
        raise MediaError(f"File not found: {path}")
    import av  # PyAV is installed together with faster-whisper

    try:
        with av.open(str(path)) as container:
            video = next((s for s in container.streams if s.type == "video"), None)
            audio = next((s for s in container.streams if s.type == "audio"), None)
            if video is None:
                raise MediaError(f"No video stream found in {path}")
            if container.duration:
                duration = float(container.duration) / av.time_base
            elif video.duration and video.time_base:
                duration = float(video.duration * video.time_base)
            else:
                duration = 0.0
            rate = video.average_rate or getattr(video, "guessed_rate", None)
            fps = float(rate) if rate else 30.0
            has_audio = audio is not None
    except MediaError:
        raise
    except Exception as exc:
        raise MediaError(f"Cannot read {path}: {exc}") from exc

    width, height = _display_size(path)
    return MediaInfo(duration=duration, width=width, height=height, fps=fps, has_audio=has_audio)
