from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QPlainTextEdit, QScrollArea, QRadioButton, QButtonGroup, QMessageBox
)
from PySide6.QtCore import Qt, QThread
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from core.rag_engine import RAGEngine
from core.embedding_engine import EmbeddingEngine
from gui.widgets.chat_bubble import ChatBubble
from gui.workers.qa_worker import QAWorker


class QAPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.history = []
        self.worker = None
        self.thread = None
        self.current_bubble = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("智能问答")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)

        top_row = QHBoxLayout()
        self.model_label = QLabel("模型状态: 未加载")
        self.model_label.setStyleSheet("color: #a6adc8;")
        top_row.addWidget(self.model_label)
        top_row.addStretch()

        mode_label = QLabel("检索模式:")
        top_row.addWidget(mode_label)
        self.mode_group = QButtonGroup()
        self.vector_radio = QRadioButton("向量")
        self.bm25_radio = QRadioButton("BM25")
        self.hybrid_radio = QRadioButton("混合")
        self.hybrid_radio.setChecked(True)
        self.mode_group.addButton(self.vector_radio, 0)
        self.mode_group.addButton(self.bm25_radio, 1)
        self.mode_group.addButton(self.hybrid_radio, 2)
        top_row.addWidget(self.vector_radio)
        top_row.addWidget(self.bm25_radio)
        top_row.addWidget(self.hybrid_radio)
        self.mode_group.buttonClicked.connect(self.on_mode_changed)
        layout.addLayout(top_row)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.setSpacing(8)
        self.chat_scroll.setWidget(self.chat_container)
        layout.addWidget(self.chat_scroll, 1)

        input_row = QHBoxLayout()
        self.input_box = QPlainTextEdit()
        self.input_box.setPlaceholderText("输入你的问题...")
        self.input_box.setMaximumHeight(80)
        self.input_box.installEventFilter(self)
        self.send_btn = QPushButton("发送")
        self.send_btn.setFixedWidth(80)
        self.send_btn.clicked.connect(self.send_question)
        input_row.addWidget(self.input_box, 1)
        input_row.addWidget(self.send_btn)
        layout.addLayout(input_row)

    def eventFilter(self, obj, event):
        if obj == self.input_box and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key_Return and not event.modifiers() & Qt.ShiftModifier:
                self.send_question()
                return True
        return super().eventFilter(obj, event)

    def send_question(self):
        question = self.input_box.toPlainText().strip()
        if not question:
            return

        self.add_bubble(question, "user")
        self.input_box.clear()
        self.send_btn.setEnabled(False)

        self.current_bubble = self.add_bubble("思考中...", "assistant")

        self.worker = QAWorker(question, history=self.history)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.chunk_received.connect(self.on_chunk)
        self.worker.sources_received.connect(self.on_sources)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)

        self.thread.start()

    def add_bubble(self, content, role, sources=None):
        bubble = ChatBubble(content, role, sources)
        self.chat_layout.addWidget(bubble)
        self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        )
        return bubble

    def on_chunk(self, text):
        if self.current_bubble:
            label = self.current_bubble.findChild(QLabel, "contentLabel")
            if label:
                current = label.text()
                if current == "思考中...":
                    label.setText(text)
                else:
                    label.setText(current + text)

    def on_sources(self, sources):
        pass

    def on_finished(self, answer):
        self.send_btn.setEnabled(True)
        if self.current_bubble:
            label = self.current_bubble.findChild(QLabel, "contentLabel")
            if label:
                label.setText(answer)

        if self.chat_layout.count() > 1:
            user_bubble = self.chat_layout.itemAt(self.chat_layout.count() - 2).widget()
            if user_bubble:
                user_label = user_bubble.findChild(QLabel, "contentLabel")
                user_text = user_label.text() if user_label else ""
            else:
                user_text = ""
        else:
            user_text = ""
        self.history.append({"user": user_text, "assistant": answer})
        self.current_bubble = None

    def on_error(self, msg):
        self.send_btn.setEnabled(True)
        if self.current_bubble:
            label = self.current_bubble.findChild(QLabel, "contentLabel")
            if label:
                label.setText(f"错误: {msg}")
        self.current_bubble = None
        QMessageBox.warning(self, "问答错误", msg)

    def on_mode_changed(self):
        mode_map = {0: "vector", 1: "bm25", 2: "hybrid"}
        mode = mode_map[self.mode_group.checkedId()]
        try:
            settings = config.load_settings()
            settings["retrieval_mode"] = mode
            config.save_settings(settings)
        except Exception:
            pass
