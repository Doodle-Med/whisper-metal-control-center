#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_VENV_DIR="${1:-$PROJECT_ROOT/.venv}"

mkdir -p "$TARGET_VENV_DIR"
python3 -m venv "$TARGET_VENV_DIR"
source "$TARGET_VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$PROJECT_ROOT/backend/requirements.txt"
