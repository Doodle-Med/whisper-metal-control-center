#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ ! -d .venv ]]; then
  echo "[info] Setting up Python environment..."
  ./scripts/bootstrap.sh
fi

if [[ ! -x vendor/whisper.cpp/build/bin/whisper-cli ]]; then
  echo "[info] Building whisper.cpp..."
  ./scripts/setup_whisper_cpp.sh
fi

source .venv/bin/activate
if ! pgrep -f "backend.app" >/dev/null 2>&1; then
  echo "[info] Starting Whisper Metal Control Center..."
  open "http://localhost:8000" >/dev/null 2>&1 || true
  python -m backend.app
else
  echo "[warn] backend.app already running. Press Ctrl+C to stop." >&2
fi
