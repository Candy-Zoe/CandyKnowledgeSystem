from PySide6.QtCore import QObject, Signal
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from core.document_parser import DocumentParser
from core.text_processor import TextProcessor
from core.embedding_engine import EmbeddingEngine


class UploadWorker(QObject):
    progress = Signal(int, int)  # (file_index, percent)
    file_done = Signal(int, str, str)  # (doc_id, status, message)
    all_done = Signal()
    error = Signal(str)

    def __init__(self, file_paths, kb_id=None):
        super().__init__()
        self.file_paths = file_paths
        self.kb_id = kb_id
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            db = DatabaseManager(str(config.DB_PATH))
            parser = DocumentParser()
            settings = config.load_settings()
            text_processor = TextProcessor(
                settings.get("chunk_size", config.CHUNK_SIZE),
                settings.get("chunk_overlap", config.CHUNK_OVERLAP)
            )
            emb_engine = EmbeddingEngine(settings.get("embedding_model", config.EMBEDDING_MODEL))

            for i, file_path in enumerate(self.file_paths):
                if self._cancelled:
                    break

                try:
                    filename = os.path.basename(file_path)
                    file_size = os.path.getsize(file_path)
                    ext = os.path.splitext(filename)[1].lower()
                    file_type = ext.lstrip('.')

                    doc_id = db.create_document(
                        filename=filename,
                        original_name=filename,
                        file_type=file_type,
                        file_size=file_size,
                        file_path=file_path,
                        kb_id=self.kb_id
                    )
                    db.update_document_status(doc_id, "processing")
                    self.progress.emit(i, 0)

                    text = parser.parse(file_path, file_type)
                    if not text:
                        db.update_document_status(doc_id, "failed", "无法提取文本内容")
                        self.file_done.emit(doc_id, "failed", "无法提取文本内容")
                        continue

                    self.progress.emit(i, 30)

                    chunks = text_processor.chunk_text(text)
                    if not chunks:
                        db.update_document_status(doc_id, "failed", "文本分块失败")
                        self.file_done.emit(doc_id, "failed", "文本分块失败")
                        continue

                    self.progress.emit(i, 50)

                    contents = [c["content"] for c in chunks]
                    embeddings = emb_engine.embed_batch(contents, batch_size=64)

                    for j, chunk in enumerate(chunks):
                        chunk["embedding"] = embeddings[j]

                    self.progress.emit(i, 80)

                    db.create_chunks(doc_id, chunks)
                    db.update_document_chunks(doc_id, len(chunks))
                    db.update_document_status(doc_id, "completed")
                    db.update_document_status(doc_id, "completed")

                    self.progress.emit(i, 100)
                    self.file_done.emit(doc_id, "completed", f"成功处理 {len(chunks)} 个分块")

                except Exception as e:
                    try:
                        db.update_document_status(doc_id, "failed", str(e))
                    except Exception:
                        pass
                    self.file_done.emit(0, "failed", str(e))

            self.all_done.emit()

        except Exception as e:
            self.error.emit(str(e))
