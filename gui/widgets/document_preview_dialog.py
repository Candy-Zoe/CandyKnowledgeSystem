"""
文档预览对话框
点击引用来源时弹出，显示原文档内容并高亮当前引用的chunk
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QTextEdit, QPushButton, QLabel,
    QSplitter, QWidget
)
from PySide6.QtCore import Qt


class DocumentPreviewDialog(QDialog):
    """文档预览对话框，显示文档所有分块并高亮当前引用的chunk"""

    def __init__(self, db, source: dict, parent=None):
        super().__init__(parent)
        self.db = db
        self.source = source
        self.chunks = []
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        """初始化对话框UI"""
        # 对话框标题使用文件名
        filename = self.source.get("document", "文档预览")
        self.setWindowTitle(f"文档预览 - {filename}")
        self.setMinimumSize(800, 500)
        self.resize(900, 600)

        # 深色主题整体样式
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
            }
            QListWidget {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #313244;
                border-radius: 8px;
                font-size: 12px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-radius: 4px;
                margin: 2px;
            }
            QListWidget::item:hover {
                background-color: #313244;
            }
            QListWidget::item:selected {
                background-color: #313244;
                color: #cdd6f4;
            }
            QTextEdit {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #313244;
                border-radius: 8px;
                font-size: 13px;
                padding: 12px;
                line-height: 1.6;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
            QPushButton:pressed {
                background-color: #585b70;
            }
            QLabel {
                color: #cdd6f4;
                font-size: 12px;
            }
            QSplitter::handle {
                background-color: #313244;
                width: 2px;
            }
        """)

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 顶部文件信息
        info_layout = QHBoxLayout()
        file_type = self.source.get("file_type", "")
        file_path = self.source.get("file_path", "")
        info_text = f"文件类型: {file_type}  |  路径: {file_path}"
        info_label = QLabel(info_text)
        info_label.setStyleSheet("color: #6c7086; font-size: 11px;")
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        main_layout.addLayout(info_layout)

        # 使用QSplitter实现左右分栏
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：chunk列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        list_title = QLabel("文档分块列表")
        list_title.setStyleSheet(
            "color: #cdd6f4; font-size: 13px; font-weight: bold;"
        )
        left_layout.addWidget(list_title)

        self.chunk_list = QListWidget()
        self.chunk_list.currentRowChanged.connect(self._on_chunk_selected)
        left_layout.addWidget(self.chunk_list)

        splitter.addWidget(left_widget)

        # 右侧：chunk内容显示
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        content_title = QLabel("分块内容")
        content_title.setStyleSheet(
            "color: #cdd6f4; font-size: 13px; font-weight: bold;"
        )
        right_layout.addWidget(content_title)

        self.content_edit = QTextEdit()
        self.content_edit.setReadOnly(True)
        self.content_edit.setPlaceholderText("请选择左侧的分块查看内容...")
        right_layout.addWidget(self.content_edit)

        splitter.addWidget(right_widget)

        # 设置左右分栏比例
        splitter.setSizes([250, 650])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        main_layout.addWidget(splitter, 1)

        # 底部关闭按钮
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.close)
        bottom_layout.addWidget(self.close_btn)

        main_layout.addLayout(bottom_layout)

    def _load_data(self):
        """从数据库加载该文档的所有chunks"""
        document_id = self.source.get("document_id")
        if not document_id:
            # 没有document_id时显示提示
            self.content_edit.setPlainText("无法获取文档信息：缺少document_id")
            return

        try:
            # 获取该文档所有分块
            self.chunks = self.db.get_chunks_by_document(document_id)
        except Exception as e:
            self.content_edit.setPlainText(f"加载文档分块失败: {e}")
            return

        if not self.chunks:
            self.content_edit.setPlainText("该文档没有分块数据")
            return

        # 当前引用的chunk_id
        current_chunk_id = self.source.get("chunk_id")
        # 当前引用的chunk_index
        current_chunk_index = self.source.get("chunk_index", -1)

        # 填充列表
        self._block_selection = True  # 防止加载时触发选择信号
        selected_row = 0
        for i, chunk in enumerate(self.chunks):
            # chunk内容预览（前50字）
            preview = chunk["content"][:50].replace("\n", " ")
            if len(chunk["content"]) > 50:
                preview += "..."
            text = f"分块 {i + 1}  (ID: {chunk['id']})\n{preview}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, chunk["id"])

            # 高亮当前引用的chunk（蓝色边框样式）
            if chunk["id"] == current_chunk_id or (current_chunk_index >= 0 and i == current_chunk_index):
                item.setSelected(True)
                selected_row = i
                item.setForeground(Qt.GlobalColor.white)
                self._highlight_item(item)

            self.chunk_list.addItem(item)

        self._block_selection = False

        # 默认选中当前引用的chunk
        if self.chunks:
            self.chunk_list.setCurrentRow(selected_row)
            self._show_chunk_content(selected_row)

    def _highlight_item(self, item: QListWidgetItem):
        """为当前引用的chunk设置高亮样式（蓝色背景）"""
        from PySide6.QtGui import QColor
        # 使用蓝色半透明背景标记当前引用的chunk
        item.setBackground(QColor("#1e3a5f"))
        item.setForeground(QColor("#89b4fa"))
        font = item.font()
        font.setBold(True)
        item.setFont(font)

    def _on_chunk_selected(self, row: int):
        """左侧列表选择变化时，更新右侧内容"""
        if self._block_selection:
            return
        if row < 0 or row >= len(self.chunks):
            return
        self._show_chunk_content(row)

    def _show_chunk_content(self, row: int):
        """在右侧显示指定行的chunk完整内容"""
        if row < 0 or row >= len(self.chunks):
            return
        chunk = self.chunks[row]
        self.content_edit.setPlainText(chunk["content"])

        # 滚动到顶部
        self.content_edit.verticalScrollBar().setValue(0)