from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QCursor
from gui.styles import NAV_BUTTON_STYLE


class NavButton(QPushButton):
    clicked_nav = Signal(str)

    def __init__(self, text, page_id, parent=None):
        super().__init__(text, parent)
        self.page_id = page_id
        self.setStyleSheet(NAV_BUTTON_STYLE)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setCheckable(False)
        self.setProperty("active", False)
        self.clicked.connect(lambda: self.clicked_nav.emit(self.page_id))

    def set_active(self, active):
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)
