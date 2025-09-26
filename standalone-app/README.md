# Whisper Metal Control Center – Standalone Bundle (Phase 3)

This subdirectory contains everything needed to build a self-contained macOS
`.app` bundle and DMG for Whisper Metal Control Center. Treat it as the root of
an independent GitHub project if you plan to publish the standalone build.

## Directory layout

```
standalone-app/
├── README.md                    # this guide
├── requirements-packaging.txt   # packaging-only Python dependencies
├── build_app_bundle.sh          # creates Whisper Metal Control Center.app
├── build_dmg.sh                 # wraps the app bundle into a DMG
├── whisper_control.spec         # PyInstaller blueprint for the .app bundle
├── src/
│   └── launcher.py              # embedded launcher (starts backend + webview)
└── .gitignore                   # ignores build artefacts (.packaging, dist, build)
```

## Prerequisites

1. macOS 13+ on Apple Silicon
2. Xcode Command Line Tools (`xcode-select --install`)
3. Homebrew (recommended) for `create-dmg` (optional but preferred)
4. `scripts/setup_whisper_cpp.sh` must have been run from the repository root so
   that `vendor/whisper.cpp/` contains a Metal-enabled build and models.
5. `ffmpeg` installed locally (Homebrew static builds work well). The packaging
   script copies the binary into the app bundle so end users do not need it.

## Quick start

From the repository root:

```bash
# 1. Ensure whisper.cpp + models exist
./scripts/setup_whisper_cpp.sh

# 2. Build the standalone .app bundle under standalone-app/dist/
standalone-app/build_app_bundle.sh

# 3. Wrap the app into a distributable DMG (optional)
standalone-app/build_dmg.sh
```

Outputs:

- `standalone-app/dist/Whisper Metal Control Center.app`
- `standalone-app/dist/WhisperMetalControlCenter.dmg` (if `build_dmg.sh` ran)

## How it works

- `build_app_bundle.sh` spins up an isolated packaging virtualenv (under
  `standalone-app/.packaging/`), installs runtime + packaging dependencies, and
  invokes PyInstaller with `whisper_control.spec`.
- PyInstaller bundles:
  - the backend (`backend/`), frontend assets (`frontend/`), and helper scripts
  - the new `src/launcher.py` entrypoint (see below)
  - Python runtime and site-packages needed for FastAPI/Uvicorn/pywebview
- After PyInstaller finishes, the script copies the existing
  `vendor/whisper.cpp` build (Metal-enabled binary + models) into the app’s
  `Contents/Resources/vendor/` folder, along with a static `ffmpeg` binary if
  available.
- `src/launcher.py` starts the FastAPI backend inside the bundle, waits for the
  health endpoint to respond, and then opens a minimal pywebview window pointing
  at `http://127.0.0.1:8777`. When the window closes, the backend shuts down and
  temp storage is cleaned up.

## Publishing as a separate repo

1. Copy the entire `standalone-app/` directory into a new Git repository.
2. Update `README.md` (this file) with project-specific branding, icons, etc.
3. Run `build_app_bundle.sh` and `build_dmg.sh` from that repo.
4. Upload `dist/WhisperMetalControlCenter.dmg` (and optional `.zip` of the `.app`)
   to your GitHub Releases page.

## Customisation

- Edit `whisper_control.spec` to change bundle identifiers, icon paths, or
  additional resources.
- Provide a custom `.icns` icon and pass it via the `--icon` flag in the spec.
- Update `src/launcher.py` if you want a different UI shell (e.g. SwiftUI or
  Electron wrapper) – the script is intentionally minimal and pure Python.

## Troubleshooting

- **Missing whisper.cpp binary** – run `./scripts/setup_whisper_cpp.sh` from the
  repository root before packaging.
- **ffmpeg not bundled** – install a static ffmpeg (Homebrew’s default) and make
  sure it’s discoverable via `which ffmpeg`. The packaging script copies it into
  the app bundle automatically.
- **Gatekeeper warnings** – unsigned apps show the usual macOS warning. You’ll
  need to codesign/notarize the `.app`/DMG using your Apple Developer ID before
  distributing broadly.
- **Cold start delay** – the first launch may take ~10 seconds while the backend
  boots, models are loaded, and the pywebview window appears.

Happy packaging!
