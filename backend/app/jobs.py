from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .models import JobStatus


@dataclass
class JobRecord:
    id: str
    filename: str
    engine: str
    params: Dict[str, Any]
    output_formats: list[str]
    storage_dir: Path
    group_id: Optional[str] = None
    status: JobStatus = JobStatus.queued
    progress: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    downloads: Dict[str, str] = field(default_factory=dict)
    archived: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "engine": self.engine,
            "status": self.status,
            "progress": self.progress,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error": self.error,
            "result": self.result,
            "output_formats": self.output_formats,
            "downloads": self.downloads,
            "group_id": self.group_id,
            "archived": self.archived,
            "storage_path": str(self.storage_dir),
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def create_job(
        self,
        job_id: str,
        filename: str,
        engine: str,
        params: Dict[str, Any],
        output_formats: list[str],
        storage_dir: Path,
        group_id: Optional[str] = None,
    ) -> JobRecord:
        record = JobRecord(
            id=job_id,
            filename=filename,
            engine=engine,
            params=params,
            output_formats=output_formats,
            storage_dir=storage_dir,
            group_id=group_id,
        )
        async with self._lock:
            self._jobs[job_id] = record
        return record

    async def update_job(self, job_id: str, updater: Callable[[JobRecord], Any]) -> JobRecord:
        async with self._lock:
            job = self._jobs[job_id]
            updater(job)
            job.updated_at = datetime.utcnow()
            return job

    async def set_progress(self, job_id: str, progress: int) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            job.progress = max(0, min(100, progress))
            job.updated_at = datetime.utcnow()

    def get_job(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def list_jobs(self, *, archived: Optional[bool] = None) -> list[JobRecord]:
        records = self._jobs.values()
        if archived is not None:
            records = [job for job in records if job.archived == archived]
        return sorted(records, key=lambda job: job.created_at, reverse=True)

    async def update_download(self, job_id: str, fmt: str, url: str) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            job.downloads[fmt] = url
            job.updated_at = datetime.utcnow()

    async def set_archived(self, job_id: str, archived: bool) -> JobRecord:
        async with self._lock:
            job = self._jobs[job_id]
            job.archived = archived
            job.updated_at = datetime.utcnow()
            return job


job_manager = JobManager()
