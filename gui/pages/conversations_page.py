from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QScrollArea, QMessageBox, QInputDialog
)
from PySide6.QtCore import Qt
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from gui.widgets.chat_bubble import ChatBubble


class ConversationsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_conv_id = None
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_panel.setFixedWidth(260)

        header = QLabel("对话历史")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        left_layout.addWidget(header)

        self.new_btn = QPushButton("+ 新建对话")
        self.new_btn.clicked.connect(self.new_conversation)
        left_layout.addWidget(self.new_btn)

        self.conv_list = QListWidget()
        self.conv_list.setStyleSheet("""
            QListWidget {
                background-color: #313244;
                border-radius: 8px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 10px;
                border-radius: 6px;
                margin: 2px;
            }
            QListWidget::item:selected {
                background-color: #45475a;
            }
        """)
        self.conv_list.currentRowChanged.connect(self.on_conv_selected)
        left_layout.addWidget(self.conv_list, 1)

        delete_btn = QPushButton("删除对话")
        delete_btn.clicked.connect(self.delete_conversation)
        left_layout.addWidget(delete_btn)

        layout.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.setSpacing(8)
        self.chat_scroll.setWidget(self.chat_container)
        right_layout.addWidget(self.chat_scroll)

        self.empty_label = QLabel("选择一个对话或新建对话")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #6c7086; font-size: 14px;")
        right_layout.addWidget(self.empty_label)

        layout.addWidget(right_panel, 1)

    def showEvent(self, event):
        super().showEvent(event)
        self.load_conversations()

    def load_conversations(self):
        self.conv_list.clear()
        try:
            db = DatabaseManager(str(config.DB_PATH))
            convs = db.list_conversations()
            for conv in convs:
                item = QListWidgetItem(conv["title"])
                item.setData(Qt.UserRole, conv["id"])
                self.conv_list.addItem(item)
        except Exception:
            pass

    def on_conv_selected(self, row):
        if row < 0:
            return
        item = self.conv_list.item(row)
        if not item:
            return
        conv_id = item.data(Qt.UserRole)
        self.current_conv_id = conv_id
        self.load_messages(conv_id)

    def load_messages(self, conv_id):
        self.chat_layout.deleteLater()
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.setSpacing(8)
        self.chat_scroll.setWidget(self.chat_container)
        self.empty_label.setVisible(False)

        try:
            db = DatabaseManager(str(config.DB_PATH))
            messages = db.get_messages(conv_id)
            for msg in messages:
                sources = msg.get("sources") if isinstance(msg.get("sources"), list) else None
                ChatBubble(msg["content"], msg["role"], sources)
                bubble = ChatBubble(msg["content"], msg["role"], sources)
                self.chat_layout.addWidget(bubble)
        except Exception as e:
            print(f"加载消息失败: {e}")

    def new_conversation(self):
        title, ok = QInputDialog.getText(self, "新建对话", "对话标题:")
        if ok and title:
            try:
                db = DatabaseManager(str(config.DB_PATH))
                db.create_conversation(title)
                self.load_conversations()
            except Exception as e:
                QMessageBox.warning(self, "错误", str(e))

    def delete_conversation(self):
        item = self.conv_list.currentItem()
        if not item:
            return
        conv_id = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "确认删除", "确定要删除这个对话吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                db = DatabaseManager(str(config.DB_PATH))
                db.delete_conversation(conv_id)
                self.load_conversations()
            except Exception as e:
                QMessageBox.warning(self, "错误", str(e))
