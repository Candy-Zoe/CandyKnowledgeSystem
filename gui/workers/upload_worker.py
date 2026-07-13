from PySide6.QtCore import QObject, Signal
import sys
import os
import gc
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from core.document_parser import DocumentParser
from core.text_processor import TextProcessor
from core.embedding_engine import EmbeddingEngine
from core.logger import log


class UploadWorker(QObject):
    progress = Signal(int, int)  # (file_index, percent)
    page_progress = Signal(str)  # 当前正在处理的页面信息
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
        log.info(f"开始上传任务，共 {len(self.file_paths)} 个文件")
        try:
            db = DatabaseManager(str(config.DB_PATH))
            settings = config.load_settings()

            # 从设置中读取 CPU 节流参数
            torch_threads = settings.get("torch_threads", config.DEFAULT_SETTINGS["torch_threads"])
            page_sleep_ms = settings.get("page_sleep_ms", config.DEFAULT_SETTINGS["page_sleep_ms"])
            max_pdf_pages = settings.get("max_pdf_pages", config.DEFAULT_SETTINGS["max_pdf_pages"])
            embedding_batch_size = settings.get("embedding_batch_size", config.DEFAULT_SETTINGS["embedding_batch_size"])

            log.info(f"CPU 节流设置: threads={torch_threads}, sleep={page_sleep_ms}ms, "
                     f"max_pages={max_pdf_pages}, batch_size={embedding_batch_size}")

            parser = DocumentParser(max_pages=max_pdf_pages, page_sleep_ms=page_sleep_ms)
            text_processor = TextProcessor(
                settings.get("chunk_size", config.CHUNK_SIZE),
                settings.get("chunk_overlap", config.CHUNK_OVERLAP)
            )
            emb_engine = EmbeddingEngine(
                settings.get("embedding_model", config.EMBEDDING_MODEL),
                torch_threads=torch_threads,
                batch_size=embedding_batch_size
            )
            log.info("初始化完成: 数据库、解析器、分词器、嵌入引擎")

            for i, file_path in enumerate(self.file_paths):
                if self._cancelled:
                    log.info("上传任务已取消")
                    break

                filename = os.path.basename(file_path)
                file_size = os.path.getsize(file_path)
                ext = os.path.splitext(filename)[1].lower()
                file_type = ext.lstrip('.')
                log.info(f"[{i+1}/{len(self.file_paths)}] 处理文件: {filename} ({file_type}, {file_size} bytes)")

                # 检查文件大小限制
                max_size = settings.get("max_file_size_mb", config.DEFAULT_SETTINGS["max_file_size_mb"]) * 1024 * 1024
                if file_size > max_size:
                    msg = f"文件过大 ({file_size // 1024 // 1024}MB > {max_size // 1024 // 1024}MB)"
                    log.warning(f"  {filename}: {msg}")
                    self.file_done.emit(0, "failed", msg)
                    continue

                try:
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
                    log.info(f"  创建文档记录: doc_id={doc_id}")

                    self.page_progress.emit("正在解析文档...")
                    text = parser.parse(file_path, file_type)
                    if not text:
                        db.update_document_status(doc_id, "failed", "无法提取文本内容")
                        self.file_done.emit(doc_id, "failed", "无法提取文本内容")
                        log.warning(f"  {filename}: 无法提取文本内容")
                        continue
                    log.info(f"  文本提取完成: {len(text)} 字符")

                    self.progress.emit(i, 30)
                    self.page_progress.emit("正在分块...")

                    chunks = text_processor.chunk_text(text)
                    if not chunks:
                        db.update_document_status(doc_id, "failed", "文本分块失败")
                        self.file_done.emit(doc_id, "failed", "文本分块失败")
                        log.warning(f"  {filename}: 文本分块失败")
                        continue
                    log.info(f"  分块完成: {len(chunks)} 个块")

                    self.progress.emit(i, 50)
                    self.page_progress.emit(f"正在生成嵌入 ({len(chunks)} 块)...")

                    contents = [c["content"] for c in chunks]
                    embeddings = emb_engine.embed_batch(contents)
                    log.info(f"  嵌入生成完成")

                    for j, chunk in enumerate(chunks):
                        chunk["embedding"] = embeddings[j]

                    self.progress.emit(i, 80)
                    self.page_progress.emit("正在保存到数据库...")

                    db.create_chunks(doc_id, chunks)
                    db.update_document_chunks(doc_id, len(chunks))
                    db.update_document_status(doc_id, "completed")
                    log.info(f"  {filename}: 处理完成，{len(chunks)} 个分块已保存")

                    self.progress.emit(i, 100)
                    self.file_done.emit(doc_id, "completed", f"成功处理 {len(chunks)} 个分块")

                    # 处理完一个文件后回收内存
                    gc.collect()

                except Exception as e:
                    log.error(f"  {filename}: 处理失败 - {e}")
                    try:
                        db.update_document_status(doc_id, "failed", str(e))
                    except Exception:
                        pass
                    self.file_done.emit(0, "failed", str(e))

            self.all_done.emit()
            log.info("上传任务全部完成")

        except Exception as e:
            log.error(f"上传任务异常: {e}")
            self.error.emit(str(e))
