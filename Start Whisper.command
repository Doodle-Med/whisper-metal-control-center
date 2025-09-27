#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$ROOT_DIR"
SCRIPTS_DIR="$PROJECT_ROOT/scripts"

# Prefer bundled ffmpeg on PATH when running server
export PATH="$PROJECT_ROOT/bin:$PATH"

# Default runtime locations (user-writable)
APP_SUPPORT="$HOME/Library/Application Support/Whisper Metal Control Center"
export WHISPER_APP_STORAGE_DIR="${WHISPER_APP_STORAGE_DIR:-$APP_SUPPORT/storage}"
export WHISPER_APP_WHISPER_ROOT="${WHISPER_APP_WHISPER_ROOT:-$PROJECT_ROOT/vendor/whisper.cpp}"
export WHISPER_APP_USER_MODELS_DIR="${WHISPER_APP_USER_MODELS_DIR:-$APP_SUPPORT/models}"

# Virtualenv location (user-writable)
VENV_DIR="${WHISPER_APP_VENV_DIR:-$APP_SUPPORT/.venv}"
mkdir -p "$APP_SUPPORT"

cd "$PROJECT_ROOT"
if [[ ! -d "$VENV_DIR" ]]; then
  echo "[info] Setting up Python environment..."
  "$SCRIPTS_DIR/bootstrap.sh" "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

if ! pgrep -f "backend.app" >/dev/null 2>&1; then
  echo "[info] Starting Whisper Metal Control Center..."
  open "http://localhost:8000" >/dev/null 2>&1 || true
  PYTHONPATH="$PROJECT_ROOT" python -m backend.app
else
  echo "[warn] backend.app already running. Press Ctrl+C to stop." >&2
fi
