from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from gui.styles import STAT_CARD_STYLE


class StatCard(QFrame):
    def __init__(self, title, value="0", parent=None):
        super().__init__(parent)
        self.setStyleSheet(STAT_CARD_STYLE)
        self.setMinimumHeight(100)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setStyleSheet("color: #a6adc8; font-size: 12px; background: transparent;")
        title_label.setAlignment(Qt.AlignCenter)

        self.value_label = QLabel(str(value))
        self.value_label.setStyleSheet("color: #89b4fa; font-size: 24px; font-weight: bold; background: transparent;")
        self.value_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value):
        self.value_label.setText(str(value))
