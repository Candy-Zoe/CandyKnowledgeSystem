from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class ChatBubble(QFrame):
    def __init__(self, content, role="user", sources=None, parent=None):
        super().__init__(parent)

        if role == "user":
            self.setStyleSheet("""
                QFrame {
                    background-color: #45475a;
                    border-radius: 12px;
                    padding: 10px 14px;
                    margin: 4px 60px 4px 20px;
                }
            """)
            align = Qt.AlignLeft
        else:
            self.setStyleSheet("""
                QFrame {
                    background-color: #313244;
                    border-radius: 12px;
                    padding: 10px 14px;
                    margin: 4px 20px 4px 60px;
                }
            """)
            align = Qt.AlignLeft

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        role_label = QLabel("You" if role == "user" else "Assistant")
        role_label.setStyleSheet(f"color: {'#f38ba8' if role == 'user' else '#89b4fa'}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        role_label.setAlignment(align)

        content_label = QLabel(content)
        content_label.setObjectName("contentLabel")
        content_label.setWordWrap(True)
        content_label.setStyleSheet("color: #cdd6f4; font-size: 13px; background: transparent; border: none;")
        content_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        layout.addWidget(role_label)
        layout.addWidget(content_label)

        if sources:
            sources_text = "\n".join([
                f"[{i+1}] {s.get('document', '')} (score: {s.get('score', 0):.2f})"
                for i, s in enumerate(sources[:5])
            ])
            sources_label = QLabel(sources_text)
            sources_label.setStyleSheet("color: #6c7086; font-size: 11px; background: transparent; border: none;")
            sources_label.setWordWrap(True)
            layout.addWidget(sources_label)
