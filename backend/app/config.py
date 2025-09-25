from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    whisper_root: Path = Path("vendor/whisper.cpp").resolve()
    whisper_binary: Path | None = None
    whisper_model: Path = Path("vendor/whisper.cpp/models/ggml-base.en.bin").resolve()
    whisper_threads: int = 4
    whisper_extra_args: list[str] = []
    storage_dir: Path = Path("storage").resolve()
    default_output_formats: list[str] = ["json", "txt", "srt"]
    max_concurrent_jobs: int = 2
    allow_cloud_offload: bool = True
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    filler_words: list[str] = [
        "uh",
        "um",
        "you know",
        "like",
        "i mean",
    ]

    class Config:
        env_prefix = "WHISPER_APP_"
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def binary_path(self) -> Path:
        if self.whisper_binary:
            return Path(self.whisper_binary).resolve()
        return (self.whisper_root / "build/bin/whisper-cli").resolve()

    @property
    def resources_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "resources"

    @property
    def models_dir(self) -> Path:
        return self.whisper_root / "models"


settings = Settings()
