"""
文档编辑 Worker - 处理文档内容编辑后的重新分块和嵌入

流程：
1. 删除文档旧分块
2. 用 TextProcessor 重新分块
3. 用 EmbeddingEngine 生成嵌入
4. 保存新分块到数据库
5. 更新文档状态
"""
from PySide6.QtCore import QObject, Signal
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from core.text_processor import TextProcessor
from core.embedding_engine import EmbeddingEngine
from core.logger import log


class EditDocumentWorker(QObject):
    progress = Signal(int)  # 百分比 0-100
    finished = Signal()     # 完成
    error = Signal(str)     # 错误信息

    def __init__(self, doc_id: int, new_content: str):
        super().__init__()
        self.doc_id = doc_id
        self.new_content = new_content
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        log.info(f"开始编辑文档 ID={self.doc_id}, 新内容长度={len(self.new_content)} 字符")
        try:
            self.progress.emit(5)
            db = DatabaseManager(str(config.DB_PATH))
            settings = config.load_settings()

            torch_threads = settings.get("torch_threads", config.DEFAULT_SETTINGS["torch_threads"])
            embedding_batch_size = settings.get("embedding_batch_size", config.DEFAULT_SETTINGS["embedding_batch_size"])
            chunk_size = settings.get("chunk_size", config.CHUNK_SIZE)
            chunk_overlap = settings.get("chunk_overlap", config.CHUNK_OVERLAP)

            # 1. 删除旧分块
            log.info("删除旧分块...")
            db.delete_document_chunks(self.doc_id)
            self.progress.emit(15)

            if self._cancelled:
                return

            # 2. 重新分块
            log.info("重新分块...")
            text_processor = TextProcessor(chunk_size, chunk_overlap)
            chunks = text_processor.chunk_text(self.new_content)
            self.progress.emit(35)

            if self._cancelled:
                return

            # 3. 生成嵌入
            log.info(f"生成嵌入向量，共 {len(chunks)} 个分块...")
            emb_engine = EmbeddingEngine(
                settings.get("embedding_model", config.EMBEDDING_MODEL),
                torch_threads=torch_threads,
                batch_size=embedding_batch_size
            )

            chunk_texts = [c["content"] for c in chunks]
            embeddings = emb_engine.embed_batch(chunk_texts)
            self.progress.emit(70)

            if self._cancelled:
                return

            # 4. 组装分块数据
            chunk_data = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_data.append({
                    "chunk_index": i,
                    "content": chunk["content"],
                    "token_count": chunk.get("token_count", 0),
                    "embedding": embedding,
                })

            # 5. 保存新分块
            log.info("保存新分块到数据库...")
            db.create_chunks(self.doc_id, chunk_data)
            self.progress.emit(90)

            # 6. 更新文档状态
            db.update_document_status(self.doc_id, "completed")
            db.update_document_chunks(self.doc_id, len(chunk_data))
            self.progress.emit(100)

            log.info(f"文档编辑完成 ID={self.doc_id}, 新分块数={len(chunk_data)}")
            self.finished.emit()

        except Exception as e:
            log.error(f"文档编辑失败: {e}")
            # 尝试恢复状态
            try:
                db = DatabaseManager(str(config.DB_PATH))
                db.update_document_status(self.doc_id, "edit_failed", str(e))
            except Exception:
                pass
            self.error.emit(str(e))
