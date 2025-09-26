#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="${SCRIPT_DIR}/dist"
APP_NAME="Whisper Metal Control Center.app"
APP_BUNDLE="${DIST_DIR}/${APP_NAME}"
DMG_NAME="WhisperMetalControlCenter.dmg"
DMG_PATH="${DIST_DIR}/${DMG_NAME}"

if [[ ! -d "${APP_BUNDLE}" ]]; then
  echo "[error] ${APP_BUNDLE} not found. Run build_app_bundle.sh first." >&2
  exit 1
fi

rm -f "${DMG_PATH}"

if command -v create-dmg >/dev/null 2>&1; then
  create-dmg \
    --volname "Whisper Metal Control Center" \
    --window-pos 200 120 \
    --window-size 600 400 \
    --icon-size 120 \
    --app-drop-link 430 190 \
    "${DMG_PATH}" \
    "${APP_BUNDLE}"
else
  echo "[warn] create-dmg not found; falling back to hdiutil."
  hdiutil create -ov -format UDZO \
    -volname "Whisper Metal Control Center" \
    -srcfolder "${APP_BUNDLE}" \
    "${DMG_PATH}"
fi

echo "[info] DMG created at ${DMG_PATH}"
