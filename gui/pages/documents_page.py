from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QLineEdit, QComboBox,
    QMessageBox, QDialog, QPlainTextEdit
)
from PySide6.QtCore import Qt
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager


class DocumentDetailDialog(QDialog):
    """文档内容查看对话框（只读）"""

    def __init__(self, doc, content, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"文档内容 - {doc['original_name']}")
        self.setMinimumSize(800, 600)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; color: #cdd6f4; }
            QPlainTextEdit { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; }
            QLabel { color: #cdd6f4; }
        """)
        layout = QVBoxLayout(self)

        info = QLabel(f"文件: {doc['original_name']} | 类型: {doc['file_type']} | 状态: {doc['status']}")
        info.setStyleSheet("color: #a6adc8; font-size: 13px;")
        layout.addWidget(info)

        text_edit = QPlainTextEdit()
        text_edit.setPlainText(content)
        text_edit.setReadOnly(True)
        layout.addWidget(text_edit)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)


class DocumentsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("文档管理")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)

        filter_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索文档...")
        self.search_input.textChanged.connect(self.filter_documents)
        self.kb_filter = QComboBox()
        self.kb_filter.setMinimumWidth(150)
        self.kb_filter.currentIndexChanged.connect(self.load_documents)
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self.load_documents)
        filter_row.addWidget(self.search_input)
        filter_row.addWidget(self.kb_filter)
        filter_row.addWidget(refresh_btn)
        layout.addLayout(filter_row)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["ID", "文件名", "类型", "大小", "分块数", "状态", "创建时间"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.doubleClicked.connect(self.view_document)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        view_btn = QPushButton("👁 查看内容")
        view_btn.clicked.connect(self.view_document)
        delete_btn = QPushButton("🗑 删除选中")
        delete_btn.clicked.connect(self.delete_selected)
        btn_row.addWidget(view_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def showEvent(self, event):
        super().showEvent(event)
        self.load_knowledge_bases()
        self.load_documents()

    def load_knowledge_bases(self):
        self.kb_filter.clear()
        self.kb_filter.addItem("所有知识库", None)
        try:
            db = DatabaseManager(str(config.DB_PATH))
            for kb in db.list_knowledge_bases():
                self.kb_filter.addItem(kb["name"], kb["id"])
        except Exception:
            pass

    def load_documents(self):
        try:
            db = DatabaseManager(str(config.DB_PATH))
            docs = db.list_documents()
            kb_id = self.kb_filter.currentData()
            if kb_id:
                docs = [d for d in docs if d.get("kb_id") == kb_id]
            self.populate_table(docs)
        except Exception as e:
            print(f"加载文档失败: {e}")

    def populate_table(self, docs):
        self.table.setRowCount(len(docs))
        for row, doc in enumerate(docs):
            self.table.setItem(row, 0, QTableWidgetItem(str(doc["id"])))
            self.table.setItem(row, 1, QTableWidgetItem(doc["original_name"]))
            self.table.setItem(row, 2, QTableWidgetItem(doc["file_type"]))
            size_mb = doc["file_size"] / (1024 * 1024)
            self.table.setItem(row, 3, QTableWidgetItem(f"{size_mb:.2f} MB"))
            self.table.setItem(row, 4, QTableWidgetItem(str(doc.get("total_chunks", 0))))
            status_item = QTableWidgetItem(doc["status"])
            if doc["status"] == "completed":
                status_item.setForeground(Qt.green)
            elif doc["status"] == "failed":
                status_item.setForeground(Qt.red)
            elif doc["status"] == "edit_failed":
                status_item.setForeground(Qt.red)
            self.table.setItem(row, 5, status_item)
            self.table.setItem(row, 6, QTableWidgetItem(doc.get("created_at", "")))
        self.table.resizeColumnsToContents()

    def filter_documents(self):
        keyword = self.search_input.text().lower()
        try:
            db = DatabaseManager(str(config.DB_PATH))
            docs = db.list_documents()
            kb_id = self.kb_filter.currentData()
            if kb_id:
                docs = [d for d in docs if d.get("kb_id") == kb_id]
            if keyword:
                docs = [d for d in docs if keyword in d["original_name"].lower()]
            self.populate_table(docs)
        except Exception:
            pass

    def _get_selected_doc_id(self) -> int:
        row = self.table.currentRow()
        if row < 0:
            return -1
        return int(self.table.item(row, 0).text())

    def view_document(self):
        doc_id = self._get_selected_doc_id()
        if doc_id < 0:
            QMessageBox.information(self, "提示", "请先选择一个文档")
            return
        try:
            db = DatabaseManager(str(config.DB_PATH))
            doc = db.get_document(doc_id)
            content = db.get_document_content(doc_id)
            dialog = DocumentDetailDialog(doc, content, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))

    def delete_selected(self):
        rows = set(idx.row() for idx in self.table.selectedIndexes())
        if not rows:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除选中的 {len(rows)} 个文档吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                db = DatabaseManager(str(config.DB_PATH))
                for row in rows:
                    doc_id = int(self.table.item(row, 0).text())
                    db.delete_document(doc_id)
                self.load_documents()
            except Exception as e:
                QMessageBox.warning(self, "错误", str(e))
