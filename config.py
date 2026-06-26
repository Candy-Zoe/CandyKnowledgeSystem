import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
MODEL_DIR = DATA_DIR / "models"
DB_PATH = DATA_DIR / "knowledge.db"

EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
EMBEDDING_DIMENSION = 512

CHUNK_SIZE = 512
CHUNK_OVERLAP = 64

TOP_K = 5
SIMILARITY_THRESHOLD = 0.3

DEFAULT_BASE_MODEL = "Qwen/Qwen2-1.5B"
DEFAULT_LORA_RANK = 16
DEFAULT_EPOCHS = 3
DEFAULT_BATCH_SIZE = 4
DEFAULT_LR = 2e-4

SECRET_KEY = os.getenv("SECRET_KEY", "candy-knowledge-dev-key")
MAX_UPLOAD_SIZE = 100 * 1024 * 1024

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
