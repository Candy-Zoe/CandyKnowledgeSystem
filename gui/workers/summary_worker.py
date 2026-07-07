from PySide6.QtCore import QObject, Signal
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from core.api_client import APIClient


class SummaryWorker(QObject):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, doc_id):
        super().__init__()
        self.doc_id = doc_id

    def run(self):
        try:
            settings = config.load_settings()
            db = DatabaseManager(str(config.DB_PATH))
            content = db.get_document_content(self.doc_id)

            if not content:
                self.error.emit("文档内容为空")
                return

            if settings.get("model_source") == "api" and settings.get("api_key"):
                client = APIClient(
                    provider=settings.get("api_provider", "qwen"),
                    api_key=settings.get("api_key", ""),
                    base_url=settings.get("api_base_url", ""),
                    model=settings.get("api_model", ""),
                )
                messages = [
                    {"role": "system", "content": "你是一个文档摘要助手，请对以下文档内容进行简洁准确的摘要。"},
                    {"role": "user", "content": f"请对以下文档进行摘要：\n\n{content[:6000]}"}
                ]
                summary = client.chat(messages, temperature=0.3, max_tokens=1024)
            else:
                summary = f"文档摘要（本地模式暂不支持自动生成，请配置 API 后使用）：\n\n{content[:500]}..."

            db.save_summary(self.doc_id, summary)
            self.finished.emit(summary)

        except Exception as e:
            self.error.emit(str(e))
