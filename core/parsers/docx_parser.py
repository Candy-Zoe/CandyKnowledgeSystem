"""
DOCX 解析器（纯Python实现，不依赖python-docx）

DOCX本质是一个ZIP包，内部包含XML文件：
- word/document.xml: 文档主体内容
- word/_rels/document.xml.rels: 关系定义（图片、超链接等）
- [Content_Types].xml: 内容类型定义

解析策略：
1. 用zipfile解压读取
2. 用xml.etree.ElementTree解析XML
3. 提取段落、表格、标题层级
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


class DocxParser:
    """DOCX文档解析器（自实现）"""

    # 常见XML命名空间
    NAMESPACES = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "ve": "http://schemas.openxmlformats.org/markup-compatibility/2006",
        "o": "urn:schemas-microsoft-com:office:office",
        "v": "urn:schemas-microsoft-com:vml",
    }

    def __init__(self):
        self.ns = self.NAMESPACES

    def parse(self, file_path: str) -> str:
        """解析DOCX文件，返回纯文本"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        if not zipfile.is_zipfile(file_path):
            raise ValueError(f"不是有效的DOCX文件: {file_path}")

        with zipfile.ZipFile(file_path, "r") as zf:
            # 检查必需的[Content_Types].xml确认是Office文档
            if "[Content_Types].xml" not in zf.namelist():
                raise ValueError(f"缺少[Content_Types].xml，不是有效的Office文档")

            # 读取document.xml
            doc_xml_path = "word/document.xml"
            if doc_xml_path not in zf.namelist():
                # 尝试其他可能路径
                alt_paths = [p for p in zf.namelist() if p.endswith("document.xml")]
                if alt_paths:
                    doc_xml_path = alt_paths[0]
                else:
                    raise ValueError(f"未找到document.xml")

            with zf.open(doc_xml_path) as f:
                xml_content = f.read()

            # 注册命名空间
            for prefix, uri in self.ns.items():
                try:
                    ET.register_namespace(prefix, uri)
                except Exception:
                    pass

            tree = ET.fromstring(xml_content)
            return self._extract_text(tree)

    def _extract_text(self, root: ET.Element) -> str:
        """从XML树中提取文本"""
        parts = []
        body = self._find(root, ".//w:body")
        if body is None:
            body = root

        for element in body:
            tag = self._strip_ns(element.tag)

            if tag == "p":
                text = self._parse_paragraph(element)
                if text:
                    heading_level = self._get_heading_level(element)
                    if heading_level:
                        parts.append(f"{'#' * heading_level} {text}")
                    else:
                        parts.append(text)

            elif tag == "tbl":
                table_text = self._parse_table(element)
                if table_text:
                    parts.append(f"[表格]\n{table_text}")

            elif tag == "sdt":
                sdt_text = self._parse_sdt(element)
                if sdt_text:
                    parts.append(sdt_text)

        return "\n\n".join(parts)

    def _find(self, elem: ET.Element, path: str) -> ET.Element:
        """查找元素，支持命名空间和回退"""
        result = elem.find(path, self.ns)
        if result is not None:
            return result
        # 回退：尝试不带命名空间
        tag = path.split("/")[-1].split(":")[-1]
        return elem.find(f".//{{*}}{tag}")

    def _findall(self, elem: ET.Element, path: str) -> list:
        """查找所有匹配元素，支持命名空间和回退"""
        results = elem.findall(path, self.ns)
        if results:
            return results
        tag = path.split("/")[-1].split(":")[-1]
        return elem.findall(f".//{{*}}{tag}")

    def _strip_ns(self, tag: str) -> str:
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    def _parse_paragraph(self, p_elem: ET.Element) -> str:
        texts = []
        for run in self._findall(p_elem, ".//w:r"):
            for t in run.findall("w:t", self.ns):
                if t.text:
                    texts.append(t.text)
            for tab in run.findall("w:tab", self.ns):
                texts.append("\t")
            for br in run.findall("w:br", self.ns):
                texts.append("\n")
            # 回退
            if not texts:
                for t in run.findall("{*}t"):
                    if t.text:
                        texts.append(t.text)
        return "".join(texts).strip()

    def _get_heading_level(self, p_elem: ET.Element) -> int:
        pPr = p_elem.find("w:pPr", self.ns)
        if pPr is None:
            pPr = p_elem.find("{*}pPr")
        if pPr is None:
            return 0

        pStyle = pPr.find("w:pStyle", self.ns)
        if pStyle is None:
            pStyle = pPr.find("{*}pStyle")
        if pStyle is not None:
            val = pStyle.get(f"{{{self.ns['w']}}}val", "")
            if not val:
                val = pStyle.get("val", "")
            if val.startswith("Heading"):
                try:
                    level = int(val.replace("Heading", "").strip())
                    if 1 <= level <= 9:
                        return level
                except ValueError:
                    pass
            if val.startswith("标题"):
                try:
                    level = int(val.replace("标题", "").strip())
                    if 1 <= level <= 9:
                        return level
                except ValueError:
                    pass
        return 0

    def _parse_table(self, tbl_elem: ET.Element) -> str:
        """解析表格元素"""
        rows = []
        for tr in tbl_elem.findall("w:tr", self.ns):
            cells = []
            for tc in tr.findall("w:tc", self.ns):
                cell_texts = []
                for p in tc.findall("w:p", self.ns):
                    text = self._parse_paragraph(p)
                    if text:
                        cell_texts.append(text)
                cells.append(" ".join(cell_texts))
            if any(cells):
                rows.append(" | ".join(cells))

        return "\n".join(rows)

    def _parse_sdt(self, sdt_elem: ET.Element) -> str:
        """解析结构化文档标签"""
        sdt_content = sdt_elem.find("w:sdtContent", self.ns)
        if sdt_content is None:
            return ""

        texts = []
        for p in sdt_content.findall("w:p", self.ns):
            text = self._parse_paragraph(p)
            if text:
                texts.append(text)
        return "\n".join(texts)

    def get_metadata(self, file_path: str) -> dict:
        """提取DOCX元数据"""
        meta = {
            "title": "",
            "author": "",
            "created": "",
            "modified": "",
            "paragraph_count": 0,
            "table_count": 0,
        }

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                # 核心属性
                if "docProps/core.xml" in zf.namelist():
                    with zf.open("docProps/core.xml") as f:
                        core_tree = ET.fromstring(f.read())
                        ns = {"dc": "http://purl.org/dc/elements/1.1/",
                              "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
                              "dcterms": "http://purl.org/dc/terms/"}
                        for title in core_tree.findall("dc:title", ns):
                            meta["title"] = title.text or ""
                        for creator in core_tree.findall("dc:creator", ns):
                            meta["author"] = creator.text or ""
                        for created in core_tree.findall("dcterms:created", ns):
                            meta["created"] = created.text or ""
                        for modified in core_tree.findall("dcterms:modified", ns):
                            meta["modified"] = modified.text or ""

                # 统计段落和表格数
                if "word/document.xml" in zf.namelist():
                    with zf.open("word/document.xml") as f:
                        doc_tree = ET.fromstring(f.read())
                        body = doc_tree.find(".//w:body", self.ns)
                        if body is not None:
                            meta["paragraph_count"] = len(body.findall("w:p", self.ns))
                            meta["table_count"] = len(body.findall("w:tbl", self.ns))
        except Exception:
            pass

        return meta
