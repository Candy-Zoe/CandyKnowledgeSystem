from PySide6.QtCore import QObject, Signal
import uuid
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from core.embedding_engine import EmbeddingEngine
from core.rag_engine import RAGEngine


class BatchQAWorker(QObject):
    progress = Signal(int, int, str)  # (current, total, answer)
    question_done = Signal(int, str, str, list)  # (index, question, answer, sources)
    finished = Signal(str)  # batch_id
    error = Signal(str)

    def __init__(self, questions):
        super().__init__()
        self.questions = questions
        self._cancelled = False
        self.batch_id = uuid.uuid4().hex[:12]

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            settings = config.load_settings()
            db = DatabaseManager(str(config.DB_PATH))
            emb_engine = EmbeddingEngine(settings.get("embedding_model", config.EMBEDDING_MODEL))
            rag = RAGEngine(db, emb_engine)
            rag.load_settings(settings)

            total = len(self.questions)
            for i, question in enumerate(self.questions):
                if self._cancelled:
                    break

                try:
                    result = rag.query(question.strip())
                    answer = result.get("answer", "")
                    sources = result.get("sources", [])
                    db.save_batch_result(self.batch_id, question.strip(), answer, sources)
                    self.progress.emit(i + 1, total, answer)
                    self.question_done.emit(i, question.strip(), answer, sources)
                except Exception as e:
                    db.save_batch_result(self.batch_id, question.strip(), f"错误: {e}", [])
                    self.progress.emit(i + 1, total, f"错误: {e}")

            self.finished.emit(self.batch_id)

        except Exception as e:
            self.error.emit(str(e))
