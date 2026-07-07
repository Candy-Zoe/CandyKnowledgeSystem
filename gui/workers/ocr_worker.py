from PySide6.QtCore import QObject, Signal
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager


class OCRWorker(QObject):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, image_path):
        super().__init__()
        self.image_path = image_path

    def run(self):
        try:
            db = DatabaseManager(str(config.DB_PATH))
            settings = config.load_settings()

            text = ""
            try:
                import pytesseract
                from PIL import Image
                img = Image.open(self.image_path)
                lang = settings.get("ocr_lang", "chi_sim+eng")
                text = pytesseract.image_to_string(img, lang=lang)
            except ImportError:
                text = "pytesseract 未安装，请运行: pip install pytesseract Pillow"
            except Exception as e:
                text = f"OCR 识别失败: {e}"

            if not text.strip():
                text = "未能识别出文字内容"

            db.save_ocr_result(self.image_path, text)
            self.finished.emit(text)

        except Exception as e:
            self.error.emit(str(e))
