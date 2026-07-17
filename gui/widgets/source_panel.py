"""
引用来源面板组件
在问答页面右侧显示，列出当前回答引用的所有文档片段
支持点击某条引用打开文档预览
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Signal, Qt


class SourceCard(QFrame):
    """单条引用卡片，可点击"""
    # 点击信号，传递完整的source字典
    clicked = Signal(dict)

    def __init__(self, source: dict, index: int, parent=None):
        super().__init__(parent)
        self.source = source
        self._setup_ui(index)

    def _setup_ui(self, index: int):
        """初始化卡片UI"""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(120)

        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # 顶行：序号 + 文件名
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        # 序号标签
        self.index_label = QLabel(f"#{index}")
        self.index_label.setStyleSheet(
            "color: #6c7086; font-size: 12px; font-weight: bold;"
        )
        self.index_label.setFixedWidth(24)
        top_row.addWidget(self.index_label)

        # 文件名标签
        filename = self.source.get("document", "未知文档")
        self.file_label = QLabel(filename)
        self.file_label.setStyleSheet(
            "color: #89b4fa; font-size: 12px; font-weight: bold;"
        )
        self.file_label.setToolTip(filename)
        top_row.addWidget(self.file_label, 1)

        # 相似度分数
        score = self.source.get("score", 0)
        self.score_label = QLabel(f"{score:.2%}")
        self.score_label.setStyleSheet(
            "color: #a6e3a1; font-size: 11px; font-weight: bold;"
        )
        self.score_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.score_label.setFixedWidth(48)
        top_row.addWidget(self.score_label)

        layout.addLayout(top_row)

        # chunk索引信息
        chunk_index = self.source.get("chunk_index", 0)
        total_chunks = self.source.get("total_chunks", 0)
        if total_chunks > 0:
            chunk_text = f"分块 {chunk_index + 1}/{total_chunks}"
        else:
            chunk_text = f"分块 {chunk_index + 1}"
        self.chunk_label = QLabel(chunk_text)
        self.chunk_label.setStyleSheet(
            "color: #6c7086; font-size: 11px;"
        )
        layout.addWidget(self.chunk_label)

        # 内容预览（前150字）
        preview = self.source.get("content_preview", "")
        if len(preview) > 150:
            preview = preview[:150] + "..."
        self.preview_label = QLabel(preview)
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet(
            "color: #6c7086; font-size: 11px; line-height: 1.4;"
        )
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self.preview_label)

        # 设置卡片样式
        self._apply_style()

    def _apply_style(self):
        """应用深色主题卡片样式"""
        self.setStyleSheet("""
            SourceCard {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 8px;
            }
            SourceCard:hover {
                background-color: #45475a;
            }
        """)

    def mousePressEvent(self, event):
        """鼠标点击事件，发出clicked信号"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.source)
        super().mousePressEvent(event)


class SourcePanel(QWidget):
    """引用来源面板，显示在问答页面右侧"""

    # 点击某条引用时发出信号，传递完整source信息
    source_clicked = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sources = []
        self._setup_ui()

    def _setup_ui(self):
        """初始化面板UI"""
        # 整体布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 面板背景
        self.setObjectName("sourcePanel")
        self.setStyleSheet("""
            #sourcePanel {
                background-color: #181825;
                border-left: 1px solid #313244;
            }
        """)

        # 顶部标题栏
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(12, 12, 12, 8)

        title_label = QLabel("引用来源")
        title_label.setStyleSheet(
            "color: #cdd6f4; font-size: 14px; font-weight: bold;"
        )
        header_layout.addWidget(title_label)

        # 引用数量badge
        self.badge = QLabel("0")
        self.badge.setFixedWidth(24)
        self.badge.setFixedHeight(20)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setStyleSheet("""
            background-color: #45475a;
            color: #cdd6f4;
            font-size: 11px;
            font-weight: bold;
            border-radius: 10px;
        """)
        header_layout.addWidget(self.badge)

        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #313244;")
        separator.setFixedHeight(1)
        main_layout.addWidget(separator)

        # 可滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background: #181825;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #45475a;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #585b70;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # 滚动区域的容器
        self.container = QWidget()
        self.container.setStyleSheet("background-color: transparent;")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(8, 8, 8, 8)
        self.container_layout.setSpacing(8)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.container)
        main_layout.addWidget(self.scroll_area, 1)

        # 默认提示文字
        self._show_empty_hint()

    def _show_empty_hint(self):
        """显示无引用时的提示文字"""
        self._clear_cards()
        hint_label = QLabel("暂无引用来源\n提问后将在此显示引用的文档片段")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setStyleSheet(
            "color: #6c7086; font-size: 12px; padding: 20px;"
        )
        hint_label.setWordWrap(True)
        self.container_layout.addWidget(hint_label)

    def _clear_cards(self):
        """清除所有卡片"""
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def set_sources(self, sources: list):
        """接收引用列表并刷新显示"""
        self.sources = sources

        # 更新badge数量
        self.badge.setText(str(len(sources)))

        # 清空现有内容
        self._clear_cards()

        # 无引用时显示提示
        if not sources:
            self._show_empty_hint()
            return

        # 逐条创建引用卡片
        for i, source in enumerate(sources):
            card = SourceCard(source, index=i + 1)
            card.clicked.connect(self.source_clicked.emit)
            self.container_layout.addWidget(card)

    def clear_sources(self):
        """清空引用面板"""
        self.sources = []
        self.badge.setText("0")
        self._show_empty_hint()