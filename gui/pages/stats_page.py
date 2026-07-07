from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QFrame
)
from PySide6.QtCore import Qt
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from gui.widgets.stat_card import StatCard


class StatsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("数据统计")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)

        cards_grid = QGridLayout()
        cards_grid.setSpacing(16)

        self.doc_card = StatCard("文档总数", "0")
        self.chunk_card = StatCard("分块总数", "0")
        self.pair_card = StatCard("训练对", "0")
        self.conv_card = StatCard("对话数", "0")
        self.msg_card = StatCard("消息数", "0")
        self.api_card = StatCard("API调用", "0")
        self.size_card = StatCard("存储大小", "0 MB")
        self.completed_card = StatCard("已完成文档", "0")

        cards_grid.addWidget(self.doc_card, 0, 0)
        cards_grid.addWidget(self.chunk_card, 0, 1)
        cards_grid.addWidget(self.pair_card, 0, 2)
        cards_grid.addWidget(self.conv_card, 0, 3)
        cards_grid.addWidget(self.msg_card, 1, 0)
        cards_grid.addWidget(self.api_card, 1, 1)
        cards_grid.addWidget(self.size_card, 1, 2)
        cards_grid.addWidget(self.completed_card, 1, 3)

        layout.addLayout(cards_grid)

        details_frame = QFrame()
        details_frame.setStyleSheet("background-color: #313244; border-radius: 12px; padding: 16px;")
        details_layout = QVBoxLayout(details_frame)

        details_title = QLabel("详细信息")
        details_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #cdd6f4; background: transparent;")
        details_layout.addWidget(details_title)

        self.details_label = QLabel("")
        self.details_label.setStyleSheet("color: #a6adc8; background: transparent;")
        self.details_label.setWordWrap(True)
        details_layout.addWidget(self.details_label)

        self.api_details_label = QLabel("")
        self.api_details_label.setStyleSheet("color: #a6adc8; background: transparent;")
        self.api_details_label.setWordWrap(True)
        details_layout.addWidget(self.api_details_label)

        layout.addWidget(details_frame)
        layout.addStretch()

    def showEvent(self, event):
        super().showEvent(event)
        self.load_stats()

    def load_stats(self):
        try:
            db = DatabaseManager(str(config.DB_PATH))
            stats = db.get_stats()

            self.doc_card.set_value(stats["document_count"])
            self.chunk_card.set_value(stats["chunk_count"])
            self.pair_card.set_value(stats["training_pair_count"])
            self.conv_card.set_value(stats["conversation_count"])
            self.msg_card.set_value(stats["message_count"])
            self.api_card.set_value(stats["api_call_count"])
            self.size_card.set_value(f"{stats['total_size_mb']} MB")
            self.completed_card.set_value(stats["completed_documents"])

            self.details_label.setText(
                f"文档: {stats['document_count']} 个 ({stats['completed_documents']} 个已完成)\n"
                f"分块: {stats['chunk_count']} 个\n"
                f"训练对: {stats['training_pair_count']} 个\n"
                f"对话: {stats['conversation_count']} 个\n"
                f"消息: {stats['message_count']} 条\n"
                f"存储: {stats['total_size_mb']} MB"
            )

            try:
                api_stats = db.get_api_stats()
                api_lines = [f"API 总调用: {api_stats['total_calls']} 次"]
                api_lines.append(f"今日调用: {api_stats['today_calls']} 次")
                if api_stats["by_endpoint"]:
                    api_lines.append("\n热门接口:")
                    for ep in api_stats["by_endpoint"][:5]:
                        api_lines.append(f"  {ep['endpoint']}: {ep['count']} 次")
                self.api_details_label.setText("\n".join(api_lines))
            except Exception:
                self.api_details_label.setText("API 统计暂不可用")

        except Exception as e:
            print(f"加载统计失败: {e}")
