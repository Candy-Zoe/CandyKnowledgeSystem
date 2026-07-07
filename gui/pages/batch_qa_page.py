from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QPlainTextEdit, QTableWidget, QTableWidgetItem, QProgressBar,
    QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, QThread
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from gui.workers.batch_qa_worker import BatchQAWorker


class BatchQAPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.thread = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("批量问答")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)

        hint = QLabel("每行输入一个问题")
        hint.setStyleSheet("color: #a6adc8; font-size: 12px;")
        layout.addWidget(hint)

        self.input_box = QPlainTextEdit()
        self.input_box.setPlaceholderText("请输入问题，每行一个...\n例如：\n什么是机器学习？\n深度学习有哪些应用？")
        layout.addWidget(self.input_box)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("开始批量问答")
        self.start_btn.clicked.connect(self.start_batch)
        self.export_btn = QPushButton("导出结果")
        self.export_btn.clicked.connect(self.export_results)
        self.export_btn.setEnabled(False)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.export_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        layout.addWidget(self.status_label)

        self.result_table = QTableWidget()
        self.result_table.setColumnCount(3)
        self.result_table.setHorizontalHeaderLabels(["问题", "回答", "来源"])
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.result_table, 1)

        self.results = []

    def start_batch(self):
        text = self.input_box.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "请输入问题")
            return

        questions = [q.strip() for q in text.split("\n") if q.strip()]
        if not questions:
            return

        self.start_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(questions))
        self.progress_bar.setValue(0)
        self.result_table.setRowCount(0)
        self.results = []

        self.worker = BatchQAWorker(questions)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.question_done.connect(self.on_question_done)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)

        self.thread.start()

    def on_progress(self, current, total, answer):
        self.progress_bar.setValue(current)
        self.status_label.setText(f"已完成 {current}/{total}")

    def on_question_done(self, index, question, answer, sources):
        self.results.append({"question": question, "answer": answer, "sources": sources})
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)
        self.result_table.setItem(row, 0, QTableWidgetItem(question[:100]))
        self.result_table.setItem(row, 1, QTableWidgetItem(answer[:200]))
        source_text = ", ".join([s.get("document", "") for s in sources[:3]])
        self.result_table.setItem(row, 2, QTableWidgetItem(source_text))

    def on_finished(self, batch_id):
        self.start_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"批量问答完成，共 {len(self.results)} 条结果")

    def on_error(self, msg):
        self.start_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"错误: {msg}")
        QMessageBox.warning(self, "错误", msg)

    def export_results(self):
        if not self.results:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出结果", "batch_results.csv", "CSV Files (*.csv);;JSON Files (*.json)"
        )
        if not path:
            return
        try:
            if path.endswith(".json"):
                import json
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.results, f, ensure_ascii=False, indent=2)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("问题,回答,来源\n")
                    for r in self.results:
                        answer = r["answer"].replace('"', '""')
                        question = r["question"].replace('"', '""')
                        sources = ", ".join([s.get("document", "") for s in r.get("sources", [])])
                        f.write(f'"{question}","{answer}","{sources}"\n')
            QMessageBox.information(self, "成功", f"结果已导出到: {path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))
