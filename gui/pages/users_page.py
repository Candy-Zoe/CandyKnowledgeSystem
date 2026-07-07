from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QInputDialog, QMessageBox, QLineEdit
)
from PySide6.QtCore import Qt
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager


class UsersPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("用户管理")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("添加用户")
        add_btn.clicked.connect(self.add_user)
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
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "用户名", "角色", "创建时间"])
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
            users = db.list_users()
            self.table.setRowCount(len(users))
            for row, user in enumerate(users):
                self.table.setItem(row, 0, QTableWidgetItem(str(user["id"])))
                self.table.setItem(row, 1, QTableWidgetItem(user["username"]))
                self.table.setItem(row, 2, QTableWidgetItem(user.get("role", "user")))
                self.table.setItem(row, 3, QTableWidgetItem(user.get("created_at", "")))
            self.table.resizeColumnsToContents()
        except Exception as e:
            print(f"加载用户失败: {e}")

    def add_user(self):
        username, ok = QInputDialog.getText(self, "添加用户", "用户名:")
        if not ok or not username:
            return

        password, ok = QInputDialog.getText(self, "添加用户", "密码:", echo=QLineEdit.Password)
        if not ok or not password:
            return

        role, ok = QInputDialog.getItem(self, "添加用户", "角色:", ["user", "admin"], 0, False)
        if not ok:
            return

        try:
            import hashlib
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            db = DatabaseManager(str(config.DB_PATH))
            db.create_user(username, password_hash, role)
            self.load_data()
            QMessageBox.information(self, "成功", f"用户 {username} 已添加")
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))

    def delete_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        user_id = int(self.table.item(row, 0).text())
        username = self.table.item(row, 1).text()
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除用户 '{username}' 吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                db = DatabaseManager(str(config.DB_PATH))
                db.delete_user(user_id)
                self.load_data()
            except Exception as e:
                QMessageBox.warning(self, "错误", str(e))
