from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QListWidget, QListWidgetItem, QComboBox,
    QProgressBar, QMessageBox, QSlider, QGroupBox, QFormLayout, QSpinBox
)
from PySide6.QtCore import Qt, QThread
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from gui.workers.upload_worker import UploadWorker


class UploadPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_paths = []
        self.worker = None
        self.thread = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("文档上传")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)

        kb_row = QHBoxLayout()
        kb_row.addWidget(QLabel("目标知识库:"))
        self.kb_combo = QComboBox()
        self.kb_combo.setMinimumWidth(200)
        kb_row.addWidget(self.kb_combo)
        kb_row.addStretch()
        layout.addLayout(kb_row)

        # 解析设置
        cpu_group = QGroupBox("解析设置")
        cpu_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #45475a;
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 16px;
                color: #cdd6f4;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
        """)
        cpu_layout = QFormLayout(cpu_group)

        settings = config.load_settings()

        # 页面休眠时间
        self.sleep_spin = QSpinBox()
        self.sleep_spin.setRange(0, 1000)
        self.sleep_spin.setSingleStep(50)
        self.sleep_spin.setValue(settings.get("page_sleep_ms", 100))
        self.sleep_spin.setSuffix(" ms")
        self.sleep_spin.setToolTip("每页处理后暂停时间，值越大越不占 CPU")
        cpu_layout.addRow("页面休眠:", self.sleep_spin)

        # PDF 最大页数
        self.max_pages_spin = QSpinBox()
        self.max_pages_spin.setRange(0, 10000)
        self.max_pages_spin.setSpecialValueText("不限制")
        self.max_pages_spin.setValue(settings.get("max_pdf_pages", 500))
        self.max_pages_spin.setSuffix(" 页")
        self.max_pages_spin.setToolTip("超过此页数的 PDF 只处理前 N 页（0=不限制）")
        cpu_layout.addRow("PDF 最大页数:", self.max_pages_spin)

        # 分块大小
        self.chunk_size_spin = QSpinBox()
        self.chunk_size_spin.setRange(128, 4096)
        self.chunk_size_spin.setSingleStep(128)
        self.chunk_size_spin.setValue(settings.get("chunk_size", config.CHUNK_SIZE))
        self.chunk_size_spin.setSuffix(" token")
        self.chunk_size_spin.setToolTip("解析后的文本按此大小分块，便于关键词定位原文")
        cpu_layout.addRow("分块大小:", self.chunk_size_spin)

        # 分块重叠
        self.chunk_overlap_spin = QSpinBox()
        self.chunk_overlap_spin.setRange(0, 512)
        self.chunk_overlap_spin.setSingleStep(16)
        self.chunk_overlap_spin.setValue(settings.get("chunk_overlap", config.CHUNK_OVERLAP))
        self.chunk_overlap_spin.setSuffix(" token")
        cpu_layout.addRow("分块重叠:", self.chunk_overlap_spin)

        layout.addWidget(cpu_group)

        btn_row = QHBoxLayout()
        self.select_btn = QPushButton("选择文件")
        self.select_btn.clicked.connect(self.select_files)
        self.upload_btn = QPushButton("开始上传")
        self.upload_btn.clicked.connect(self.start_upload)
        self.upload_btn.setEnabled(False)
        btn_row.addWidget(self.select_btn)
        btn_row.addWidget(self.upload_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 8px;
                padding: 8px;
            }
            QListWidget::item {
                background-color: #1e1e2e;
                border-radius: 6px;
                padding: 8px;
                margin: 2px;
            }
        """)
        layout.addWidget(self.file_list)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        layout.addWidget(self.status_label)

    def showEvent(self, event):
        super().showEvent(event)
        self.load_knowledge_bases()

    def load_knowledge_bases(self):
        self.kb_combo.clear()
        try:
            db = DatabaseManager(str(config.DB_PATH))
            kbs = db.list_knowledge_bases()
            for kb in kbs:
                self.kb_combo.addItem(kb["name"], kb["id"])
            if not kbs:
                self.kb_combo.addItem("默认知识库", None)
        except Exception:
            self.kb_combo.addItem("默认知识库", None)

    def _save_settings(self):
        settings = config.load_settings()
        settings["page_sleep_ms"] = self.sleep_spin.value()
        settings["max_pdf_pages"] = self.max_pages_spin.value()
        settings["chunk_size"] = self.chunk_size_spin.value()
        settings["chunk_overlap"] = self.chunk_overlap_spin.value()
        config.save_settings(settings)

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择文件", "",
            "所有支持的文件 ("
            "*.pdf *.docx *.doc *.dotx *.dotm *.pptx *.ppt *.potx *.potm *.xlsx *.xls *.xlsm *.xltx *.xlam *.xlsb "
            "*.epub *.rtf *.odt *.ods *.odp *.mht *.mhtml "
            "*.mp3 *.wav *.flac *.aac *.m4a *.ogg *.wma *.opus "
            "*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.m4v *.3gp "
            "*.srt *.vtt *.ass *.ssa *.sub "
            "*.txt *.md *.html *.htm *.csv *.tsv "
            "*.json *.xml *.yaml *.yml *.toml *.ini *.conf *.cfg *.properties *.log "
            "*.py *.js *.java *.c *.cpp *.h *.hpp *.cs *.go *.rs "
            "*.rb *.php *.swift *.kt *.scala *.r *.m *.mm "
            "*.sql *.sh *.bat *.cmd *.ps1 *.bash *.zsh "
            "*.css *.scss *.sass *.less *.vue *.jsx *.tsx "
            "*.tex *.bib *.rst *.adoc *.org "
            "*.zip "
            "*.jpg *.jpeg *.png *.bmp *.gif *.tiff *.tif *.webp);;"
            "PDF (*.pdf);;"
            "Word (*.docx *.doc *.dotx *.dotm);;"
            "PowerPoint (*.pptx *.ppt *.potx *.potm);;"
            "Excel (*.xlsx *.xls *.xlsm *.xltx *.xlam *.xlsb);;"
            "EPUB (*.epub);;"
            "RTF (*.rtf);;"
            "OpenDocument (*.odt *.ods *.odp);;"
            "MHTML (*.mht *.mhtml);;"
            "音频 (*.mp3 *.wav *.flac *.aac *.m4a *.ogg *.wma *.opus);;"
            "视频 (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.m4v *.3gp);;"
            "字幕 (*.srt *.vtt *.ass *.ssa *.sub);;"
            "文本 (*.txt *.md);;"
            "网页 (*.html *.htm);;"
            "数据文件 (*.json *.xml *.yaml *.yml *.toml *.ini *.conf *.cfg *.properties *.log);;"
            "代码文件 (*.py *.js *.java *.c *.cpp *.h *.hpp *.cs *.go *.rs *.rb *.php *.swift *.kt *.scala *.r *.m *.mm *.sql *.sh *.bat *.cmd *.ps1 *.bash *.zsh *.css *.scss *.sass *.less *.vue *.jsx *.tsx *.tex *.bib *.rst *.adoc *.org);;"
            "表格 (*.csv *.tsv);;"
            "压缩包 (*.zip);;"
            "图片OCR (*.jpg *.jpeg *.png *.bmp *.gif *.tiff *.tif *.webp)"
        )
        if files:
            self.file_paths = files
            self.file_list.clear()
            for f in files:
                item = QListWidgetItem(os.path.basename(f))
                self.file_list.addItem(item)
            self.upload_btn.setEnabled(True)
            self.status_label.setText(f"已选择 {len(files)} 个文件")

    def start_upload(self):
        if not self.file_paths:
            return

        self._save_settings()

        self.upload_btn.setEnabled(False)
        self.select_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self.file_paths))
        self.progress_bar.setValue(0)

        kb_id = self.kb_combo.currentData()

        self.worker = UploadWorker(self.file_paths, kb_id)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.page_progress.connect(self.on_page_progress)
        self.worker.file_done.connect(self.on_file_done)
        self.worker.all_done.connect(self.on_all_done)
        self.worker.error.connect(self.on_error)
        self.worker.all_done.connect(self.thread.quit)

        self.thread.start()

    def on_progress(self, file_idx, percent):
        self.progress_bar.setValue(file_idx)
        self.status_label.setText(f"正在处理第 {file_idx + 1} 个文件... ({percent}%)")

    def on_page_progress(self, info):
        self.status_label.setText(info)

    def on_file_done(self, doc_id, status, message):
        if status == "completed":
            self.status_label.setText(f"文档处理完成: {message}")
        else:
            self.status_label.setText(f"处理失败: {message}")

    def on_all_done(self):
        self.upload_btn.setEnabled(True)
        self.select_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("所有文件上传完成")
        self.file_paths = []
        self.file_list.clear()

    def on_error(self, msg):
        self.upload_btn.setEnabled(True)
        self.select_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"错误: {msg}")
        QMessageBox.warning(self, "上传错误", msg)
