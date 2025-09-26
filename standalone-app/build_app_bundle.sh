#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PACKAGING_DIR="${SCRIPT_DIR}/.packaging"
VENV_DIR="${PACKAGING_DIR}/venv"
DIST_DIR="${SCRIPT_DIR}/dist"
BUILD_DIR="${SCRIPT_DIR}/build"
APP_NAME="Whisper Metal Control Center.app"
APP_BUNDLE="${DIST_DIR}/${APP_NAME}"
RESOURCES_DIR="${APP_BUNDLE}/Contents/Resources"

mkdir -p "${PACKAGING_DIR}"

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"
pip install --upgrade pip
pip install -r "${SCRIPT_DIR}/requirements-packaging.txt"
pip install -r "${REPO_ROOT}/backend/requirements.txt"

if [[ ! -x "${REPO_ROOT}/vendor/whisper.cpp/build/bin/whisper-cli" ]]; then
  echo "[info] whisper.cpp build missing – running scripts/setup_whisper_cpp.sh"
  "${REPO_ROOT}/scripts/setup_whisper_cpp.sh"
fi

rm -rf "${DIST_DIR}" "${BUILD_DIR}"
mkdir -p "${DIST_DIR}" "${BUILD_DIR}"

export WHISPER_PROJECT_ROOT="${REPO_ROOT}"
export WHISPER_SPEC_DIR="${SCRIPT_DIR}"

pyinstaller \
  --noconfirm \
  --clean \
  --log-level WARN \
  --workpath "${BUILD_DIR}" \
  --distpath "${DIST_DIR}" \
  "${SCRIPT_DIR}/whisper_control.spec"

if [[ ! -d "${APP_BUNDLE}" ]]; then
  echo "[error] PyInstaller did not produce ${APP_BUNDLE}" >&2
  exit 1
fi

mkdir -p "${RESOURCES_DIR}/vendor/whisper.cpp"
rsync -a --delete "${REPO_ROOT}/vendor/whisper.cpp/build" "${RESOURCES_DIR}/vendor/whisper.cpp/"
rsync -a "${REPO_ROOT}/vendor/whisper.cpp/models" "${RESOURCES_DIR}/vendor/whisper.cpp/"

FFMPEG_PATH="$(command -v ffmpeg || true)"
if [[ -n "${FFMPEG_PATH}" ]]; then
  mkdir -p "${RESOURCES_DIR}/bin"
  cp "${FFMPEG_PATH}" "${RESOURCES_DIR}/bin/ffmpeg"
  chmod +x "${RESOURCES_DIR}/bin/ffmpeg"
else
  echo "[warn] ffmpeg not found on PATH; end-users must supply their own binary." >&2
fi

default_storage="${RESOURCES_DIR}/defaults/storage"
mkdir -p "${default_storage}"

cat > "${RESOURCES_DIR}/NOTICE.txt" <<TXT
This bundle packages Whisper Metal Control Center along with its Python runtime,
whisper.cpp binaries, and optional ffmpeg executable. Source repository:
https://github.com/whisper-metal-control-center
TXT

echo "[info] App bundle created at ${APP_BUNDLE}"
