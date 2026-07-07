DARK_THEME = """
QMainWindow {
    background-color: #1e1e2e;
}
QWidget {
    background-color: transparent;
    color: #cdd6f4;
}
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #45475a;
    border-color: #585b70;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton:disabled {
    background-color: #1e1e2e;
    color: #6c7086;
    border-color: #313244;
}
QTableWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    gridline-color: #313244;
    border: 1px solid #313244;
    border-radius: 6px;
    font-size: 12px;
    selection-background-color: #45475a;
}
QTableWidget::item {
    padding: 4px 8px;
}
QHeaderView::section {
    background-color: #313244;
    color: #cdd6f4;
    border: none;
    padding: 6px 8px;
    font-weight: bold;
}
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px;
    font-size: 13px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #89b4fa;
}
QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #313244;
    color: #cdd6f4;
    selection-background-color: #45475a;
    border: 1px solid #45475a;
}
QProgressBar {
    border: 1px solid #45475a;
    border-radius: 6px;
    text-align: center;
    color: #cdd6f4;
    background-color: #313244;
    height: 20px;
}
QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 5px;
}
QScrollBar:vertical {
    background-color: #1e1e2e;
    width: 10px;
    border: none;
}
QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #585b70;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QTabWidget::pane {
    border: 1px solid #313244;
    border-radius: 6px;
    background-color: #1e1e2e;
}
QTabBar::tab {
    background-color: #313244;
    color: #cdd6f4;
    padding: 8px 20px;
    border: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #45475a;
}
QTabBar::tab:hover {
    background-color: #585b70;
}
QSpinBox, QDoubleSpinBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 4px 8px;
}
QSlider::groove:horizontal {
    height: 6px;
    background-color: #313244;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background-color: #89b4fa;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover {
    background-color: #b4befe;
}
QCheckBox {
    spacing: 8px;
    color: #cdd6f4;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #45475a;
    border-radius: 4px;
    background-color: #313244;
}
QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}
QMessageBox {
    background-color: #1e1e2e;
}
QInputDialog {
    background-color: #1e1e2e;
}
QLabel {
    color: #cdd6f4;
}
QStatusBar {
    background-color: #181825;
    color: #a6adc8;
    border-top: 1px solid #313244;
}
"""

NAV_BUTTON_STYLE = """
QPushButton {
    text-align: left;
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 14px;
    color: #cdd6f4;
    background-color: #313244;
    border: 1px solid #45475a;
    margin: 2px 0px;
}
QPushButton:hover {
    background-color: #45475a;
    border-color: #585b70;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton[active="true"] {
    background-color: #89b4fa;
    color: #1e1e2e;
    font-weight: bold;
    border-color: #89b4fa;
}
"""

WEB_BUTTON_STYLE = """
QPushButton {
    text-align: left;
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 14px;
    color: #a6e3a1;
    background-color: #1e1e2e;
    border: 2px solid #a6e3a1;
}
QPushButton:hover {
    background-color: #a6e3a1;
    color: #1e1e2e;
}
"""

STAT_CARD_STYLE = """
QFrame {
    background-color: #313244;
    border-radius: 12px;
    padding: 16px;
}
"""
