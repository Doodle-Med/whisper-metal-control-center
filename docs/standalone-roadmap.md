# Standalone macOS App Roadmap

This project is still delivered as a Python web service that you can double-click
via `Start Whisper.command`. Phase 3 is to ship a self-contained app bundle that
installs its own runtime and dependencies (Python, whisper.cpp, ffmpeg, etc.) and
launches without opening a Terminal window.

## Goals

1. **Embed the Python runtime** so users do not need Homebrew or a system-wide
   Python/ffmpeg install.
2. **Bake whisper.cpp + models** into the bundle (or download on first run) while
   linking against Metal/CoreML.
3. **Provide a native launcher** (`Whisper Metal Control Center.app`) that starts
   Uvicorn in the background and opens the UI in a minimal webview window instead
   of a browser tab.
4. **Produce a notarized DMG** for distribution on GitHub releases.

## Implementation snapshot

Phase 3a is now implemented in the repository under `standalone-app/`:

- `build_app_bundle.sh` builds a PyInstaller-based `.app` bundle and copies the
  Metal-enabled `whisper.cpp` binaries/models plus an optional static `ffmpeg`
  into `Contents/Resources/`.
- `build_dmg.sh` wraps the bundle in a DMG (using `create-dmg` if available,
  otherwise falling back to `hdiutil`).
- `src/launcher.py` boots the backend inside the bundle and displays the UI via
  a lightweight pywebview shell pointing at `http://127.0.0.1:8777`.
- `requirements-packaging.txt` lists packaging-only dependencies (PyInstaller,
  pywebview, PyObjC).

Run the following from the repo root to produce distributables:

```bash
./scripts/setup_whisper_cpp.sh                 # ensure Metal build + models exist
standalone-app/build_app_bundle.sh             # creates dist/Whisper Metal Control Center.app
standalone-app/build_dmg.sh                    # (optional) dist/WhisperMetalControlCenter.dmg
```

## Remaining work (Phase 3b / 3c)

1. **Minimal native shell** – replace the pywebview window with a SwiftUI or
   AppKit wrapper if a pure-native UI is preferred. The current implementation is
   sufficient for a lightweight embed but does rely on Python + PyObjC.
2. **Auto-updates & notarization** – add Sparkle (or similar) for updates and
   notarize/sign the bundle and DMG using an Apple Developer ID before shipping
   to end users.
3. **Model management** – optionally provide a UI/logic for downloading and
   switching between ggml models within the packaged app rather than bundling
   only `ggml-base.en.bin`.

This document now tracks the future work required to polish Phase 3. The
self-contained app bundle scaffolding lives entirely in `standalone-app/`, ready
for deployment as its own GitHub repository.
