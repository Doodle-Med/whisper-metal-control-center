from __future__ import annotations

import os
import platform
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings

APP_NAME = "Whisper Metal Control Center"
DEFAULT_MODEL_NAME = "ggml-base.en.bin"


@lru_cache(maxsize=1)
def _detect_resources_root() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == "Resources":
            return parent
    return None


def _candidate_vendor_roots() -> list[Path]:
    candidates: list[Path] = []
    resources_root = _detect_resources_root()
    if resources_root is not None:
        candidates.append(resources_root / "vendor" / "whisper.cpp")

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "vendor" / "whisper.cpp"
        if candidate not in candidates:
            candidates.append(candidate)

    if not candidates:
        candidates.append(here.parent / "vendor" / "whisper.cpp")

    return candidates


def _default_whisper_root() -> Path:
    for candidate in _candidate_vendor_roots():
        if candidate.exists():
            return candidate
    return _candidate_vendor_roots()[0]


def _default_resources_dir() -> Path:
    resources_root = _detect_resources_root()
    if resources_root is not None:
        return resources_root
    return Path(__file__).resolve().parents[2]


def _default_user_data_root() -> Path:
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
        return (base / APP_NAME).expanduser()
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return (base / APP_NAME).expanduser()
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        return (Path(data_home) / "whisper-metal-control-center").expanduser()
    return (Path.home() / ".local" / "share" / "whisper-metal-control-center").expanduser()


def _default_storage_dir() -> Path:
    return (_default_user_data_root() / "storage").expanduser()


def _default_models_dir() -> Path:
    return (_default_user_data_root() / "models").expanduser()


def _expand_path(value: Path | str) -> Path:
    return Path(value).expanduser()


class Settings(BaseSettings):
    whisper_root: Path = Field(default_factory=_default_whisper_root)
    whisper_binary: Path | None = None
    whisper_model: Path | None = None
    whisper_threads: int = 4
    whisper_extra_args: list[str] = Field(default_factory=list)
    storage_dir: Path | None = None
    user_models_dir: Path | None = None
    default_output_formats: list[str] = Field(default_factory=lambda: ["json", "txt", "srt"])
    max_concurrent_jobs: int = 2
    allow_cloud_offload: bool = True
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    filler_words: list[str] = Field(
        default_factory=lambda: ["uh", "um", "you know", "like", "i mean"]
    )

    class Config:
        env_prefix = "WHISPER_APP_"
        env_file = ".env"
        env_file_encoding = "utf-8"

    def model_post_init(self, __context: object) -> None:
        self.whisper_root = _expand_path(self.whisper_root)

        if self.whisper_binary is not None:
            self.whisper_binary = _expand_path(self.whisper_binary)

        if self.whisper_model is None:
            self.whisper_model = self.whisper_root / "models" / DEFAULT_MODEL_NAME
        else:
            self.whisper_model = _expand_path(self.whisper_model)

        if self.storage_dir is None:
            self.storage_dir = _default_storage_dir()
        else:
            self.storage_dir = _expand_path(self.storage_dir)

        if self.user_models_dir is None:
            self.user_models_dir = _default_models_dir()
        else:
            self.user_models_dir = _expand_path(self.user_models_dir)

        self._resources_dir = _default_resources_dir()

    @property
    def binary_path(self) -> Path:
        if self.whisper_binary is not None:
            return self.whisper_binary
        return self.whisper_root / "build/bin/whisper-cli"

    @property
    def resources_dir(self) -> Path:
        return self._resources_dir

    @property
    def models_dir(self) -> Path:
        return self.user_models_dir

    @property
    def bundle_models_dir(self) -> Path | None:
        resources_root = _detect_resources_root()
        if resources_root is not None:
            bundled = resources_root / "vendor" / "whisper.cpp" / "models"
            if bundled.exists():
                return bundled

        candidate = self.whisper_root / "models"
        if candidate.exists() and candidate != self.models_dir:
            return candidate

        return None


settings = Settings()
