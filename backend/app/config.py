"""Backend configuration. Reads the local ignored .env without overriding
explicit environment variables. Safe defaults per PRODUCT_BRIEF.md section 14."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # does not override explicit environment variables


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


class Settings:
    def __init__(self) -> None:
        self.gemini_api_key: str = os.environ.get("GEMINI_API_KEY", "")
        self.model: str = os.environ.get("EVIDENCE_MODEL", "gemma-4-31b-it")
        self.data_dir: Path = Path(os.environ.get("EVIDENCE_DATA_DIR", "./data"))
        self.max_pages: int = _get_int("EVIDENCE_MAX_PAGES", 20)
        self.max_documents: int = _get_int("EVIDENCE_MAX_DOCUMENTS", 5)
        self.requests_per_minute: int = _get_int("EVIDENCE_REQUESTS_PER_MINUTE", 6)
        self.max_calls_per_search: int = _get_int("EVIDENCE_MAX_CALLS_PER_SEARCH", 60)
        self.max_calls_per_day: int = _get_int("EVIDENCE_MAX_CALLS_PER_DAY", 600)
        self.provider_timeout_seconds: int = _get_int(
            "EVIDENCE_PROVIDER_TIMEOUT_SECONDS", 60
        )

    @property
    def key_present(self) -> bool:
        return bool(self.gemini_api_key)


def get_settings() -> Settings:
    """Build a fresh Settings from the current environment on every call so
    tests can isolate state with monkeypatched environment variables."""
    return Settings()
