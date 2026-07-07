from PySide6.QtCore import QObject, Signal
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from core.embedding_engine import EmbeddingEngine
from core.rag_engine import RAGEngine


class ModelLoadWorker(QObject):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, model_path, model_type="finetuned"):
        super().__init__()
        self.model_path = model_path
        self.model_type = model_type

    def run(self):
        try:
            settings = config.load_settings()
            db = DatabaseManager(str(config.DB_PATH))
            emb_engine = EmbeddingEngine(settings.get("embedding_model", config.EMBEDDING_MODEL))
            rag = RAGEngine(db, emb_engine)
            rag.load_settings(settings)
            rag.load_model(self.model_path, self.model_type)
            self.finished.emit(f"模型加载成功: {self.model_path}")

        except Exception as e:
            self.error.emit(str(e))
