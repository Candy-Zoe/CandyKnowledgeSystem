from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QLabel, QStatusBar
)
from PySide6.QtCore import Qt
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Candy 知识库系统")
        self.setMinimumSize(1200, 750)
        self.resize(1400, 850)

        self.pages = {}
        self.nav_buttons = {}

        self.init_ui()
        self.navigate_to("upload")

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet("background-color: #181825;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 16, 12, 16)
        sidebar_layout.setSpacing(4)

        logo = QLabel("CANDY")
        logo.setStyleSheet("color: #89b4fa; font-size: 18px; font-weight: bold; padding: 8px;")
        logo.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(logo)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #313244;")
        sidebar_layout.addWidget(sep)

        nav_items = [
            ("📤 上传文档", "upload"),
            ("📄 文档管理", "documents"),
            ("📚 知识库", "knowledge_bases"),
            ("❓ 智能问答", "qa"),
            ("📦 批量问答", "batch_qa"),
            ("💬 对话历史", "conversations"),
        ]

        from gui.widgets.nav_button import NavButton
        for text, page_id in nav_items:
            btn = NavButton(text, page_id)
            btn.clicked_nav.connect(self.navigate_to)
            sidebar_layout.addWidget(btn)
            self.nav_buttons[page_id] = btn

        sidebar_layout.addStretch()

        main_layout.addWidget(sidebar)

        content = QWidget()
        content.setStyleSheet("background-color: #1e1e2e;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)
        main_layout.addWidget(content, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

    def navigate_to(self, page_id):
        if page_id not in self.pages:
            self.pages[page_id] = self.create_page(page_id)
            self.stack.addWidget(self.pages[page_id])

        self.stack.setCurrentWidget(self.pages[page_id])

        for pid, btn in self.nav_buttons.items():
            btn.set_active(pid == page_id)

    def create_page(self, page_id):
        from gui.pages.upload_page import UploadPage
        from gui.pages.documents_page import DocumentsPage
        from gui.pages.qa_page import QAPage
        from gui.pages.batch_qa_page import BatchQAPage
        from gui.pages.conversations_page import ConversationsPage
        from gui.pages.knowledge_bases_page import KnowledgeBasesPage

        page_map = {
            "upload": UploadPage,
            "documents": DocumentsPage,
            "qa": QAPage,
            "batch_qa": BatchQAPage,
            "conversations": ConversationsPage,
            "knowledge_bases": KnowledgeBasesPage,
        }
        return page_map[page_id]()

    def closeEvent(self, event):
        event.accept()
