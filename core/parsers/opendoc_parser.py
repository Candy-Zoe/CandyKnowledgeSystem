"""
OpenDocument 解析器（纯Python实现）

支持格式：
- ODT (OpenDocument Text)
- ODS (OpenDocument Spreadsheet)
- ODP (OpenDocument Presentation)

这些格式本质都是ZIP包，内部包含XML文件：
- content.xml: 主要内容
- styles.xml: 样式定义
- meta.xml: 元数据

解析策略：
1. 用zipfile解压读取
2. 解析content.xml提取文本
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


class OpenDocParser:
    """OpenDocument文档解析器"""

    # OpenDocument命名空间
    NAMESPACES = {
        "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
        "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
        "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
        "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
        "presentation": "urn:oasis:names:tc:opendocument:xmlns:presentation:1.0",
        "xlink": "http://www.w3.org/1999/xlink",
        "dc": "http://purl.org/dc/elements/1.1/",
        "meta": "urn:oasis:names:tc:opendocument:xmlns:meta:1.0",
    }

    def __init__(self):
        self.ns = self.NAMESPACES

    def parse_odt(self, file_path: str) -> str:
        """解析ODT文字处理文档"""
        return self._parse_opendoc(file_path, doc_type="text")

    def parse_ods(self, file_path: str) -> str:
        """解析ODS电子表格"""
        return self._parse_opendoc(file_path, doc_type="spreadsheet")

    def parse_odp(self, file_path: str) -> str:
        """解析ODP演示文稿"""
        return self._parse_opendoc(file_path, doc_type="presentation")

    def _parse_opendoc(self, file_path: str, doc_type: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        if not zipfile.is_zipfile(file_path):
            raise ValueError(f"不是有效的OpenDocument文件: {file_path}")

        with zipfile.ZipFile(file_path, "r") as zf:
            if "content.xml" not in zf.namelist():
                raise ValueError(f"缺少content.xml")

            # 读取元数据
            meta_texts = []
            if "meta.xml" in zf.namelist():
                try:
                    with zf.open("meta.xml") as f:
                        meta_tree = ET.fromstring(f.read())
                    for title in meta_tree.findall(".//dc:title", self.ns):
                        if title.text:
                            meta_texts.append(f"[标题] {title.text}")
                    for creator in meta_tree.findall(".//dc:creator", self.ns):
                        if creator.text:
                            meta_texts.append(f"[作者] {creator.text}")
                    for desc in meta_tree.findall(".//dc:description", self.ns):
                        if desc.text:
                            meta_texts.append(f"[描述] {desc.text}")
                except Exception:
                    pass

            # 读取内容
            with zf.open("content.xml") as f:
                content_tree = ET.fromstring(f.read())

            body = content_tree.find("office:body", self.ns)
            if body is None:
                body = content_tree.find("{*}body")
            if body is None:
                return ""

            if doc_type == "text":
                text_content = self._parse_odt_body(body)
            elif doc_type == "spreadsheet":
                text_content = self._parse_ods_body(body)
            elif doc_type == "presentation":
                text_content = self._parse_odp_body(body)
            else:
                text_content = self._parse_odt_body(body)

            if meta_texts:
                return "\n".join(meta_texts) + "\n\n" + text_content
            return text_content

    def _parse_odt_body(self, body: ET.Element) -> str:
        text_elem = body.find("office:text", self.ns)
        if text_elem is None:
            text_elem = body.find("{*}text")
        if text_elem is None:
            return ""

        parts = []
        for elem in text_elem:
            tag = self._strip_ns(elem.tag)

            if tag == "p":
                text = self._extract_text_from_element(elem)
                if text.strip():
                    style = elem.get(f"{{{self.ns['text']}}}style-name", "")
                    if not style:
                        style = elem.get("style-name", "")
                    if "heading" in style.lower():
                        level = ""
                        for ch in style:
                            if ch.isdigit():
                                level += ch
                        if level:
                            parts.append(f"{'#' * int(level)} {text}")
                        else:
                            parts.append(text)
                    else:
                        parts.append(text)

            elif tag == "h":
                text = self._extract_text_from_element(elem)
                level = elem.get(f"{{{self.ns['text']}}}outline-level", "1")
                if not level:
                    level = elem.get("outline-level", "1")
                parts.append(f"{'#' * int(level)} {text}")

            elif tag == "table":
                table_text = self._parse_odt_table(elem)
                if table_text:
                    parts.append(f"[表格]\n{table_text}")

            elif tag == "list":
                list_texts = self._parse_odt_list(elem)
                parts.extend(list_texts)

        return "\n\n".join(parts)

    def _parse_ods_body(self, body: ET.Element) -> str:
        spreadsheet = body.find("office:spreadsheet", self.ns)
        if spreadsheet is None:
            spreadsheet = body.find("{*}spreadsheet")
        if spreadsheet is None:
            return ""

        all_sheets = []
        for table in spreadsheet.findall("table:table", self.ns):
            if table is None:
                table = spreadsheet.findall("{*}table")
            sheet_name = table.get(f"{{{self.ns['table']}}}name", "Sheet")
            if not sheet_name:
                sheet_name = table.get("name", "Sheet")
            rows = []
            for row in table.findall("table:table-row", self.ns):
                if row is None:
                    row = table.findall("{*}table-row")
                cells = []
                for cell in row.findall("table:table-cell", self.ns):
                    if cell is None:
                        cell = row.findall("{*}table-cell")
                    text = self._extract_text_from_element(cell)
                    cells.append(text)
                if any(cells):
                    rows.append(" | ".join(cells))

            if rows:
                all_sheets.append(f"[工作表: {sheet_name}]\n" + "\n".join(rows))

        return "\n\n".join(all_sheets)

    def _parse_odp_body(self, body: ET.Element) -> str:
        """解析ODP正文"""
        presentation = body.find("office:presentation", self.ns)
        if presentation is None:
            return ""

        slides = []
        for i, page in enumerate(presentation.findall("draw:page", self.ns), 1):
            texts = []
            for frame in page.findall("draw:frame", self.ns):
                text_box = frame.find("draw:text-box", self.ns)
                if text_box is not None:
                    for p in text_box.findall("text:p", self.ns):
                        text = self._extract_text_from_element(p)
                        if text.strip():
                            texts.append(text)
            if texts:
                slides.append(f"[第{i}页幻灯片]\n" + "\n".join(texts))

        return "\n\n".join(slides)

    def _extract_text_from_element(self, elem: ET.Element) -> str:
        """递归提取元素中的所有文本"""
        texts = []
        if elem.text and elem.text.strip():
            texts.append(elem.text.strip())
        for child in elem:
            child_text = self._extract_text_from_element(child)
            if child_text:
                texts.append(child_text)
            if child.tail and child.tail.strip():
                texts.append(child.tail.strip())
        return " ".join(texts)

    def _parse_odt_table(self, table: ET.Element) -> str:
        """解析ODT表格"""
        rows = []
        for row in table.findall("table:table-row", self.ns):
            cells = []
            for cell in row.findall("table:table-cell", self.ns):
                text = self._extract_text_from_element(cell)
                cells.append(text)
            if any(cells):
                rows.append(" | ".join(cells))
        return "\n".join(rows)

    def _parse_odt_list(self, list_elem: ET.Element, level: int = 0) -> list:
        """解析ODT列表"""
        items = []
        for item in list_elem.findall("text:list-item", self.ns):
            for p in item.findall("text:p", self.ns):
                text = self._extract_text_from_element(p)
                if text.strip():
                    items.append(f"{'  ' * level}- {text}")
            # 嵌套列表
            for sublist in item.findall("text:list", self.ns):
                items.extend(self._parse_odt_list(sublist, level + 1))
        return items

    def _strip_ns(self, tag: str) -> str:
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag
