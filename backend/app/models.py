from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class JobSummary(BaseModel):
    id: str
    filename: str
    engine: str
    status: JobStatus
    progress: int
    created_at: datetime
    updated_at: datetime
    error: Optional[str] = None
    group_id: Optional[str] = None
    archived: bool = False


class JobDetail(JobSummary):
    result: Optional[Dict[str, Any]] = None
    output_formats: List[str] = []
    downloads: Dict[str, str] = {}


class ModelInfo(BaseModel):
    name: str
    path: str
    size_mb: float
    quantization: Optional[str] = None


class CapabilityResponse(BaseModel):
    default_threads: int
    max_concurrent_jobs: int
    allow_cloud_offload: bool
    available_models: List[ModelInfo]
    default_formats: List[str]


def job_to_summary(payload: Dict[str, Any]) -> JobSummary:
    return JobSummary(
        id=payload["id"],
        filename=payload["filename"],
        engine=payload["engine"],
        status=payload["status"],
        progress=payload.get("progress", 0),
        created_at=datetime.fromisoformat(payload["created_at"]),
        updated_at=datetime.fromisoformat(payload["updated_at"]),
        error=payload.get("error"),
        group_id=payload.get("group_id"),
        archived=payload.get("archived", False),
    )
