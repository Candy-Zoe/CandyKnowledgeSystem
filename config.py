import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "knowledge.db"
SETTINGS_FILE = DATA_DIR / "settings.json"

CHUNK_SIZE = 512
CHUNK_OVERLAP = 64
CHUNK_STRATEGY = "semantic"

MAX_UPLOAD_SIZE = 200 * 1024 * 1024

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS = {
    "chunk_strategy": "semantic",
    "chunk_size": 512,
    "chunk_overlap": 64,
    "page_sleep_ms": 100,
    "max_pdf_pages": 500,
    "max_file_size_mb": 200,
}


def load_settings():
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            settings = DEFAULT_SETTINGS.copy()
            settings.update(saved)
            return settings
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
