#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="Whisper Metal Control Center"

# Detect read-only DMG; copy to ~/Applications (or ~) before proceeding
TEST_FILE="$SCRIPT_DIR/.write-test"
if ! ( : > "$TEST_FILE" 2>/dev/null ); then
  DEST_ROOT="$HOME/Applications/$APP_NAME"
  mkdir -p "$HOME/Applications" 2>/dev/null || DEST_ROOT="$HOME/$APP_NAME"
  echo "[info] Copying $APP_NAME to $DEST_ROOT"
  rsync -a --delete "$SCRIPT_DIR/" "$DEST_ROOT/"
  echo "[info] Relaunching from installed location..."
  exec "$DEST_ROOT/Start Whisper.command"
fi
rm -f "$TEST_FILE"

PROJECT_ROOT="$SCRIPT_DIR"
SCRIPTS_DIR="$PROJECT_ROOT/scripts"

# Prefer bundled ffmpeg
export PATH="$PROJECT_ROOT/bin:$PATH"

APP_SUPPORT="$HOME/Library/Application Support/$APP_NAME"
mkdir -p "$APP_SUPPORT"

export WHISPER_APP_STORAGE_DIR="${WHISPER_APP_STORAGE_DIR:-$APP_SUPPORT/storage}"
export WHISPER_APP_WHISPER_ROOT="${WHISPER_APP_WHISPER_ROOT:-$PROJECT_ROOT/vendor/whisper.cpp}"
export WHISPER_APP_USER_MODELS_DIR="${WHISPER_APP_USER_MODELS_DIR:-$APP_SUPPORT/models}"

VENV_DIR="${WHISPER_APP_VENV_DIR:-$APP_SUPPORT/.venv}"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "[info] Setting up Python environment..."
  "$SCRIPTS_DIR/bootstrap.sh" "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

if [[ ! -x "$WHISPER_APP_WHISPER_ROOT/build/bin/whisper-cli" ]]; then
  echo "[info] Building whisper.cpp..."
  "$SCRIPTS_DIR/setup_whisper_cpp.sh" "$WHISPER_APP_WHISPER_ROOT" base.en
fi

if ! pgrep -f "backend.app" >/dev/null 2>&1; then
  echo "[info] Starting $APP_NAME..."
  open "http://localhost:8000" >/dev/null 2>&1 || true
  PYTHONPATH="$PROJECT_ROOT" python -m backend.app
else
  echo "[warn] backend.app already running. Press Ctrl+C to stop." >&2
fi
