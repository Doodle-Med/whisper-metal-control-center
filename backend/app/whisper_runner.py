from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

from .config import settings
from .postprocess import apply_cleaners

ProgressCallback = Callable[[int], Awaitable[None]]


FORMAT_FLAGS = {
    "json": "-oj",
    "json_full": "-ojf",
    "txt": "-otxt",
    "srt": "-osrt",
    "vtt": "-ovtt",
    "csv": "-ocsv",
    "words": "-owts",
    "lrc": "-olrc",
}


@dataclass
class TranscriptionOptions:
    model_path: Path
    language: str = "auto"
    translate: bool = False
    threads: int = settings.whisper_threads
    temperature: float | None = None
    temperature_inc: float | None = None
    beam_size: int | None = None
    best_of: int | None = None
    no_timestamps: bool = False
    vad: bool = False
    vad_model: Path | None = None
    diarize: bool = False
    tinydiarize: bool = False
    initial_prompt: str | None = None
    suppress_regex: str | None = None
    extra_args: list[str] = field(default_factory=list)
    output_formats: list[str] = field(default_factory=lambda: list(settings.default_output_formats))
    cleaners: list[str] = field(default_factory=list)
    detect_language: bool = False


class WhisperRuntimeError(RuntimeError):
    pass


class WhisperRunner:
    def __init__(self, binary: Path) -> None:
        self.binary = binary
        if not self.binary.exists():
            raise FileNotFoundError(
                f"whisper.cpp binary not found at {self.binary}. Run scripts/setup_whisper_cpp.sh first."
            )
        if not os.access(self.binary, os.X_OK):
            raise PermissionError(f"whisper.cpp binary not executable: {self.binary}")

    async def transcribe(
        self,
        audio_path: Path,
        *,
        options: TranscriptionOptions,
        output_dir: Path,
        progress_cb: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        if not options.model_path.exists():
            raise FileNotFoundError(f"Whisper model not found: {options.model_path}")

        output_dir.mkdir(parents=True, exist_ok=True)
        output_base = output_dir / "transcript"

        cmd = self._build_command(audio_path, options, output_base)

        env = os.environ.copy()
        metal_root = self.binary.parent
        ggml_metal = settings.whisper_root / "ggml-metal"
        if ggml_metal.exists():
            env.setdefault("GGML_METAL_PATH_RESOURCES", str(ggml_metal))
        env.setdefault("GGML_METAL_PATH_BIN", str(metal_root))

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        stderr_task = asyncio.create_task(
            self._consume_stderr(process.stderr, progress_cb)
        )

        stdout_data = await process.stdout.read() if process.stdout else b""
        return_code = await process.wait()
        await stderr_task

        if return_code != 0:
            raise WhisperRuntimeError(stdout_data.decode("utf-8", "ignore"))

        json_path = output_base.with_suffix(".json")
        if not json_path.exists():
            raise WhisperRuntimeError(
                "whisper.cpp did not produce a JSON transcript."
            )

        with json_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        normalized = self._normalize_output(raw, options)
        normalized["artifacts"] = self._collect_artifacts(output_base, options.output_formats)
        return normalized

    async def _consume_stderr(
        self,
        stream: asyncio.StreamReader | None,
        progress_cb: ProgressCallback | None,
    ) -> None:
        if stream is None:
            return
        async for raw_line in stream:
            line = raw_line.decode("utf-8", "ignore").strip()
            if progress_cb and "progress =" in line:
                try:
                    percent = int(line.split("progress =")[-1].strip().rstrip("%"))
                except ValueError:
                    continue
                await progress_cb(percent)

    def _build_command(
        self,
        audio_path: Path,
        options: TranscriptionOptions,
        output_base: Path,
    ) -> list[str]:
        cmd = [
            str(self.binary),
            "-m",
            str(options.model_path),
            "-f",
            str(audio_path),
            "-t",
            str(options.threads),
            "-l",
            options.language,
            "-of",
            str(output_base),
            "-pp",
        ]

        requested_formats = set(fmt.lower() for fmt in options.output_formats)
        for fmt in requested_formats:
            flag = FORMAT_FLAGS.get(fmt)
            if flag:
                cmd.append(flag)
        if "json" not in requested_formats and "json_full" not in requested_formats:
            cmd.append("-oj")

        if options.translate:
            cmd.append("-tr")
        if options.no_timestamps:
            cmd.append("-nt")
        if options.beam_size and options.beam_size > 1:
            cmd.extend(["-bs", str(options.beam_size)])
        if options.best_of and options.best_of > 1:
            cmd.extend(["-bo", str(options.best_of)])
        if options.temperature is not None:
            cmd.extend(["-tp", f"{options.temperature:.2f}"])
        if options.temperature_inc is not None:
            cmd.extend(["-tpi", f"{options.temperature_inc:.2f}"])
        if options.vad:
            cmd.append("--vad")
            if options.vad_model:
                cmd.extend(["-vm", str(options.vad_model)])
        if options.diarize:
            cmd.append("-di")
        if options.tinydiarize:
            cmd.append("-tdrz")
        if options.initial_prompt:
            cmd.extend(["--prompt", options.initial_prompt])
        if options.suppress_regex:
            cmd.extend(["--suppress-regex", options.suppress_regex])
        if options.detect_language:
            cmd.append("-dl")

        cmd.extend(options.extra_args)
        cmd.extend(settings.whisper_extra_args)
        return cmd

    def _normalize_output(
        self, raw: dict[str, Any], options: TranscriptionOptions
    ) -> dict[str, Any]:
        segments: list[dict[str, Any]] = []

        if isinstance(raw.get("transcription"), list):
            for idx, item in enumerate(raw["transcription"]):
                text = (item.get("text") or "").strip()
                offsets = item.get("offsets") or {}
                start = offsets.get("from", 0) / 1000 if offsets.get("from") else None
                end = offsets.get("to", 0) / 1000 if offsets.get("to") else None
                if start is None and isinstance(item.get("timestamps"), dict):
                    start = self._parse_timecode(item["timestamps"].get("from"))
                    end = self._parse_timecode(item["timestamps"].get("to"))
                segments.append(
                    {
                        "id": item.get("id", idx),
                        "start": start,
                        "end": end,
                        "text": text,
                    }
                )
            language = (
                raw.get("result", {}).get("language")
                or raw.get("params", {}).get("language")
                or options.language
            )
            text = " ".join(segment["text"] for segment in segments).strip()
        else:
            raw_segments = raw.get("segments") if isinstance(raw, dict) else None
            if isinstance(raw_segments, list):
                for item in raw_segments:
                    segments.append(
                        {
                            "id": item.get("id"),
                            "start": item.get("start"),
                            "end": item.get("end"),
                            "text": (item.get("text") or "").strip(),
                        }
                    )
            language = (
                raw.get("language")
                or raw.get("result", {}).get("language")
                or raw.get("params", {}).get("language")
                or options.language
            )
            text = raw.get("text") or " ".join(seg["text"] for seg in segments).strip()

        if options.cleaners:
            text = apply_cleaners(text, options.cleaners)
            for segment in segments:
                segment["text"] = apply_cleaners(segment.get("text", ""), options.cleaners)

        return {
            "language": language,
            "text": text,
            "segments": segments,
        }

    def _collect_artifacts(self, output_base: Path, formats: Iterable[str]) -> dict[str, Path]:
        artifacts: dict[str, Path] = {}
        for fmt in formats:
            candidate = output_base.with_suffix(f".{fmt}")
            if candidate.exists():
                artifacts[fmt] = candidate
        # JSON is always useful for API consumers
        json_path = output_base.with_suffix(".json")
        if json_path.exists():
            artifacts.setdefault("json", json_path)
        return artifacts

    @staticmethod
    def _parse_timecode(value: Any) -> float | None:
        if not isinstance(value, str):
            return None
        try:
            hours, minutes, rest = value.split(":")
            seconds, millis = rest.split(",")
            total_ms = (
                int(hours) * 3600 * 1000
                + int(minutes) * 60 * 1000
                + int(seconds) * 1000
                + int(millis)
            )
            return total_ms / 1000.0
        except (ValueError, AttributeError):
            return None


runner = WhisperRunner(settings.binary_path)
