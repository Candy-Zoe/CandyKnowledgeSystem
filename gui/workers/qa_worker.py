from PySide6.QtCore import QObject, Signal
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from core.embedding_engine import EmbeddingEngine
from core.rag_engine import RAGEngine
from core.logger import log


class QAWorker(QObject):
    chunk_received = Signal(str)
    sources_received = Signal(list)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, question, history=None):
        super().__init__()
        self.question = question
        self.history = history or []

    def run():
        log.info(f"收到问题: {self.question}")
        try:
            settings = config.load_settings()
            db = DatabaseManager(str(config.DB_PATH))
            emb_engine = EmbeddingEngine(settings.get("embedding_model", config.EMBEDDING_MODEL))
            rag = RAGEngine(db, emb_engine)
            rag.load_settings(settings)
            log.info("RAG引擎初始化完成")

            chunks = db.get_all_chunks_with_embeddings()
            if not chunks:
                log.warning("知识库中暂无数据")
                self.finished.emit("知识库中暂无数据，请先上传文档。")
                return
            log.info(f"知识库中有 {len(chunks)} 个分块")

            results = rag.retrieve(self.question, top_k=5)
            log.info(f"检索到 {len(results)} 个相关分块")

            # 构建引用信息，包含文档和分块的详细字段
            sources = []
            for r in results:
                chunk = r["chunk"]
                sources.append({
                    "chunk_id": chunk["id"],
                    "document_id": chunk.get("document_id"),
                    "document": chunk.get("original_name", "Unknown"),
                    "file_type": chunk.get("file_type", ""),
                    "file_path": chunk.get("file_path", ""),
                    "chunk_index": chunk.get("chunk_index", 0),
                    "total_chunks": chunk.get("total_chunks", 0),
                    "content_preview": chunk["content"][:300],
                    "score": round(r["score"], 4),
                })
            self.sources_received.emit(sources)

            full_answer = ""
            for chunk_text in rag.generate_answer_stream(self.question, results, history=self.history):
                full_answer += chunk_text
                self.chunk_received.emit(chunk_text)

            log.info(f"回答生成完成: {len(full_answer)} 字符")
            self.finished.emit(full_answer)

        except Exception as e:
            log.error(f"问答失败: {e}")
            self.error.emit(str(e))
