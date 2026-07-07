from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QTextEdit, QMessageBox
)
from PySide6.QtCore import QThread
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from gui.workers.summary_worker import SummaryWorker


class SummaryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.thread = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("文档摘要")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)

        select_row = QHBoxLayout()
        select_row.addWidget(QLabel("选择文档:"))
        self.doc_combo = QComboBox()
        self.doc_combo.setMinimumWidth(300)
        self.doc_combo.currentIndexChanged.connect(self.on_doc_selected)
        select_row.addWidget(self.doc_combo)
        select_row.addStretch()
        layout.addLayout(select_row)

        btn_row = QHBoxLayout()
        self.generate_btn = QPushButton("生成摘要")
        self.generate_btn.clicked.connect(self.generate_summary)
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.save_summary)
        self.save_btn.setEnabled(False)
        btn_row.addWidget(self.generate_btn)
        btn_row.addWidget(self.save_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.result_edit = QTextEdit()
        self.result_edit.setReadOnly(True)
        self.result_edit.setPlaceholderText("摘要结果将显示在这里...")
        layout.addWidget(self.result_edit, 1)

    def showEvent(self, event):
        super().showEvent(event)
        self.load_documents()

    def load_documents(self):
        self.doc_combo.clear()
        try:
            db = DatabaseManager(str(config.DB_PATH))
            docs = db.list_documents()
            for doc in docs:
                if doc["status"] == "completed":
                    self.doc_combo.addItem(doc["original_name"], doc["id"])
        except Exception:
            pass

    def on_doc_selected(self, index):
        doc_id = self.doc_combo.currentData()
        if doc_id:
            try:
                db = DatabaseManager(str(config.DB_PATH))
                summary = db.get_summary(doc_id)
                if summary:
                    self.result_edit.setPlainText(summary)
                    self.save_btn.setEnabled(False)
                else:
                    self.result_edit.clear()
            except Exception:
                pass

    def generate_summary(self):
        doc_id = self.doc_combo.currentData()
        if not doc_id:
            QMessageBox.warning(self, "提示", "请先选择文档")
            return

        self.generate_btn.setEnabled(False)
        self.result_edit.setPlainText("正在生成摘要...")

        self.worker = SummaryWorker(doc_id)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)

        self.thread.start()

    def on_finished(self, summary):
        self.generate_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.result_edit.setPlainText(summary)

    def on_error(self, msg):
        self.generate_btn.setEnabled(True)
        self.result_edit.setPlainText(f"错误: {msg}")
        QMessageBox.warning(self, "摘要错误", msg)

    def save_summary(self):
        doc_id = self.doc_combo.currentData()
        if not doc_id:
            return
        summary = self.result_edit.toPlainText()
        if not summary:
            return
        try:
            db = DatabaseManager(str(config.DB_PATH))
            db.save_summary(doc_id, summary)
            self.save_btn.setEnabled(False)
            QMessageBox.information(self, "成功", "摘要已保存")
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))
