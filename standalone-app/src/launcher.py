from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import requests
import webview


def resource_path(*segments: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*segments)


def configure_environment() -> tuple[Path, Path, Path]:
    resources_root = resource_path()
    project_root = resources_root  # backend + frontend live directly under resources
    vendor_root = resources_root / "vendor" / "whisper.cpp"

    storage_root = Path.home() / "Library" / "Application Support" / "WhisperMetalControlCenter"
    storage_root.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    os.environ.setdefault("WHISPER_APP_STORAGE_DIR", str(storage_root / "storage"))
    os.environ.setdefault("WHISPER_APP_WHISPER_ROOT", str(vendor_root))

    # Expose user models directory to backend for listing
    user_models_dir = storage_root / "models"
    user_models_dir.mkdir(parents=True, exist_ok=True)
    os.environ["WHISPER_APP_USER_MODELS_DIR"] = str(user_models_dir)

    binary_path = vendor_root / "build" / "bin" / "whisper-cli"
    if binary_path.exists():
        os.environ.setdefault("WHISPER_APP_WHISPER_BINARY", str(binary_path))

    # If a bundled base model exists (future), prefer it unless user override is set during runtime
    base_model = vendor_root / "models" / "ggml-base.en.bin"
    if base_model.exists():
        os.environ.setdefault("WHISPER_APP_WHISPER_MODEL", str(base_model))

    # Ensure bundled backend/frontends are importable
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, str(project_root / "backend"))

    return resources_root, project_root, vendor_root


def _download_file(url: str, destination: Path, chunk_size: int = 1024 * 1024) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=30) as response:
        response.raise_for_status()
        with destination.open("wb") as file_handle:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    file_handle.write(chunk)


def _try_urls(urls: list[str], out_path: Path) -> bool:
    for url in urls:
        try:
            _download_file(url, out_path)
            return True
        except Exception:
            continue
    return out_path.exists()


MODEL_MAP = {
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


def ensure_models(vendor_root: Path) -> Optional[Path]:
    user_models_dir = (
        Path.home()
        / "Library"
        / "Application Support"
        / "WhisperMetalControlCenter"
        / "models"
    )
    user_models_dir.mkdir(parents=True, exist_ok=True)

    # Download base model first to unblock UI quickly
    base_path = user_models_dir / "ggml-base.en.bin"
    if not base_path.exists():
        _try_urls(MODEL_MAP["ggml-base.en.bin"], base_path)

    # Kick off background downloads for other models (non-blocking)
    def _bg_download() -> None:
        for name, urls in MODEL_MAP.items():
            if name == "ggml-base.en.bin":
                continue
            out = user_models_dir / name
            if out.exists():
                continue
            _try_urls(urls, out)

    threading.Thread(target=_bg_download, name="model-downloader", daemon=True).start()

    if base_path.exists():
        os.environ["WHISPER_APP_WHISPER_MODEL"] = str(base_path)
        return base_path
    return None


class BackendServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8777) -> None:
        self.host = host
        self.port = port
        self._thread: Optional[threading.Thread] = None
        self._server: Optional["uvicorn.Server"] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="uvicorn-thread", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        import uvicorn
        from backend.app.main import app

        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="info",
            reload=False,
            lifespan="on",
        )
        self._server = uvicorn.Server(config)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._server.serve())

    def wait_until_ready(self, timeout: float = 30.0) -> bool:
        deadline = time.time() + timeout
        url = f"http://{self.host}:{self.port}/api/health"
        while time.time() < deadline:
            try:
                response = requests.get(url, timeout=1.0)
                if response.ok:
                    return True
            except requests.RequestException:
                time.sleep(0.5)
        return False

    def stop(self) -> None:
        if not self._server:
            return
        self._server.should_exit = True


def main() -> None:
    resources_root, project_root, vendor_root = configure_environment()

    # Ensure base model first, then background download others
    with contextlib.suppress(Exception):
        ensure_models(vendor_root)

    backend = BackendServer()
    backend.start()
    ready = backend.wait_until_ready()
    if not ready:
        raise SystemExit("Backend failed to start. Check bundled resources.")

    window = webview.create_window(
        title="Whisper Metal Control Center",
        url="http://127.0.0.1:8777",
        width=1280,
        height=720,
        resizable=True,
        confirm_close=False,
    )

    def on_closed() -> None:
        backend.stop()
        time.sleep(0.5)

    window.events.closed += on_closed

    try:
        webview.start()
    finally:
        backend.stop()
        time.sleep(0.2)


def _install_signal_handlers() -> None:
    def shutdown(signum, frame):  # type: ignore[unused-argument]
        raise SystemExit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(Exception):
            signal.signal(sig, shutdown)


if __name__ == "__main__":
    _install_signal_handlers()
    main()
