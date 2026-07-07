from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QListWidget, QListWidgetItem, QComboBox,
    QProgressBar, QMessageBox
)
from PySide6.QtCore import Qt, QThread
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from gui.workers.upload_worker import UploadWorker


class UploadPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_paths = []
        self.worker = None
        self.thread = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("文档上传")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)

        kb_row = QHBoxLayout()
        kb_row.addWidget(QLabel("目标知识库:"))
        self.kb_combo = QComboBox()
        self.kb_combo.setMinimumWidth(200)
        kb_row.addWidget(self.kb_combo)
        kb_row.addStretch()
        layout.addLayout(kb_row)

        btn_row = QHBoxLayout()
        self.select_btn = QPushButton("选择文件")
        self.select_btn.clicked.connect(self.select_files)
        self.upload_btn = QPushButton("开始上传")
        self.upload_btn.clicked.connect(self.start_upload)
        self.upload_btn.setEnabled(False)
        btn_row.addWidget(self.select_btn)
        btn_row.addWidget(self.upload_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 8px;
                padding: 8px;
            }
            QListWidget::item {
                background-color: #1e1e2e;
                border-radius: 6px;
                padding: 8px;
                margin: 2px;
            }
        """)
        layout.addWidget(self.file_list)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        layout.addWidget(self.status_label)

    def showEvent(self, event):
        super().showEvent(event)
        self.load_knowledge_bases()

    def load_knowledge_bases(self):
        self.kb_combo.clear()
        self.kb_combo.addItem("默认知识库", None)
        try:
            db = DatabaseManager(str(config.DB_PATH))
            for kb in db.list_knowledge_bases():
                self.kb_combo.addItem(kb["name"], kb["id"])
        except Exception:
            pass

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择文件", "",
            "所有支持的文件 (*.pdf *.docx *.doc *.txt *.md);;PDF (*.pdf);;Word (*.docx *.doc);;文本 (*.txt *.md)"
        )
        if files:
            self.file_paths = files
            self.file_list.clear()
            for f in files:
                item = QListWidgetItem(os.path.basename(f))
                self.file_list.addItem(item)
            self.upload_btn.setEnabled(True)
            self.status_label.setText(f"已选择 {len(files)} 个文件")

    def start_upload(self):
        if not self.file_paths:
            return

        self.upload_btn.setEnabled(False)
        self.select_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self.file_paths))
        self.progress_bar.setValue(0)

        kb_id = self.kb_combo.currentData()

        self.worker = UploadWorker(self.file_paths, kb_id)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.file_done.connect(self.on_file_done)
        self.worker.all_done.connect(self.on_all_done)
        self.worker.error.connect(self.on_error)
        self.worker.all_done.connect(self.thread.quit)

        self.thread.start()

    def on_progress(self, file_idx, percent):
        self.progress_bar.setValue(file_idx)
        self.status_label.setText(f"正在处理第 {file_idx + 1} 个文件... ({percent}%)")

    def on_file_done(self, doc_id, status, message):
        if status == "completed":
            self.status_label.setText(f"文档处理完成: {message}")
        else:
            self.status_label.setText(f"处理失败: {message}")

    def on_all_done(self):
        self.upload_btn.setEnabled(True)
        self.select_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("所有文件上传完成")
        self.file_paths = []
        self.file_list.clear()

    def on_error(self, msg):
        self.upload_btn.setEnabled(True)
        self.select_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"错误: {msg}")
        QMessageBox.warning(self, "上传错误", msg)
