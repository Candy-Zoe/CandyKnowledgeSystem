from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QSpinBox, QDoubleSpinBox,
    QLineEdit, QProgressBar, QTextEdit, QMessageBox, QCheckBox
)
from PySide6.QtCore import Qt, QThread
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from gui.workers.finetune_worker import FinetuneWorker


class FinetunePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.thread = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("模型微调")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)

        config_layout = QHBoxLayout()

        left_config = QVBoxLayout()
        left_config.addWidget(QLabel("模型名称:"))
        self.model_name_input = QLineEdit("my_finetuned_model")
        left_config.addWidget(self.model_name_input)

        left_config.addWidget(QLabel("基础模型:"))
        self.base_model_input = QLineEdit(config.DEFAULT_BASE_MODEL)
        left_config.addWidget(self.base_model_input)

        config_layout.addLayout(left_config, 1)

        right_config = QVBoxLayout()
        epochs_row = QHBoxLayout()
        epochs_row.addWidget(QLabel("Epochs:"))
        self.epochs_spin = QSpinBox()
        self.epochs_spin.setRange(1, 100)
        self.epochs_spin.setValue(config.DEFAULT_EPOCHS)
        epochs_row.addWidget(self.epochs_spin)
        right_config.addLayout(epochs_row)

        rank_row = QHBoxLayout()
        rank_row.addWidget(QLabel("LoRA Rank:"))
        self.lora_spin = QSpinBox()
        self.lora_spin.setRange(4, 128)
        self.lora_spin.setValue(config.DEFAULT_LORA_RANK)
        rank_row.addWidget(self.lora_spin)
        right_config.addLayout(rank_row)

        batch_row = QHBoxLayout()
        batch_row.addWidget(QLabel("Batch Size:"))
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 32)
        self.batch_spin.setValue(config.DEFAULT_BATCH_SIZE)
        batch_row.addWidget(self.batch_spin)
        right_config.addLayout(batch_row)

        lr_row = QHBoxLayout()
        lr_row.addWidget(QLabel("学习率:"))
        self.lr_spin = QDoubleSpinBox()
        self.lr_spin.setRange(1e-6, 1e-2)
        self.lr_spin.setDecimals(6)
        self.lr_spin.setValue(config.DEFAULT_LR)
        lr_row.addWidget(self.lr_spin)
        right_config.addLayout(lr_row)

        config_layout.addLayout(right_config, 1)
        layout.addLayout(config_layout)

        layout.addWidget(QLabel("训练数据:"))
        self.data_table = QTableWidget()
        self.data_table.setColumnCount(4)
        self.data_table.setHorizontalHeaderLabels(["选择", "问题", "回答", "来源"])
        self.data_table.horizontalHeader().setStretchLastSection(True)
        self.data_table.setMaximumHeight(200)
        layout.addWidget(self.data_table)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("开始训练")
        self.start_btn.clicked.connect(self.start_training)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self.stop_training)
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        self.log_text.setStyleSheet("background-color: #1e1e2e; font-family: Consolas; font-size: 12px;")
        layout.addWidget(self.log_text)

    def showEvent(self, event):
        super().showEvent(event)
        self.load_training_pairs()

    def load_training_pairs(self):
        try:
            db = DatabaseManager(str(config.DB_PATH))
            pairs = db.list_training_pairs()
            self.data_table.setRowCount(len(pairs))
            for row, pair in enumerate(pairs):
                checkbox = QTableWidgetItem()
                checkbox.setCheckState(Qt.Checked)
                self.data_table.setItem(row, 0, checkbox)
                self.data_table.setItem(row, 1, QTableWidgetItem(pair["question"][:100]))
                self.data_table.setItem(row, 2, QTableWidgetItem(pair["answer"][:100]))
                self.data_table.setItem(row, 3, QTableWidgetItem(str(pair.get("document_id", ""))))
        except Exception as e:
            print(f"加载训练数据失败: {e}")

    def start_training(self):
        pairs = []
        for row in range(self.data_table.rowCount()):
            checkbox = self.data_table.item(row, 0)
            if checkbox and checkbox.checkState() == Qt.Checked:
                question = self.data_table.item(row, 1).text()
                answer = self.data_table.item(row, 2).text()
                pairs.append({"question": question, "answer": answer})

        if not pairs:
            QMessageBox.warning(self, "提示", "请选择训练数据")
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(self.epochs_spin.value())
        self.log_text.clear()

        self.worker = FinetuneWorker(
            pairs, self.model_name_input.text(),
            self.base_model_input.text(), self.epochs_spin.value(),
            self.lora_spin.value(), self.batch_spin.value(), self.lr_spin.value()
        )
        self.thread = QThread()
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.log_message.connect(self.on_log)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)

        self.thread.start()

    def stop_training(self):
        if self.worker:
            self.worker.cancel()
            self.log_text.append("正在停止训练...")

    def on_progress(self, current, total):
        self.progress_bar.setValue(current)

    def on_log(self, msg):
        self.log_text.append(msg)

    def on_finished(self, output_path):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.log_text.append(f"\n训练完成! 模型保存在: {output_path}")

    def on_error(self, msg):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.log_text.append(f"\n错误: {msg}")
        QMessageBox.warning(self, "训练错误", msg)
