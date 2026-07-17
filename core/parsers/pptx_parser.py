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
3. 提取shape中的文本
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


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

    def parse(self, file_path: str) -> str:
        """解析PPTX文件，返回纯文本"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        if not zipfile.is_zipfile(file_path):
            raise ValueError(f"不是有效的PPTX文件: {file_path}")

        with zipfile.ZipFile(file_path, "r") as zf:
            if "[Content_Types].xml" not in zf.namelist():
                raise ValueError(f"缺少[Content_Types].xml")

            # 获取所有幻灯片文件，按名称排序
            slide_files = sorted([
                name for name in zf.namelist()
                if re.match(r"ppt/slides/slide\d+\.xml", name)
            ], key=lambda x: int(re.search(r"slide(\d+)", x).group(1)))

            if not slide_files:
                # 尝试其他路径
                slide_files = sorted([
                    name for name in zf.namelist()
                    if name.endswith("slide.xml") or "/slides/" in name
                ])

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

            # 尝试解析备注
            notes_files = sorted([
                name for name in zf.namelist()
                if re.match(r"ppt/notesSlides/notesSlide\d+\.xml", name)
            ], key=lambda x: int(re.search(r"notesSlide(\d+)", x).group(1)))

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

            return "\n\n".join(all_texts)

    def _parse_slide(self, root: ET.Element) -> str:
        """解析单张幻灯片"""
        parts = []

        for sp in self._findall(root, ".//p:sp"):
            text = self._parse_shape(sp)
            if text.strip():
                parts.append(text)

        for graphic in self._findall(root, ".//a:graphic"):
            chart_text = self._parse_chart(graphic)
            if chart_text:
                parts.append(chart_text)

        return "\n".join(parts)

    def _find(self, elem: ET.Element, path: str) -> ET.Element:
        result = elem.find(path, self.ns)
        if result is not None:
            return result
        tag = path.split("/")[-1].split(":")[-1]
        return elem.find(f".//{{*}}{tag}")

    def _findall(self, elem: ET.Element, path: str) -> list:
        results = elem.findall(path, self.ns)
        if results:
            return results
        tag = path.split("/")[-1].split(":")[-1]
        return elem.findall(f".//{{*}}{tag}")

    def _parse_shape(self, sp_elem: ET.Element) -> str:
        texts = []
        tx_body = sp_elem.find("p:txBody", self.ns)
        if tx_body is None:
            tx_body = sp_elem.find("{*}txBody")
        if tx_body is None:
            return ""

        for para in tx_body.findall("a:p", self.ns):
            if para is None:
                para = tx_body.findall("{*}p")
            para_texts = []
            for run in para.findall("a:r", self.ns):
                t = run.find("a:t", self.ns)
                if t is None:
                    t = run.find("{*}t")
                if t is not None and t.text:
                    para_texts.append(t.text)
            for fld in para.findall("a:fld", self.ns):
                t = fld.find("a:t", self.ns)
                if t is None:
                    t = fld.find("{*}t")
                if t is not None and t.text:
                    para_texts.append(t.text)

            if para_texts:
                texts.append("".join(para_texts))

        return "\n".join(texts)

    def _parse_chart(self, graphic_elem: ET.Element) -> str:
        texts = []
        for t_elem in graphic_elem.findall(".//c:title//c:tx//c:t", self.ns):
            if t_elem.text:
                texts.append(f"[图表标题] {t_elem.text}")
        for cat in graphic_elem.findall(".//c:cat//c:v", self.ns):
            if cat.text:
                texts.append(f"[类别] {cat.text}")
        for val in graphic_elem.findall(".//c:val//c:v", self.ns):
            if val.text:
                texts.append(f"[数值] {val.text}")
        return "\n".join(texts)

    def get_metadata(self, file_path: str) -> dict:
        """提取PPTX元数据"""
        meta = {"slide_count": 0, "title": "", "author": ""}

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                slide_files = [n for n in zf.namelist() if re.match(r"ppt/slides/slide\d+\.xml", n)]
                meta["slide_count"] = len(slide_files)

                if "docProps/core.xml" in zf.namelist():
                    with zf.open("docProps/core.xml") as f:
                        core_tree = ET.fromstring(f.read())
                        ns = {"dc": "http://purl.org/dc/elements/1.1/",
                              "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"}
                        for title in core_tree.findall("dc:title", ns):
                            meta["title"] = title.text or ""
                        for creator in core_tree.findall("dc:creator", ns):
                            meta["author"] = creator.text or ""
        except Exception:
            pass

        return meta
