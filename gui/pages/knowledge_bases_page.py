from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QInputDialog, QMessageBox
)
from PySide6.QtCore import Qt
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager


class KnowledgeBasesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("知识库管理")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("新建知识库")
        add_btn.clicked.connect(self.add_knowledge_base)
        delete_btn = QPushButton("删除选中")
        delete_btn.clicked.connect(self.delete_selected)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.load_data)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "名称", "描述", "创建时间"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        self.doc_label = QLabel("关联文档:")
        self.doc_label.setStyleSheet("font-weight: bold; margin-top: 16px;")
        layout.addWidget(self.doc_label)

        self.doc_table = QTableWidget()
        self.doc_table.setColumnCount(4)
        self.doc_table.setHorizontalHeaderLabels(["ID", "文件名", "状态", "分块数"])
        self.doc_table.horizontalHeader().setStretchLastSection(True)
        self.doc_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.doc_table.setMaximumHeight(200)
        layout.addWidget(self.doc_table)

        self.table.currentCellChanged.connect(self.on_kb_selected)

    def showEvent(self, event):
        super().showEvent(event)
        self.load_data()

    def load_data(self):
        try:
            db = DatabaseManager(str(config.DB_PATH))
            kbs = db.list_knowledge_bases()
            self.table.setRowCount(len(kbs))
            for row, kb in enumerate(kbs):
                self.table.setItem(row, 0, QTableWidgetItem(str(kb["id"])))
                self.table.setItem(row, 1, QTableWidgetItem(kb["name"]))
                self.table.setItem(row, 2, QTableWidgetItem(kb.get("description", "")))
                self.table.setItem(row, 3, QTableWidgetItem(kb.get("created_at", "")))
            self.table.resizeColumnsToContents()
        except Exception as e:
            print(f"加载知识库失败: {e}")

    def on_kb_selected(self, row, col, prev_row, prev_col):
        if row < 0:
            return
        kb_id = int(self.table.item(row, 0).text())
        try:
            db = DatabaseManager(str(config.DB_PATH))
            docs = db.list_documents_by_knowledge_base(kb_id)
            self.doc_table.setRowCount(len(docs))
            for r, doc in enumerate(docs):
                self.doc_table.setItem(r, 0, QTableWidgetItem(str(doc["id"])))
                self.doc_table.setItem(r, 1, QTableWidgetItem(doc["original_name"]))
                self.doc_table.setItem(r, 2, QTableWidgetItem(doc["status"]))
                self.doc_table.setItem(r, 3, QTableWidgetItem(str(doc.get("total_chunks", 0))))
            self.doc_label.setText(f"关联文档 ({len(docs)} 个):")
        except Exception:
            pass

    def add_knowledge_base(self):
        name, ok = QInputDialog.getText(self, "新建知识库", "知识库名称:")
        if ok and name:
            desc, ok2 = QInputDialog.getText(self, "新建知识库", "描述 (可选):")
            if not ok2:
                desc = ""
            try:
                db = DatabaseManager(str(config.DB_PATH))
                db.create_knowledge_base(name, desc)
                self.load_data()
            except Exception as e:
                QMessageBox.warning(self, "错误", str(e))

    def delete_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        kb_id = int(self.table.item(row, 0).text())
        name = self.table.item(row, 1).text()
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除知识库 '{name}' 吗？\n该知识库下的文档将被取消关联。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                db = DatabaseManager(str(config.DB_PATH))
                db.delete_knowledge_base(kb_id)
                self.load_data()
            except Exception as e:
                QMessageBox.warning(self, "错误", str(e))
