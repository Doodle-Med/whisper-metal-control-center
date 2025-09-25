from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


@dataclass
class CloudTranscriptionResult:
    text: str
    language: Optional[str]
    segments: List[Dict[str, Any]]


class CloudTranscriptionError(RuntimeError):
    pass


def transcribe_openai(
    audio_path: Path,
    *,
    api_key: str,
    model: str = "whisper-1",
    language: str | None = None,
    translate: bool = False,
) -> CloudTranscriptionResult:
    url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}

    mime, _ = mimetypes.guess_type(audio_path)
    if mime is None:
        mime = "application/octet-stream"

    with audio_path.open("rb") as fh:
        files = {"file": (audio_path.name, fh, mime)}
        data: Dict[str, Any] = {"model": model, "response_format": "verbose_json"}
        if language and language != "auto":
            data["language"] = language
        if translate:
            data["translate"] = True

        response = requests.post(url, headers=headers, files=files, data=data, timeout=600)

    if response.status_code >= 400:
        raise CloudTranscriptionError(
            f"OpenAI transcription failed ({response.status_code}): {response.text}"
        )

    payload = response.json()
    return CloudTranscriptionResult(
        text=payload.get("text", ""),
        language=payload.get("language", language),
        segments=payload.get("segments", []),
    )


def transcribe_gemini(*_args: Any, **_kwargs: Any) -> CloudTranscriptionResult:
    raise CloudTranscriptionError(
        "Gemini transcription is not yet implemented. Provide a custom cloud endpoint or use OpenAI."
    )
