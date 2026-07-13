"""
Candy PDF 解析器
专门用于解析PDF文件，支持多种PDF类型：
- 普通文本PDF
- 表格型PDF
- 扫描版/图片型PDF（OCR）
- 混合型PDF
"""
import re
import io
import logging
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PDFPage:
    """单页解析结果"""
    page_number: int
    text: str = ""
    tables: list = field(default_factory=list)
    images_count: int = 0
    has_text: bool = False
    method: str = "text"  # text / ocr / mixed


@dataclass
class PDFResult:
    """完整解析结果"""
    file_path: str
    page_count: int = 0
    pages: list = field(default_factory=list)
    full_text: str = ""
    metadata: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def total_chars(self):
        return len(self.full_text)

    @property
    def is_empty(self):
        return self.total_chars == 0


class PDFParser:
    """
    专用PDF解析器
    
    解析策略：
    1. 优先使用 PyMuPDF 提取文本
    2. 使用 pdfplumber 提取表格
    3. 如果文本太少，尝试 OCR（需要 easyocr）
    4. 容错处理各种异常情况
    """

    def __init__(self, use_ocr=True, ocr_threshold=50, ocr_lang=None,
                 max_pages=0, page_sleep_ms=0):
        """
        Args:
            use_ocr: 是否在文本不足时启用OCR
            ocr_threshold: 每页平均字符数低于此值时触发OCR
            ocr_lang: OCR语言列表，如 ['ch_sim', 'en']
            max_pages: 最大处理页数，0=不限制
            page_sleep_ms: 每页处理后休眠毫秒数（CPU 节流），0=不休眠
        """
        self.use_ocr = use_ocr
        self.ocr_threshold = ocr_threshold
        self.ocr_lang = ocr_lang or ['ch_sim', 'en']
        self.max_pages = max_pages
        self.page_sleep_ms = page_sleep_ms
        self._ocr_reader = None

    def parse(self, file_path: str) -> PDFResult:
        """
        解析PDF文件
        
        Args:
            file_path: PDF文件路径
            
        Returns:
            PDFResult 解析结果
        """
        file_path = str(file_path)
        result = PDFResult(file_path=file_path)

        # 验证文件
        if not self._validate_file(file_path, result):
            return result

        # 尝试解析
        try:
            result = self._parse_with_pymupdf(file_path, result)
        except Exception as e:
            logger.error(f"PyMuPDF解析失败: {e}")
            result.errors.append(f"PyMuPDF解析失败: {str(e)}")

        # 如果PyMuPDF失败，尝试pdfplumber
        if result.is_empty or result.errors:
            try:
                result = self._parse_with_pdfplumber(file_path, result)
            except Exception as e:
                logger.error(f"pdfplumber解析也失败: {e}")
                result.errors.append(f"pdfplumber解析失败: {str(e)}")

        # 如果文本仍然太少，尝试OCR
        if result.is_empty and self.use_ocr:
            try:
                result = self._parse_with_ocr(file_path, result)
            except ImportError:
                result.warnings.append("OCR需要安装easyocr: pip install easyocr")
            except Exception as e:
                logger.error(f"OCR解析失败: {e}")
                result.errors.append(f"OCR解析失败: {str(e)}")

        # 合并所有页面文本
        self._merge_text(result)

        return result

    def _validate_file(self, file_path: str, result: PDFResult) -> bool:
        """验证文件有效性"""
        path = Path(file_path)
        if not path.exists():
            result.errors.append(f"文件不存在: {file_path}")
            return False
        if not path.suffix.lower() == '.pdf':
            result.errors.append(f"不是PDF文件: {file_path}")
            return False
        if path.stat().st_size == 0:
            result.errors.append("文件为空")
            return False
        return True

    def _parse_with_pymupdf(self, file_path: str, result: PDFResult) -> PDFResult:
        """使用PyMuPDF解析"""
        import fitz

        doc = fitz.open(file_path)
        total_pages = len(doc)
        result.page_count = total_pages

        # 应用页数限制
        pages_to_process = total_pages
        if self.max_pages > 0 and total_pages > self.max_pages:
            pages_to_process = self.max_pages
            result.warnings.append(f"PDF共{total_pages}页，已限制处理前{self.max_pages}页")

        # 提取元数据
        meta = doc.metadata
        if meta:
            result.metadata = {
                "title": meta.get("title", ""),
                "author": meta.get("author", ""),
                "subject": meta.get("subject", ""),
                "creator": meta.get("creator", ""),
                "producer": meta.get("producer", ""),
            }

        text_parts = []
        total_text_len = 0

        for i in range(pages_to_process):
            page = doc[i]
            page_result = PDFPage(page_number=i + 1)

            # 提取文本
            try:
                page_text = page.get_text("text")
                if page_text and page_text.strip():
                    page_result.text = page_text.strip()
                    page_result.has_text = True
                    total_text_len += len(page_result.text)
            except Exception as e:
                logger.warning(f"第{i+1}页文本提取失败: {e}")

            # 提取表格
            try:
                tables = page.find_tables()
                if tables and tables.tables:
                    for table in tables.tables:
                        table_data = table.extract()
                        if table_data:
                            table_text = self._format_table(table_data)
                            if table_text:
                                page_result.tables.append(table_text)
            except Exception as e:
                logger.warning(f"第{i+1}页表格提取失败: {e}")

            # 统计图片数量
            try:
                images = page.get_images(full=True)
                page_result.images_count = len(images)
            except Exception:
                pass

            result.pages.append(page_result)

            # CPU 节流：每页处理后休眠
            if self.page_sleep_ms > 0:
                import time
                time.sleep(self.page_sleep_ms / 1000.0)

        doc.close()

        # 判断是否需要OCR
        avg_text = total_text_len / result.page_count if result.page_count > 0 else 0
        if avg_text < self.ocr_threshold:
            result.warnings.append(f"平均每页仅{avg_text:.0f}字符，可能是扫描版PDF")

        return result

    def _parse_with_pdfplumber(self, file_path: str, result: PDFResult) -> PDFResult:
        """使用pdfplumber解析（表格提取更好）"""
        try:
            import pdfplumber
        except ImportError:
            result.warnings.append("pdfplumber未安装，跳过增强表格提取")
            return result

        try:
            with pdfplumber.open(file_path) as pdf:
                if not result.page_count:
                    result.page_count = len(pdf.pages)

                for i, page in enumerate(pdf.pages):
                    if i < len(result.pages):
                        page_result = result.pages[i]
                    else:
                        page_result = PDFPage(page_number=i + 1)
                        result.pages.append(page_result)

                    # pdfplumber提取文本
                    if not page_result.has_text:
                        try:
                            text = page.extract_text()
                            if text and text.strip():
                                page_result.text = text.strip()
                                page_result.has_text = True
                                page_result.method = "pdfplumber"
                        except Exception:
                            pass

                    # pdfplumber提取表格（更准确）
                    try:
                        tables = page.extract_tables()
                        if tables:
                            for table in tables:
                                if table:
                                    table_text = self._format_table(table)
                                    if table_text:
                                        # 避免重复添加
                                        if table_text not in page_result.tables:
                                            page_result.tables.append(table_text)
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"pdfplumber解析失败: {e}")
            result.errors.append(f"pdfplumber: {str(e)}")

        return result

    def _parse_with_ocr(self, file_path: str, result: PDFResult) -> PDFResult:
        """使用OCR解析扫描版PDF"""
        import fitz

        # 延迟初始化OCR reader
        if self._ocr_reader is None:
            try:
                import easyocr
                self._ocr_reader = easyocr.Reader(self.ocr_lang, gpu=False)
            except ImportError:
                raise ImportError("需要安装easyocr: pip install easyocr")

        doc = fitz.open(file_path)

        if not result.page_count:
            result.page_count = len(doc)

        for i, page in enumerate(doc):
            if i < len(result.pages) and result.pages[i].has_text:
                continue  # 已有文本，跳过

            page_result = result.pages[i] if i < len(result.pages) else PDFPage(page_number=i + 1)

            try:
                # 渲染页面为图片（降低分辨率减少 CPU 占用：1.5x 而非 2x）
                mat = fitz.Matrix(1.5, 1.5)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")

                # OCR识别
                import numpy as np
                from PIL import Image
                img = Image.open(io.BytesIO(img_data))
                img_array = np.array(img)

                results = self._ocr_reader.readtext(img_array)
                ocr_text = "\n".join([r[1] for r in results if r[1].strip()])

                if ocr_text.strip():
                    page_result.text = ocr_text.strip()
                    page_result.has_text = True
                    page_result.method = "ocr"

            except Exception as e:
                logger.warning(f"第{i+1}页OCR失败: {e}")

            if i >= len(result.pages):
                result.pages.append(page_result)

            # CPU 节流：OCR 每页后休眠（OCR 最耗 CPU，给其他进程喘息）
            if self.page_sleep_ms > 0:
                import time
                time.sleep(self.page_sleep_ms / 1000.0)

        doc.close()
        return result

    def _format_table(self, table_data: list) -> str:
        """格式化表格数据"""
        if not table_data:
            return ""

        rows = []
        for row in table_data:
            cells = [str(cell).strip() if cell else "" for cell in row]
            if any(cells):  # 至少有一个非空单元格
                rows.append(" | ".join(cells))

        return "\n".join(rows) if rows else ""

    def _merge_text(self, result: PDFResult):
        """合并所有页面文本"""
        parts = []
        for page in result.pages:
            page_parts = []

            if page.text:
                page_parts.append(f"[第{page.page_number}页]\n{page.text}")

            for table in page.tables:
                page_parts.append(f"[表格 第{page.page_number}页]\n{table}")

            if page_parts:
                parts.append("\n\n".join(page_parts))

        result.full_text = "\n\n".join(parts)


class PDFValidator:
    """PDF文件验证器"""

    @staticmethod
    def check(file_path: str) -> dict:
        """
        检查PDF文件状态
        
        Returns:
            dict: {"valid": bool, "issues": list, "info": dict}
        """
        result = {"valid": True, "issues": [], "info": {}}
        path = Path(file_path)

        if not path.exists():
            result["valid"] = False
            result["issues"].append("文件不存在")
            return result

        if path.stat().st_size == 0:
            result["valid"] = False
            result["issues"].append("文件为空")
            return result

        result["info"]["size_mb"] = round(path.stat().st_size / (1024 * 1024), 2)

        try:
            import fitz
            doc = fitz.open(file_path)
            result["info"]["page_count"] = len(doc)
            result["info"]["metadata"] = doc.metadata or {}

            # 检查是否加密
            if doc.is_encrypted:
                result["issues"].append("PDF已加密")

            # 检查是否为扫描版
            total_text = 0
            for page in doc:
                text = page.get_text("text")
                total_text += len(text.strip()) if text else 0

            avg_text = total_text / len(doc) if len(doc) > 0 else 0
            result["info"]["avg_chars_per_page"] = round(avg_text, 1)
            result["info"]["is_likely_scanned"] = avg_text < 50

            doc.close()
        except Exception as e:
            result["issues"].append(f"无法读取PDF: {str(e)}")
            result["valid"] = False

        return result


def parse_pdf(file_path: str, use_ocr=True, max_pages=0, page_sleep_ms=0) -> str:
    """
    便捷函数：解析PDF并返回文本
    
    Args:
        file_path: PDF文件路径
        use_ocr: 是否启用OCR
        max_pages: 最大处理页数，0=不限制
        page_sleep_ms: 每页处理后休眠毫秒数（CPU 节流）
        
    Returns:
        解析后的文本内容
    """
    parser = PDFParser(use_ocr=use_ocr, max_pages=max_pages, page_sleep_ms=page_sleep_ms)
    result = parser.parse(file_path)

    if result.errors and result.is_empty:
        raise RuntimeError(f"PDF解析失败: {'; '.join(result.errors)}")

    return result.full_text


def parse_pdf_with_info(file_path: str, use_ocr=True, max_pages=0, page_sleep_ms=0) -> tuple:
    """
    解析PDF并返回文本和详细信息
    
    Returns:
        (text, result): 文本内容和PDFResult对象
    """
    parser = PDFParser(use_ocr=use_ocr, max_pages=max_pages, page_sleep_ms=page_sleep_ms)
    result = parser.parse(file_path)
    return result.full_text, result


def validate_pdf(file_path: str) -> dict:
    """
    验证PDF文件
    
    Returns:
        验证结果字典
    """
    return PDFValidator.check(file_path)
