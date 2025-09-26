# Whisper Metal Control Center

A local-first transcription workstation for Apple Silicon. Audio stays on-device while [`whisper.cpp`](https://github.com/ggml-org/whisper.cpp) runs at Metal speed, and the revamped browser UI gives you full control over decoding, batching, and exports. When you need extra horsepower you can flip a switch and offload jobs to the cloud.

## Highlights
- ⚡️ **Metal-accelerated whisper.cpp** with optional Core ML encoder support and configurable thread count.
- 🗂️ **Smart job queue** – drop in multiple files, watch per-job progress, cancel, and revisit completed transcripts.
- 🎯 **Decoding controls** – choose models, beam search, best-of, temperature, prompts, timestamps, diarization, VAD, and automatic filler-word cleanup.
- 🔁 **Live progress tracking** fed by whisper.cpp’ s internal progress callback, surfaced in the UI with status badges and progress bars.
- 📦 **One-click exports** – download TXT, SRT, VTT, or JSON artefacts for every job.
- 🧩 **Batch combine option** – merge multi-file uploads into a single, ordered transcript with filename separators.
- 🗃️ **Archive workflow** – sweep completed jobs into cold storage to keep the queue lean while preserving downloads.
- ☁️ **Cloud offload option** – point the job at OpenAI’s Whisper API (Gemini stub included) by pasting an API key; handy when you need to chew through huge queues.
- 🎙️ **Inline recorder** – capture a quick note directly from the browser.

## Prerequisites
- macOS 13 or newer on Apple Silicon (Metal support)
- Xcode Command Line Tools (`xcode-select --install`)
- Homebrew (recommended)
- Python 3.11+
- `ffmpeg` (`brew install ffmpeg`)
- `cmake` (`brew install cmake`)

> **Why no Docker?** Docker on macOS cannot access Metal/ANE acceleration. This setup mirrors the convenience of a container but keeps the workload on the host so you get native GPU speed.

## 1. Build whisper.cpp with Metal
```bash
./scripts/setup_whisper_cpp.sh
```
- Clones `whisper.cpp` under `vendor/`
- Builds it with `GGML_METAL=1`
- Downloads the `base.en` model (edit the second argument to choose another model)

The Metal-enabled binary lives at `vendor/whisper.cpp/build/bin/whisper-cli`. Model files are downloaded to `vendor/whisper.cpp/models/`.

## 2. Install backend dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

## 3. Launch the server
```bash
python -m backend.app
```
This runs Uvicorn on `http://0.0.0.0:8000` by default (see `backend/app/__main__.py`).

Open `http://localhost:8000` in Chrome to access the UI.

### Makefile shortcuts

```bash
make bootstrap   # create venv, install deps, build whisper.cpp
make run         # start the server (bootstraps automatically if needed)
make clean-storage
```

On macOS you can also run `./scripts/start_whisper.command` to launch everything from Terminal.

### Combining transcripts & archiving

- Tick **Combine transcripts into a single output** when uploading to merge every
  file from the batch into a single transcript panel. Each section is separated
  by the source filename, and the combined output stays available via the
  *Combined Transcript* row in the queue.
- Use **Archive Completed** (or the per-row *Archive* button) to move finished
  jobs into cold storage. Toggle between active and archived jobs with
  *Show Archived*; archived jobs retain their downloads and can be restored at
  any time.

## Configuration
The backend reads environment variables with the `WHISPER_APP_` prefix. Useful knobs:

| Variable | Purpose | Default |
| --- | --- | --- |
| `WHISPER_APP_WHISPER_MODEL` | Path to a `.bin` Whisper ggml model | `vendor/whisper.cpp/models/ggml-base.en.bin` |
| `WHISPER_APP_WHISPER_BINARY` | Path to the `whisper-cli` executable | `vendor/whisper.cpp/build/bin/whisper-cli` |
| `WHISPER_APP_WHISPER_THREADS` | Number of CPU threads whisper.cpp may use | `4` |
| `WHISPER_APP_STORAGE_DIR` | Where uploads/outputs are cached | `./storage` |
| `WHISPER_APP_MAX_CONCURRENT_JOBS` | Parallel local jobs | `2` |
| `WHISPER_APP_OPENAI_API_KEY` | Optional default key for cloud offload | _(empty)_ |
| `WHISPER_APP_WHISPER_EXTRA_ARGS` | Extra CLI flags passed to `whisper-cli` | _(none)_ |

Create a `.env` file in the project root or export variables in your shell before launching the server.

### Using a different model
```bash
./scripts/setup_whisper_cpp.sh vendor/whisper.cpp large-v3-turbo
export WHISPER_APP_WHISPER_MODEL=$(pwd)/vendor/whisper.cpp/models/ggml-large-v3-turbo.bin
python -m backend.app
```

### Enabling Core ML (ANE)
`whisper.cpp` supports Core ML encoder acceleration. To enable:
1. Generate the Core ML encoder (`./models/generate-coreml-model.sh base.en`)
2. Rebuild with `cmake -B build -DWHISPER_COREML=1`
3. Keep the model artifacts alongside your ggml model so that `whisper-cli` picks them up automatically.

## API reference
Everything the UI does is exposed via JSON APIs:

- `GET /api/health` – simple heartbeat.
- `GET /api/capabilities` – server metadata, available models, default formats.
- `GET /api/models` – raw list of `.bin` models on disk.
- `POST /api/jobs` – queue one or more files.
  - Multipart fields: `files`, `engine`, `model`, `language`, `translate`, `beam_size`, `best_of`, `temperature`, `cleaners`, `output_formats`, etc.
- `GET /api/jobs` – queue snapshot (status, progress, artefact links).
- `GET /api/jobs/{job_id}` – detailed payload plus segments.
- `GET /api/jobs/{job_id}/download/{fmt}` – stream exported artefacts (txt, srt, vtt, json, …).
- `DELETE /api/jobs/{job_id}` – cancel a running job.
- `DELETE /api/jobs/{job_id}/files` – prune cached artefacts.

All responses are JSON. Errors return a `detail` message.

## Frontend tour
Static assets live in `frontend/` and are served directly by FastAPI. Highlights:

- **Engine selector** toggles between local Metal execution and OpenAI/Gemini offload (key supplied per request).
- **Quality presets** adjust beam search, best-of, and temperature in one click.
- **Advanced toggles** enable diarization, TinyDiarize, VAD (with optional Silero model), timestamp suppression, translation, and filler-word scrubbing.
- **Batch combine** switch bundles every file in a multi-upload into a single transcript box with filename dividers—perfect for rapid copy/paste.
- **Archive controls** move completed jobs out of the active queue (one-click “Archive completed” or per-job archive/restore) while keeping artefacts downloadable from the archive view.
- **Job queue** shows progress bars fed by whisper.cpp’ s progress callback. You can cancel or reopen finished transcripts without re-running them.
- **Transcript viewer** renders the full text, timestamps, and segments, and surfaces download buttons for TXT/SRT/VTT/JSON.
- **Recorder** captures a quick voice memo using the MediaRecorder API and drops it into the queue.

Everything is plain ES modules & CSS—no build step required.

## Building a distributable DMG

The repository ships with a packaging helper for macOS releases.

```bash
# Ensure dependencies are installed and whisper.cpp is built first
make bootstrap

# Clean cached outputs and build a DMG under dist/
make package-dmg
```

The script copies the project (excluding caches, virtualenvs, etc.), drops a
`Start Whisper.command` launcher into the DMG root, and produces
`dist/WhisperMetalControlCenter.dmg`. Upload that file to GitHub releases for
easy one-click installs.

Recipients simply mount the DMG, drag the folder anywhere, and double-click the
launcher. The terminal window that opens handles the first-time bootstrap and
starts the server before opening the UI in the default browser.

### Toward a standalone app (Phase 3)

Phase 3 will turn this into a fully self-contained macOS app bundle (no manual
Python/ffmpeg installs). The high-level plan—embedding the Python runtime,
bundling whisper.cpp, and generating a `.app` + notarised DMG—is tracked in
`docs/standalone-roadmap.md`.

## Tips & troubleshooting
- **Metal build issues** → ensure the Xcode Command Line Tools are installed and re-run `./scripts/setup_whisper_cpp.sh`.
- **Progress never updates** → confirm the binary is the latest whisper.cpp build; `--print-progress` is required.
- **`ffmpeg is required`** → install with `brew install ffmpeg`; it is used for WAV conversion.
- **Cloud offload fails** → verify `engine=openai` and that an API key is supplied via the form or `WHISPER_APP_OPENAI_API_KEY`.
- **Quantized models** → quantize with `whisper-cli quantize ...` and they’ll appear in the model dropdown automatically.

## Roadmap
- Optional auth & per-user job storage
- WebSocket/SSE progress streaming instead of polling
- Gemini offload implementation once the official audio endpoint stabilises
