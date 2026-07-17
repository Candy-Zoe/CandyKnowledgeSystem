"""
DOCX 解析器（纯Python实现，不依赖python-docx）

DOCX本质是一个ZIP包，内部包含XML文件：
- word/document.xml: 文档主体内容
- word/_rels/document.xml.rels: 关系定义（图片、超链接等）
- [Content_Types].xml: 内容类型定义
- word/header*.xml: 页眉文件
- word/footer*.xml: 页脚文件
- word/footnotes.xml: 脚注文件
- word/endnotes.xml: 尾注文件

解析策略：
1. 用zipfile解压读取
2. 用xml.etree.ElementTree解析XML
3. 提取段落、表格、标题层级
4. 处理表格合并单元格（gridSpan / vMerge）
5. 解析页眉、页脚、脚注、尾注
6. 最终调用 clean_text() 清洗文本
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from core.parsers.text_utils import clean_text


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

    # ===================== 公共方法 =====================

    def parse(self, file_path: str) -> str:
        """解析DOCX文件，返回纯文本

        外层 try-except 保证解析失败时返回错误提示而非崩溃。
        末尾调用 clean_text() 进行文本清洗。
        """
        try:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")

            if not zipfile.is_zipfile(file_path):
                raise ValueError(f"不是有效的DOCX文件: {file_path}")

            with zipfile.ZipFile(file_path, "r") as zf:
                # 检查必需的[Content_Types].xml确认是Office文档
                if "[Content_Types].xml" not in zf.namelist():
                    raise ValueError("缺少[Content_Types].xml，不是有效的Office文档")

                # ---------- 注册命名空间 ----------
                for prefix, uri in self.ns.items():
                    try:
                        ET.register_namespace(prefix, uri)
                    except Exception:
                        pass

                # ---------- 读取关系文件，获取页眉页脚引用 ----------
                rels = self._read_rels(zf)

                # ---------- 解析主体内容 ----------
                doc_xml_path = "word/document.xml"
                if doc_xml_path not in zf.namelist():
                    alt_paths = [p for p in zf.namelist() if p.endswith("document.xml")]
                    if alt_paths:
                        doc_xml_path = alt_paths[0]
                    else:
                        raise ValueError("未找到document.xml")

                doc_tree = self._read_xml(zf, doc_xml_path)
                body = self._find(doc_tree, ".//w:body")
                if body is None:
                    body = doc_tree

                # ---------- 提取主体文本 ----------
                parts = []
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

                # ---------- 解析页眉页脚 ----------
                header_texts = self._parse_headers_footers(zf, rels, is_header=True)
                if header_texts:
                    parts.insert(0, f"[页眉]\n{header_texts}")

                footer_texts = self._parse_headers_footers(zf, rels, is_header=False)
                if footer_texts:
                    parts.append(f"\n[页脚]\n{footer_texts}")

                # ---------- 解析脚注 ----------
                footnotes_text = self._parse_footnotes(zf)
                if footnotes_text:
                    parts.append(f"\n[脚注]\n{footnotes_text}")

                # ---------- 解析尾注 ----------
                endnotes_text = self._parse_endnotes(zf)
                if endnotes_text:
                    parts.append(f"\n[尾注]\n{endnotes_text}")

                result = "\n\n".join(parts)

            # ---------- 文本清洗 ----------
            result = clean_text(result)

            return result

        except (FileNotFoundError, ValueError) as e:
            # 已知的业务异常，直接返回错误信息
            return f"[解析错误] {e}"
        except Exception as e:
            # 未知异常，返回友好提示
            return f"[解析错误] 解析DOCX文件时发生异常: {e}"

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
                        ns = {
                            "dc": "http://purl.org/dc/elements/1.1/",
                            "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
                            "dcterms": "http://purl.org/dc/terms/",
                        }
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
                        body = self._find(doc_tree, ".//w:body")
                        if body is not None:
                            meta["paragraph_count"] = len(self._findall(body, "w:p"))
                            meta["table_count"] = len(self._findall(body, "w:tbl"))
        except Exception:
            pass

        return meta

    # ===================== 命名空间工具方法 =====================

    def _find(self, elem: ET.Element, path: str) -> ET.Element:
        """查找元素，支持命名空间和回退

        优先使用带前缀的命名空间查找，失败则尝试 {*}/无前缀回退。
        """
        result = elem.find(path, self.ns)
        if result is not None:
            return result
        # 回退1：尝试 {*}/无命名空间通配
        tag = path.split("/")[-1].split(":")[-1]
        return elem.find(f".//{{*}}{tag}")

    def _findall(self, elem: ET.Element, path: str) -> list:
        """查找所有匹配元素，支持命名空间和回退

        优先使用带前缀的命名空间查找，失败则尝试 {*}/无前缀回退。
        """
        results = elem.findall(path, self.ns)
        if results:
            return results
        # 回退1：尝试 {*}/无命名空间通配
        tag = path.split("/")[-1].split(":")[-1]
        results = elem.findall(f".//{{*}}{tag}")
        if results:
            return results
        # 回退2：尝试完全无命名空间的标签
        results = elem.findall(f".//{tag}")
        return results

    def _find_in(self, elem: ET.Element, path: str) -> ET.Element:
        """在元素内查找（非递归），支持命名空间和回退"""
        # 去掉路径中的 .// 使其仅在直接子元素中查找
        local_path = path.lstrip(".")
        result = elem.find(local_path, self.ns)
        if result is not None:
            return result
        # 回退
        tag = path.split(":")[-1] if ":" in path else path
        return elem.find(f"{{{tag}}}")

    def _findall_in(self, elem: ET.Element, path: str) -> list:
        """在元素内查找所有（非递归），支持命名空间和回退"""
        local_path = path.lstrip(".")
        results = elem.findall(local_path, self.ns)
        if results:
            return results
        # 回退
        tag = path.split(":")[-1] if ":" in path else path
        results = elem.findall(f"{{{tag}}}")
        return results

    def _get_attr(self, elem: ET.Element, name: str) -> str:
        """获取元素属性，支持带命名空间和不带命名空间两种形式"""
        # 优先尝试带 w 命名空间的属性
        val = elem.get(f"{{{self.ns['w']}}}{name}", "")
        if val:
            return val
        # 回退：不带命名空间
        val = elem.get(name, "")
        return val

    def _strip_ns(self, tag: str) -> str:
        """去除标签的命名空间前缀"""
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    def _read_xml(self, zf: zipfile.ZipFile, path: str) -> ET.Element:
        """从ZIP中读取并解析XML文件"""
        with zf.open(path) as f:
            return ET.fromstring(f.read())

    # ===================== 段落/标题解析 =====================

    def _parse_paragraph(self, p_elem: ET.Element) -> str:
        """解析段落元素，提取其中的文本、制表符、换行"""
        texts = []
        for run in self._findall(p_elem, ".//w:r"):
            # 带命名空间查找 w:t
            run_texts = self._findall_in(run, "w:t")
            for t in run_texts:
                if t.text:
                    texts.append(t.text)
            # 制表符
            for _ in self._findall_in(run, "w:tab"):
                texts.append("\t")
            # 换行
            for _ in self._findall_in(run, "w:br"):
                texts.append("\n")
        return "".join(texts).strip()

    def _get_heading_level(self, p_elem: ET.Element) -> int:
        """获取段落对应的标题级别（0 表示非标题）"""
        pPr = self._find_in(p_elem, "w:pPr")
        if pPr is None:
            return 0

        pStyle = self._find_in(pPr, "w:pStyle")
        if pStyle is None:
            return 0

        val = self._get_attr(pStyle, "val")
        if not val:
            return 0

        # 支持 "Heading1" / "标题1" 等格式
        for prefix in ("Heading", "heading", "标题"):
            if val.startswith(prefix):
                try:
                    level = int(val[len(prefix):].strip())
                    if 1 <= level <= 9:
                        return level
                except ValueError:
                    pass
        return 0

    # ===================== 表格解析（支持合并单元格）=====================

    def _parse_table(self, tbl_elem: ET.Element) -> str:
        """解析表格元素，支持 gridSpan（水平合并）和 vMerge（垂直合并）

        策略：
        - gridSpan: 单元格水平跨越多列，用空格填充被合并的列
        - vMerge:   单元格垂直合并，值为 "restart" 表示合并起始，
                    缺省或 "continue" 表示被合并（内容归到起始单元格）
        """
        rows = []
        # 记录每列是否处于垂直合并的"继续"状态，key=列索引, value=合并起始单元格的内容
        vmerge_cells = {}

        for tr in tbl_elem.findall("w:tr", self.ns):
            if not tr.findall("w:tr", self.ns):
                pass  # 只在第一层查找 tr
            tc_elements = self._findall_in(tr, "w:tc")
            if not tc_elements:
                # 回退：直接查找
                tc_elements = tr.findall("w:tc", self.ns)
            if not tc_elements:
                continue

            cells = []
            col_idx = 0  # 当前列索引（考虑 gridSpan）

            for tc in tc_elements:
                tcPr = self._find_in(tc, "w:tcPr")
                if tcPr is None:
                    tcPr = tc.find(".//w:tcPr", self.ns)
                    if tcPr is None:
                        tcPr = tc.find(".//{{*}}tcPr")

                # ---- 水平合并: gridSpan ----
                grid_span = 1
                if tcPr is not None:
                    gs_elem = self._find_in(tcPr, "w:gridSpan")
                    if gs_elem is not None:
                        val = self._get_attr(gs_elem, "val")
                        if val and val.isdigit():
                            grid_span = int(val)

                # ---- 垂直合并: vMerge ----
                vmerge_val = None  # None=未设置, "restart"=起始, "continue"=继续
                if tcPr is not None:
                    vm_elem = self._find_in(tcPr, "w:vMerge")
                    if vm_elem is not None:
                        vmerge_val = self._get_attr(vm_elem, "val") or "continue"
                        # 如果 val 属性不存在，OXML 规范中表示 "continue"

                # ---- 提取单元格文本 ----
                cell_texts = []
                for p in tc.findall("w:p", self.ns):
                    if not p.findall("w:p", self.ns):
                        pass
                    text = self._parse_paragraph(p)
                    if text:
                        cell_texts.append(text)
                cell_content = " ".join(cell_texts)

                # ---- 处理垂直合并逻辑 ----
                if vmerge_val == "restart":
                    # 合并起始：记录内容，占位
                    vmerge_cells[col_idx] = cell_content
                    cells.append(cell_content)
                    # 如果 gridSpan > 1，额外填充列也需要记录
                    for extra_col in range(col_idx + 1, col_idx + grid_span):
                        vmerge_cells[extra_col] = ""
                    col_idx += grid_span
                elif vmerge_val == "continue":
                    # 被合并的单元格：不输出新内容，但保留占位
                    if col_idx in vmerge_cells:
                        cells.append("")  # 占位，不重复内容
                    else:
                        cells.append("")
                    col_idx += grid_span
                else:
                    # 普通单元格
                    cells.append(cell_content)
                    col_idx += grid_span

            if any(c.strip() for c in cells):
                rows.append(" | ".join(cells))

        return "\n".join(rows)

    # ===================== SDT解析 =====================

    def _parse_sdt(self, sdt_elem: ET.Element) -> str:
        """解析结构化文档标签（Structured Document Tag）"""
        sdt_content = self._find(sdt_elem, "w:sdtContent")
        if sdt_content is None:
            return ""

        texts = []
        for p in self._findall(sdt_content, "w:p"):
            text = self._parse_paragraph(p)
            if text:
                texts.append(text)
        return "\n".join(texts)

    # ===================== 关系文件读取 =====================

    def _read_rels(self, zf: zipfile.ZipFile) -> dict:
        """读取关系文件，返回 rId -> 目标路径的映射

        用于定位页眉、页脚等引用文件。
        """
        rels = {}
        rels_path = "word/_rels/document.xml.rels"
        if rels_path not in zf.namelist():
            # 尝试其他可能路径
            alt = [p for p in zf.namelist() if p.endswith("document.xml.rels")]
            if not alt:
                return rels
            rels_path = alt[0]

        try:
            tree = self._read_xml(zf, rels_path)
            rel_ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
            for rel in tree.findall("r:Relationship", rel_ns):
                rid = rel.get("Id", "")
                target = rel.get("Target", "")
                rel_type = rel.get("Type", "")
                if rid and target:
                    # Target 可能是相对路径，需要补全 word/ 前缀
                    if not target.startswith("word/"):
                        target = f"word/{target}"
                    rels[rid] = {
                        "target": target,
                        "type": rel_type,
                    }
        except Exception:
            pass

        return rels

    # ===================== 页眉页脚解析 =====================

    def _parse_headers_footers(self, zf: zipfile.ZipFile, rels: dict, is_header: bool) -> str:
        """解析页眉或页脚文件

        Args:
            zf: ZipFile对象
            rels: 关系映射
            is_header: True=解析页眉, False=解析页脚
        """
        texts = []
        # 页眉/页脚的关系类型关键字
        keyword = "header" if is_header else "footer"

        # 遍历关系文件，找到所有页眉/页脚引用
        header_footer_files = []
        for rid, info in rels.items():
            if keyword in info.get("type", "").lower() or keyword in info.get("target", "").lower():
                header_footer_files.append(info["target"])

        # 同时尝试直接匹配文件名（即使关系文件中没有引用）
        for name in zf.namelist():
            if name.startswith(f"word/{keyword}") and name.endswith(".xml"):
                if name not in header_footer_files:
                    header_footer_files.append(name)

        for hf_path in header_footer_files:
            if hf_path not in zf.namelist():
                continue
            try:
                tree = self._read_xml(zf, hf_path)
                # 提取所有段落
                for p in self._findall(tree, "w:p"):
                    text = self._parse_paragraph(p)
                    if text:
                        texts.append(text)
            except Exception:
                continue

        return "\n".join(texts) if texts else ""

    # ===================== 脚注解析 =====================

    def _parse_footnotes(self, zf: zipfile.ZipFile) -> str:
        """解析 word/footnotes.xml 脚注内容"""
        fn_path = "word/footnotes.xml"
        if fn_path not in zf.namelist():
            # 尝试其他可能路径
            alt = [p for p in zf.namelist() if "footnote" in p.lower() and p.endswith(".xml")]
            if not alt:
                return ""
            fn_path = alt[0]

        try:
            tree = self._read_xml(zf, fn_path)
            texts = []
            for fn in self._findall(tree, "w:footnote"):
                # 获取脚注ID
                fn_id = self._get_attr(fn, "id")
                if fn_id in ("0", "-1", ""):
                    # id=0 是分隔符，id=-1 是延续符，跳过
                    continue

                fn_parts = []
                for p in self._findall(fn, "w:p"):
                    text = self._parse_paragraph(p)
                    if text:
                        fn_parts.append(text)

                if fn_parts:
                    texts.append(f"[{fn_id}] {' '.join(fn_parts)}")

            return "\n".join(texts) if texts else ""
        except Exception:
            return ""

    # ===================== 尾注解析 =====================

    def _parse_endnotes(self, zf: zipfile.ZipFile) -> str:
        """解析 word/endnotes.xml 尾注内容"""
        en_path = "word/endnotes.xml"
        if en_path not in zf.namelist():
            # 尝试其他可能路径
            alt = [p for p in zf.namelist() if "endnote" in p.lower() and p.endswith(".xml")]
            if not alt:
                return ""
            en_path = alt[0]

        try:
            tree = self._read_xml(zf, en_path)
            texts = []
            for en in self._findall(tree, "w:endnote"):
                # 获取尾注ID
                en_id = self._get_attr(en, "id")
                if en_id in ("0", "-1", ""):
                    # id=0 是分隔符，id=-1 是延续符，跳过
                    continue

                en_parts = []
                for p in self._findall(en, "w:p"):
                    text = self._parse_paragraph(p)
                    if text:
                        en_parts.append(text)

                if en_parts:
                    texts.append(f"[{en_id}] {' '.join(en_parts)}")

            return "\n".join(texts) if texts else ""
        except Exception:
            return ""
