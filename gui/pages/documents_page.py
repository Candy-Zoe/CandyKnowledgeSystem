from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QLineEdit, QComboBox,
    QMessageBox, QDialog, QPlainTextEdit, QProgressBar,
    QDialogButtonBox
)
from PySide6.QtCore import Qt, QThread
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from core.file_editor import FileEditor
from gui.workers.edit_document_worker import EditDocumentWorker


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


class DocumentEditDialog(QDialog):
    """文档内容编辑对话框 - 支持所有格式的通用编辑器"""

    def __init__(self, doc, content, mode, info, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.edit_mode = mode
        self.setWindowTitle(f"编辑 - {doc['original_name']}")
        self.setMinimumSize(900, 700)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; color: #cdd6f4; }
            QPlainTextEdit { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; font-size: 14px; }
            QLabel { color: #cdd6f4; }
            QPushButton { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; padding: 8px 20px; }
            QPushButton:hover { background-color: #45475a; }
            QProgressBar { border: 1px solid #45475a; background-color: #313244; color: #cdd6f4; }
            QProgressBar::chunk { background-color: #89b4fa; }
        """)
        self.init_ui(content, info)

    def init_ui(self, content, info):
        layout = QVBoxLayout(self)

        # 顶部信息
        info_label = QLabel(f"📝 编辑: {self.doc['original_name']} | 类型: {self.doc['file_type']}")
        info_label.setStyleSheet("color: #a6adc8; font-size: 13px;")
        layout.addWidget(info_label)

        # 编辑模式提示
        hint = QLabel(f"模式: {info}")
        hint.setStyleSheet("color: #a6e3a1; font-size: 12px;")
        layout.addWidget(hint)

        # 编辑区域
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlainText(content)
        layout.addWidget(self.text_edit)

        # 进度条（隐藏）
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.save_btn = QPushButton("💾 保存")
        self.save_btn.setStyleSheet("background-color: #a6e3a1; color: #1e1e2e; font-weight: bold;")
        self.save_btn.clicked.connect(self.on_save)
        btn_layout.addWidget(self.save_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def get_content(self) -> str:
        return self.text_edit.toPlainText()

    def on_save(self):
        content = self.get_content().strip()
        if not content:
            QMessageBox.warning(self, "警告", "文档内容不能为空")
            return
        self.accept()

    def show_progress(self, value: int):
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(value)
        self.save_btn.setEnabled(False)
        self.save_btn.setText("处理中...")

    def hide_progress(self):
        self.progress_bar.setVisible(False)
        self.save_btn.setEnabled(True)
        self.save_btn.setText("💾 保存")


class DocumentsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.edit_worker = None
        self.edit_thread = None
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
        edit_btn = QPushButton("✏ 编辑内容")
        edit_btn.clicked.connect(self.edit_document)
        delete_btn = QPushButton("🗑 删除选中")
        delete_btn.clicked.connect(self.delete_selected)
        btn_row.addWidget(view_btn)
        btn_row.addWidget(edit_btn)
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

    def edit_document(self):
        doc_id = self._get_selected_doc_id()
        if doc_id < 0:
            QMessageBox.information(self, "提示", "请先选择一个文档")
            return
        try:
            db = DatabaseManager(str(config.DB_PATH))
            doc = db.get_document(doc_id)

            # 使用FileEditor加载文件内容
            content, mode, info = FileEditor.load_for_edit(
                doc["file_path"], doc["file_type"]
            )

            dialog = DocumentEditDialog(doc, content, mode, info, self)
            if dialog.exec() == QDialog.Accepted:
                new_content = dialog.get_content()

                # 1. 保存文件编辑
                result = FileEditor.save_edit(
                    doc["file_path"], doc["file_type"], new_content, mode
                )

                if not result["success"]:
                    QMessageBox.warning(self, "保存失败", result["message"])
                    return

                # 显示保存结果
                saved_path = result["saved_path"]
                if saved_path != doc["file_path"]:
                    QMessageBox.information(
                        self, "文件已保存",
                        f"由于格式限制，已保存为新文件:\n{saved_path}\n\n"
                        f"原文件保持不变。"
                    )

                # 2. 更新知识库（重新分块嵌入）
                self._run_edit_worker(doc_id, new_content, dialog)
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))

    def _run_edit_worker(self, doc_id: int, new_content: str, dialog: DocumentEditDialog):
        """运行文档编辑Worker"""
        dialog.show_progress(0)

        self.edit_worker = EditDocumentWorker(doc_id, new_content)
        self.edit_thread = QThread()
        self.edit_worker.moveToThread(self.edit_thread)

        self.edit_thread.started.connect(self.edit_worker.run)
        self.edit_worker.progress.connect(dialog.show_progress)
        self.edit_worker.finished.connect(lambda: self._on_edit_finished(dialog))
        self.edit_worker.error.connect(lambda msg: self._on_edit_error(msg, dialog))
        self.edit_worker.finished.connect(self.edit_thread.quit)
        self.edit_worker.error.connect(self.edit_thread.quit)

        self.edit_thread.start()

    def _on_edit_finished(self, dialog: DocumentEditDialog):
        dialog.hide_progress()
        QMessageBox.information(self, "完成", "文档内容已更新，知识库已同步。")
        self.load_documents()
        dialog.close()

    def _on_edit_error(self, msg: str, dialog: DocumentEditDialog):
        dialog.hide_progress()
        QMessageBox.warning(self, "编辑失败", f"更新文档时出错:\n{msg}")
        self.load_documents()

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
