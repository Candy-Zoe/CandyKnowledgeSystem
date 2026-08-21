from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QLineEdit, QComboBox,
    QMessageBox, QDialog, QPlainTextEdit, QInputDialog
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
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["ID", "文件名", "知识库", "类型", "大小", "分块数", "状态", "创建时间"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.doubleClicked.connect(self.view_document)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        view_btn = QPushButton("👁 查看内容")
        view_btn.clicked.connect(self.view_document)
        copy_btn = QPushButton("复制到知识库")
        copy_btn.clicked.connect(self.copy_to_knowledge_base)
        move_btn = QPushButton("移动到知识库")
        move_btn.clicked.connect(self.move_to_knowledge_base)
        delete_btn = QPushButton("🗑 删除选中")
        delete_btn.clicked.connect(self.delete_selected)
        btn_row.addWidget(view_btn)
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(move_btn)
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
            kb_id = self.kb_filter.currentData()
            docs = db.list_documents_by_knowledge_base(kb_id) if kb_id else db.list_documents()
            self.populate_table(docs)
        except Exception as e:
            print(f"加载文档失败: {e}")

    def populate_table(self, docs):
        self.table.setRowCount(len(docs))
        for row, doc in enumerate(docs):
            self.table.setItem(row, 0, QTableWidgetItem(str(doc["id"])))
            self.table.setItem(row, 1, QTableWidgetItem(doc["original_name"]))
            self.table.setItem(row, 2, QTableWidgetItem(doc.get("kb_names") or "未关联"))
            self.table.setItem(row, 3, QTableWidgetItem(doc["file_type"]))
            size_mb = doc["file_size"] / (1024 * 1024)
            self.table.setItem(row, 4, QTableWidgetItem(f"{size_mb:.2f} MB"))
            self.table.setItem(row, 5, QTableWidgetItem(str(doc.get("total_chunks", 0))))
            status_item = QTableWidgetItem(doc["status"])
            if doc["status"] == "completed":
                status_item.setForeground(Qt.green)
            elif doc["status"] == "failed":
                status_item.setForeground(Qt.red)
            elif doc["status"] == "edit_failed":
                status_item.setForeground(Qt.red)
            self.table.setItem(row, 6, status_item)
            self.table.setItem(row, 7, QTableWidgetItem(doc.get("created_at", "")))
        self.table.resizeColumnsToContents()

    def filter_documents(self):
        keyword = self.search_input.text().lower()
        try:
            db = DatabaseManager(str(config.DB_PATH))
            kb_id = self.kb_filter.currentData()
            docs = db.list_documents_by_knowledge_base(kb_id) if kb_id else db.list_documents()
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

    def _selected_doc_ids(self) -> list:
        rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        doc_ids = []
        for row in rows:
            item = self.table.item(row, 0)
            if item:
                doc_ids.append(int(item.text()))
        return doc_ids

    def _choose_knowledge_base(self, title: str):
        db = DatabaseManager(str(config.DB_PATH))
        kbs = db.list_knowledge_bases()
        if not kbs:
            QMessageBox.information(self, "提示", "请先创建知识库")
            return None
        labels = [f"{kb['id']} - {kb['name']}" for kb in kbs]
        label, ok = QInputDialog.getItem(self, title, "目标知识库:", labels, 0, False)
        if not ok or not label:
            return None
        return int(label.split(" - ", 1)[0])

    def copy_to_knowledge_base(self):
        doc_ids = self._selected_doc_ids()
        if not doc_ids:
            QMessageBox.information(self, "提示", "请先选择一个或多个文档")
            return
        kb_id = self._choose_knowledge_base("复制到知识库")
        if not kb_id:
            return
        try:
            db = DatabaseManager(str(config.DB_PATH))
            for doc_id in doc_ids:
                db.add_document_to_knowledge_base(doc_id, kb_id)
            self.load_documents()
            QMessageBox.information(self, "完成", f"已复制关联 {len(doc_ids)} 个文档到目标知识库")
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))

    def move_to_knowledge_base(self):
        doc_ids = self._selected_doc_ids()
        if not doc_ids:
            QMessageBox.information(self, "提示", "请先选择一个或多个文档")
            return
        kb_id = self._choose_knowledge_base("移动到知识库")
        if not kb_id:
            return
        try:
            db = DatabaseManager(str(config.DB_PATH))
            for doc_id in doc_ids:
                db.move_document_to_knowledge_base(doc_id, kb_id)
            self.load_documents()
            QMessageBox.information(self, "完成", f"已移动 {len(doc_ids)} 个文档到目标知识库")
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))

    def delete_selected(self):
        doc_ids = self._selected_doc_ids()
        if not doc_ids:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除选中的 {len(doc_ids)} 个文档吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                db = DatabaseManager(str(config.DB_PATH))
                for doc_id in doc_ids:
                    db.delete_document(doc_id)
                self.load_documents()
            except Exception as e:
                QMessageBox.warning(self, "错误", str(e))
