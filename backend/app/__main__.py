import os

import uvicorn


def _should_reload() -> bool:
    return os.getenv("WHISPER_APP_RELOAD", "0") in {"1", "true", "True"}


if __name__ == "__main__":
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=_should_reload(),
    )
