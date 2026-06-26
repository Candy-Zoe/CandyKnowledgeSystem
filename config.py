import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
MODEL_DIR = DATA_DIR / "models"
CUSTOM_MODEL_DIR = DATA_DIR / "custom_models"
DB_PATH = DATA_DIR / "knowledge.db"
SETTINGS_FILE = DATA_DIR / "settings.json"

EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
EMBEDDING_DIMENSION = 512

CHUNK_SIZE = 512
CHUNK_OVERLAP = 64
CHUNK_STRATEGY = "semantic"

TOP_K = 5
SIMILARITY_THRESHOLD = 0.3

RETRIEVAL_MODE = "hybrid"
BM25_WEIGHT = 0.3
VECTOR_WEIGHT = 0.7

RERANK_ENABLED = False
RERANK_MODEL = "BAAI/bge-reranker-base"

DEFAULT_BASE_MODEL = "Qwen/Qwen2-1.5B"
DEFAULT_LORA_RANK = 16
DEFAULT_EPOCHS = 3
DEFAULT_BATCH_SIZE = 4
DEFAULT_LR = 2e-4

SECRET_KEY = os.getenv("SECRET_KEY", "candy-knowledge-dev-key")
MAX_UPLOAD_SIZE = 200 * 1024 * 1024

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
CUSTOM_MODEL_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS = {
    "model_source": "local",
    "local_model_path": "",
    "api_provider": "qwen",
    "api_key": "",
    "api_model": "qwen-turbo",
    "api_base_url": "",
    "chunk_strategy": "semantic",
    "chunk_size": 512,
    "chunk_overlap": 64,
    "retrieval_mode": "hybrid",
    "vector_weight": 0.7,
    "bm25_weight": 0.3,
    "top_k": 5,
    "similarity_threshold": 0.3,
    "embedding_model": "BAAI/bge-small-zh-v1.5",
    "temperature": 0.7,
    "max_tokens": 1024,
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
