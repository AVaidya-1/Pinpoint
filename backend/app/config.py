import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

DATA_DIR = Path(os.getenv("EVIDENCE_DATA_DIR", "./data")).resolve()
UPLOADS_DIR = DATA_DIR / "uploads"
PAGES_DIR = DATA_DIR / "pages"
ORIGINALS_DIR = DATA_DIR / "originals"
DB_PATH = DATA_DIR / "pinpoint.db"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
EVIDENCE_MODEL = os.getenv("EVIDENCE_MODEL", "google/gemma-4-31b-it:free")
MAX_PAGES = int(os.getenv("EVIDENCE_MAX_PAGES", "20"))
MAX_DOCUMENTS = int(os.getenv("EVIDENCE_MAX_DOCUMENTS", "5"))
REQUESTS_PER_MINUTE = int(os.getenv("EVIDENCE_REQUESTS_PER_MINUTE", "6"))
MAX_CALLS_PER_SEARCH = int(os.getenv("EVIDENCE_MAX_CALLS_PER_SEARCH", "60"))
MAX_CALLS_PER_DAY = int(os.getenv("EVIDENCE_MAX_CALLS_PER_DAY", "600"))
PROVIDER_TIMEOUT = int(os.getenv("EVIDENCE_PROVIDER_TIMEOUT_SECONDS", "60"))

CANONICAL_LONG_EDGE = 3000
MODEL_LONG_EDGE = 2048
MODEL_MAX_BYTES = 4 * 1024 * 1024

for d in (DATA_DIR, UPLOADS_DIR, PAGES_DIR, ORIGINALS_DIR):
    d.mkdir(parents=True, exist_ok=True)
