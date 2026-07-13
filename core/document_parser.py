import chardet
import csv
import io
from pathlib import Path
from docx import Document
from core.pdf_parser import PDFParser, parse_pdf
from core.logger import log, LogCapture


class DocumentParser:
    SUPPORTED_TYPES = {
        "pdf": "PDF文档",
        "docx": "Word文档",
        "doc": "Word文档(旧版)",
        "txt": "纯文本",
        "md": "Markdown",
        "html": "HTML网页",
        "htm": "HTML网页",
        "csv": "CSV表格",
        "xlsx": "Excel表格",
        "xls": "Excel表格(旧版)",
    }

    def __init__(self, max_pages=0, page_sleep_ms=0):
        """
        Args:
            max_pages: PDF最大处理页数，0=不限制
            page_sleep_ms: 每页处理后休眠毫秒数（CPU 节流）
        """
        self.max_pages = max_pages
        self.page_sleep_ms = page_sleep_ms

    def parse(self, file_path: str, file_type: str) -> str:
        file_type = file_type.lower().lstrip(".")
        log.info(f"开始解析文件: {file_path} (类型: {file_type})")
        
        parsers = {
            "pdf": lambda fp: parse_pdf(
                fp, use_ocr=True,
                max_pages=self.max_pages,
                page_sleep_ms=self.page_sleep_ms
            ),
            "docx": DocumentParser.parse_docx,
            "doc": DocumentParser.parse_docx,
            "txt": DocumentParser.parse_txt,
            "md": DocumentParser.parse_markdown,
            "html": DocumentParser.parse_html,
            "htm": DocumentParser.parse_html,
            "csv": DocumentParser.parse_csv,
            "xlsx": DocumentParser.parse_excel,
            "xls": DocumentParser.parse_excel,
        }
        parser = parsers.get(file_type)
        if not parser:
            error_msg = f"不支持的文件类型: {file_type}，支持: {', '.join(DocumentParser.SUPPORTED_TYPES.keys())}"
            log.error(error_msg)
            raise ValueError(error_msg)
        
        try:
            result = parser(file_path)
            log.info(f"解析完成: {file_path} -> {len(result)} 字符")
            return result
        except Exception as e:
            log.error(f"解析失败: {file_path} - {e}")
            raise

    @staticmethod
    def get_metadata(file_path: str, file_type: str) -> dict:
        file_type = file_type.lower().lstrip(".")
        metadata = {
            "file_type": file_type,
            "file_size": Path(file_path).stat().st_size,
        }
        if file_type == "pdf":
            try:
                from core.pdf_parser import PDFValidator
                check = PDFValidator.check(file_path)
                metadata.update(check.get("info", {}))
            except Exception:
                pass
        elif file_type in ("docx", "doc"):
            try:
                doc = Document(file_path)
                core = doc.core_properties
                metadata["title"] = core.title or ""
                metadata["author"] = core.author or ""
                metadata["paragraph_count"] = len(doc.paragraphs)
                metadata["table_count"] = len(doc.tables)
            except Exception:
                pass
        return metadata

    @staticmethod
    def parse_docx(file_path: str) -> str:
        doc = Document(file_path)
        text_parts = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                style = para.style.name if para.style else ""
                if "Heading" in style:
                    level = style.replace("Heading", "").strip() or "1"
                    text_parts.append(f"{'#' * int(level)} {text}")
                else:
                    text_parts.append(text)
        for table in doc.tables:
            table_rows = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                table_rows.append(" | ".join(cells))
            if table_rows:
                text_parts.append("[表格]\n" + "\n".join(table_rows))
        return "\n\n".join(text_parts)

    @staticmethod
    def parse_txt(file_path: str) -> str:
        with open(file_path, "rb") as f:
            raw = f.read()
        detected = chardet.detect(raw)
        encoding = detected.get("encoding", "utf-8")
        return raw.decode(encoding, errors="replace")

    @staticmethod
    def parse_markdown(file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    @staticmethod
    def parse_html(file_path: str) -> str:
        try:
            from html.parser import HTMLParser
            class TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.text = []
                    self.skip = False
                def handle_starttag(self, tag, attrs):
                    if tag in ("script", "style"):
                        self.skip = True
                def handle_endtag(self, tag):
                    if tag in ("script", "style"):
                        self.skip = False
                    if tag in ("p", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
                        self.text.append("\n")
                def handle_data(self, data):
                    if not self.skip:
                        self.text.append(data)
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                html = f.read()
            extractor = TextExtractor()
            extractor.feed(html)
            return "".join(extractor.text)
        except Exception as e:
            return f"[HTML解析错误: {e}]"

    @staticmethod
    def parse_csv(file_path: str) -> str:
        with open(file_path, "rb") as f:
            raw = f.read()
        detected = chardet.detect(raw)
        encoding = detected.get("encoding", "utf-8")
        text = raw.decode(encoding, errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return ""
        header = rows[0]
        lines = ["[表头] " + " | ".join(header)]
        for row in rows[1:1000]:
            lines.append(" | ".join(row))
        if len(rows) > 1001:
            lines.append(f"... 共{len(rows)-1}行数据（已截取前1000行）")
        return "\n".join(lines)

    @staticmethod
    def parse_excel(file_path: str) -> str:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            text_parts = []
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                text_parts.append(f"[工作表: {sheet_name}]")
                rows = list(ws.iter_rows(values_only=True))
                if rows:
                    header = [str(c) if c else "" for c in rows[0]]
                    text_parts.append(" | ".join(header))
                    for row in rows[1:500]:
                        cells = [str(c) if c else "" for c in row]
                        text_parts.append(" | ".join(cells))
                    if len(rows) > 501:
                        text_parts.append(f"... 共{len(rows)-1}行数据")
            wb.close()
            return "\n\n".join(text_parts)
        except ImportError:
            return "[需要安装openpyxl: pip install openpyxl]"
        except Exception as e:
            return f"[Excel解析错误: {e}]"
