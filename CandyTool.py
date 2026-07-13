"""
Candy 知识库系统 - 桌面端启动文件
双击运行即可启动桌面应用
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.logger import log
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from gui.main_window import MainWindow
from gui.styles import DARK_THEME


def main():
    log.info("=" * 50)
    log.info("Candy 知识库系统启动")
    log.info("=" * 50)
    
    try:
        app = QApplication(sys.argv)
        app.setStyleSheet(DARK_THEME)
        app.setFont(QFont("Microsoft YaHei", 10))
        
        log.info("创建主窗口...")
        window = MainWindow()
        window.show()
        
        log.info("应用启动成功，等待用户操作...")
        sys.exit(app.exec())
        
    except Exception as e:
        log.error(f"应用启动失败: {e}")
        raise


if __name__ == "__main__":
    main()
