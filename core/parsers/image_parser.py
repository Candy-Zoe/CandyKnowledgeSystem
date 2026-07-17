"""
图片OCR解析器

支持格式：
- JPG/JPEG
- PNG
- BMP
- GIF（第一帧）
- TIFF
- WEBP

解析策略：
1. 优先使用 easyocr（如果已安装）
2. 回退到 pytesseract（如果已安装）
3. 如果没有OCR库，返回提示信息
"""
import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ImageParser:
    """图片OCR解析器"""

    SUPPORTED_FORMATS = {"jpg", "jpeg", "png", "bmp", "gif", "tiff", "tif", "webp"}

    def parse(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        ext = path.suffix.lower().lstrip(".")
        if ext not in self.SUPPORTED_FORMATS:
            raise ValueError(f"不支持的图片格式: {ext}")

        # 尝试 easyocr
        try:
            return self._parse_with_easyocr(file_path)
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"easyocr解析失败: {e}")

        # 尝试 pytesseract
        try:
            return self._parse_with_pytesseract(file_path)
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"pytesseract解析失败: {e}")

        return (
            "[图片OCR] 未能提取图片中的文本。"
            "请安装OCR库：pip install easyocr 或 pip install pytesseract"
        )

    def _parse_with_easyocr(self, file_path: str) -> str:
        import easyocr
        import numpy as np
        from PIL import Image

        reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
        img = Image.open(file_path)
        img_array = np.array(img)
        results = reader.readtext(img_array)
        texts = [r[1] for r in results if r[1].strip()]
        return "\n".join(texts)

    def _parse_with_pytesseract(self, file_path: str) -> str:
        import pytesseract
        from PIL import Image

        img = Image.open(file_path)
        text = pytesseract.image_to_string(img, lang="chi_sim+eng")
        return text.strip()
