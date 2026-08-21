from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QDialog, QPlainTextEdit, QMessageBox
)
from PySide6.QtCore import Qt
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager


class SearchResultDialog(QDialog):
    def __init__(self, result: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"原文预览 - {result.get('original_name', '')}")
        self.setMinimumSize(900, 650)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; color: #cdd6f4; }
            QLabel { color: #cdd6f4; }
            QPlainTextEdit {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                padding: 8px 18px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #45475a; }
        """)

        layout = QVBoxLayout(self)
        info = QLabel(
            f"文件: {result.get('original_name', '')} | "
            f"类型: {result.get('file_type', '')} | "
            f"片段: {result.get('chunk_index', 0) + 1}/{result.get('total_chunks', 0)}"
        )
        info.setStyleSheet("color: #a6adc8; font-size: 13px;")
        layout.addWidget(info)

        path_label = QLabel(f"路径: {result.get('file_path', '')}")
        path_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        path_label.setWordWrap(True)
        layout.addWidget(path_label)

        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(self._format_context(result))
        layout.addWidget(text, 1)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

    @staticmethod
    def _format_context(result: dict) -> str:
        context = result.get("context") or [result]
        parts = []
        target_id = result.get("id")
        for chunk in context:
            marker = "命中片段" if chunk.get("id") == target_id else "上下文片段"
            parts.append(
                f"[{marker} {chunk.get('chunk_index', 0) + 1}]\n"
                f"{chunk.get('content', '')}"
            )
        return "\n\n".join(parts)


class SearchPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.results = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("内容检索")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)

        search_row = QHBoxLayout()
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("输入一个或多个关键词，用空格或逗号分隔")
        self.keyword_input.returnPressed.connect(self.search)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("全部关键词", "all")
        self.mode_combo.addItem("任一关键词", "any")

        self.kb_combo = QComboBox()
        self.kb_combo.setMinimumWidth(160)

        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self.search)

        search_row.addWidget(self.keyword_input, 1)
        search_row.addWidget(self.mode_combo)
        search_row.addWidget(self.kb_combo)
        search_row.addWidget(search_btn)
        layout.addLayout(search_row)

        self.status_label = QLabel("输入关键词后搜索，双击结果查看原文上下文。")
        self.status_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        layout.addWidget(self.status_label)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["文件", "类型", "片段", "命中词", "摘要", "路径"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.doubleClicked.connect(self.open_selected)
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        open_btn = QPushButton("查看原文")
        open_btn.clicked.connect(self.open_selected)
        refresh_btn = QPushButton("刷新知识库")
        refresh_btn.clicked.connect(self.load_knowledge_bases)
        btn_row.addWidget(open_btn)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def showEvent(self, event):
        super().showEvent(event)
        self.load_knowledge_bases()

    def load_knowledge_bases(self):
        current = self.kb_combo.currentData()
        self.kb_combo.clear()
        self.kb_combo.addItem("所有知识库", None)
        try:
            db = DatabaseManager(str(config.DB_PATH))
            for kb in db.list_knowledge_bases():
                self.kb_combo.addItem(kb["name"], kb["id"])
        except Exception:
            pass
        if current is not None:
            idx = self.kb_combo.findData(current)
            if idx >= 0:
                self.kb_combo.setCurrentIndex(idx)

    def search(self):
        keywords = self.keyword_input.text().strip()
        if not keywords:
            QMessageBox.information(self, "提示", "请输入关键词")
            return

        try:
            db = DatabaseManager(str(config.DB_PATH))
            self.results = db.search_content(
                keywords,
                kb_id=self.kb_combo.currentData(),
                match_mode=self.mode_combo.currentData(),
            )
            self.populate_table()
            self.status_label.setText(f"找到 {len(self.results)} 条相关内容")
        except Exception as e:
            QMessageBox.warning(self, "搜索失败", str(e))

    def populate_table(self):
        self.table.setRowCount(len(self.results))
        for row, item in enumerate(self.results):
            self.table.setItem(row, 0, QTableWidgetItem(item.get("original_name", "")))
            self.table.setItem(row, 1, QTableWidgetItem(item.get("file_type", "")))
            chunk_text = f"{item.get('chunk_index', 0) + 1}/{item.get('total_chunks', 0)}"
            self.table.setItem(row, 2, QTableWidgetItem(chunk_text))
            self.table.setItem(row, 3, QTableWidgetItem(", ".join(item.get("matched_terms", []))))
            self.table.setItem(row, 4, QTableWidgetItem(item.get("snippet", "")))
            self.table.setItem(row, 5, QTableWidgetItem(item.get("file_path", "")))
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(4, 520)

    def open_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.results):
            QMessageBox.information(self, "提示", "请先选择一条结果")
            return
        try:
            db = DatabaseManager(str(config.DB_PATH))
            detail = db.get_chunk_context(self.results[row]["id"], radius=2)
            dialog = SearchResultDialog(detail, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))
