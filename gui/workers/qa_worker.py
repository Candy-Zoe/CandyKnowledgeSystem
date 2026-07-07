from PySide6.QtCore import QObject, Signal
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from core.embedding_engine import EmbeddingEngine
from core.rag_engine import RAGEngine


class QAWorker(QObject):
    chunk_received = Signal(str)
    sources_received = Signal(list)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, question, history=None):
        super().__init__()
        self.question = question
        self.history = history or []

    def run(self):
        try:
            settings = config.load_settings()
            db = DatabaseManager(str(config.DB_PATH))
            emb_engine = EmbeddingEngine(settings.get("embedding_model", config.EMBEDDING_MODEL))
            rag = RAGEngine(db, emb_engine)
            rag.load_settings(settings)

            chunks = db.get_all_chunks_with_embeddings()
            if not chunks:
                self.finished.emit("知识库中暂无数据，请先上传文档。")
                return

            results = rag.retrieve(self.question, top_k=5)

            sources = []
            for r in results:
                chunk = r["chunk"]
                sources.append({
                    "chunk_id": chunk["id"],
                    "document": chunk.get("original_name", "Unknown"),
                    "content_preview": chunk["content"][:300],
                    "score": round(r["score"], 4),
                })
            self.sources_received.emit(sources)

            full_answer = ""
            for chunk_text in rag.generate_answer_stream(self.question, results, history=self.history):
                full_answer += chunk_text
                self.chunk_received.emit(chunk_text)

            self.finished.emit(full_answer)

        except Exception as e:
            self.error.emit(str(e))
