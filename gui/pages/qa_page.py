from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QPlainTextEdit, QScrollArea, QRadioButton, QButtonGroup, QMessageBox,
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
    QGroupBox, QCheckBox, QTextEdit
)
from PySide6.QtCore import Qt, QThread
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from core.rag_engine import RAGEngine
from core.embedding_engine import EmbeddingEngine
from core.api_client import APIClient
from gui.widgets.chat_bubble import ChatBubble
from gui.widgets.source_panel import SourcePanel
from gui.widgets.document_preview_dialog import DocumentPreviewDialog
from gui.workers.qa_worker import QAWorker


class SettingsDialog(QDialog):
    """简易设置对话框 - 选择API提供商"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API 设置")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; color: #cdd6f4; }
            QLabel { color: #cdd6f4; }
            QComboBox { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; padding: 4px 8px; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #313244; color: #cdd6f4; }
            QLineEdit { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; padding: 4px 8px; }
            QGroupBox { color: #a6adc8; border: 1px solid #45475a; margin-top: 8px; padding-top: 16px; }
            QGroupBox::title { padding: 0 8px; }
            QPushButton { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; padding: 6px 16px; }
            QPushButton:hover { background-color: #45475a; }
            QTextEdit { background-color: #313244; color: #a6adc8; border: 1px solid #45475a; }
        """)
        self.settings = config.load_settings()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 提供商选择
        provider_group = QGroupBox("模型提供商")
        provider_layout = QFormLayout(provider_group)

        self.provider_combo = QComboBox()
        providers = APIClient.list_providers()
        self.provider_data = providers
        for p in providers:
            label = f"{p['name']} {'(无需API Key)' if not p['need_key'] else ''}"
            self.provider_combo.addItem(label, p["id"])
        current_provider = self.settings.get("api_provider", "local")
        idx = self.provider_combo.findData(current_provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        provider_layout.addRow("提供商:", self.provider_combo)

        # 模型选择
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setMinimumWidth(250)
        provider_layout.addRow("模型:", self.model_combo)
        self._refresh_models()

        # API Key
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("输入API Key（本地模式无需填写）")
        self.api_key_input.setText(self.settings.get("api_key", ""))
        provider_layout.addRow("API Key:", self.api_key_input)

        # 自定义API地址
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("自定义API地址（留空使用默认）")
        self.base_url_input.setText(self.settings.get("api_base_url", ""))
        provider_layout.addRow("API地址:", self.base_url_input)

        provider_group.setLayout(provider_layout)
        layout.addWidget(provider_group)

        # 提示信息
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(100)
        self.info_text.setPlainText(self._get_provider_info())
        layout.addWidget(self.info_text)

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.ollama_check_btn = QPushButton("检测 Ollama")
        self.ollama_check_btn.clicked.connect(self._check_ollama)
        self.ollama_check_btn.setVisible(False)
        button_layout.addWidget(self.ollama_check_btn)

        self.save_btn = QPushButton("保存")
        self.save_btn.setStyleSheet("background-color: #89b4fa; color: #1e1e2e; font-weight: bold;")
        self.save_btn.clicked.connect(self.save)
        button_layout.addWidget(self.save_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def _on_provider_changed(self):
        self._refresh_models()
        provider_id = self.provider_combo.currentData()
        info = APIClient.PROVIDERS.get(provider_id, {})
        self.ollama_check_btn.setVisible(provider_id == "ollama")
        self.api_key_input.setEnabled(info.get("need_key", True))
        self.api_key_input.setPlaceholderText(
            "输入API Key" if info.get("need_key", True) else "本地模式无需API Key"
        )
        self.info_text.setPlainText(self._get_provider_info())

    def _refresh_models(self):
        self.model_combo.clear()
        provider_id = self.provider_combo.currentData()
        info = APIClient.PROVIDERS.get(provider_id, {})
        models = info.get("models", [])
        for m in models:
            self.model_combo.addItem(m)
        current_model = self.settings.get("api_model", "")
        if current_model:
            idx = self.model_combo.findText(current_model)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)

    def _get_provider_info(self):
        provider_id = self.provider_combo.currentData()
        info = APIClient.PROVIDERS.get(provider_id, {})
        return info.get("description", "")

    def _check_ollama(self):
        ok, models = APIClient.check_ollama()
        if ok:
            self.model_combo.clear()
            for m in models:
                self.model_combo.addItem(m)
            QMessageBox.information(self, "Ollama", f"检测到 Ollama，已安装 {len(models)} 个模型：\n" + "\n".join(models))
        else:
            QMessageBox.warning(self, "Ollama", "未检测到 Ollama。\n请先安装 Ollama: https://ollama.com\n然后运行: ollama pull qwen2.5:7b")

    def save(self):
        provider_id = self.provider_combo.currentData()
        self.settings["api_provider"] = provider_id
        self.settings["api_model"] = self.model_combo.currentText().strip()
        self.settings["api_key"] = self.api_key_input.text().strip()
        self.settings["api_base_url"] = self.base_url_input.text().strip()
        config.save_settings(self.settings)
        self.accept()


class QAPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.history = []
        self.worker = None
        self.thread = None
        self.current_bubble = None
        self.db = DatabaseManager(str(config.DB_PATH))
        self.init_ui()
        self._update_model_label()

    def init_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setSpacing(0)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # 顶部区域
        top_container = QWidget()
        top_container.setStyleSheet("background-color: transparent;")
        top_layout = QVBoxLayout(top_container)
        top_layout.setSpacing(8)
        top_layout.setContentsMargins(24, 24, 24, 12)

        title = QLabel("智能问答")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        top_layout.addWidget(title)

        # 第一行：模型状态 + 设置按钮
        top_row1 = QHBoxLayout()
        self.model_label = QLabel("模型状态: 本地检索")
        self.model_label.setStyleSheet("color: #a6adc8; font-size: 13px;")
        top_row1.addWidget(self.model_label)
        top_row1.addStretch()

        self.settings_btn = QPushButton("⚙ 设置")
        self.settings_btn.setFixedWidth(80)
        self.settings_btn.setStyleSheet("""
            QPushButton { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; 
                          padding: 4px 12px; border-radius: 4px; font-size: 13px; }
            QPushButton:hover { background-color: #45475a; }
        """)
        self.settings_btn.clicked.connect(self._open_settings)
        top_row1.addWidget(self.settings_btn)
        top_layout.addLayout(top_row1)

        # 第二行：检索模式
        top_row2 = QHBoxLayout()
        mode_label = QLabel("检索模式:")
        top_row2.addWidget(mode_label)
        self.mode_group = QButtonGroup()
        self.vector_radio = QRadioButton("向量")
        self.bm25_radio = QRadioButton("BM25")
        self.hybrid_radio = QRadioButton("混合")
        self.hybrid_radio.setChecked(True)
        self.mode_group.addButton(self.vector_radio, 0)
        self.mode_group.addButton(self.bm25_radio, 1)
        self.mode_group.addButton(self.hybrid_radio, 2)
        top_row2.addWidget(self.vector_radio)
        top_row2.addWidget(self.bm25_radio)
        top_row2.addWidget(self.hybrid_radio)
        self.mode_group.buttonClicked.connect(self.on_mode_changed)
        top_row2.addStretch()
        top_layout.addLayout(top_row2)

        outer_layout.addWidget(top_container)

        # 主内容区域：左右分栏
        content_layout = QHBoxLayout()
        content_layout.setSpacing(0)
        content_layout.setContentsMargins(24, 0, 0, 0)

        # 左侧：聊天区域
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setSpacing(12)
        left_layout.setContentsMargins(0, 0, 12, 0)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.setSpacing(8)
        self.chat_scroll.setWidget(self.chat_container)
        left_layout.addWidget(self.chat_scroll, 1)

        # 输入区域
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 24)
        self.input_box = QPlainTextEdit()
        self.input_box.setPlaceholderText("输入你的问题...")
        self.input_box.setMaximumHeight(80)
        self.input_box.installEventFilter(self)
        self.send_btn = QPushButton("发送")
        self.send_btn.setFixedWidth(80)
        self.send_btn.clicked.connect(self.send_question)
        input_row.addWidget(self.input_box, 1)
        input_row.addWidget(self.send_btn)
        left_layout.addLayout(input_row)

        content_layout.addWidget(left_container, 3)

        # 右侧：引用面板
        self.source_panel = SourcePanel()
        self.source_panel.setFixedWidth(320)
        self.source_panel.source_clicked.connect(self._on_source_clicked)
        content_layout.addWidget(self.source_panel)

        outer_layout.addLayout(content_layout, 1)

    def _update_model_label(self):
        """更新模型状态标签"""
        settings = config.load_settings()
        provider = settings.get("api_provider", "local")
        info = APIClient.PROVIDERS.get(provider, {})
        name = info.get("name", "未知")
        model = settings.get("api_model", "")
        if provider == "local":
            self.model_label.setText("📋 模式: 仅检索（无模型）")
            self.model_label.setStyleSheet("color: #a6e3a1; font-size: 13px;")
        elif provider == "ollama":
            self.model_label.setText(f"🖥️ 模式: {name} - {model}")
            self.model_label.setStyleSheet("color: #89b4fa; font-size: 13px;")
        else:
            self.model_label.setText(f"☁️ 模式: {name} - {model}")
            self.model_label.setStyleSheet("color: #f9e2af; font-size: 13px;")

    def _open_settings(self):
        """打开设置对话框"""
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self._update_model_label()
            QMessageBox.information(self, "设置", "API设置已保存，下次问答将使用新配置。")

    def eventFilter(self, obj, event):
        if obj == self.input_box and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key_Return and not event.modifiers() & Qt.ShiftModifier:
                self.send_question()
                return True
        return super().eventFilter(obj, event)

    def send_question(self):
        question = self.input_box.toPlainText().strip()
        if not question:
            return

        self.add_bubble(question, "user")
        self.input_box.clear()
        self.send_btn.setEnabled(False)
        self.source_panel.clear_sources()

        self.current_bubble = self.add_bubble("思考中...", "assistant")

        self.worker = QAWorker(question, history=self.history)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.chunk_received.connect(self.on_chunk)
        self.worker.sources_received.connect(self.on_sources)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)

        self.thread.start()

    def add_bubble(self, content, role, sources=None):
        bubble = ChatBubble(content, role, sources)
        self.chat_layout.addWidget(bubble)
        self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        )
        return bubble

    def on_chunk(self, text):
        if self.current_bubble:
            label = self.current_bubble.findChild(QLabel, "contentLabel")
            if label:
                current = label.text()
                if current == "思考中...":
                    label.setText(text)
                else:
                    label.setText(current + text)

    def on_sources(self, sources):
        if sources:
            self.source_panel.set_sources(sources)

    def on_finished(self, answer):
        self.send_btn.setEnabled(True)
        if self.current_bubble:
            label = self.current_bubble.findChild(QLabel, "contentLabel")
            if label:
                # 本地模式：完整回答可能已经通过chunk流式输出，也可能直接传入
                if label.text() == "思考中...":
                    label.setText(answer)
                # 否则保持流式输出结果

        if self.chat_layout.count() > 1:
            user_bubble = self.chat_layout.itemAt(self.chat_layout.count() - 2).widget()
            if user_bubble:
                user_label = user_bubble.findChild(QLabel, "contentLabel")
                user_text = user_label.text() if user_label else ""
            else:
                user_text = ""
        else:
            user_text = ""
        self.history.append({"user": user_text, "assistant": answer})
        self.current_bubble = None

    def on_error(self, msg):
        self.send_btn.setEnabled(True)
        if self.current_bubble:
            label = self.current_bubble.findChild(QLabel, "contentLabel")
            if label:
                label.setText(f"错误: {msg}")
        self.source_panel.clear_sources()
        self.current_bubble = None
        QMessageBox.warning(self, "问答错误", msg)

    def on_mode_changed(self):
        mode_map = {0: "vector", 1: "bm25", 2: "hybrid"}
        mode = mode_map[self.mode_group.checkedId()]
        try:
            settings = config.load_settings()
            settings["retrieval_mode"] = mode
            config.save_settings(settings)
        except Exception:
            pass

    def _on_source_clicked(self, source: dict):
        dialog = DocumentPreviewDialog(self.db, source, parent=self)
        dialog.exec()