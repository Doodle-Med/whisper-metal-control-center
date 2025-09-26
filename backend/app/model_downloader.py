from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Dict, List, Optional

import requests


MODEL_SOURCES: Dict[str, List[str]] = {
    "ggml-base.en.bin": [
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin?download=true",
        "https://ggml.ggerganov.com/whisper/ggml-base.en.bin",
    ],
    "ggml-small.en.bin": [
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin?download=true",
        "https://ggml.ggerganov.com/whisper/ggml-small.en.bin",
    ],
    "ggml-medium.en.bin": [
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.en.bin?download=true",
        "https://ggml.ggerganov.com/whisper/ggml-medium.en.bin",
    ],
    "ggml-large-v3.bin": [
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin?download=true",
        "https://ggml.ggerganov.com/whisper/ggml-large-v3.bin",
    ],
}


class ModelDownloadManager:
    def __init__(
        self,
        search_dirs: List[Path],
        download_dir: Path,
        base_model_name: str = "ggml-base.en.bin",
        on_primary_ready: Optional[callable] = None,
    ) -> None:
        self.search_dirs = [path for path in search_dirs if path]
        self.download_dir = download_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.base_model_name = base_model_name
        self.on_primary_ready = on_primary_ready

        self._lock = threading.Lock()
        self._state: Dict[str, Dict[str, Optional[float]]] = {}
        self._events: Dict[str, threading.Event] = {}

        self._init_state()

    # Public API ---------------------------------------------------------
    def ensure_base_model(self, blocking: bool = False) -> Optional[Path]:
        """Ensure the primary (base) model download has started.

        If ``blocking`` is True, this call waits for the download to complete.
        """

        return self._download_model(self.base_model_name, blocking=blocking)

    def download_missing_async(self) -> None:
        for name in MODEL_SOURCES.keys():
            if name == self.base_model_name:
                continue
            self._download_model(name, blocking=False)

    def retry_download(self, name: str) -> None:
        if name not in MODEL_SOURCES:
            raise ValueError(f"Unknown model: {name}")
        with self._lock:
            entry = self._state[name]
            entry.update(
                status="pending",
                error=None,
                bytes_downloaded=0,
                total_bytes=None,
                progress=0.0,
            )
        target = Path(self._state[name]["path"] or "")
        target.unlink(missing_ok=True)
        self._download_model(name, blocking=False, force=True)

    def get_state(self) -> Dict[str, Dict[str, Optional[float]]]:
        with self._lock:
            return {name: entry.copy() for name, entry in self._state.items()}

    def ready_models(self) -> List[Dict[str, Optional[float]]]:
        models: List[Dict[str, Optional[float]]] = []
        with self._lock:
            for name, entry in self._state.items():
                if entry.get("status") == "ready" and entry.get("path"):
                    models.append(
                        {
                            "name": name,
                            "path": entry["path"],
                            "size_mb": entry.get("size_mb"),
                            "quantization": self._infer_quantization(name),
                        }
                    )

        models.extend(self._discover_extra_models())
        return self._deduplicate(models)

    # Internal helpers ---------------------------------------------------
    def _init_state(self) -> None:
        for name in MODEL_SOURCES.keys():
            self._events[name] = threading.Event()
            existing = self._find_existing(name)
            if existing:
                size_bytes = existing.stat().st_size
                self._state[name] = {
                    "status": "ready",
                    "path": str(existing),
                    "bytes_downloaded": size_bytes,
                    "total_bytes": size_bytes,
                    "progress": 1.0,
                    "size_mb": round(size_bytes / (1024 * 1024), 2),
                    "error": None,
                }
                self._events[name].set()
                if name == self.base_model_name:
                    os.environ.setdefault("WHISPER_APP_WHISPER_MODEL", str(existing))
            else:
                target = self.download_dir / name
                self._state[name] = {
                    "status": "pending",
                    "path": str(target),
                    "bytes_downloaded": 0,
                    "total_bytes": None,
                    "progress": 0.0,
                    "size_mb": None,
                    "error": None,
                }

    def _find_existing(self, name: str) -> Optional[Path]:
        for directory in self.search_dirs:
            candidate = directory / name
            if candidate.exists():
                return candidate
        return None

    def _download_model(self, name: str, *, blocking: bool, force: bool = False) -> Optional[Path]:
        with self._lock:
            entry = self._state.get(name)
            if not entry:
                raise ValueError(f"Unknown model: {name}")
            status = entry["status"]
            if status == "downloading":
                return None
            if status == "ready" and not force:
                return Path(entry["path"]) if entry.get("path") else None
            entry.update(
                status="downloading",
                error=None,
                bytes_downloaded=0,
                total_bytes=None,
                progress=0.0,
            )
            self._events[name].clear()
        target = Path(self._state[name]["path"] or "")
        target.parent.mkdir(parents=True, exist_ok=True)
        if force:
            target.unlink(missing_ok=True)

        def worker() -> Optional[Path]:
            for url in MODEL_SOURCES[name]:
                result = self._download_from_url(name, url, target)
                if result:
                    return result
            # All sources failed; state already updated inside _download_from_url
            return None

        if blocking:
            return worker()
        thread = threading.Thread(target=worker, name=f"download-{name}", daemon=True)
        thread.start()
        return None

    def _download_from_url(self, name: str, url: str, target: Path) -> Optional[Path]:
        tmp_path = target.with_suffix(target.suffix + ".tmp")
        try:
            with requests.get(url, stream=True, timeout=30) as response:
                response.raise_for_status()
                total = response.headers.get("Content-Length")
                total_bytes = int(total) if total and total.isdigit() else None
                downloaded = 0
                with self._lock:
                    self._state[name]["total_bytes"] = total_bytes
                with tmp_path.open("wb") as buffer:
                    for chunk in response.iter_content(chunk_size=2 * 1024 * 1024):
                        if not chunk:
                            continue
                        buffer.write(chunk)
                        downloaded += len(chunk)
                        with self._lock:
                            self._state[name]["bytes_downloaded"] = downloaded
                            self._state[name]["progress"] = (
                                downloaded / total_bytes if total_bytes else None
                            )
            tmp_path.replace(target)
            size_bytes = target.stat().st_size
            with self._lock:
                self._state[name].update(
                    status="ready",
                    error=None,
                    bytes_downloaded=size_bytes,
                    total_bytes=size_bytes,
                    progress=1.0,
                    size_mb=round(size_bytes / (1024 * 1024), 2),
                    path=str(target),
                )
            self._events[name].set()
            if name == self.base_model_name:
                os.environ["WHISPER_APP_WHISPER_MODEL"] = str(target)
                if self.on_primary_ready:
                    self.on_primary_ready(target)
            return target
        except Exception as exc:  # pragma: no cover - network failures
            tmp_path.unlink(missing_ok=True)
            with self._lock:
                self._state[name].update(status="error", error=str(exc), progress=None)
            return None

    def _discover_extra_models(self) -> List[Dict[str, Optional[float]]]:
        extras: List[Dict[str, Optional[float]]] = []
        seen = set(self._state.keys())
        for directory in self.search_dirs + [self.download_dir]:
            if not directory or not directory.exists():
                continue
            for path in directory.glob("*.bin"):
                name = path.name
                if name in seen:
                    continue
                size_bytes = path.stat().st_size
                extras.append(
                    {
                        "name": name,
                        "path": str(path.resolve()),
                        "size_mb": round(size_bytes / (1024 * 1024), 2),
                        "quantization": self._infer_quantization(name),
                    }
                )
        return extras

    def _deduplicate(self, models: List[Dict[str, Optional[float]]]) -> List[Dict[str, Optional[float]]]:
        deduped: Dict[str, Dict[str, Optional[float]]] = {}
        for entry in models:
            deduped[entry["path"]] = entry
        return list(deduped.values())

    def _infer_quantization(self, name: str) -> Optional[str]:
        stem = Path(name).stem
        if "q" in stem:
            parts = stem.split("-")
            candidate = parts[-1] if parts else ""
            if "q" in candidate.lower():
                return candidate
        return None


