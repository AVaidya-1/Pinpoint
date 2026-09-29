"""Backend configuration, read from the ignored root .env without overriding
explicit environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")
load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


class Settings:
    def __init__(self) -> None:
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
        self.nvidia_api_key = os.environ.get("NVIDIA_API_KEY", "")
        self.openrouter_key = os.environ.get("OPENROUTER_KEY", "")
        self.data_dir = Path(os.environ.get("EVIDENCE_DATA_DIR", str(_ROOT / "data")))
        if not self.data_dir.is_absolute():
            self.data_dir = (_ROOT / self.data_dir).resolve()
        self.embedding_model = os.environ.get("EVIDENCE_EMBEDDING_MODEL", "gemini-embedding-001")
        self.embedding_dims = _int("EVIDENCE_EMBEDDING_DIMS", 768)
        # 0 disables the cap. Uploads stream to disk and the viewer uses range
        # requests, so large PDFs never sit in memory whole.
        self.max_upload_mb = _int("EVIDENCE_MAX_UPLOAD_MB", 2048)
        # Seconds to wait before adding another provider in parallel;
        # whichever answers first wins.
        self.hedge_after_seconds = _int("PINPOINT_HEDGE_AFTER_SECONDS", 7)
        self.ocr_enabled = os.environ.get("EVIDENCE_OCR", "1") != "0"


def get_settings() -> Settings:
    return Settings()
