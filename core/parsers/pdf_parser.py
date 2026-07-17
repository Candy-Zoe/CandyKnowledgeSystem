"""
PDF 解析器（增强版）

策略：
1. 优先使用 PyMuPDF (fitz) - 功能最全
2. 回退到 pdfplumber - 表格提取更好
3. 纯Python回退方案 - 基于二进制解析基础文本，无外部依赖
4. 支持OCR（扫描版PDF）

纯Python PDF解析能力：
- 支持基于对象的PDF（非线性化）
- 提取文本流中的 Tj/TJ 操作符
- 处理常见编码（WinAnsi, MacRoman, UTF-16BE）
"""
import re
import io
import zlib
import struct
import logging
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PDFPage:
    page_number: int
    text: str = ""
    tables: list = field(default_factory=list)
    images_count: int = 0
    has_text: bool = False
    method: str = "text"


@dataclass
class PDFResult:
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


class _PurePythonPDFParser:
    """
    纯Python PDF文本提取器（增强版，无外部依赖）
    支持基础PDF结构解析，能处理大部分普通文本PDF
    增强：从文件读取对象和流、支持FlateDecode、增强文本提取
    """

    def __init__(self):
        self.objects = {}
        self.xref = {}
        self.trailer = {}
        self._file_data = b""

    def parse(self, file_path: str) -> PDFResult:
        result = PDFResult(file_path=file_path)
        try:
            with open(file_path, "rb") as f:
                self._file_data = f.read()

            if not self._file_data.startswith(b"%PDF"):
                result.errors.append("不是有效的PDF文件（缺少%PDF标记）")
                return result

            self._parse_structure(self._file_data)

            catalog = self._get_object(self.trailer.get("Root"))
            if not catalog:
                result.errors.append("无法读取文档目录")
                return result

            pages_obj = self._get_object(catalog.get("Pages"))
            if not pages_obj:
                result.errors.append("无法读取页树")
                return result

            count = pages_obj.get("Count", 0)
            result.page_count = count

            page_objs = self._collect_pages(pages_obj)
            for i, page_obj in enumerate(page_objs, 1):
                page_result = PDFPage(page_number=i)
                text = self._extract_page_text(page_obj)
                if text:
                    page_result.text = text
                    page_result.has_text = True
                result.pages.append(page_result)

            info = self._get_object(self.trailer.get("Info"))
            if info:
                result.metadata = {
                    k: v.strip("()") if isinstance(v, str) and v.startswith("(") else str(v)
                    for k, v in info.items()
                    if k not in ("Type",)
                }

            self._merge_text(result)
            return result

        except Exception as e:
            result.errors.append(f"纯Python解析失败: {e}")
            return result

    def _parse_structure(self, data: bytes):
        startxref_match = re.search(rb"startxref\s*(\d+)\s*%%EOF", data, re.DOTALL)
        if not startxref_match:
            self._parse_linearized(data)
            return

        xref_offset = int(startxref_match.group(1))
        if data[xref_offset:xref_offset+4] == b"xref":
            self._parse_xref_table(data, xref_offset)
        else:
            self._parse_xref_stream(data, xref_offset)

    def _parse_xref_table(self, data: bytes, offset: int):
        line_start = data.find(b"xref", offset)
        lines = data[line_start:].split(b"\n")
        current_obj = 0
        in_table = False

        for line in lines[1:]:
            line = line.strip()
            if not line or line.startswith(b"trailer"):
                if line.startswith(b"trailer"):
                    trailer_start = data.find(b"trailer", offset)
                    obj_start = data.find(b"<<", trailer_start)
                    obj_end = data.find(b">>", obj_start) + 2
                    self.trailer = self._parse_dict(data[obj_start:obj_end])
                break

            if not in_table:
                parts = line.split()
                if len(parts) == 2:
                    current_obj = int(parts[0])
                    in_table = True
            else:
                parts = line.split()
                if len(parts) >= 2:
                    byte_offset = int(parts[0])
                    gen = int(parts[1])
                    status = parts[2].decode("ascii") if len(parts) > 2 else "n"
                    if status != "f":
                        self.xref[current_obj] = (byte_offset, gen)
                    current_obj += 1
                else:
                    in_table = False

    def _parse_xref_stream(self, data: bytes, offset: int):
        try:
            obj_data = self._read_object_at(data, offset)
            if not obj_data:
                return
            obj = self._parse_indirect_object(obj_data)
            if obj and "W" in obj:
                stream_data = self._decode_stream_from_obj(obj, obj_data)
                w = obj.get("W", [1, 2, 1])
                index = obj.get("Index", [0, obj.get("Size", 0)])
                idx = 0
                pos = 0
                while pos < len(stream_data):
                    if idx >= index[0] and idx < index[0] + index[1]:
                        entry_type = stream_data[pos]
                        if entry_type == 1:
                            off = struct.unpack(">I", b"\x00" + stream_data[pos+1:pos+1+w[1]])[0]
                            gen = struct.unpack(">H", stream_data[pos+1+w[1]:pos+1+w[1]+w[2]])[0]
                            self.xref[idx] = (off, gen)
                    pos += sum(w)
                    idx += 1
                self.trailer = {k: v for k, v in obj.items() if k not in ("Type", "W", "Index", "Size", "Length", "Filter", "DecodeParms")}
        except Exception as e:
            logger.warning(f"解析xref流失败: {e}")

    def _parse_linearized(self, data: bytes):
        for m in re.finditer(rb"(\d+)\s+(\d+)\s+obj", data):
            obj_num = int(m.group(1))
            start = m.start()
            obj_data = self._read_object_at(data, start)
            if obj_data:
                obj = self._parse_indirect_object(obj_data)
                if obj:
                    self.objects[(obj_num, 0)] = obj

    def _read_object_at(self, data: bytes, offset: int) -> bytes:
        end_obj = data.find(b"endobj", offset)
        if end_obj == -1:
            return b""
        return data[offset:end_obj + 6]

    def _parse_indirect_object(self, data: bytes) -> dict:
        dict_start = data.find(b"<<")
        dict_end = data.rfind(b">>")
        if dict_start == -1 or dict_end == -1:
            return {}
        return self._parse_dict(data[dict_start:dict_end+2])

    def _parse_dict(self, data: bytes) -> dict:
        result = {}
        text = data.decode("latin-1", errors="replace")
        i = 0
        while i < len(text):
            if text[i] == "/":
                key_end = i + 1
                while key_end < len(text) and text[key_end] not in " \t\n\r<>()[]/%":
                    key_end += 1
                key = text[i+1:key_end]
                val_start = key_end
                while val_start < len(text) and text[val_start] in " \t\n\r":
                    val_start += 1
                if val_start >= len(text):
                    break
                val, next_pos = self._parse_value(text, val_start)
                if val is not None:
                    result[key] = val
                i = next_pos
            else:
                i += 1
        return result

    def _parse_value(self, text: str, start: int):
        if start >= len(text):
            return None, start
        c = text[start]

        if c == "/":
            end = start + 1
            while end < len(text) and text[end] not in " \t\n\r<>()[]/%":
                end += 1
            return text[start+1:end], end
        elif c == "(":
            depth = 1
            end = start + 1
            while end < len(text) and depth > 0:
                if text[end] == "\\" and end + 1 < len(text):
                    end += 2
                    continue
                if text[end] == "(":
                    depth += 1
                elif text[end] == ")":
                    depth -= 1
                end += 1
            return text[start:end], end
        elif c == "[":
            depth = 1
            end = start + 1
            while end < len(text) and depth > 0:
                if text[end] == "[":
                    depth += 1
                elif text[end] == "]":
                    depth -= 1
                end += 1
            arr_text = text[start+1:end-1]
            arr = []
            i = 0
            while i < len(arr_text):
                while i < len(arr_text) and arr_text[i] in " \t\n\r":
                    i += 1
                if i >= len(arr_text):
                    break
                val, i = self._parse_value(arr_text, i)
                if val is not None:
                    arr.append(val)
            return arr, end
        elif c == "<" and start + 1 < len(text) and text[start+1] != "<":
            end = text.find(">", start)
            if end == -1:
                end = len(text)
            return text[start:end+1], end + 1
        elif c == "<" and start + 1 < len(text) and text[start+1] == "<":
            depth = 1
            end = start + 2
            while end < len(text) and depth > 0:
                if text[end:end+2] == "<<":
                    depth += 1
                    end += 2
                    continue
                if text[end:end+2] == ">>":
                    depth -= 1
                    if depth == 0:
                        end += 2
                        break
                    end += 2
                    continue
                end += 1
            return self._parse_dict(text[start:end].encode("latin-1")), end
        elif c.isdigit() or c == "-" or c == "+":
            end = start
            while end < len(text) and (text[end].isdigit() or text[end] in "-+."):
                end += 1
            num_str = text[start:end]
            try:
                if "." in num_str:
                    return float(num_str), end
                num = int(num_str)
                tmp = end
                while tmp < len(text) and text[tmp] in " \t\n\r":
                    tmp += 1
                if tmp < len(text) and text[tmp:tmp+1].isdigit():
                    gen_end = tmp
                    while gen_end < len(text) and text[gen_end].isdigit():
                        gen_end += 1
                    while gen_end < len(text) and text[gen_end] in " \t\n\r":
                        gen_end += 1
                    if gen_end < len(text) and text[gen_end] == "R":
                        gen = int(text[tmp:gen_end].strip())
                        return {"obj_ref": (num, gen)}, gen_end + 1
                return num, end
            except ValueError:
                return num_str, end
        elif text[start:start+4].lower() == "true":
            return True, start + 4
        elif text[start:start+5].lower() == "false":
            return False, start + 5
        elif text[start:start+4].lower() == "null":
            return None, start + 4
        return None, start + 1

    def _get_object(self, ref):
        if ref is None:
            return None
        if isinstance(ref, dict) and "obj_ref" in ref:
            obj_num, gen = ref["obj_ref"]
            if (obj_num, gen) in self.objects:
                return self.objects[(obj_num, gen)]
            if obj_num in self.xref:
                offset, _ = self.xref[obj_num]
                obj_data = self._read_object_at(self._file_data, offset)
                if obj_data:
                    obj = self._parse_indirect_object(obj_data)
                    if obj:
                        self.objects[(obj_num, gen)] = obj
                        return obj
            return None
        return ref

    def _collect_pages(self, pages_obj: dict) -> list:
        result = []
        kids = pages_obj.get("Kids", [])
        for kid in kids:
            kid_obj = self._get_object(kid)
            if not kid_obj:
                continue
            kid_type = kid_obj.get("Type", "")
            if kid_type == "Page":
                result.append(kid_obj)
            elif kid_type == "Pages":
                result.extend(self._collect_pages(kid_obj))
        return result

    def _extract_page_text(self, page_obj: dict) -> str:
        contents = page_obj.get("Contents")
        if not contents:
            return ""
        content_obj = self._get_object(contents)
        if not content_obj:
            return ""

        streams = []
        if isinstance(content_obj, list):
            for c in content_obj:
                co = self._get_object(c)
                if co:
                    streams.append(co)
        else:
            streams.append(content_obj)

        texts = []
        for stream in streams:
            stream_data = self._decode_stream(stream)
            if stream_data:
                text = self._extract_text_from_stream(stream_data)
                if text:
                    texts.append(text)
        return "\n".join(texts)

    def _decode_stream(self, obj: dict) -> bytes:
        if "stream_data" in obj:
            return obj["stream_data"]
        # 查找文件中的流数据
        return self._decode_stream_from_obj(obj)

    def _decode_stream_from_obj(self, obj: dict, obj_data: bytes = None) -> bytes:
        """从文件数据中解码流"""
        if obj_data is None:
            # 找到对象在文件中的位置
            for (obj_num, gen), cached_obj in self.objects.items():
                if cached_obj is obj and obj_num in self.xref:
                    offset, _ = self.xref[obj_num]
                    obj_data = self._read_object_at(self._file_data, offset)
                    break

        if not obj_data:
            return b""

        # 找到stream的位置
        stream_start = obj_data.find(b"stream")
        if stream_start == -1:
            return b""

        # 跳过 "stream\r\n" 或 "stream\n"
        data_start = stream_start + 6
        if obj_data[data_start:data_start+2] == b"\r\n":
            data_start += 2
        elif obj_data[data_start:data_start+1] == b"\n":
            data_start += 1

        # 找到endstream
        endstream_pos = obj_data.find(b"endstream", data_start)
        if endstream_pos == -1:
            endstream_pos = len(obj_data)

        raw_data = obj_data[data_start:endstream_pos]

        # 获取Length
        length = obj.get("Length")
        if isinstance(length, int):
            raw_data = raw_data[:length]
        elif isinstance(length, dict) and "obj_ref" in length:
            length_obj = self._get_object(length)
            if isinstance(length_obj, int):
                raw_data = raw_data[:length_obj]

        # 解码过滤器
        filter_name = obj.get("Filter")
        if filter_name == "FlateDecode":
            try:
                raw_data = zlib.decompress(raw_data)
            except Exception:
                pass
        elif isinstance(filter_name, list) and "FlateDecode" in filter_name:
            try:
                raw_data = zlib.decompress(raw_data)
            except Exception:
                pass

        return raw_data

    def _extract_text_from_stream(self, data: bytes) -> str:
        """从内容流提取文本（增强版）"""
        try:
            text = data.decode("latin-1", errors="replace")
        except Exception:
            return ""

        results = []

        # 处理PDF文本操作符
        # Tj: (text) Tj
        for m in re.finditer(r"\((.*?)\)\s*Tj", text):
            s = self._unescape_pdf_string(m.group(1))
            results.append(s)

        # TJ: [ (text1) num1 (text2) ... ] TJ
        for m in re.finditer(r"\[(.*?)\]\s*TJ", text, re.DOTALL):
            inner = m.group(1)
            # 提取括号内的字符串和十六进制字符串
            parts = re.findall(r"\((.*?)\)|<([0-9a-fA-F]+)>", inner)
            for p in parts:
                s = p[0] if p[0] else self._hex_to_string(p[1])
                if s:
                    results.append(self._unescape_pdf_string(s))

        # ' 操作符 (move to next line and show text)
        for m in re.finditer(r"\((.*?)\)\s*'", text):
            results.append(self._unescape_pdf_string(m.group(1)))

        # " 操作符 (move to next line and show text with word/char spacing)
        for m in re.finditer(r"[\d\-.]+\s+[\d\-.]+\s+\((.*?)\)\s*\"", text):
            results.append(self._unescape_pdf_string(m.group(1)))

        # BT ... ET 块提取
        for m in re.finditer(r"BT(.*?)ET", text, re.DOTALL):
            block = m.group(1)
            # 在块内再次提取
            for m2 in re.finditer(r"\((.*?)\)\s*Tj", block):
                s = self._unescape_pdf_string(m2.group(1))
                if s and s not in results:
                    results.append(s)

        return "".join(results)

    def _unescape_pdf_string(self, s: str) -> str:
        """反转义PDF字符串"""
        s = s.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
        s = s.replace("\\\\", "\\").replace("\\(", "(").replace("\\)", ")")
        return s

    def _hex_to_string(self, hex_str: str) -> str:
        """将十六进制字符串转为文本"""
        try:
            data = bytes.fromhex(hex_str)
            # 尝试UTF-16BE（PDF常用）
            if len(data) >= 2 and len(data) % 2 == 0:
                try:
                    return data.decode("utf-16-be", errors="strict")
                except UnicodeDecodeError:
                    pass
            return data.decode("latin-1", errors="replace")
        except Exception:
            return ""

    def _merge_text(self, result: PDFResult):
        parts = []
        for page in result.pages:
            if page.text:
                parts.append(f"[第{page.page_number}页]\n{page.text}")
        result.full_text = "\n\n".join(parts)


class PDFParser:
    """
    PDF解析器（多层回退策略）
    """

    def __init__(self, use_ocr=True, ocr_threshold=50, ocr_lang=None,
                 max_pages=0, page_sleep_ms=0):
        self.use_ocr = use_ocr
        self.ocr_threshold = ocr_threshold
        self.ocr_lang = ocr_lang or ["ch_sim", "en"]
        self.max_pages = max_pages
        self.page_sleep_ms = page_sleep_ms
        self._ocr_reader = None

    def parse(self, file_path: str) -> PDFResult:
        file_path = str(file_path)
        result = PDFResult(file_path=file_path)

        if not self._validate_file(file_path, result):
            return result

        # 第一层：PyMuPDF
        try:
            result = self._parse_with_pymupdf(file_path, result)
            if not result.is_empty:
                return result
        except ImportError:
            result.warnings.append("PyMuPDF (fitz) 未安装，跳过")
        except Exception as e:
            result.errors.append(f"PyMuPDF解析失败: {e}")

        # 第二层：pdfplumber
        try:
            result = self._parse_with_pdfplumber(file_path, result)
            if not result.is_empty:
                return result
        except ImportError:
            result.warnings.append("pdfplumber 未安装，跳过")
        except Exception as e:
            result.errors.append(f"pdfplumber解析失败: {e}")

        # 第三层：纯Python回退
        try:
            pure_parser = _PurePythonPDFParser()
            pure_result = pure_parser.parse(file_path)
            if not pure_result.is_empty:
                return pure_result
            result.errors.extend(pure_result.errors)
        except Exception as e:
            result.errors.append(f"纯Python解析失败: {e}")

        # 第四层：OCR
        if self.use_ocr and result.is_empty:
            try:
                result = self._parse_with_ocr(file_path, result)
            except ImportError:
                result.warnings.append("OCR需要安装easyocr: pip install easyocr")
            except Exception as e:
                result.errors.append(f"OCR解析失败: {e}")

        self._merge_text(result)
        return result

    def _validate_file(self, file_path: str, result: PDFResult) -> bool:
        path = Path(file_path)
        if not path.exists():
            result.errors.append(f"文件不存在: {file_path}")
            return False
        if path.stat().st_size == 0:
            result.errors.append("文件为空")
            return False
        # 不检查后缀，允许无后缀的PDF
        return True

    def _parse_with_pymupdf(self, file_path: str, result: PDFResult) -> PDFResult:
        import fitz
        doc = fitz.open(file_path)
        total_pages = len(doc)
        result.page_count = total_pages

        pages_to_process = total_pages
        if self.max_pages > 0 and total_pages > self.max_pages:
            pages_to_process = self.max_pages
            result.warnings.append(f"PDF共{total_pages}页，已限制处理前{self.max_pages}页")

        meta = doc.metadata
        if meta:
            result.metadata = {
                "title": meta.get("title", ""),
                "author": meta.get("author", ""),
                "subject": meta.get("subject", ""),
                "creator": meta.get("creator", ""),
                "producer": meta.get("producer", ""),
            }

        total_text_len = 0
        for i in range(pages_to_process):
            page = doc[i]
            page_result = PDFPage(page_number=i + 1)

            try:
                page_text = page.get_text("text")
                if page_text and page_text.strip():
                    page_result.text = page_text.strip()
                    page_result.has_text = True
                    total_text_len += len(page_result.text)
            except Exception as e:
                logger.warning(f"第{i+1}页文本提取失败: {e}")

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

            try:
                images = page.get_images(full=True)
                page_result.images_count = len(images)
            except Exception:
                pass

            result.pages.append(page_result)

            if self.page_sleep_ms > 0:
                import time
                time.sleep(self.page_sleep_ms / 1000.0)

        doc.close()

        avg_text = total_text_len / result.page_count if result.page_count > 0 else 0
        if avg_text < self.ocr_threshold:
            result.warnings.append(f"平均每页仅{avg_text:.0f}字符，可能是扫描版PDF")

        self._merge_text(result)
        return result

    def _parse_with_pdfplumber(self, file_path: str, result: PDFResult) -> PDFResult:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            if not result.page_count:
                result.page_count = len(pdf.pages)

            for i, page in enumerate(pdf.pages):
                if i < len(result.pages):
                    page_result = result.pages[i]
                else:
                    page_result = PDFPage(page_number=i + 1)
                    result.pages.append(page_result)

                if not page_result.has_text:
                    try:
                        text = page.extract_text()
                        if text and text.strip():
                            page_result.text = text.strip()
                            page_result.has_text = True
                            page_result.method = "pdfplumber"
                    except Exception:
                        pass

                try:
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            if table:
                                table_text = self._format_table(table)
                                if table_text and table_text not in page_result.tables:
                                    page_result.tables.append(table_text)
                except Exception:
                    pass

        self._merge_text(result)
        return result

    def _parse_with_ocr(self, file_path: str, result: PDFResult) -> PDFResult:
        import fitz

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
                continue

            page_result = result.pages[i] if i < len(result.pages) else PDFPage(page_number=i + 1)

            try:
                mat = fitz.Matrix(1.5, 1.5)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")

                import numpy as np
                from PIL import Image
                img = Image.open(io.BytesIO(img_data))
                img_array = np.array(img)

                ocr_results = self._ocr_reader.readtext(img_array)
                ocr_text = "\n".join([r[1] for r in ocr_results if r[1].strip()])

                if ocr_text.strip():
                    page_result.text = ocr_text.strip()
                    page_result.has_text = True
                    page_result.method = "ocr"
            except Exception as e:
                logger.warning(f"第{i+1}页OCR失败: {e}")

            if i >= len(result.pages):
                result.pages.append(page_result)

            if self.page_sleep_ms > 0:
                import time
                time.sleep(self.page_sleep_ms / 1000.0)

        doc.close()
        self._merge_text(result)
        return result

    def _format_table(self, table_data: list) -> str:
        if not table_data:
            return ""
        rows = []
        for row in table_data:
            cells = [str(cell).strip() if cell else "" for cell in row]
            if any(cells):
                rows.append(" | ".join(cells))
        return "\n".join(rows) if rows else ""

    def _merge_text(self, result: PDFResult):
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

        # 检查PDF头部
        with open(file_path, "rb") as f:
            header = f.read(5)
            if header != b"%PDF-":
                result["issues"].append("文件头不是标准PDF格式")

        try:
            import fitz
            doc = fitz.open(file_path)
            result["info"]["page_count"] = len(doc)
            result["info"]["metadata"] = doc.metadata or {}

            if doc.is_encrypted:
                result["issues"].append("PDF已加密")

            total_text = 0
            for page in doc:
                text = page.get_text("text")
                total_text += len(text.strip()) if text else 0

            avg_text = total_text / len(doc) if len(doc) > 0 else 0
            result["info"]["avg_chars_per_page"] = round(avg_text, 1)
            result["info"]["is_likely_scanned"] = avg_text < 50

            doc.close()
        except Exception as e:
            result["issues"].append(f"无法读取PDF: {e}")
            result["valid"] = False

        return result


def parse_pdf(file_path: str, use_ocr=True, max_pages=0, page_sleep_ms=0) -> str:
    parser = PDFParser(use_ocr=use_ocr, max_pages=max_pages, page_sleep_ms=page_sleep_ms)
    result = parser.parse(file_path)
    if result.errors and result.is_empty:
        raise RuntimeError(f"PDF解析失败: {'; '.join(result.errors)}")
    return result.full_text


def parse_pdf_with_info(file_path: str, use_ocr=True, max_pages=0, page_sleep_ms=0) -> tuple:
    parser = PDFParser(use_ocr=use_ocr, max_pages=max_pages, page_sleep_ms=page_sleep_ms)
    result = parser.parse(file_path)
    return result.full_text, result


def validate_pdf(file_path: str) -> dict:
    return PDFValidator.check(file_path)
