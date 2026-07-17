import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "knowledge.db"
SETTINGS_FILE = DATA_DIR / "settings.json"

# HuggingFace 国内镜像（解决下载慢/超时问题）
# 如需使用官方源，设置环境变量 HF_ENDPOINT=https://huggingface.co
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

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

SECRET_KEY = os.getenv("SECRET_KEY", "candy-knowledge-dev-key")
MAX_UPLOAD_SIZE = 200 * 1024 * 1024

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS = {
    "api_provider": "local",       # 默认：仅检索模式，无需API Key
    "api_key": "",
    "api_model": "retrieve-only",
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
    # CPU 节流设置
    "torch_threads": 2,           # PyTorch 线程数（限制 CPU 核心占用）
    "page_sleep_ms": 100,         # 每页解析后休眠毫秒数（0=不休眠）
    "max_pdf_pages": 500,         # PDF 最大处理页数（0=不限制）
    "max_file_size_mb": 200,      # 单文件最大 MB
    "embedding_batch_size": 16,   # 嵌入生成批次大小
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
