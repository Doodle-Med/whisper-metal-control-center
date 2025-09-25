from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class AudioConversionError(RuntimeError):
    pass


def ensure_ffmpeg() -> str:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise AudioConversionError(
            "ffmpeg is required to transcode audio. Install via 'brew install ffmpeg'."
        )
    return ffmpeg_path


def convert_to_pcm16_mono(src: Path, dest: Path) -> None:
    ffmpeg = ensure_ffmpeg()
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
