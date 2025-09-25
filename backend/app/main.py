from __future__ import annotations

import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import audio
from .cloud import CloudTranscriptionError, transcribe_gemini, transcribe_openai
from .config import settings
from .jobs import job_manager
from .models import CapabilityResponse, JobDetail, JobStatus, JobSummary, ModelInfo
from .postprocess import apply_cleaners
from .whisper_runner import TranscriptionOptions, WhisperRuntimeError, runner

app = FastAPI(title="Whisper Metal Control Center", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = settings.storage_dir / "uploads"
JOB_DIR = settings.storage_dir / "jobs"
job_tasks: dict[str, asyncio.Task] = {}
job_secrets: dict[str, Dict[str, Optional[str]]] = {}
job_semaphore = asyncio.Semaphore(max(1, settings.max_concurrent_jobs))


def parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid float value: {value}")


def parse_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid integer value: {value}")


def parse_list(csv: str | None) -> list[str]:
    if not csv:
        return []
    return [item.strip() for item in csv.split(",") if item.strip()]


def resolve_model_path(name: str | None) -> Path:
    if not name:
        return settings.whisper_model
    path = Path(name)
    if not path.is_absolute():
        path = settings.models_dir / path
    return path.resolve()


def resolve_optional_path(name: str | None) -> Optional[Path]:
    if not name:
        return None
    path = Path(name)
    if not path.is_absolute():
        path = settings.models_dir / path
    return path.resolve()


@app.on_event("startup")
async def startup_event() -> None:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    JOB_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/api/models", response_model=List[ModelInfo])
async def list_models() -> List[ModelInfo]:
    models: list[ModelInfo] = []
    if not settings.models_dir.exists():
        return models
    for path in sorted(settings.models_dir.glob("*.bin")):
        size_mb = round(path.stat().st_size / (1024 * 1024), 2)
        quant = None
        if "q" in path.stem:
            parts = path.stem.split("-")
            quant = parts[-1] if parts else None
        models.append(
            ModelInfo(
                name=path.name,
                path=str(path.resolve()),
                size_mb=size_mb,
                quantization=quant,
            )
        )
    return models


@app.get("/api/capabilities", response_model=CapabilityResponse)
async def capabilities() -> CapabilityResponse:
    return CapabilityResponse(
        default_threads=settings.whisper_threads,
        max_concurrent_jobs=settings.max_concurrent_jobs,
        allow_cloud_offload=settings.allow_cloud_offload,
        available_models=await list_models(),
        default_formats=settings.default_output_formats,
    )


@app.post("/api/jobs")
async def create_jobs(
    request: Request,
    files: List[UploadFile] = File(...),
    engine: str = Form("local"),
    model: str = Form(""),
    language: str = Form("auto"),
    translate: str = Form("false"),
    temperature: str = Form(""),
    temperature_inc: str = Form(""),
    beam_size: str = Form(""),
    best_of: str = Form(""),
    no_timestamps: str = Form("false"),
    vad: str = Form("false"),
    vad_model: str = Form(""),
    diarize: str = Form("false"),
    tinydiarize: str = Form("false"),
    initial_prompt: str = Form(""),
    suppress_regex: str = Form(""),
    cleaners: str = Form(""),
    output_formats: str = Form("json,txt,srt"),
    detect_language: str = Form("false"),
    cloud_provider: str = Form("openai"),
    cloud_model: str = Form("whisper-1"),
    cloud_api_key: str | None = Form(None),
) -> JSONResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    translate_flag = parse_bool(translate)
    no_timestamps_flag = parse_bool(no_timestamps)
    vad_flag = parse_bool(vad)
    diarize_flag = parse_bool(diarize)
    tinydiarize_flag = parse_bool(tinydiarize)
    detect_language_flag = parse_bool(detect_language)

    temperature_value = parse_float(temperature)
    temperature_inc_value = parse_float(temperature_inc)
    beam_size_value = parse_int(beam_size)
    best_of_value = parse_int(best_of)

    model_path = resolve_model_path(model)
    vad_model_path = resolve_optional_path(vad_model)

    requested_formats = parse_list(output_formats) or settings.default_output_formats
    requested_cleaners = parse_list(cleaners)

    jobs_created: list[JobSummary] = []

    for file in files:
        if not file.filename:
            raise HTTPException(status_code=400, detail="File missing filename")

        job_id = uuid4().hex
        safe_name = Path(file.filename).name
        upload_dir = UPLOAD_DIR / job_id
        output_dir = JOB_DIR / job_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        original_path = upload_dir / safe_name
        await _save_upload(file, original_path)

        params = {
            "model": str(model_path),
            "language": language,
            "translate": translate_flag,
            "temperature": temperature_value,
            "temperature_inc": temperature_inc_value,
            "beam_size": beam_size_value,
            "best_of": best_of_value,
            "no_timestamps": no_timestamps_flag,
            "vad": vad_flag,
            "vad_model": str(vad_model_path) if vad_model_path else None,
            "diarize": diarize_flag,
            "tinydiarize": tinydiarize_flag,
            "initial_prompt": initial_prompt,
            "suppress_regex": suppress_regex,
            "cleaners": requested_cleaners,
            "output_formats": requested_formats,
            "detect_language": detect_language_flag,
            "cloud_provider": cloud_provider,
            "cloud_model": cloud_model,
        }

        record = await job_manager.create_job(
            job_id,
            filename=safe_name,
            engine=engine,
            params=params,
            output_formats=requested_formats,
            storage_dir=output_dir,
        )

        job_secrets[job_id] = {"cloud_api_key": cloud_api_key}

        task = asyncio.create_task(
            _process_job(
                job_id=job_id,
                engine=engine,
                original_audio=original_path,
                output_dir=output_dir,
            )
        )
        job_tasks[job_id] = task

        jobs_created.append(
            JobSummary(
                id=record.id,
                filename=record.filename,
                engine=record.engine,
                status=record.status,
                progress=record.progress,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
        )

    return JSONResponse([job.model_dump(mode="json") for job in jobs_created])


async def _process_job(job_id: str, engine: str, original_audio: Path, output_dir: Path) -> None:
    try:
        async with job_semaphore:
            await job_manager.update_job(
                job_id, lambda job: setattr(job, "status", JobStatus.running)
            )

            params = job_manager.get_job(job_id).params
            await job_manager.set_progress(job_id, 5)

            if engine == "local":
                await _run_local_job(job_id, original_audio, output_dir, params)
            elif engine in {"openai", "cloud", "gemini"}:
                await _run_cloud_job(job_id, original_audio, output_dir, params)
            else:
                raise HTTPException(status_code=400, detail=f"Unknown engine: {engine}")

            await job_manager.update_job(
                job_id,
                lambda job: (
                    setattr(job, "status", JobStatus.completed),
                    setattr(job, "progress", 100),
                ),
            )
    except asyncio.CancelledError:
        await job_manager.update_job(
            job_id,
            lambda job: (
                setattr(job, "status", JobStatus.cancelled),
                setattr(job, "error", "Job cancelled"),
            ),
        )
        raise
    except (WhisperRuntimeError, audio.AudioConversionError, CloudTranscriptionError) as err:
        await job_manager.update_job(
            job_id,
            lambda job: (
                setattr(job, "status", JobStatus.failed),
                setattr(job, "error", str(err)),
            ),
        )
    except Exception as err:  # pragma: no cover - safety net
        await job_manager.update_job(
            job_id,
            lambda job: (
                setattr(job, "status", JobStatus.failed),
                setattr(job, "error", f"Unexpected error: {err}"),
            ),
        )
    finally:
        job_tasks.pop(job_id, None)
        job_secrets.pop(job_id, None)


async def _run_local_job(job_id: str, original_audio: Path, output_dir: Path, params: Dict[str, Any]) -> None:
    converted_audio = output_dir / "input.wav"
    await asyncio.get_event_loop().run_in_executor(
        None, audio.convert_to_pcm16_mono, original_audio, converted_audio
    )

    options = TranscriptionOptions(
        model_path=Path(params["model"]),
        language=params.get("language", "auto"),
        translate=params.get("translate", False),
        threads=settings.whisper_threads,
        temperature=params.get("temperature"),
        temperature_inc=params.get("temperature_inc"),
        beam_size=params.get("beam_size"),
        best_of=params.get("best_of"),
        no_timestamps=params.get("no_timestamps", False),
        vad=params.get("vad", False),
        vad_model=Path(params["vad_model"]) if params.get("vad_model") else None,
        diarize=params.get("diarize", False),
        tinydiarize=params.get("tinydiarize", False),
        initial_prompt=params.get("initial_prompt") or None,
        suppress_regex=params.get("suppress_regex") or None,
        output_formats=params.get("output_formats", settings.default_output_formats),
        cleaners=params.get("cleaners", []),
        detect_language=params.get("detect_language", False),
    )

    async def progress_cb(value: int) -> None:
        await job_manager.set_progress(job_id, value)

    result = await runner.transcribe(
        converted_audio,
        options=options,
        output_dir=output_dir,
        progress_cb=progress_cb,
    )

    downloads = {}
    for fmt, path in result.get("artifacts", {}).items():
        relative = path.relative_to(settings.storage_dir)
        url = f"/api/jobs/{job_id}/download/{fmt}?path={relative.as_posix()}"
        downloads[fmt] = url
        await job_manager.update_download(job_id, fmt, url)

    await job_manager.update_job(
        job_id,
        lambda job: setattr(
            job,
            "result",
            {
                "language": result.get("language"),
                "text": result.get("text"),
                "segments": result.get("segments"),
            },
        ),
    )


async def _run_cloud_job(job_id: str, original_audio: Path, output_dir: Path, params: Dict[str, Any]) -> None:
    provider = params.get("cloud_provider", "openai")
    api_key = job_secrets.get(job_id, {}).get("cloud_api_key") or settings.openai_api_key
    if provider == "openai" and not api_key:
        raise CloudTranscriptionError("OpenAI API key not provided")

    if provider == "openai":
        result = transcribe_openai(
            original_audio,
            api_key=api_key,
            model=params.get("cloud_model", "whisper-1"),
            language=params.get("language"),
            translate=params.get("translate", False),
        )
    elif provider == "gemini":
        result = transcribe_gemini()
    else:
        raise CloudTranscriptionError(f"Unsupported cloud provider: {provider}")

    cleaners = params.get("cleaners", [])
    text = apply_cleaners(result.text, cleaners)
    cleaned_segments = []
    for idx, segment in enumerate(result.segments or []):
        cleaned_segments.append(
            {
                "id": segment.get("id", idx),
                "start": segment.get("start"),
                "end": segment.get("end"),
                "text": apply_cleaners(segment.get("text", ""), cleaners),
            }
        )

    job_payload = {
        "language": result.language or params.get("language"),
        "text": text,
        "segments": cleaned_segments,
    }

    await _store_cloud_outputs(job_id, output_dir, job_payload, params.get("output_formats", settings.default_output_formats))

    await job_manager.update_job(
        job_id,
        lambda job: setattr(job, "result", job_payload),
    )
    await job_manager.set_progress(job_id, 100)


async def _store_cloud_outputs(
    job_id: str,
    output_dir: Path,
    payload: Dict[str, Any],
    formats: List[str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    base = output_dir / "transcript"

    (base.with_suffix(".json")).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (base.with_suffix(".txt")).write_text(payload.get("text", ""), encoding="utf-8")
    segments = payload.get("segments", [])
    _write_srt(base.with_suffix(".srt"), segments)
    if "vtt" in formats:
        _write_vtt(base.with_suffix(".vtt"), segments)

    for fmt in set(formats + ["json", "txt", "srt"]):
        candidate = base.with_suffix(f".{fmt}")
        if candidate.exists():
            relative = candidate.relative_to(settings.storage_dir)
            url = f"/api/jobs/{job_id}/download/{fmt}?path={relative.as_posix()}"
            await job_manager.update_download(job_id, fmt, url)


def _write_srt(path: Path, segments: List[Dict[str, Any]]) -> None:
    lines: list[str] = []
    for idx, seg in enumerate(segments, start=1):
        start = _format_timestamp(seg.get("start"))
        end = _format_timestamp(seg.get("end"))
        text = seg.get("text", "")
        lines.extend([str(idx), f"{start} --> {end}", text, ""]) 
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_vtt(path: Path, segments: List[Dict[str, Any]]) -> None:
    lines: list[str] = ["WEBVTT", ""]
    for seg in segments:
        start = _format_timestamp(seg.get("start")).replace(",", ".")
        end = _format_timestamp(seg.get("end")).replace(",", ".")
        text = seg.get("text", "")
        lines.extend([f"{start} --> {end}", text, ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _format_timestamp(value: Any) -> str:
    if not isinstance(value, (int, float)):
        value = 0
    milliseconds = int(round(float(value) * 1000))
    hours = milliseconds // 3_600_000
    minutes = (milliseconds % 3_600_000) // 60_000
    seconds = (milliseconds % 60_000) // 1000
    millis = milliseconds % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


async def _save_upload(file: UploadFile, destination: Path) -> None:
    with destination.open("wb") as buffer:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            buffer.write(chunk)


@app.get("/api/jobs", response_model=List[JobDetail])
async def list_jobs_endpoint() -> List[JobDetail]:
    results: list[JobDetail] = []
    for job in job_manager.list_jobs():
        data = job.to_dict()
        results.append(
            JobDetail(
                id=data["id"],
                filename=data["filename"],
                engine=data["engine"],
                status=data["status"],
                progress=data["progress"],
                created_at=datetime.fromisoformat(data["created_at"]),
                updated_at=datetime.fromisoformat(data["updated_at"]),
                error=data.get("error"),
                result=data.get("result"),
                output_formats=data.get("output_formats", []),
                downloads=data.get("downloads", {}),
            )
        )
    return results


@app.get("/api/jobs/{job_id}", response_model=JobDetail)
async def get_job(job_id: str) -> JobDetail:
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    data = job.to_dict()
    return JobDetail(
        id=data["id"],
        filename=data["filename"],
        engine=data["engine"],
        status=data["status"],
        progress=data["progress"],
        created_at=datetime.fromisoformat(data["created_at"]),
        updated_at=datetime.fromisoformat(data["updated_at"]),
        error=data.get("error"),
        result=data.get("result"),
        output_formats=data.get("output_formats", []),
        downloads=data.get("downloads", {}),
    )


@app.delete("/api/jobs/{job_id}")
async def cancel_job(job_id: str) -> dict[str, str]:
    task = job_tasks.get(job_id)
    if not task:
        raise HTTPException(status_code=404, detail="Job not running")
    task.cancel()
    return {"status": "cancelled"}


@app.get("/api/jobs/{job_id}/download/{fmt}")
async def download_job(job_id: str, fmt: str, path: str) -> FileResponse:
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    target = settings.storage_dir / Path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = "text/plain"
    if fmt.lower() == "srt":
        media_type = "application/x-subrip"
    elif fmt.lower() == "json":
        media_type = "application/json"
    elif fmt.lower() == "vtt":
        media_type = "text/vtt"
    filename = f"{job.filename.rsplit('.', 1)[0]}-{job.id[:6]}.{fmt}"
    return FileResponse(target, filename=filename, media_type=media_type)


@app.get("/api/jobs/{job_id}/artifacts")
async def list_artifacts(job_id: str) -> dict[str, Any]:
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    payload = job.to_dict()
    return {
        "downloads": payload.get("downloads", {}),
        "output_formats": payload.get("output_formats", []),
    }


@app.delete("/api/jobs/{job_id}/files")
async def delete_job_files(job_id: str) -> dict[str, str]:
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    shutil.rmtree(job.storage_dir, ignore_errors=True)
    return {"status": "deleted"}


# Serve the static frontend bundle
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
