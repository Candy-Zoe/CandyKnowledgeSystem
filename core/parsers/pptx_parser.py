"""
PPTX 解析器（纯Python实现，不依赖python-pptx）

PPTX本质是一个ZIP包，内部包含：
- ppt/slides/slide*.xml: 幻灯片内容
- ppt/slideLayouts/*.xml: 幻灯片布局
- ppt/slideMasters/*.xml: 幻灯片母版
- ppt/notesSlides/*.xml: 备注页

解析策略：
1. 用zipfile解压读取
2. 遍历所有slide*.xml
3. 递归解析形状（包括分组形状、表格）
4. 尝试从母版提取占位符文本
5. 文本清洗后返回
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from core.parsers.text_utils import clean_text


class PptxParser:
    """PPTX演示文稿解析器（自实现）"""

    NAMESPACES = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    }

    def __init__(self):
        self.ns = self.NAMESPACES

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def parse(self, file_path: str) -> str:
        """解析PPTX文件，返回纯文本（经过clean_text清洗）"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        if not zipfile.is_zipfile(file_path):
            raise ValueError(f"不是有效的PPTX文件: {file_path}")

        with zipfile.ZipFile(file_path, "r") as zf:
            if "[Content_Types].xml" not in zf.namelist():
                raise ValueError("缺少 [Content_Types].xml")

            # ---------- 母版占位符文本（用于填充幻灯片中空占位符） ----------
            master_texts = self._extract_master_placeholder_texts(zf)

            # ---------- 获取所有幻灯片文件，按编号排序 ----------
            slide_files = sorted(
                [
                    name
                    for name in zf.namelist()
                    if re.match(r"ppt/slides/slide\d+\.xml", name)
                ],
                key=lambda x: int(re.search(r"slide(\d+)", x).group(1)),
            )
            if not slide_files:
                # 回退：尝试其他路径
                slide_files = sorted(
                    [
                        name
                        for name in zf.namelist()
                        if name.endswith("slide.xml") or "/slides/" in name
                    ]
                )

            all_texts = []
            for slide_file in slide_files:
                try:
                    with zf.open(slide_file) as f:
                        tree = ET.fromstring(f.read())
                    slide_text = self._parse_slide(tree)
                    if slide_text.strip():
                        slide_num = re.search(r"slide(\d+)", slide_file)
                        num = slide_num.group(1) if slide_num else "?"
                        all_texts.append(f"[第{num}页幻灯片]\n{slide_text}")
                except Exception as e:
                    all_texts.append(f"[第?页幻灯片: 解析失败 {e}]")

            # ---------- 尝试解析备注 ----------
            notes_files = sorted(
                [
                    name
                    for name in zf.namelist()
                    if re.match(r"ppt/notesSlides/notesSlide\d+\.xml", name)
                ],
                key=lambda x: int(re.search(r"notesSlide(\d+)", x).group(1)),
            )
            for notes_file in notes_files:
                try:
                    with zf.open(notes_file) as f:
                        tree = ET.fromstring(f.read())
                    notes_text = self._parse_slide(tree)
                    if notes_text.strip():
                        slide_num = re.search(r"notesSlide(\d+)", notes_file)
                        num = slide_num.group(1) if slide_num else "?"
                        all_texts.append(f"[第{num}页备注]\n{notes_text}")
                except Exception:
                    pass

            # ---------- 合并母版文本 ----------
            if master_texts.strip():
                all_texts.insert(0, f"[母版占位符文本]\n{master_texts}")

            raw = "\n\n".join(all_texts)
            return clean_text(raw)

    # ------------------------------------------------------------------
    # 内部解析方法
    # ------------------------------------------------------------------

    def _parse_slide(self, root: ET.Element) -> str:
        """解析单张幻灯片，提取所有形状文本"""
        parts = []

        # 1. 解析普通形状
        for sp in self._findall(root, ".//p:sp"):
            text = self._parse_shape(sp)
            if text.strip():
                parts.append(text)

        # 2. 解析分组形状（递归）
        for grp_sp in self._findall(root, ".//p:grpSp"):
            text = self._parse_group_shape(grp_sp)
            if text.strip():
                parts.append(text)

        # 3. 解析表格
        for tbl in self._findall(root, ".//a:tbl"):
            text = self._parse_table(tbl)
            if text.strip():
                parts.append(text)

        # 4. 解析图表
        for graphic in self._findall(root, ".//a:graphic"):
            chart_text = self._parse_chart(graphic)
            if chart_text:
                parts.append(chart_text)

        return "\n".join(parts)

    def _parse_group_shape(self, grp_sp: ET.Element) -> str:
        """递归解析分组形状（p:grpSp）内的所有子形状"""
        parts = []

        # 分组形状内的子形状可能是 p:sp、p:grpSp（嵌套分组）等
        for sp in self._findall(grp_sp, ".//p:sp"):
            text = self._parse_shape(sp)
            if text.strip():
                parts.append(text)

        # 递归处理嵌套的分组形状
        for nested_grp in self._findall(grp_sp, "p:grpSp"):
            text = self._parse_group_shape(nested_grp)
            if text.strip():
                parts.append(text)

        return "\n".join(parts)

    def _parse_table(self, tbl: ET.Element) -> str:
        """解析PPTX中的表格元素（a:tbl），返回格式化文本"""
        rows = []
        # 获取所有行
        tr_elements = self._findall(tbl, "a:tr")
        for tr in tr_elements:
            cells = []
            # 获取行内所有单元格
            tc_elements = self._findall(tr, "a:tc")
            for tc in tc_elements:
                cell_text = self._extract_text_from_element(tc)
                cells.append(cell_text.strip() if cell_text else "")
            rows.append(" | ".join(cells))

        if not rows:
            return ""

        # 如果有表头行，在第一行加标记
        if len(rows) > 1:
            rows[0] = "[表头] " + rows[0]

        return "\n".join(rows)

    def _parse_shape(self, sp_elem: ET.Element) -> str:
        """解析单个形状（p:sp），提取文本框中的文本"""
        tx_body = self._find(sp_elem, "p:txBody")
        if tx_body is None:
            return ""

        texts = []
        for para in self._findall(tx_body, "a:p"):
            para_texts = []
            for run in self._findall(para, "a:r"):
                t_elem = self._find(run, "a:t")
                if t_elem is not None and t_elem.text:
                    para_texts.append(t_elem.text)
            # 处理字段引用（如幻灯片编号、日期等）
            for fld in self._findall(para, "a:fld"):
                t_elem = self._find(fld, "a:t")
                if t_elem is not None and t_elem.text:
                    para_texts.append(t_elem.text)

            if para_texts:
                texts.append("".join(para_texts))

        return "\n".join(texts)

    def _parse_chart(self, graphic_elem: ET.Element) -> str:
        """解析图表元素，提取标题、类别和数值"""
        texts = []
        for t_elem in self._findall(graphic_elem, ".//c:title//c:tx//c:rich//a:r//a:t"):
            if t_elem is not None and t_elem.text:
                texts.append(f"[图表标题] {t_elem.text}")
        # 回退：直接在 c:tx 下找 a:t
        if not texts:
            for t_elem in self._findall(graphic_elem, ".//c:title//a:t"):
                if t_elem is not None and t_elem.text:
                    texts.append(f"[图表标题] {t_elem.text}")
        for cat in self._findall(graphic_elem, ".//c:cat//c:v"):
            if cat is not None and cat.text:
                texts.append(f"[类别] {cat.text}")
        for val in self._findall(graphic_elem, ".//c:val//c:v"):
            if val is not None and val.text:
                texts.append(f"[数值] {val.text}")
        return "\n".join(texts)

    # ------------------------------------------------------------------
    # 母版占位符文本
    # ------------------------------------------------------------------

    def _extract_master_placeholder_texts(self, zf: zipfile.ZipFile) -> str:
        """从 slideMasters 目录提取占位符文本，用于填充幻灯片中的空占位符"""
        master_files = [
            name
            for name in zf.namelist()
            if re.match(r"ppt/slideMasters/slideMaster\d+\.xml", name)
        ]

        if not master_files:
            return ""

        all_texts = []
        for master_file in master_files:
            try:
                with zf.open(master_file) as f:
                    tree = ET.fromstring(f.read())
                # 提取母版中所有文本形状
                for sp in self._findall(tree, ".//p:sp"):
                    text = self._parse_shape(sp)
                    if text.strip():
                        all_texts.append(text)
                # 提取母版中的表格
                for tbl in self._findall(tree, ".//a:tbl"):
                    text = self._parse_table(tbl)
                    if text.strip():
                        all_texts.append(text)
            except Exception:
                pass

        return "\n".join(all_texts)

    # ------------------------------------------------------------------
    # XML 辅助方法
    # ------------------------------------------------------------------

    def _find(self, elem: ET.Element, path: str):
        """安全的 find，带命名空间回退"""
        # 尝试使用命名空间查找
        result = elem.find(path, self.ns)
        if result is not None:
            return result

        # 回退：去掉所有前缀，用通配符匹配
        # 将 "a:p" 转为 ".//{*}p"，"p:txBody" 转为 ".//{*}txBody"
        parts = path.lstrip("./").split("/")
        wildcard_path = "./"
        for part in parts:
            if ":" in part:
                _, local = part.split(":", 1)
                wildcard_path += f"{{{self.ns.get('*', '')}*}}{local}/"
            else:
                wildcard_path += f"{part}/"
        wildcard_path = wildcard_path.rstrip("/")

        result = elem.find(wildcard_path)
        if result is not None:
            return result

        # 最终回退：按标签名查找（无命名空间）
        if ":" in path.split("/")[-1]:
            tag = path.split("/")[-1].split(":")[-1]
        else:
            tag = path.split("/")[-1]
        return elem.find(f".//{tag}")

    def _findall(self, elem: ET.Element, path: str) -> list:
        """安全的 findall，带命名空间回退，始终返回列表"""
        # 尝试使用命名空间查找
        results = elem.findall(path, self.ns)
        if results:
            return results

        # 回退：使用通配符命名空间
        parts = path.lstrip("./").split("/")
        wildcard_path = "."
        for part in parts:
            if ":" in part:
                _, local = part.split(":", 1)
                wildcard_path += f"/{{{self.ns.get('*', '')}*}}{local}"
            else:
                wildcard_path += f"/{part}"

        results = elem.findall(wildcard_path)
        if results:
            return results

        # 最终回退：按标签名查找（无命名空间）
        if ":" in path.split("/")[-1]:
            tag = path.split("/")[-1].split(":")[-1]
        else:
            tag = path.split("/")[-1]
        return elem.findall(f".//{tag}")

    def _extract_text_from_element(self, elem: ET.Element) -> str:
        """从元素及其子元素中递归提取所有 a:t 文本节点"""
        texts = []
        for t_elem in self._findall(elem, ".//a:t"):
            if t_elem is not None and t_elem.text:
                texts.append(t_elem.text)
        return "".join(texts)

    # ------------------------------------------------------------------
    # 元数据
    # ------------------------------------------------------------------

    def get_metadata(self, file_path: str) -> dict:
        """提取PPTX元数据"""
        meta = {"slide_count": 0, "title": "", "author": ""}

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                slide_files = [
                    n
                    for n in zf.namelist()
                    if re.match(r"ppt/slides/slide\d+\.xml", n)
                ]
                meta["slide_count"] = len(slide_files)

                if "docProps/core.xml" in zf.namelist():
                    with zf.open("docProps/core.xml") as f:
                        core_tree = ET.fromstring(f.read())
                        ns = {
                            "dc": "http://purl.org/dc/elements/1.1/",
                            "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
                        }
                        for title in core_tree.findall("dc:title", ns):
                            meta["title"] = title.text or ""
                        for creator in core_tree.findall("dc:creator", ns):
                            meta["author"] = creator.text or ""
        except Exception:
            pass

        return meta
