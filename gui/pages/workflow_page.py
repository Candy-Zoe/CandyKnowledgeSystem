from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QListWidget, QProgressBar, QMessageBox,
    QTextEdit, QComboBox, QLineEdit
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QTextCursor
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from core.document_parser import DocumentParser
from core.text_processor import TextProcessor
from core.embedding_engine import EmbeddingEngine


class WizardWorker(QObject):
    log = Signal(str)
    progress = Signal(int, int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, file_paths, kb_id, do_finetune=False):
        super().__init__()
        self.file_paths = file_paths
        self.kb_id = kb_id
        self.do_finetune = do_finetune

    def run(self):
        try:
            db = DatabaseManager(str(config.DB_PATH))
            settings = config.load_settings()
            parser = DocumentParser()
            text_processor = TextProcessor(
                settings.get("chunk_size", config.CHUNK_SIZE),
                settings.get("chunk_overlap", config.CHUNK_OVERLAP)
            )

            total_steps = 2 + (1 if self.do_finetune else 0)

            self.progress.emit(1, total_steps)
            self.log.emit("Step 1: 解析 PDF 文件...")

            doc_ids = []
            all_chunks = []
            for i, file_path in enumerate(self.file_paths):
                filename = os.path.basename(file_path)
                file_size = os.path.getsize(file_path)
                ext = os.path.splitext(filename)[1].lower()
                file_type = ext.lstrip('.')

                doc_id = db.create_document(
                    filename=filename, original_name=filename,
                    file_type=file_type, file_size=file_size,
                    file_path=file_path, kb_id=self.kb_id
                )
                db.update_document_status(doc_id, "processing")
                doc_ids.append(doc_id)

                try:
                    text = parser.parse(file_path, file_type)
                    if not text:
                        db.update_document_status(doc_id, "failed", "无法提取文本")
                        self.log.emit("  X %s: 无法提取文本" % filename)
                        continue

                    self.log.emit("  OK %s: %d 字" % (filename, len(text)))

                    chunks = text_processor.chunk_text(text)
                    if not chunks:
                        db.update_document_status(doc_id, "failed", "分块失败")
                        continue

                    self.log.emit("  OK 分成 %d 个块" % len(chunks))

                    emb_engine = EmbeddingEngine(settings.get("embedding_model", config.EMBEDDING_MODEL))
                    contents = [c["content"] for c in chunks]
                    embeddings = emb_engine.embed_batch(contents, batch_size=64)

                    for j, chunk in enumerate(chunks):
                        chunk["embedding"] = embeddings[j]

                    db.create_chunks(doc_id, chunks)
                    db.update_document_chunks(doc_id, len(chunks))
                    db.update_document_status(doc_id, "completed")

                    all_chunks.extend(chunks)
                    self.log.emit("  OK 嵌入完成")

                except Exception as e:
                    db.update_document_status(doc_id, "failed", str(e))
                    self.log.emit("  X %s: %s" % (filename, str(e)))

            self.progress.emit(2, total_steps)
            self.log.emit("")
            self.log.emit("Step 2: 知识库构建完成!")
            self.log.emit("  文档: %d 个" % len(doc_ids))
            self.log.emit("  分块: %d 个" % len(all_chunks))

            if self.do_finetune and all_chunks:
                self.progress.emit(3, total_steps)
                self.log.emit("")
                self.log.emit("Step 3: 训练自定义模型...")

                training_pairs = []
                for chunk in all_chunks[:50]:
                    content = chunk["content"]
                    if len(content) < 50:
                        continue
                    question = "请解释以下内容: %s" % content[:200]
                    answer = content[:500]
                    db.create_training_pair(question, answer, [chunk["id"]], chunk.get("document_id"), True)
                    training_pairs.append({"question": question, "answer": answer})

                self.log.emit("  训练数据: %d 对" % len(training_pairs))

                from core.finetune_engine import FinetuneEngine
                engine = FinetuneEngine()
                model_name = "my_kb_model"
                base_model = config.DEFAULT_BASE_MODEL
                epochs = 3
                lora_rank = 16

                job_id = db.create_finetune_job(model_name, base_model, len(training_pairs), epochs, lora_rank)
                db.update_finetune_job(job_id, status="training")

                try:
                    def progress_callback(current, total):
                        self.log.emit("  Epoch %d/%d" % (current, total))

                    output_path = engine.train(
                        training_pairs=training_pairs,
                        model_name=model_name,
                        base_model=base_model,
                        lora_rank=lora_rank,
                        epochs=epochs,
                        batch_size=config.DEFAULT_BATCH_SIZE,
                        learning_rate=config.DEFAULT_LR,
                        progress_callback=progress_callback
                    )

                    db.update_finetune_job(job_id, status="completed", output_path=output_path)
                    self.log.emit("  OK 模型训练完成!")
                except Exception as e:
                    db.update_finetune_job(job_id, status="failed", error_message=str(e))
                    self.log.emit("  X 训练失败: %s" % str(e))

            self.finished.emit("全部完成!")

        except Exception as e:
            self.error.emit(str(e))


class WorkflowPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_paths = []
        self.worker = None
        self.thread = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(24)
        layout.setContentsMargins(60, 40, 60, 40)

        title = QLabel("Candy 知识库")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #89b4fa;")
        layout.addWidget(title)

        subtitle = QLabel("上传 PDF -> 构建知识库 -> 开始问答")
        subtitle.setStyleSheet("color: #a6adc8; font-size: 15px; margin-bottom: 10px;")
        layout.addWidget(subtitle)

        # 文件选择
        file_label = QLabel("1. 选择 PDF 文件")
        file_label.setStyleSheet("color: #a6e3a1; font-size: 16px; font-weight: bold; padding-top: 10px;")
        layout.addWidget(file_label)

        file_row = QHBoxLayout()
        self.select_btn = QPushButton("选择 PDF 文件")
        self.select_btn.setFixedHeight(48)
        self.select_btn.setStyleSheet("""
            QPushButton {
                background-color: #a6e3a1;
                color: #1e1e2e;
                font-size: 16px;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 0 32px;
            }
            QPushButton:hover { background-color: #94e2d5; }
        """)
        self.select_btn.clicked.connect(self.select_files)
        file_row.addWidget(self.select_btn)

        self.file_label = QLabel("未选择文件")
        self.file_label.setStyleSheet("color: #6c7086; font-size: 14px; padding-left: 10px;")
        file_row.addWidget(self.file_label, 1)
        layout.addLayout(file_row)

        # 操作
        action_label = QLabel("2. 选择操作")
        action_label.setStyleSheet("color: #f9e2af; font-size: 16px; font-weight: bold; padding-top: 10px;")
        layout.addWidget(action_label)

        btn_row = QHBoxLayout()
        self.btn_knowledge = QPushButton("仅构建知识库")
        self.btn_knowledge.setFixedHeight(52)
        self.btn_knowledge.setStyleSheet("""
            QPushButton {
                background-color: #f9e2af;
                color: #1e1e2e;
                font-size: 16px;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 0 24px;
            }
            QPushButton:hover { background-color: #f5c2e7; }
        """)
        self.btn_knowledge.clicked.connect(lambda: self._start_workflow(False))

        self.btn_train = QPushButton("构建知识库 + 训练模型")
        self.btn_train.setFixedHeight(52)
        self.btn_train.setStyleSheet("""
            QPushButton {
                background-color: #f5c2e7;
                color: #1e1e2e;
                font-size: 16px;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 0 24px;
            }
            QPushButton:hover { background-color: #cba6f7; }
        """)
        self.btn_train.clicked.connect(lambda: self._start_workflow(True))

        btn_row.addWidget(self.btn_knowledge)
        btn_row.addWidget(self.btn_train)
        layout.addLayout(btn_row)

        # 进度
        progress_label = QLabel("3. 执行进度")
        progress_label.setStyleSheet("color: #89b4fa; font-size: 16px; font-weight: bold; padding-top: 10px;")
        layout.addWidget(progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(24)
        layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(180)
        self.log_text.setStyleSheet("background-color: #181825; font-family: Consolas, monospace; font-size: 13px; border: 1px solid #45475a; border-radius: 8px; padding: 10px;")
        layout.addWidget(self.log_text)

        # 问答
        qa_label = QLabel("4. 快速问答")
        qa_label.setStyleSheet("color: #f38ba8; font-size: 16px; font-weight: bold; padding-top: 10px;")
        layout.addWidget(qa_label)

        qa_row = QHBoxLayout()
        self.qa_input = QLineEdit()
        self.qa_input.setPlaceholderText("输入你的问题，按回车发送...")
        self.qa_input.setFixedHeight(44)
        self.qa_input.returnPressed.connect(self.quick_ask)
        qa_row.addWidget(self.qa_input)

        self.ask_btn = QPushButton("发送")
        self.ask_btn.setFixedHeight(44)
        self.ask_btn.setFixedWidth(100)
        self.ask_btn.setStyleSheet("""
            QPushButton {
                background-color: #f38ba8;
                color: #1e1e2e;
                font-size: 16px;
                font-weight: bold;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #eba0ac; }
        """)
        self.ask_btn.clicked.connect(self.quick_ask)
        qa_row.addWidget(self.ask_btn)
        layout.addLayout(qa_row)

        self.qa_log = QTextEdit()
        self.qa_log.setReadOnly(True)
        self.qa_log.setMaximumHeight(150)
        self.qa_log.setStyleSheet("background-color: #181825; font-size: 13px; border: 1px solid #45475a; border-radius: 8px; padding: 10px;")
        layout.addWidget(self.qa_log)

        layout.addStretch()

        self.load_knowledge_bases()

    def load_knowledge_bases(self):
        self.kb_combo = None
        try:
            db = DatabaseManager(str(config.DB_PATH))
            kbs = db.list_knowledge_bases()
            if kbs:
                pass
        except Exception:
            pass

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择 PDF 文件", "",
            "PDF 文件 (*.pdf);;所有文件 (*.*)"
        )
        if files:
            self.file_paths = files
            names = [os.path.basename(f) for f in files]
            if len(names) > 3:
                self.file_label.setText("已选择 %d 个文件" % len(names))
            else:
                self.file_label.setText(", ".join(names))

    def _start_workflow(self, do_finetune=False):
        if not self.file_paths:
            QMessageBox.warning(self, "提示", "请先选择 PDF 文件")
            return

        self.select_btn.setEnabled(False)
        self.btn_knowledge.setEnabled(False)
        self.btn_train.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(3 if not do_finetune else 4)
        self.progress_bar.setValue(0)
        self.log_text.clear()

        kb_id = None

        self.worker = WizardWorker(self.file_paths, kb_id, do_finetune)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.on_log)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)

        self.thread.start()

    def on_log(self, msg):
        self.log_text.append(msg)

    def on_progress(self, step, total):
        self.progress_bar.setValue(step)

    def on_finished(self, msg):
        self.select_btn.setEnabled(True)
        self.btn_knowledge.setEnabled(True)
        self.btn_train.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.log_text.append("")
        self.log_text.append("=== %s ===" % msg)

    def on_error(self, msg):
        self.select_btn.setEnabled(True)
        self.btn_knowledge.setEnabled(True)
        self.btn_train.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.log_text.append("ERROR: %s" % msg)
        QMessageBox.warning(self, "错误", msg)

    def quick_ask(self):
        question = self.qa_input.text().strip()
        if not question:
            return

        self.qa_input.clear()
        self.qa_log.append("You: %s" % question)
        self.qa_log.append("Assistant: ...")

        from gui.workers.qa_worker import QAWorker
        self.qa_worker = QAWorker(question)
        self.qa_thread = QThread()
        self.qa_worker.moveToThread(self.qa_thread)

        self.qa_thread.started.connect(self.qa_worker.run)
        self.qa_worker.chunk_received.connect(self.on_qa_chunk)
        self.qa_worker.finished.connect(self.on_qa_finished)
        self.qa_worker.error.connect(self.on_qa_error)
        self.qa_worker.finished.connect(self.qa_thread.quit)

        self.qa_thread.start()

    def on_qa_chunk(self, text):
        cursor = self.qa_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.select(QTextCursor.BlockUnderCursor)
        cursor.removeSelectedText()
        cursor.insertText("Assistant: " + text)
        self.qa_log.setTextCursor(cursor)

    def on_qa_finished(self, answer):
        cursor = self.qa_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.select(QTextCursor.BlockUnderCursor)
        cursor.removeSelectedText()
        cursor.insertText("Assistant: " + answer)
        self.qa_log.append("")

    def on_qa_error(self, msg):
        cursor = self.qa_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.select(QTextCursor.BlockUnderCursor)
        cursor.removeSelectedText()
        cursor.insertText("Error: " + msg)
