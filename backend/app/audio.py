from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import settings


class AudioConversionError(RuntimeError):
    pass


def _bundled_ffmpeg() -> Path | None:
    candidate = settings.resources_dir / "bin" / "ffmpeg"
    if candidate.exists():
        return candidate
    return None


def ensure_ffmpeg() -> str:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        bundled = _bundled_ffmpeg()
        if bundled is not None:
            ffmpeg_path = str(bundled)
    if not ffmpeg_path:
        raise AudioConversionError(
            "ffmpeg is required to transcode audio. Install via 'brew install ffmpeg'."
        )
    return ffmpeg_path


def convert_to_pcm16_mono(src: Path, dest: Path) -> None:
    ffmpeg = ensure_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(dest),
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        raise AudioConversionError(result.stdout)
