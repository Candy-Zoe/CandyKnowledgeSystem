import fitz
import chardet
import csv
import io
from pathlib import Path
from docx import Document


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

    @staticmethod
    def parse(file_path: str, file_type: str) -> str:
        file_type = file_type.lower().lstrip(".")
        parsers = {
            "pdf": DocumentParser.parse_pdf,
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
            raise ValueError(f"不支持的文件类型: {file_type}，支持: {', '.join(DocumentParser.SUPPORTED_TYPES.keys())}")
        return parser(file_path)

    @staticmethod
    def get_metadata(file_path: str, file_type: str) -> dict:
        file_type = file_type.lower().lstrip(".")
        metadata = {
            "file_type": file_type,
            "file_size": Path(file_path).stat().st_size,
        }
        if file_type == "pdf":
            try:
                doc = fitz.open(file_path)
                metadata["page_count"] = len(doc)
                meta = doc.metadata
                if meta:
                    metadata["title"] = meta.get("title", "")
                    metadata["author"] = meta.get("author", "")
                    metadata["subject"] = meta.get("subject", "")
                doc.close()
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
    def parse_pdf(file_path: str) -> str:
        doc = fitz.open(file_path)
        text_parts = []
        total_text_len = 0

        # Pass 1: Try to extract text directly
        for i, page in enumerate(doc):
            page_text = page.get_text("text")
            if page_text.strip():
                text_parts.append(f"[第{i+1}页]\n{page_text}")
                total_text_len += len(page_text.strip())
            tables = page.find_tables()
            if tables and tables.tables:
                for table in tables.tables:
                    table_data = table.extract()
                    if table_data:
                        table_text = "\n".join([" | ".join(str(cell) if cell else "" for cell in row) for row in table_data])
                        text_parts.append(f"[表格 第{i+1}页]\n{table_text}")

        # Pass 2: If text is too little, use OCR
        page_count = len(doc)
        avg_text_per_page = total_text_len / page_count if page_count > 0 else 0

        if avg_text_per_page < 50:
            try:
                import easyocr
                import io
                from PIL import Image

                reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
                text_parts = []

                for i, page in enumerate(doc):
                    page_text = page.get_text("text")
                    if page_text.strip() and len(page_text.strip()) > 30:
                        text_parts.append(f"[第{i+1}页]\n{page_text}")
                    else:
                        # Render page to image
                        mat = fitz.Matrix(1.5, 1.5)
                        pix = page.get_pixmap(matrix=mat)
                        img_data = pix.tobytes("png")
                        img = Image.open(io.BytesIO(img_data))

                        # OCR with easyocr
                        import numpy as np
                        img_array = np.array(img)
                        results = reader.readtext(img_array)
                        ocr_text = "\n".join([r[1] for r in results if r[1].strip()])
                        if ocr_text.strip():
                            text_parts.append(f"[第{i+1}页 OCR]\n{ocr_text.strip()}")
            except ImportError:
                pass
            except Exception:
                pass

        doc.close()
        return "\n\n".join(text_parts)

    @staticmethod
    def parse_pdf_with_images(file_path: str) -> dict:
        doc = fitz.open(file_path)
        result = {"text": "", "images": [], "page_count": len(doc)}
        for i, page in enumerate(doc):
            page_text = page.get_text("text")
            if page_text.strip():
                result["text"] += f"[第{i+1}页]\n{page_text}\n\n"
            image_list = page.get_images(full=True)
            for img_index, img in enumerate(image_list):
                xref = img[0]
                try:
                    base_image = doc.extract_image(xref)
                    result["images"].append({
                        "page": i + 1,
                        "index": img_index,
                        "width": base_image.get("width", 0),
                        "height": base_image.get("height", 0),
                        "ext": base_image.get("ext", "png"),
                    })
                except Exception:
                    pass
        doc.close()
        return result

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
