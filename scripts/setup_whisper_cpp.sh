#!/usr/bin/env bash
set -euo pipefail

# This script bootstraps whisper.cpp with Metal support on Apple Silicon.
# Usage: ./scripts/setup_whisper_cpp.sh [whisper_dir] [model]
#   whisper_dir: optional path to checkout whisper.cpp (default: vendor/whisper.cpp)
#   model: whisper model to download (default: base.en)

WHISPER_DIR="${1:-vendor/whisper.cpp}"
MODEL="${2:-base.en}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "[error] This helper is intended for macOS hosts." >&2
  exit 1
fi

command -v git >/dev/null 2>&1 || { echo "[error] git is required" >&2; exit 1; }
command -v cmake >/dev/null 2>&1 || { echo "[error] cmake is required (brew install cmake)" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "[error] python3 is required" >&2; exit 1; }

mkdir -p "$(dirname "$WHISPER_DIR")"

if [[ ! -d "$WHISPER_DIR/.git" ]]; then
  echo "[info] Cloning whisper.cpp into $WHISPER_DIR"
  git clone https://github.com/ggml-org/whisper.cpp.git "$WHISPER_DIR"
else
  echo "[info] Updating existing whisper.cpp checkout"
  git -C "$WHISPER_DIR" pull --ff-only
fi

pushd "$WHISPER_DIR" >/dev/null

# Ensure submodules (if any) are present
if [[ -f ".gitmodules" ]]; then
  git submodule update --init --recursive
fi

# Build with Metal backend enabled
mkdir -p build
cmake -B build \
  -DGGML_METAL=1 \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j

# Download requested ggml model (stored under models/)
if [[ -x "./models/download-ggml-model.sh" ]]; then
  echo "[info] Downloading ggml model: $MODEL"
  ./models/download-ggml-model.sh "$MODEL"
else
  echo "[warn] Model download script missing; skipping"
fi

popd >/dev/null

echo "[info] whisper.cpp ready at $WHISPER_DIR"
echo "[info] Default Metal-enabled CLI binary: $WHISPER_DIR/build/bin/whisper-cli"
