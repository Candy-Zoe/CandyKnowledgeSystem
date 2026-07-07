from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QListWidget, QListWidgetItem, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QPixmap
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from gui.workers.ocr_worker import OCRWorker


class OCRPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.thread = None
        self.current_image_path = None
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        left_panel = QVBoxLayout()

        title = QLabel("OCR 文字识别")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        left_panel.addWidget(title)

        btn_row = QHBoxLayout()
        self.select_btn = QPushButton("选择图片")
        self.select_btn.clicked.connect(self.select_image)
        self.process_btn = QPushButton("开始识别")
        self.process_btn.clicked.connect(self.process_image)
        self.process_btn.setEnabled(False)
        btn_row.addWidget(self.select_btn)
        btn_row.addWidget(self.process_btn)
        btn_row.addStretch()
        left_panel.addLayout(btn_row)

        self.preview_label = QLabel("请拖拽或选择图片文件")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(200)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #313244;
                border: 2px dashed #45475a;
                border-radius: 12px;
                color: #6c7086;
            }
        """)
        self.preview_label.setAcceptDrops(True)
        left_panel.addWidget(self.preview_label)

        left_panel.addWidget(QLabel("识别结果:"))
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setPlaceholderText("识别结果将显示在这里...")
        left_panel.addWidget(self.result_text, 1)

        save_btn = QPushButton("保存为文档")
        save_btn.clicked.connect(self.save_as_document)
        left_panel.addWidget(save_btn)

        layout.addLayout(left_panel, 2)

        right_panel = QVBoxLayout()
        right_panel.addWidget(QLabel("历史记录:"))
        self.history_list = QListWidget()
        self.history_list.setStyleSheet("""
            QListWidget {
                background-color: #313244;
                border-radius: 8px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
                margin: 2px;
            }
        """)
        self.history_list.currentRowChanged.connect(self.on_history_selected)
        right_panel.addWidget(self.history_list)
        layout.addLayout(right_panel, 1)

    def select_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.tiff *.gif)"
        )
        if path:
            self.load_image(path)

    def load_image(self, path):
        self.current_image_path = path
        pixmap = QPixmap(path)
        scaled = pixmap.scaled(400, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)
        self.process_btn.setEnabled(True)

    def process_image(self):
        if not self.current_image_path:
            return

        self.process_btn.setEnabled(False)
        self.result_text.setPlainText("正在识别...")

        self.worker = OCRWorker(self.current_image_path)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)

        self.thread.start()

    def on_finished(self, text):
        self.process_btn.setEnabled(True)
        self.result_text.setPlainText(text)
        self.load_history()

    def on_error(self, msg):
        self.process_btn.setEnabled(True)
        self.result_text.setPlainText(f"错误: {msg}")
        QMessageBox.warning(self, "OCR 错误", msg)

    def load_history(self):
        self.history_list.clear()
        try:
            db = DatabaseManager(str(config.DB_PATH))
            conn = db.get_connection()
            rows = conn.execute("SELECT id, image_path, substr(extracted_text, 1, 50) as preview, created_at FROM ocr_results ORDER BY created_at DESC LIMIT 20").fetchall()
            conn.close()
            for row in rows:
                item = QListWidgetItem(f"{os.path.basename(row['image_path'])} - {row['created_at']}")
                item.setData(Qt.UserRole, row["id"])
                self.history_list.addItem(item)
        except Exception:
            pass

    def on_history_selected(self, row):
        if row < 0:
            return
        item = self.history_list.item(row)
        result_id = item.data(Qt.UserRole)
        try:
            db = DatabaseManager(str(config.DB_PATH))
            conn = db.get_connection()
            row_data = conn.execute("SELECT * FROM ocr_results WHERE id=?", (result_id,)).fetchone()
            conn.close()
            if row_data:
                self.result_text.setPlainText(row_data["extracted_text"] or "")
        except Exception:
            pass

    def save_as_document(self):
        text = self.result_text.toPlainText()
        if not text:
            QMessageBox.warning(self, "提示", "没有可保存的内容")
            return
        try:
            db = DatabaseManager(str(config.DB_PATH))
            doc_id = db.create_document(
                filename=f"ocr_{len(text)}.txt",
                original_name=f"OCR结果_{text[:20]}.txt",
                file_type="txt",
                file_size=len(text.encode("utf-8")),
                file_path=self.current_image_path or ""
            )
            from core.text_processor import TextProcessor
            settings = config.load_settings()
            tp = TextProcessor(settings.get("chunk_size", 512), settings.get("chunk_overlap", 64))
            chunks = tp.chunk_text(text)
            if chunks:
                db.create_chunks(doc_id, chunks)
                db.update_document_chunks(doc_id, len(chunks))
                db.update_document_status(doc_id, "completed")
            QMessageBox.information(self, "成功", "OCR 结果已保存为文档")
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))
