"""
XLSX 解析器（纯Python实现，不依赖openpyxl）

XLSX本质是一个ZIP包，内部包含：
- xl/worksheets/sheet*.xml: 工作表数据
- xl/sharedStrings.xml: 共享字符串表
- xl/workbook.xml: 工作簿定义
- xl/styles.xml: 样式定义（含数字格式，用于日期转换）

解析策略：
1. 读取sharedStrings.xml构建字符串表
2. 读取styles.xml构建 xf索引 → 是否为日期 的映射
3. 遍历每个worksheet，提取行和单元格数据
4. 支持内联字符串和共享字符串两种模式
5. 处理合并单元格，将合并区域内的所有单元格填入左上角的值
6. 根据单元格引用对齐列位置，补齐缺失列
7. 将Excel日期序列号转为可读日期字符串
8. 最终调用 clean_text() 清洗输出文本
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

from .text_utils import clean_text


# Excel 内置日期/时间格式编号
# 这些编号对应的 numFmtId 表示该单元格是日期类型
_BUILTIN_DATE_IDS = {
    14, 15, 16, 17, 18, 19, 20, 21, 22, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36,
    45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58,
}

# 自定义格式中包含以下占位符的视为日期格式
_DATE_FORMAT_TOKENS = re.compile(
    r"[yYmMdDhHsS]",  # 日期/时间相关占位符
)

# Excel 日期起始日（1899-12-30），Excel 序列号 1 对应 1900-01-01
_EXCEL_EPOCH = datetime(1899, 12, 30)


class XlsxParser:
    """XLSX表格解析器（自实现）"""

    NAMESPACES = {
        "w": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }

    def __init__(self):
        self.ns = self.NAMESPACES

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

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

            # 1. 读取共享字符串表
            shared_strings = self._read_shared_strings(zf)

            # 2. 读取样式信息，构建 xf 索引 → 是否为日期的映射
            date_xf_indices = self._read_date_styles(zf)

            # 3. 获取工作表列表和名称
            sheet_names = self._read_sheet_names(zf)

            # 4. 获取工作表文件路径映射
            sheet_files = self._read_sheet_files(zf)

            # 5. 解析每个工作表
            all_texts = []
            for rid, sheet_name in sheet_names.items():
                sheet_path = sheet_files.get(rid)
                if not sheet_path or sheet_path not in zf.namelist():
                    continue

                try:
                    with zf.open(sheet_path) as f:
                        sheet_tree = ET.fromstring(f.read())
                    sheet_text = self._parse_worksheet(
                        sheet_tree, shared_strings, date_xf_indices
                    )
                    if sheet_text.strip():
                        all_texts.append(f"[工作表: {sheet_name}]\n{sheet_text}")
                except Exception as e:
                    all_texts.append(f"[工作表: {sheet_name}: 解析失败 {e}]")

            raw_text = "\n\n".join(all_texts)
            # 最终调用 clean_text 清洗输出文本
            return clean_text(raw_text)

    def get_metadata(self, file_path: str) -> dict:
        """提取XLSX元数据"""
        meta = {"sheet_count": 0, "title": "", "author": ""}

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                sheet_files = [
                    n for n in zf.namelist()
                    if re.match(r"xl/worksheets/sheet\d+\.xml", n)
                ]
                meta["sheet_count"] = len(sheet_files)

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

    # ------------------------------------------------------------------
    # 内部方法：读取共享字符串表
    # ------------------------------------------------------------------

    def _read_shared_strings(self, zf: zipfile.ZipFile) -> list:
        """从 xl/sharedStrings.xml 读取共享字符串列表"""
        shared_strings = []
        if "xl/sharedStrings.xml" not in zf.namelist():
            return shared_strings

        with zf.open("xl/sharedStrings.xml") as f:
            sst_tree = ET.fromstring(f.read())
            for si in sst_tree.findall("w:si", self.ns):
                texts = []
                for t in si.findall(".//w:t", self.ns):
                    if t.text:
                        texts.append(t.text)
                shared_strings.append("".join(texts))

        return shared_strings

    # ------------------------------------------------------------------
    # 内部方法：读取日期样式映射
    # ------------------------------------------------------------------

    def _read_date_styles(self, zf: zipfile.ZipFile) -> set:
        """从 xl/styles.xml 读取样式，返回属于日期类型的 xf 索引集合

        Excel 中单元格通过 s 属性（xf 索引）引用样式，
        样式中的 numFmtId 指向数字格式。
        内置日期 numFmtId 直接识别；自定义格式通过格式字符串中的
        日期/时间占位符（y/m/d/h/s 等）来判断。
        """
        date_xf_indices = set()

        styles_path = "xl/styles.xml"
        if styles_path not in zf.namelist():
            return date_xf_indices

        try:
            with zf.open(styles_path) as f:
                styles_tree = ET.fromstring(f.read())

            # 第一步：收集自定义 numFmt 中属于日期格式的 numFmtId
            # <numFmts><numFmt numFmtId="164" formatCode="yyyy/mm/dd"/></numFmts>
            custom_date_numfmt_ids = set()
            numFmts_elem = styles_tree.find("w:numFmts", self.ns)
            if numFmts_elem is None:
                numFmts_elem = self._find_with_fallback(styles_tree, "numFmts")
            if numFmts_elem is not None:
                for numFmt in numFmts_elem.findall("w:numFmt", self.ns):
                    fmt_id_str = numFmt.get("numFmtId", "")
                    fmt_code = numFmt.get("formatCode", "")
                    if fmt_id_str and fmt_code:
                        if _DATE_FORMAT_TOKENS.search(fmt_code):
                            custom_date_numfmt_ids.add(int(fmt_id_str))

            # 第二步：遍历 cellXfs，收集每个 xf 的索引
            # 如果该 xf 的 numFmtId 属于日期类型，则记录其索引
            # <cellXfs><xf numFmtId="14" .../></cellXfs>
            cellXfs_elem = styles_tree.find("w:cellXfs", self.ns)
            if cellXfs_elem is None:
                cellXfs_elem = self._find_with_fallback(styles_tree, "cellXfs")
            if cellXfs_elem is not None:
                for xf_index, xf in enumerate(cellXfs_elem.findall("w:xf", self.ns)):
                    fmt_id_str = xf.get("numFmtId", "")
                    if not fmt_id_str:
                        continue
                    try:
                        fmt_id = int(fmt_id_str)
                    except ValueError:
                        continue
                    # 内置日期编号 或 自定义日期格式
                    if fmt_id in _BUILTIN_DATE_IDS or fmt_id in custom_date_numfmt_ids:
                        date_xf_indices.add(xf_index)
        except Exception:
            pass

        return date_xf_indices

    # ------------------------------------------------------------------
    # 内部方法：读取工作表名称映射
    # ------------------------------------------------------------------

    def _read_sheet_names(self, zf: zipfile.ZipFile) -> dict:
        """从 xl/workbook.xml 读取 rId → 工作表名称的映射"""
        sheet_names = {}
        if "xl/workbook.xml" not in zf.namelist():
            return sheet_names

        with zf.open("xl/workbook.xml") as f:
            wb_tree = ET.fromstring(f.read())
            for sheet in wb_tree.findall(".//w:sheet", self.ns):
                sheet_id = sheet.get("sheetId", "")
                name = sheet.get("name", f"Sheet{sheet_id}")
                # r:id 如 r:id="rId1"
                rid = sheet.get(f"{{{self.ns['r']}}}id", "")
                sheet_names[rid] = name

        return sheet_names

    # ------------------------------------------------------------------
    # 内部方法：读取工作表文件路径映射
    # ------------------------------------------------------------------

    def _read_sheet_files(self, zf: zipfile.ZipFile) -> dict:
        """从 xl/_rels/workbook.xml.rels 读取 rId → 工作表文件路径的映射"""
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
                        # target 可能是相对路径如 worksheets/sheet1.xml
                        sheet_files[rid] = "xl/" + target.replace("\\", "/")

        # 如果没有从 rels 读到，直接扫描
        if not sheet_files:
            worksheet_files = sorted(
                [
                    name for name in zf.namelist()
                    if re.match(r"xl/worksheets/sheet\d+\.xml", name)
                ],
                key=lambda x: int(re.search(r"sheet(\d+)", x).group(1)),
            )
            for i, wf in enumerate(worksheet_files):
                sheet_files[f"rId{i+1}"] = wf

        return sheet_files

    # ------------------------------------------------------------------
    # 内部方法：解析单个工作表
    # ------------------------------------------------------------------

    def _parse_worksheet(
        self, root: ET.Element, shared_strings: list, date_xf_indices: set
    ) -> str:
        """解析单个工作表，返回格式化文本

        处理步骤：
        1. 解析合并单元格区域，构建填充映射
        2. 遍历行和单元格，根据 r 属性确定列位置
        3. 将合并区域内的单元格填入左上角的值
        4. 补齐缺失列，保持列对齐
        5. 将日期序列号转换为可读日期字符串
        """
        # --- 解析合并单元格 ---
        merge_map = self._parse_merge_cells(root, shared_strings, date_xf_indices)
        # merge_map: {(行号, 列号): 值}  记录每个被合并的单元格应该显示的值

        # --- 获取 sheetData ---
        sheet_data = root.find("w:sheetData", self.ns)
        if sheet_data is None:
            sheet_data = self._find_with_fallback(root, "sheetData")
        if sheet_data is None:
            return ""
        # _find_with_fallback 使用 find，不会返回列表

        # --- 遍历行（带命名空间回退） ---
        row_list = sheet_data.findall("w:row", self.ns)
        if not row_list:
            row_list = sheet_data.findall("{*}row")
        if not row_list:
            return ""

        rows = []
        for row_elem in row_list:
            # 解析该行的所有单元格
            cell_dict = self._parse_row(row_elem, shared_strings, date_xf_indices)

            # 填充合并单元格的值
            row_num_str = row_elem.get("r", "")
            try:
                current_row_num = int(row_num_str)
            except ValueError:
                current_row_num = None

            if current_row_num is not None:
                for (r, c), val in merge_map.items():
                    if r == current_row_num and c not in cell_dict:
                        cell_dict[c] = val

            if not cell_dict:
                continue

            # 根据列索引对齐，补齐缺失列
            max_col = max(cell_dict.keys()) if cell_dict else 0
            row_values = []
            for col_idx in range(max_col + 1):
                row_values.append(cell_dict.get(col_idx, ""))

            if any(row_values):
                rows.append(" | ".join(row_values))

            if len(rows) >= 500:
                rows.append("... （已截取前500行）")
                break

        return "\n".join(rows)

    # ------------------------------------------------------------------
    # 内部方法：解析合并单元格
    # ------------------------------------------------------------------

    def _parse_merge_cells(
        self, root: ET.Element, shared_strings: list, date_xf_indices: set
    ) -> dict:
        """解析 mergeCells 元素，返回 {(行号, 列号): 值} 的映射

        合并单元格在 XML 中的结构：
        <mergeCells count="2">
            <mergeCell ref="B2:C3"/>
            <mergeCell ref="E5:F5"/>
        </mergeCells>

        对于每个合并区域，只有左上角单元格在 sheetData 中有实际值，
        其余单元格需要填入同样的值。
        """
        merge_map = {}

        # 查找 mergeCells 容器元素
        merge_cells_elem = root.find("w:mergeCells", self.ns)
        if merge_cells_elem is None:
            merge_cells_elem = self._find_with_fallback(root, "mergeCells")
        if merge_cells_elem is None:
            return merge_map
        # _find_with_fallback 使用 find，不会返回列表

        # 构建 origin_map: (行号, 列号) → (左上角行号, 左上角列号)
        origin_map = {}
        # 记录所有左上角坐标
        origin_coords = set()

        for merge_cell in merge_cells_elem.findall("w:mergeCell", self.ns):
            ref = merge_cell.get("ref", "")
            if not ref or ":" not in ref:
                continue
            try:
                start_ref, end_ref = ref.split(":", 1)
                start_col, start_row = self._cell_ref_to_indices(start_ref)
                end_col, end_row = self._cell_ref_to_indices(end_ref)

                origin_coords.add((start_row, start_col))

                for r in range(start_row, end_row + 1):
                    for c in range(start_col, end_col + 1):
                        # 跳过左上角本身（它有自己的值）
                        if r == start_row and c == start_col:
                            continue
                        origin_map[(r, c)] = (start_row, start_col)
                        merge_map[(r, c)] = None  # 稍后填充
            except (ValueError, IndexError):
                continue

        if not merge_map:
            return merge_map

        # 从 sheetData 中提取左上角单元格的值
        origin_values = {}
        sheet_data = root.find("w:sheetData", self.ns)
        if sheet_data is None:
            sheet_data = self._find_with_fallback(root, "sheetData")
        if sheet_data is None:
            return merge_map

        # 获取行列表（带回退）
        row_list = sheet_data.findall("w:row", self.ns)
        if not row_list:
            row_list = sheet_data.findall("{*}row")

        for row_elem in row_list:
            row_num_str = row_elem.get("r", "")
            try:
                row_num = int(row_num_str)
            except ValueError:
                continue

            # 获取单元格列表（带回退）
            cell_list = row_elem.findall("w:c", self.ns)
            if not cell_list:
                cell_list = row_elem.findall("{*}c")

            for cell_elem in cell_list:
                cell_ref = cell_elem.get("r", "")
                if not cell_ref:
                    continue
                try:
                    col_idx, _ = self._cell_ref_to_indices(cell_ref)
                except (ValueError, IndexError):
                    continue

                # 只关心合并区域的左上角单元格
                if (row_num, col_idx) not in origin_coords:
                    continue
                if (row_num, col_idx) in origin_values:
                    continue

                value = self._get_cell_value(cell_elem, shared_strings, date_xf_indices)
                origin_values[(row_num, col_idx)] = value

        # 填充 merge_map：将每个被合并的单元格值设为其左上角的值
        for (r, c), val in merge_map.items():
            if val is None and (r, c) in origin_map:
                origin = origin_map[(r, c)]
                merge_map[(r, c)] = origin_values.get(origin, "")

        return merge_map

    # ------------------------------------------------------------------
    # 内部方法：解析单行数据
    # ------------------------------------------------------------------

    def _parse_row(
        self, row_elem: ET.Element, shared_strings: list, date_xf_indices: set
    ) -> dict:
        """解析一行中的所有单元格，返回 {列索引: 值} 的字典

        根据 cell 的 r 属性（如 "A1", "C1"）确定列位置，
        缺失的列会在上层调用中补齐。
        """
        cell_dict = {}

        # 获取单元格列表（带命名空间回退）
        cell_list = row_elem.findall("w:c", self.ns)
        if not cell_list:
            cell_list = row_elem.findall("{*}c")

        for cell_elem in cell_list:
            cell_ref = cell_elem.get("r", "")
            try:
                col_idx, _ = self._cell_ref_to_indices(cell_ref)
            except (ValueError, IndexError):
                # 如果无法解析引用，按出现顺序依次分配列号
                col_idx = len(cell_dict)

            value = self._get_cell_value(cell_elem, shared_strings, date_xf_indices)
            cell_dict[col_idx] = value

        return cell_dict

    # ------------------------------------------------------------------
    # 内部方法：获取单元格的值
    # ------------------------------------------------------------------

    def _get_cell_value(
        self, cell: ET.Element, shared_strings: list, date_xf_indices: set
    ) -> str:
        """获取单元格的值

        处理以下类型：
        - t="s": 共享字符串（通过索引引用 sharedStrings.xml）
        - t="inlineStr": 内联字符串
        - t="str": 公式返回的字符串
        - 普通数值：检查是否为日期格式，是则转换
        - 其他：直接返回文本
        """
        cell_type = cell.get("t", "")

        # 查找 v 元素（单元格值）—— find 不会返回列表，无需特殊处理
        v_elem = cell.find("w:v", self.ns)
        if v_elem is None:
            v_elem = self._find_with_fallback(cell, "v")

        # 查找 is 元素（内联字符串）
        is_elem = cell.find("w:is", self.ns)
        if is_elem is None:
            is_elem = self._find_with_fallback(cell, "is")

        # 获取单元格样式索引，用于日期格式判断
        style_idx = cell.get("s", "")

        if cell_type == "s" and v_elem is not None and v_elem.text:
            # 共享字符串类型
            try:
                idx = int(v_elem.text)
                if 0 <= idx < len(shared_strings):
                    return shared_strings[idx]
            except ValueError:
                pass
            return v_elem.text

        if cell_type == "str" and v_elem is not None and v_elem.text:
            # 公式返回的字符串
            return v_elem.text

        if is_elem is not None:
            # 内联字符串类型
            texts = []
            t_list = is_elem.findall(".//w:t", self.ns)
            if not t_list:
                t_list = is_elem.findall(".//{*}t")
            for t in t_list:
                if t.text:
                    texts.append(t.text)
            return "".join(texts)

        if v_elem is not None and v_elem.text:
            raw_value = v_elem.text

            # 尝试判断是否为日期
            if self._is_date_cell(style_idx, date_xf_indices, cell_type):
                date_str = self._excel_date_to_string(raw_value)
                if date_str is not None:
                    return date_str

            return raw_value

        return ""

    # ------------------------------------------------------------------
    # 内部方法：判断单元格是否为日期格式
    # ------------------------------------------------------------------

    @staticmethod
    def _is_date_cell(style_idx: str, date_xf_indices: set, cell_type: str) -> bool:
        """判断单元格是否使用日期数字格式

        Args:
            style_idx: 单元格的 s 属性（xf 索引）
            date_xf_indices: 从 styles.xml 中收集的日期样式 xf 索引集合
            cell_type: 单元格的 t 属性
        """
        # 字符串相关类型不当作日期
        if cell_type in ("s", "inlineStr", "str", "e"):
            return False

        # 没有样式索引则无法判断
        if not style_idx:
            return False

        try:
            idx = int(style_idx)
        except ValueError:
            return False

        return idx in date_xf_indices

    # ------------------------------------------------------------------
    # 内部方法：Excel 日期序列号 → 可读日期字符串
    # ------------------------------------------------------------------

    @staticmethod
    def _excel_date_to_string(serial_str: str) -> str | None:
        """将 Excel 日期序列号转换为 "YYYY-MM-DD" 格式的字符串

        Excel 日期起始日为 1899-12-30（序列号 0）。
        序列号 1 = 1900-01-01，依次类推。
        注意 Excel 有一个 1900 年闰年 bug，序列号 60 对应不存在的 1900-02-29，
        序列号 >= 60 时需要减 1 天来修正。

        Args:
            serial_str: Excel 日期序列号的字符串形式

        Returns:
            格式化后的日期字符串，如 "2024-01-15"；含时间时返回 "2024-01-15 14:30:00"；
            转换失败返回 None
        """
        try:
            serial = float(serial_str)
        except (ValueError, TypeError):
            return None

        # Excel 日期序列号通常为正整数或带小数（小数部分表示时间）
        if serial < 1 or serial > 2958465:  # 上限约 9999-12-31
            return None

        try:
            # 处理 Excel 的 1900 闰年 bug
            if serial >= 60:
                serial -= 1

            days = int(serial)
            frac = serial - days

            delta = timedelta(days=days)
            date_obj = _EXCEL_EPOCH + delta

            # 如果有小数部分，说明包含时间
            if frac > 0.00001:
                total_seconds = int(frac * 86400)
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                return (
                    date_obj.strftime("%Y-%m-%d")
                    + f" {hours:02d}:{minutes:02d}:{seconds:02d}"
                )

            return date_obj.strftime("%Y-%m-%d")
        except (ValueError, OverflowError, OSError):
            return None

    # ------------------------------------------------------------------
    # 内部方法：单元格引用 → (列索引, 行号)
    # ------------------------------------------------------------------

    @staticmethod
    def _cell_ref_to_indices(cell_ref: str) -> tuple[int, int]:
        """将单元格引用（如 "A1", "AA42"）转换为 (列索引, 行号)

        列索引从 0 开始：A=0, B=1, ..., Z=25, AA=26, ...
        行号从 1 开始。

        Args:
            cell_ref: 单元格引用字符串，如 "B3", "AB10"

        Returns:
            (列索引, 行号) 元组

        Raises:
            ValueError: 如果引用格式无效
        """
        if not cell_ref:
            raise ValueError("空的单元格引用")

        # 分离字母部分和数字部分
        match = re.match(r"^([A-Za-z]+)(\d+)$", cell_ref)
        if not match:
            raise ValueError(f"无效的单元格引用: {cell_ref}")

        col_str = match.group(1).upper()
        row_str = match.group(2)

        # 计算列索引（类似 26 进制，但没有 0）
        col_idx = 0
        for ch in col_str:
            col_idx = col_idx * 26 + (ord(ch) - ord("A") + 1)
        col_idx -= 1  # 转为 0-based

        row_idx = int(row_str)

        return col_idx, row_idx

    # ------------------------------------------------------------------
    # 内部方法：安全的命名空间回退查找（仅用于 find，不用于 findall）
    # ------------------------------------------------------------------

    def _find_with_fallback(self, parent: ET.Element, tag: str):
        """带命名空间回退的 find 操作，仅用于返回单个元素的场景

        先尝试用标准命名空间查找，如果找不到再用 "{*}tag" 通配符回退。
        find() 不会返回列表，因此无需担心列表类型问题。

        对于 findall 场景（返回列表），应在调用处直接处理：
            lst = parent.findall("w:tag", self.ns)
            if not lst:
                lst = parent.findall("{*}tag")

        Args:
            parent: 父 XML 元素
            tag: 标签名（不含命名空间前缀）

        Returns:
            找到的 Element，或 None
        """
        result = parent.find(f"w:{tag}", self.ns)
        if result is not None:
            return result
        return parent.find(f"{{*}}{tag}")