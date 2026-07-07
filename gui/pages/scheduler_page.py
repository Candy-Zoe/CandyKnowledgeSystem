from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QInputDialog, QMessageBox,
    QFileDialog, QSpinBox
)
from PySide6.QtCore import Qt
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager


class SchedulerPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("调度任务")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("新建任务")
        add_btn.clicked.connect(self.add_task)
        delete_btn = QPushButton("删除选中")
        delete_btn.clicked.connect(self.delete_selected)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.load_data)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "名称", "文件夹路径", "间隔(分钟)", "启用", "上次运行"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

    def showEvent(self, event):
        super().showEvent(event)
        self.load_data()

    def load_data(self):
        try:
            db = DatabaseManager(str(config.DB_PATH))
            tasks = db.list_scheduled_tasks()
            self.table.setRowCount(len(tasks))
            for row, task in enumerate(tasks):
                self.table.setItem(row, 0, QTableWidgetItem(str(task["id"])))
                self.table.setItem(row, 1, QTableWidgetItem(task["name"]))
                self.table.setItem(row, 2, QTableWidgetItem(task["folder_path"]))
                self.table.setItem(row, 3, QTableWidgetItem(str(task.get("interval_minutes", 60))))
                enabled = "是" if task.get("enabled", 1) else "否"
                self.table.setItem(row, 4, QTableWidgetItem(enabled))
                self.table.setItem(row, 5, QTableWidgetItem(task.get("last_run", "从未")))
            self.table.resizeColumnsToContents()
        except Exception as e:
            print(f"加载任务失败: {e}")

    def add_task(self):
        name, ok = QInputDialog.getText(self, "新建任务", "任务名称:")
        if not ok or not name:
            return

        folder = QFileDialog.getExistingDirectory(self, "选择监控文件夹")
        if not folder:
            return

        interval, ok = QInputDialog.getInt(self, "新建任务", "检查间隔(分钟):", 60, 1, 1440)
        if not ok:
            return

        try:
            db = DatabaseManager(str(config.DB_PATH))
            db.create_scheduled_task(name, folder, interval)
            self.load_data()
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))

    def delete_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        task_id = int(self.table.item(row, 0).text())
        reply = QMessageBox.question(
            self, "确认删除", "确定要删除这个任务吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                db = DatabaseManager(str(config.DB_PATH))
                db.delete_scheduled_task(task_id)
                self.load_data()
            except Exception as e:
                QMessageBox.warning(self, "错误", str(e))
