#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "[error] DMG packaging requires macOS." >&2
  exit 1
fi

command -v hdiutil >/dev/null 2>&1 || {
  echo "[error] hdiutil not found. This script must run on macOS." >&2
  exit 1
}

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$PROJECT_ROOT/dist"
STAGING="$DIST_DIR/Whisper Metal Control Center"
DMG_NAME="WhisperMetalControlCenter.dmg"

rm -rf "$DIST_DIR"
mkdir -p "$STAGING"

EXCLUDES=(
  --exclude '.git'
  --exclude '.github'
  --exclude '.venv'
  --exclude 'storage'
  --exclude 'dist'
  --exclude '__pycache__'
  --exclude '*.pyc'
  --exclude 'server.log'
)

rsync -a "${EXCLUDES[@]}" "$PROJECT_ROOT/" "$STAGING/"

# Provide a friendly launcher in the DMG root
mv "$STAGING/scripts/start_whisper.command" "$STAGING/Start Whisper.command"
chmod +x "$STAGING/Start Whisper.command"

cat > "$STAGING/README.txt" <<'TXT'
Whisper Metal Control Center
============================

1. Double-click "Start Whisper.command" to bootstrap dependencies and launch the server.
2. A terminal window will stay open; leave it running while you use the UI.
3. Visit http://localhost:8000 in Chrome (opens automatically).

First launch may take several minutes while whisper.cpp builds and models download.
TXT

hdiutil create -ov -format UDZO -volname "Whisper Metal Control Center" \
  -srcfolder "$STAGING" "$DIST_DIR/$DMG_NAME"

echo "[info] DMG created at $DIST_DIR/$DMG_NAME"
