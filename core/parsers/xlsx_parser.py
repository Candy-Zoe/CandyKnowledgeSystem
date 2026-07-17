"""
XLSX 解析器（纯Python实现，不依赖openpyxl）

XLSX本质是一个ZIP包，内部包含：
- xl/worksheets/sheet*.xml: 工作表数据
- xl/sharedStrings.xml: 共享字符串表
- xl/workbook.xml: 工作簿定义

解析策略：
1. 读取sharedStrings.xml构建字符串表
2. 遍历每个worksheet，提取行和单元格数据
3. 支持内联字符串和共享字符串两种模式
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


class XlsxParser:
    """XLSX表格解析器（自实现）"""

    NAMESPACES = {
        "w": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }

    def __init__(self):
        self.ns = self.NAMESPACES

    def parse(self, file_path: str) -> str:
        """解析XLSX文件，返回纯文本"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        if not zipfile.is_zipfile(file_path):
            raise ValueError(f"不是有效的XLSX文件: {file_path}")

        with zipfile.ZipFile(file_path, "r") as zf:
            if "[Content_Types].xml" not in zf.namelist():
                raise ValueError(f"缺少[Content_Types].xml")

            # 读取共享字符串表
            shared_strings = []
            if "xl/sharedStrings.xml" in zf.namelist():
                with zf.open("xl/sharedStrings.xml") as f:
                    sst_tree = ET.fromstring(f.read())
                    for si in sst_tree.findall("w:si", self.ns):
                        # 收集所有文本片段
                        texts = []
                        for t in si.findall(".//w:t", self.ns):
                            if t.text:
                                texts.append(t.text)
                        shared_strings.append("".join(texts))

            # 获取工作表列表和名称
            sheet_names = {}
            if "xl/workbook.xml" in zf.namelist():
                with zf.open("xl/workbook.xml") as f:
                    wb_tree = ET.fromstring(f.read())
                    for sheet in wb_tree.findall(".//w:sheet", self.ns):
                        sheet_id = sheet.get("sheetId", "")
                        name = sheet.get("name", f"Sheet{sheet_id}")
                        # r:id 如 r:id="rId1"
                        rid = sheet.get(f"{{{self.ns['r']}}}id", "")
                        sheet_names[rid] = name

            # 获取工作表文件路径映射 (从 xl/_rels/workbook.xml.rels)
            sheet_files = {}
            rels_path = "xl/_rels/workbook.xml.rels"
            if rels_path in zf.namelist():
                with zf.open(rels_path) as f:
                    rels_tree = ET.fromstring(f.read())
                    rels_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
                    for rel in rels_tree.findall(f"{{{rels_ns}}}Relationship"):
                        rid = rel.get("Id", "")
                        target = rel.get("Target", "")
                        rel_type = rel.get("Type", "")
                        if "worksheet" in rel_type and rid and target:
                            # target可能是相对路径如 worksheets/sheet1.xml
                            sheet_files[rid] = "xl/" + target.replace("\\", "/")

            # 如果没有从rels读到，直接扫描
            if not sheet_files:
                worksheet_files = sorted([
                    name for name in zf.namelist()
                    if re.match(r"xl/worksheets/sheet\d+\.xml", name)
                ], key=lambda x: int(re.search(r"sheet(\d+)", x).group(1)))
                for i, wf in enumerate(worksheet_files):
                    sheet_files[f"rId{i+1}"] = wf

            # 解析每个工作表
            all_texts = []
            for rid, sheet_name in sheet_names.items():
                sheet_path = sheet_files.get(rid)
                if not sheet_path or sheet_path not in zf.namelist():
                    continue

                try:
                    with zf.open(sheet_path) as f:
                        sheet_tree = ET.fromstring(f.read())
                    sheet_text = self._parse_worksheet(sheet_tree, shared_strings)
                    if sheet_text.strip():
                        all_texts.append(f"[工作表: {sheet_name}]\n{sheet_text}")
                except Exception as e:
                    all_texts.append(f"[工作表: {sheet_name}: 解析失败 {e}]")

            return "\n\n".join(all_texts)

    def _parse_worksheet(self, root: ET.Element, shared_strings: list) -> str:
        """解析单个工作表"""
        rows = []
        sheet_data = root.find("w:sheetData", self.ns)
        if sheet_data is None:
            sheet_data = root.find("{*}sheetData")
        if sheet_data is None:
            return ""

        for row in sheet_data.findall("w:row", self.ns):
            if row is None:
                row = sheet_data.findall("{*}row")
            cells = []
            for cell in row.findall("w:c", self.ns):
                if cell is None:
                    cell = row.findall("{*}c")
                cell_value = self._get_cell_value(cell, shared_strings)
                cells.append(cell_value)
            if any(cells):
                rows.append(" | ".join(cells))

            if len(rows) >= 500:
                rows.append("... （已截取前500行）")
                break

        return "\n".join(rows)

    def _get_cell_value(self, cell: ET.Element, shared_strings: list) -> str:
        """获取单元格的值"""
        cell_type = cell.get("t", "")
        v_elem = cell.find("w:v", self.ns)
        if v_elem is None:
            v_elem = cell.find("{*}v")
        is_elem = cell.find("w:is", self.ns)
        if is_elem is None:
            is_elem = cell.find("{*}is")

        if cell_type == "s" and v_elem is not None and v_elem.text:
            try:
                idx = int(v_elem.text)
                if 0 <= idx < len(shared_strings):
                    return shared_strings[idx]
            except ValueError:
                pass
        elif is_elem is not None:
            texts = []
            for t in is_elem.findall(".//w:t", self.ns):
                if t is None:
                    t = is_elem.findall("{*}t")
                if t.text:
                    texts.append(t.text)
            return "".join(texts)
        elif v_elem is not None and v_elem.text:
            return v_elem.text

        return ""

    def get_metadata(self, file_path: str) -> dict:
        """提取XLSX元数据"""
        meta = {"sheet_count": 0, "title": "", "author": ""}

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                sheet_files = [n for n in zf.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n)]
                meta["sheet_count"] = len(sheet_files)

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
