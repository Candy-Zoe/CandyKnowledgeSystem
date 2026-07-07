from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QRadioButton,
    QButtonGroup, QTabWidget, QSlider, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("系统设置")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)

        tabs = QTabWidget()

        model_tab = QWidget()
        model_layout = QVBoxLayout(model_tab)

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("模型来源:"))
        self.source_group = QButtonGroup()
        self.local_radio = QRadioButton("本地模型")
        self.api_radio = QRadioButton("API")
        self.source_group.addButton(self.local_radio, 0)
        self.source_group.addButton(self.api_radio, 1)
        source_row.addWidget(self.local_radio)
        source_row.addWidget(self.api_radio)
        source_row.addStretch()
        model_layout.addLayout(source_row)

        model_layout.addWidget(QLabel("本地模型路径:"))
        model_path_row = QHBoxLayout()
        self.model_path_input = QLineEdit()
        model_path_btn = QPushButton("浏览")
        model_path_btn.clicked.connect(self.browse_model_path)
        model_path_row.addWidget(self.model_path_input)
        model_path_row.addWidget(model_path_btn)
        model_layout.addLayout(model_path_row)

        model_layout.addWidget(QLabel("API 提供商:"))
        self.api_provider_combo = QComboBox()
        self.api_provider_combo.addItems(["qwen", "openai", "zhipu", "custom"])
        model_layout.addWidget(self.api_provider_combo)

        model_layout.addWidget(QLabel("API Key:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        model_layout.addWidget(self.api_key_input)

        model_layout.addWidget(QLabel("API Base URL (可选):"))
        self.api_url_input = QLineEdit()
        model_layout.addWidget(self.api_url_input)

        model_layout.addWidget(QLabel("API 模型:"))
        self.api_model_input = QLineEdit("qwen-turbo")
        model_layout.addWidget(self.api_model_input)

        model_layout.addStretch()
        tabs.addTab(model_tab, "模型设置")

        chunk_tab = QWidget()
        chunk_layout = QVBoxLayout(chunk_tab)

        chunk_layout.addWidget(QLabel("分块策略:"))
        self.chunk_strategy_combo = QComboBox()
        self.chunk_strategy_combo.addItems(["semantic", "fixed", "sentence"])
        chunk_layout.addWidget(self.chunk_strategy_combo)

        chunk_layout.addWidget(QLabel("分块大小:"))
        self.chunk_size_spin = QSpinBox()
        self.chunk_size_spin.setRange(64, 4096)
        self.chunk_size_spin.setValue(512)
        chunk_layout.addWidget(self.chunk_size_spin)

        chunk_layout.addWidget(QLabel("分块重叠:"))
        self.chunk_overlap_spin = QSpinBox()
        self.chunk_overlap_spin.setRange(0, 512)
        self.chunk_overlap_spin.setValue(64)
        chunk_layout.addWidget(self.chunk_overlap_spin)

        chunk_layout.addStretch()
        tabs.addTab(chunk_tab, "分块设置")

        retrieval_tab = QWidget()
        retrieval_layout = QVBoxLayout(retrieval_tab)

        retrieval_layout.addWidget(QLabel("检索模式:"))
        self.retrieval_combo = QComboBox()
        self.retrieval_combo.addItems(["vector", "bm25", "hybrid"])
        retrieval_layout.addWidget(self.retrieval_combo)

        retrieval_layout.addWidget(QLabel("向量权重:"))
        self.vector_weight_slider = QSlider(Qt.Horizontal)
        self.vector_weight_slider.setRange(0, 100)
        self.vector_weight_slider.setValue(70)
        self.vector_weight_label = QLabel("0.7")
        self.vector_weight_slider.valueChanged.connect(
            lambda v: self.vector_weight_label.setText(f"{v/100:.1f}")
        )
        weight_row = QHBoxLayout()
        weight_row.addWidget(self.vector_weight_slider)
        weight_row.addWidget(self.vector_weight_label)
        retrieval_layout.addLayout(weight_row)

        retrieval_layout.addWidget(QLabel("BM25 权重:"))
        self.bm25_weight_slider = QSlider(Qt.Horizontal)
        self.bm25_weight_slider.setRange(0, 100)
        self.bm25_weight_slider.setValue(30)
        self.bm25_weight_label = QLabel("0.3")
        self.bm25_weight_slider.valueChanged.connect(
            lambda v: self.bm25_weight_label.setText(f"{v/100:.1f}")
        )
        bm25_row = QHBoxLayout()
        bm25_row.addWidget(self.bm25_weight_slider)
        bm25_row.addWidget(self.bm25_weight_label)
        retrieval_layout.addLayout(bm25_row)

        retrieval_layout.addWidget(QLabel("Top K:"))
        self.top_k_spin = QSpinBox()
        self.top_k_spin.setRange(1, 50)
        self.top_k_spin.setValue(5)
        retrieval_layout.addWidget(self.top_k_spin)

        retrieval_layout.addWidget(QLabel("相似度阈值:"))
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(0, 100)
        self.threshold_slider.setValue(30)
        self.threshold_label = QLabel("0.3")
        self.threshold_slider.valueChanged.connect(
            lambda v: self.threshold_label.setText(f"{v/100:.1f}")
        )
        thresh_row = QHBoxLayout()
        thresh_row.addWidget(self.threshold_slider)
        thresh_row.addWidget(self.threshold_label)
        retrieval_layout.addLayout(thresh_row)

        retrieval_layout.addStretch()
        tabs.addTab(retrieval_tab, "检索设置")

        gen_tab = QWidget()
        gen_layout = QVBoxLayout(gen_tab)

        gen_layout.addWidget(QLabel("Temperature:"))
        self.temp_slider = QSlider(Qt.Horizontal)
        self.temp_slider.setRange(0, 100)
        self.temp_slider.setValue(70)
        self.temp_label = QLabel("0.7")
        self.temp_slider.valueChanged.connect(
            lambda v: self.temp_label.setText(f"{v/100:.1f}")
        )
        temp_row = QHBoxLayout()
        temp_row.addWidget(self.temp_slider)
        temp_row.addWidget(self.temp_label)
        gen_layout.addLayout(temp_row)

        gen_layout.addWidget(QLabel("Max Tokens:"))
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(64, 8192)
        self.max_tokens_spin.setValue(1024)
        gen_layout.addWidget(self.max_tokens_spin)

        gen_layout.addWidget(QLabel("Embedding 模型:"))
        self.embedding_input = QLineEdit("BAAI/bge-small-zh-v1.5")
        gen_layout.addWidget(self.embedding_input)

        gen_layout.addStretch()
        tabs.addTab(gen_tab, "生成设置")

        layout.addWidget(tabs)

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("保存设置")
        self.save_btn.clicked.connect(self.save_settings)
        self.test_api_btn = QPushButton("测试 API 连接")
        self.test_api_btn.clicked.connect(self.test_api)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.test_api_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def load_settings(self):
        settings = config.load_settings()

        source = settings.get("model_source", "local")
        if source == "api":
            self.api_radio.setChecked(True)
        else:
            self.local_radio.setChecked(True)

        self.model_path_input.setText(settings.get("local_model_path", ""))
        self.api_provider_combo.setCurrentText(settings.get("api_provider", "qwen"))
        self.api_key_input.setText(settings.get("api_key", ""))
        self.api_url_input.setText(settings.get("api_base_url", ""))
        self.api_model_input.setText(settings.get("api_model", "qwen-turbo"))

        self.chunk_strategy_combo.setCurrentText(settings.get("chunk_strategy", "semantic"))
        self.chunk_size_spin.setValue(settings.get("chunk_size", 512))
        self.chunk_overlap_spin.setValue(settings.get("chunk_overlap", 64))

        self.retrieval_combo.setCurrentText(settings.get("retrieval_mode", "hybrid"))
        self.vector_weight_slider.setValue(int(settings.get("vector_weight", 0.7) * 100))
        self.bm25_weight_slider.setValue(int(settings.get("bm25_weight", 0.3) * 100))
        self.top_k_spin.setValue(settings.get("top_k", 5))
        self.threshold_slider.setValue(int(settings.get("similarity_threshold", 0.3) * 100))

        self.temp_slider.setValue(int(settings.get("temperature", 0.7) * 100))
        self.max_tokens_spin.setValue(settings.get("max_tokens", 1024))
        self.embedding_input.setText(settings.get("embedding_model", "BAAI/bge-small-zh-v1.5"))

    def save_settings(self):
        settings = {
            "model_source": "api" if self.api_radio.isChecked() else "local",
            "local_model_path": self.model_path_input.text(),
            "api_provider": self.api_provider_combo.currentText(),
            "api_key": self.api_key_input.text(),
            "api_base_url": self.api_url_input.text(),
            "api_model": self.api_model_input.text(),
            "chunk_strategy": self.chunk_strategy_combo.currentText(),
            "chunk_size": self.chunk_size_spin.value(),
            "chunk_overlap": self.chunk_overlap_spin.value(),
            "retrieval_mode": self.retrieval_combo.currentText(),
            "vector_weight": self.vector_weight_slider.value() / 100,
            "bm25_weight": self.bm25_weight_slider.value() / 100,
            "top_k": self.top_k_spin.value(),
            "similarity_threshold": self.threshold_slider.value() / 100,
            "temperature": self.temp_slider.value() / 100,
            "max_tokens": self.max_tokens_spin.value(),
            "embedding_model": self.embedding_input.text(),
        }
        try:
            config.save_settings(settings)
            QMessageBox.information(self, "成功", "设置已保存")
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))

    def browse_model_path(self):
        path = QFileDialog.getExistingDirectory(self, "选择模型目录")
        if path:
            self.model_path_input.setText(path)

    def test_api(self):
        if not self.api_key_input.text():
            QMessageBox.warning(self, "提示", "请先输入 API Key")
            return
        try:
            from core.api_client import APIClient
            client = APIClient(
                provider=self.api_provider_combo.currentText(),
                api_key=self.api_key_input.text(),
                base_url=self.api_url_input.text(),
                model=self.api_model_input.text(),
            )
            response = client.chat([{"role": "user", "content": "你好"}])
            QMessageBox.information(self, "成功", f"API 连接成功!\n响应: {response[:100]}...")
        except Exception as e:
            QMessageBox.warning(self, "失败", f"API 连接失败:\n{e}")
