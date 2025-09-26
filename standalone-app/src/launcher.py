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
    binary_path = vendor_root / "build" / "bin" / "whisper-cli"
    if binary_path.exists():
        os.environ.setdefault("WHISPER_APP_WHISPER_BINARY", str(binary_path))
    base_model = vendor_root / "models" / "ggml-base.en.bin"
    if base_model.exists():
        os.environ.setdefault("WHISPER_APP_WHISPER_MODEL", str(base_model))

    ffmpeg_binary = resources_root / "bin" / "ffmpeg"
    if ffmpeg_binary.exists():
        os.environ["PATH"] = f"{ffmpeg_binary.parent}:{os.environ.get('PATH', '')}"

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


def ensure_base_model(vendor_root: Path, model_name: str = "ggml-base.en.bin") -> Optional[Path]:
    # Always download to a writable per-user location so it works even when launching from a read-only DMG
    user_models_dir = (
        Path.home()
        / "Library"
        / "Application Support"
        / "WhisperMetalControlCenter"
        / "models"
    )
    model_path = user_models_dir / model_name
    if model_path.exists():
        return model_path

    # Try to download from known mirrors. We prefer Hugging Face; fall back to ggml mirror.
    candidate_urls = [
        f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{model_name}?download=true",
        f"https://ggml.ggerganov.com/whisper/{model_name}",
    ]

    for url in candidate_urls:
        try:
            _download_file(url, model_path)
            break
        except Exception:
            # Try the next mirror
            continue

    if not model_path.exists():
        # As a last resort, try the bundled shell helper if present
        helper = vendor_root / "models" / "download-ggml-model.sh"
        if helper.exists():
            try:
                import subprocess

                subprocess.run(
                    ["bash", str(helper), "base.en"],
                    check=True,
                    cwd=str(user_models_dir),
                )
            except Exception:
                pass

    if model_path.exists():
        os.environ["WHISPER_APP_WHISPER_MODEL"] = str(model_path)
        return model_path
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

    # Ensure a minimal model is present so the app works out of the box. If download fails,
    # the app will still launch; the user can point to a model later.
    with contextlib.suppress(Exception):
        ensure_base_model(vendor_root)

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
