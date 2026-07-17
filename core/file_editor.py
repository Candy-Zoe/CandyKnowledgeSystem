"""
通用文件编辑器 - 纯Python实现，支持所有110+格式的文件编辑

编辑策略：
1. 纯文本文件(txt/md/html/csv/json/xml/yaml/代码/字幕等): 直接编辑原始文件内容
2. 新版Office(docx/xlsx/pptx及变体): 纯Python操作ZIP+XML编辑
3. OpenDocument(odt/ods/odp): 纯Python操作ZIP+XML编辑
4. EPUB电子书: 纯Python操作ZIP+XHTML编辑
5. RTF富文本: 纯Python解析RTF控制词并编辑文本内容
6. MHT/MHTML: 纯Python提取HTML部分并编辑
7. XLSB(Excel二进制): ZIP+XML解压编辑
8. 旧版Office(doc/ppt/xls): 解析后文本编辑，保存为新文件
9. PDF: 解析后文本编辑，保存为新文件
10. 音频/视频/图片/ZIP: 元数据/解析文本编辑，保存为新文件

使用流程：
  content, mode, info = FileEditor.load_for_edit(file_path, file_type)
  # 用户编辑 content
  result = FileEditor.save_edit(file_path, file_type, content, mode)
"""
import os
import re
import struct
import shutil
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from core.logger import log


class FileEditor:
    """通用文件编辑器（纯Python实现，无外部依赖）"""

    # 纯文本格式 - 可以直接编辑原始文件
    TEXT_FORMATS = {
        "txt", "md", "html", "htm", "csv", "tsv",
        "json", "xml", "yaml", "yml", "toml",
        "ini", "conf", "cfg", "properties", "log",
        # 代码文件
        "py", "js", "java", "c", "cpp", "h", "hpp", "cs", "go", "rs",
        "rb", "php", "swift", "kt", "scala", "r", "m", "mm",
        "sql", "sh", "bat", "cmd", "ps1", "bash", "zsh",
        "css", "scss", "sass", "less", "vue", "jsx", "tsx",
        "dockerfile", "makefile", "cmake", "gradle",
        "tex", "bib", "rst", "adoc", "org",
        # 字幕
        "srt", "vtt", "ass", "ssa", "sub",
    }

    # 新版Office格式 - 纯Python操作ZIP+XML编辑（可回写原文件）
    OFFICE_FORMATS = {
        "docx", "dotx", "dotm",
        "xlsx", "xlsm", "xltx", "xlam",
        "pptx", "potx", "potm",
    }

    # OpenDocument格式 - 纯Python操作ZIP+XML编辑（可回写原文件）
    OPENDOC_FORMATS = {"odt", "ods", "odp"}

    # EPUB电子书 - 纯Python操作ZIP+XHTML编辑（可回写原文件）
    EPUB_FORMATS = {"epub"}

    # XLSB - ZIP+XML编辑（可回写原文件）
    XLSB_FORMATS = {"xlsb"}

    # RTF富文本 - 纯Python解析编辑（可回写原文件）
    RTF_FORMATS = {"rtf"}

    # MHT/MHTML - MIME HTML编辑（可回写原文件）
    MHT_FORMATS = {"mht", "mhtml"}

    # PDF格式 - 解析后编辑（保存为新文件）
    PDF_FORMATS = {"pdf"}

    # 旧版Office - 解析后编辑（保存为新文件）
    LEGACY_OFFICE_FORMATS = {"doc", "ppt", "xls"}

    # 音频格式 - 元数据编辑（保存为新文件）
    AUDIO_FORMATS = {"mp3", "wav", "flac", "aac", "m4a", "ogg", "wma", "opus"}

    # 视频格式 - 元数据编辑（保存为新文件）
    VIDEO_FORMATS = {"mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "3gp"}

    # 图片格式 - OCR文本编辑（保存为新文件）
    IMAGE_FORMATS = {"jpg", "jpeg", "png", "bmp", "gif", "tiff", "tif", "webp"}

    # 压缩包 - 内部文本编辑（保存为新文件）
    ARCHIVE_FORMATS = {"zip"}

    # 所有可回写原文件的格式集合
    WRITABLE_FORMATS = (
        TEXT_FORMATS | OFFICE_FORMATS | OPENDOC_FORMATS | EPUB_FORMATS
        | XLSB_FORMATS | RTF_FORMATS | MHT_FORMATS
    )

    # 所有格式集合
    ALL_FORMATS = (
        TEXT_FORMATS | OFFICE_FORMATS | OPENDOC_FORMATS | EPUB_FORMATS
        | XLSB_FORMATS | RTF_FORMATS | MHT_FORMATS | PDF_FORMATS
        | LEGACY_OFFICE_FORMATS | AUDIO_FORMATS | VIDEO_FORMATS
        | IMAGE_FORMATS | ARCHIVE_FORMATS
    )

    @classmethod
    def get_edit_mode(cls, file_type: str) -> str:
        """获取文件类型的编辑模式

        Returns:
            "text" - 直接编辑原始文件
            "office" - Office ZIP+XML编辑
            "opendoc" - OpenDocument ZIP+XML编辑
            "epub" - EPUB ZIP+XHTML编辑
            "xlsb" - Excel二进制ZIP+XML编辑
            "rtf" - RTF富文本编辑
            "mht" - MHTML编辑
            "pdf" - PDF解析后编辑
            "parsed" - 通用解析后编辑
        """
        ft = file_type.lower().lstrip(".")
        if ft in cls.TEXT_FORMATS:
            return "text"
        elif ft in cls.OFFICE_FORMATS:
            return "office"
        elif ft in cls.OPENDOC_FORMATS:
            return "opendoc"
        elif ft in cls.EPUB_FORMATS:
            return "epub"
        elif ft in cls.XLSB_FORMATS:
            return "xlsb"
        elif ft in cls.RTF_FORMATS:
            return "rtf"
        elif ft in cls.MHT_FORMATS:
            return "mht"
        elif ft in cls.PDF_FORMATS:
            return "pdf"
        else:
            return "parsed"

    @classmethod
    def get_edit_info(cls, mode: str, file_type: str) -> str:
        """获取编辑模式对应的描述信息"""
        info_map = {
            "text": "直接编辑原始文件内容，保存后覆盖原文件",
            "office": f"{file_type.upper()}文件（纯Python ZIP+XML编辑），保存后更新原文件",
            "opendoc": f"{file_type.upper()}文件（纯Python ZIP+XML编辑），保存后更新原文件",
            "epub": "EPUB电子书（纯Python ZIP+XHTML编辑），保存后更新原文件",
            "xlsb": "Excel二进制工作簿（纯Python ZIP+XML编辑），保存后更新原文件",
            "rtf": "RTF富文本（纯Python解析编辑），保存后更新原文件",
            "mht": "MHTML网页归档（纯Python提取HTML编辑），保存后更新原文件",
            "pdf": "PDF文件，编辑解析后的文本，保存为_edited.txt",
            "parsed": f"{file_type.upper()}文件，编辑解析后的文本，保存为_edited.txt",
        }
        return info_map.get(mode, f"{file_type.upper()}文件，编辑解析后的文本")

    @classmethod
    def load_for_edit(cls, file_path: str, file_type: str) -> tuple:
        """加载文件内容供编辑

        Returns:
            (content: str, mode: str, info: str)
        """
        mode = cls.get_edit_mode(file_type)

        try:
            if mode == "text":
                content = cls._read_text_file(file_path)
            elif mode == "office":
                content, success = cls._load_office_for_edit(file_path, file_type)
                if not success:
                    mode = "parsed"
            elif mode == "opendoc":
                content, success = cls._load_opendoc_for_edit(file_path, file_type)
                if not success:
                    mode = "parsed"
            elif mode == "epub":
                content, success = cls._load_epub_for_edit(file_path)
                if not success:
                    mode = "parsed"
            elif mode == "xlsb":
                content, success = cls._load_xlsb_for_edit(file_path)
                if not success:
                    mode = "parsed"
            elif mode == "rtf":
                content, success = cls._load_rtf_for_edit(file_path)
                if not success:
                    mode = "parsed"
            elif mode == "mht":
                content, success = cls._load_mht_for_edit(file_path)
                if not success:
                    mode = "parsed"
            elif mode == "pdf":
                content = cls._load_binary_for_edit(file_path, "pdf")
                mode = "parsed"
            else:
                content = cls._load_binary_for_edit(file_path, file_type)
        except Exception as e:
            log.warning(f"文件加载失败，使用解析器回退: {e}")
            content = cls._load_binary_for_edit(file_path, file_type)
            mode = "parsed"

        info = cls.get_edit_info(mode, file_type)
        return content, mode, info

    @classmethod
    def save_edit(cls, file_path: str, file_type: str, new_content: str, mode: str) -> dict:
        """保存编辑后的内容

        Returns:
            {"success": bool, "saved_path": str, "message": str}
        """
        try:
            if mode == "text":
                return cls._save_text_file(file_path, new_content)
            elif mode == "office":
                return cls._save_office_edit(file_path, file_type, new_content)
            elif mode == "opendoc":
                return cls._save_opendoc_edit(file_path, file_type, new_content)
            elif mode == "epub":
                return cls._save_epub_edit(file_path, new_content)
            elif mode == "xlsb":
                return cls._save_xlsb_edit(file_path, new_content)
            elif mode == "rtf":
                return cls._save_rtf_edit(file_path, new_content)
            elif mode == "mht":
                return cls._save_mht_edit(file_path, new_content)
            else:  # parsed / pdf
                return cls._save_parsed_text(file_path, new_content)
        except Exception as e:
            log.error(f"保存失败: {e}")
            # 回退到保存txt
            return cls._save_parsed_text(file_path, new_content)

    # ===== 纯文本文件处理 =====

    @staticmethod
    def _read_text_file(file_path: str) -> str:
        """读取文本文件，自动检测编码"""
        with open(file_path, "rb") as f:
            raw = f.read()
        for enc in ["utf-8", "utf-8-sig", "gbk", "gb2312", "gb18030", "big5", "latin-1"]:
            try:
                return raw.decode(enc, errors="strict")
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", errors="replace")

    @staticmethod
    def _save_text_file(file_path: str, content: str) -> dict:
        """保存文本文件"""
        try:
            backup_path = str(file_path) + ".backup"
            shutil.copy2(file_path, backup_path)

            # 检测原始编码
            with open(file_path, "rb") as f:
                raw = f.read()
            encoding = "utf-8"
            has_bom = raw.startswith(b'\xef\xbb\xbf')
            for enc in ["utf-8-sig", "utf-8", "gbk", "gb18030"]:
                try:
                    raw.decode(enc, errors="strict")
                    if enc == "utf-8-sig" and not has_bom:
                        encoding = "utf-8"
                    else:
                        encoding = enc
                    break
                except (UnicodeDecodeError, LookupError):
                    continue

            with open(file_path, "w", encoding=encoding, newline='') as f:
                f.write(content)

            os.remove(backup_path)
            return {"success": True, "saved_path": file_path, "message": f"已保存到原文件 ({encoding})"}
        except Exception as e:
            return {"success": False, "saved_path": "", "message": f"保存失败: {e}"}

    # ===== Office文件处理 =====

    @classmethod
    def _load_office_for_edit(cls, file_path: str, file_type: str) -> tuple:
        """加载Office文件供编辑"""
        ft = file_type.lower().lstrip(".")
        try:
            if ft in ("docx", "dotx", "dotm"):
                return cls._load_docx_text(file_path)
            elif ft in ("xlsx", "xlsm", "xltx", "xlam"):
                return cls._load_xlsx_text(file_path)
            elif ft in ("pptx", "potx", "potm"):
                return cls._load_pptx_text(file_path)
            else:
                raise ValueError(f"不支持的Office格式: {ft}")
        except Exception as e:
            log.warning(f"Office文件加载失败，回退到解析模式: {e}")
            from core.document_parser import DocumentParser
            parser = DocumentParser()
            return parser.parse(file_path, file_type), False

    # ---- DOCX ----

    @staticmethod
    def _load_docx_text(file_path: str) -> tuple:
        """纯Python加载DOCX文本"""
        with zipfile.ZipFile(file_path, 'r') as zf:
            doc_xml = zf.read('word/document.xml').decode('utf-8', errors='replace')

        root = ET.fromstring(doc_xml.encode('utf-8'))
        ns_w = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

        lines = []
        for para in root.iter(f'{ns_w}p'):
            texts = []
            for t in para.iter(f'{ns_w}t'):
                if t.text:
                    texts.append(t.text)
            if texts:
                line = ''.join(texts)
                pPr = para.find(f'{ns_w}pPr')
                if pPr is not None:
                    pStyle = pPr.find(f'{ns_w}pStyle')
                    if pStyle is not None:
                        val = pStyle.get(f'{ns_w}val')
                        if val and 'Heading' in val:
                            try:
                                level = int(re.search(r'\d+', val).group())
                            except (AttributeError, ValueError):
                                level = 1
                            lines.append(f"{'#' * min(level, 6)} {line}")
                            continue
                lines.append(line)

        for tbl in root.iter(f'{ns_w}tbl'):
            lines.append("[表格]")
            for tr in tbl.iter(f'{ns_w}tr'):
                cells = []
                for tc in tr.iter(f'{ns_w}tc'):
                    cell_texts = []
                    for t in tc.iter(f'{ns_w}t'):
                        if t.text:
                            cell_texts.append(t.text)
                    cells.append(''.join(cell_texts))
                lines.append(' | '.join(cells))

        return '\n\n'.join(lines), True

    @staticmethod
    def _save_docx_edit(file_path: str, new_content: str) -> dict:
        """纯Python保存DOCX编辑"""
        try:
            backup_path = str(file_path) + ".backup"
            shutil.copy2(file_path, backup_path)
            import tempfile
            tmpdir = tempfile.mkdtemp()

            with zipfile.ZipFile(file_path, 'r') as zf:
                zf.extractall(tmpdir)

            doc_path = os.path.join(tmpdir, 'word', 'document.xml')
            with open(doc_path, 'rb') as f:
                doc_xml = f.read()

            root = ET.fromstring(doc_xml)
            ns_w = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
            ET.register_namespace('w', ns_w)
            ET.register_namespace('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')
            ET.register_namespace('mc', 'http://schemas.openxmlformats.org/markup-compatibility/2006')

            body = root.find(f'{{{ns_w}}}body')
            if body is not None:
                sectPr = body.find(f'{{{ns_w}}}sectPr')
                for child in list(body):
                    if child.tag != f'{{{ns_w}}}sectPr':
                        body.remove(child)

                for line in new_content.split('\n'):
                    line = line.strip()
                    if not line:
                        continue

                    p = ET.SubElement(body, f'{{{ns_w}}}p')
                    pPr = ET.SubElement(p, f'{{{ns_w}}}pPr')
                    pStyle = ET.SubElement(pPr, f'{{{ns_w}}}pStyle')

                    if line.startswith('#'):
                        level = len(line) - len(line.lstrip('#'))
                        text = line.lstrip('#').strip()
                        pStyle.set(f'{{{ns_w}}}val', f'Heading{min(level, 9)}')
                    else:
                        pStyle.set(f'{{{ns_w}}}val', 'Normal')
                        text = line

                    r = ET.SubElement(p, f'{{{ns_w}}}r')
                    t = ET.SubElement(r, f'{{{ns_w}}}t')
                    t.text = text

            xml_str = _serialize_xml_with_ns(root)
            with open(doc_path, 'w', encoding='utf-8') as f:
                f.write(xml_str)

            os.remove(file_path)
            with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for dirpath, dirnames, filenames in os.walk(tmpdir):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        arcname = os.path.relpath(filepath, tmpdir)
                        zf.write(filepath, arcname)

            shutil.rmtree(tmpdir)
            os.remove(backup_path)
            return {"success": True, "saved_path": file_path, "message": "已保存到原DOCX文件"}
        except Exception as e:
            log.warning(f"DOCX保存失败，回退到txt: {e}")
            return FileEditor._save_parsed_text(file_path, new_content)

    # ---- XLSX ----

    @staticmethod
    def _load_xlsx_text(file_path: str) -> tuple:
        """纯Python加载XLSX文本（支持多sheet、共享字符串表）"""
        with zipfile.ZipFile(file_path, 'r') as zf:
            # 读取共享字符串表
            shared_strings = []
            ss_path = 'xl/sharedStrings.xml'
            if ss_path in zf.namelist():
                ss_xml = zf.read(ss_path).decode('utf-8', errors='replace')
                ss_root = ET.fromstring(ss_xml.encode('utf-8'))
                ns_s = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
                for si in ss_root.iter(f'{ns_s}si'):
                    texts = []
                    for t in si.iter(f'{ns_s}t'):
                        if t.text:
                            texts.append(t.text)
                    shared_strings.append(''.join(texts))

            # 读取workbook.xml获取sheet列表
            wb_xml = zf.read('xl/workbook.xml').decode('utf-8', errors='replace')
            wb_root = ET.fromstring(wb_xml.encode('utf-8'))

            sheets = []
            ns_s2 = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
            for sheet in wb_root.iter(f'{ns_s2}sheet'):
                name = sheet.get('name', 'Sheet')
                sheets.append(name)

            lines = []
            for i, sheet_name in enumerate(sheets):
                lines.append(f"[工作表: {sheet_name}]")
                sheet_path = f'xl/worksheets/sheet{i+1}.xml'
                if sheet_path not in zf.namelist():
                    lines.append("(空)")
                    continue
                sheet_xml = zf.read(sheet_path).decode('utf-8', errors='replace')
                sheet_root = ET.fromstring(sheet_xml.encode('utf-8'))
                ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'

                for row in sheet_root.iter(f'{ns}row'):
                    cells = []
                    row_cells = list(row.iter(f'{ns}c'))
                    for cell in row_cells:
                        ref = cell.get('r', '')
                        cell_type = cell.get('t', '')
                        v_elem = cell.find(f'{ns}v')
                        if v_elem is not None and v_elem.text:
                            if cell_type == 's':
                                idx = int(v_elem.text)
                                if idx < len(shared_strings):
                                    cells.append(shared_strings[idx])
                                else:
                                    cells.append(v_elem.text)
                            else:
                                cells.append(v_elem.text)
                        elif cell_type == 'inlineStr':
                            # inlineStr: <is><t>text</t></is>
                            is_elem = cell.find(f'{ns}is')
                            if is_elem is not None:
                                t_elem = is_elem.find(f'{ns}t')
                                if t_elem is not None and t_elem.text:
                                    cells.append(t_elem.text)
                                else:
                                    cells.append('')
                            else:
                                cells.append('')
                        elif cell_type == 'str':
                            # str: formula result
                            f_elem = cell.find(f'{ns}f')
                            v_elem2 = cell.find(f'{ns}v')
                            if v_elem2 is not None and v_elem2.text:
                                cells.append(v_elem2.text)
                            else:
                                cells.append('')
                        else:
                            cells.append('')
                    if any(cells):
                        lines.append(' | '.join(cells))

            return '\n\n'.join(lines), True

    @staticmethod
    def _col_to_letter(col_idx: int) -> str:
        """列索引转Excel列字母（支持超过26列）"""
        result = ""
        col_idx += 1  # 0-based to 1-based
        while col_idx > 0:
            col_idx -= 1
            result = chr(ord('A') + col_idx % 26) + result
            col_idx //= 26
        return result

    @staticmethod
    def _save_xlsx_edit(file_path: str, new_content: str) -> dict:
        """纯Python保存XLSX编辑（支持多sheet重建）"""
        try:
            backup_path = str(file_path) + ".backup"
            shutil.copy2(file_path, backup_path)
            import tempfile
            tmpdir = tempfile.mkdtemp()

            with zipfile.ZipFile(file_path, 'r') as zf:
                zf.extractall(tmpdir)

            # 解析工作表标记
            sheets_content = []
            current_sheet = None
            current_lines = []

            for line in new_content.split('\n'):
                stripped = line.strip()
                if stripped.startswith('[工作表:') and stripped.endswith(']'):
                    if current_sheet is not None:
                        sheets_content.append((current_sheet, current_lines))
                    current_sheet = stripped[5:-1]
                    current_lines = []
                elif stripped:
                    current_lines.append(stripped)

            if current_sheet is not None:
                sheets_content.append((current_sheet, current_lines))

            if not sheets_content:
                sheets_content = [("Sheet1", current_lines)]

            ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
            ET.register_namespace('', ns)

            # 清理旧sheet文件，重建
            sheets_dir = os.path.join(tmpdir, 'xl', 'worksheets')
            if os.path.exists(sheets_dir):
                for f_name in os.listdir(sheets_dir):
                    if f_name.startswith('sheet') and f_name.endswith('.xml'):
                        os.remove(os.path.join(sheets_dir, f_name))

            for sheet_idx, (sheet_name, sheet_lines) in enumerate(sheets_content):
                sheet_path = os.path.join(sheets_dir, f'sheet{sheet_idx + 1}.xml')
                row_num = 1
                rows_xml = []

                for line in sheet_lines:
                    cells = line.split(' | ')
                    row_cells_xml = []
                    for col_idx, cell_text in enumerate(cells):
                        col_letter = FileEditor._col_to_letter(col_idx)
                        cell_text = cell_text.strip()
                        # 判断是否是数字
                        is_number = False
                        try:
                            float(cell_text)
                            is_number = True
                        except ValueError:
                            pass

                        if is_number:
                            row_cells_xml.append(
                                f'<c r="{col_letter}{row_num}"><v>{cell_text}</v></c>'
                            )
                        else:
                            # 非数字使用inlineStr避免需要共享字符串表
                            row_cells_xml.append(
                                f'<c r="{col_letter}{row_num}" t="inlineStr">'
                                f'<is><t>{_xml_escape(cell_text)}</t></is></c>'
                            )

                    rows_xml.append(
                        f'<row r="{row_num}">{"".join(row_cells_xml)}</row>'
                    )
                    row_num += 1

                sheet_xml = (
                    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    f'<worksheet xmlns="{ns}">'
                    f'<sheetData>{"".join(rows_xml)}</sheetData>'
                    f'</worksheet>'
                )
                with open(sheet_path, 'w', encoding='utf-8') as f:
                    f.write(sheet_xml)

            # 更新workbook.xml的sheet引用
            wb_path = os.path.join(tmpdir, 'xl', 'workbook.xml')
            ns_r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
            ET.register_namespace('r', ns_r)

            sheets_xml_parts = []
            for i, (name, _) in enumerate(sheets_content):
                sheets_xml_parts.append(
                    f'<sheet name="{_xml_escape(name)}" sheetId="{i+1}" r:id="rId{i+1}"/>'
                )

            wb_xml = (
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<workbook xmlns="{ns}" xmlns:r="{ns_r}">'
                f'<sheets>{"".join(sheets_xml_parts)}</sheets>'
                f'</workbook>'
            )
            with open(wb_path, 'w', encoding='utf-8') as f:
                f.write(wb_xml)

            # 更新workbook.xml.rels
            wb_rels_path = os.path.join(tmpdir, 'xl', '_rels', 'workbook.xml.rels')
            rels_parts = []
            for i in range(len(sheets_content)):
                rels_parts.append(
                    f'<Relationship Id="rId{i+1}" '
                    f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                    f'Target="worksheets/sheet{i+1}.xml"/>'
                )

            rels_xml = (
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f'{"".join(rels_parts)}'
                f'</Relationships>'
            )
            os.makedirs(os.path.dirname(wb_rels_path), exist_ok=True)
            with open(wb_rels_path, 'w', encoding='utf-8') as f:
                f.write(rels_xml)

            # 重新压缩
            os.remove(file_path)
            with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for dirpath, dirnames, filenames in os.walk(tmpdir):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        arcname = os.path.relpath(filepath, tmpdir)
                        zf.write(filepath, arcname)

            shutil.rmtree(tmpdir)
            os.remove(backup_path)
            return {"success": True, "saved_path": file_path, "message": "已保存到原XLSX文件"}
        except Exception as e:
            log.warning(f"XLSX保存失败，回退到txt: {e}")
            return FileEditor._save_parsed_text(file_path, new_content)

    # ---- PPTX ----

    @staticmethod
    def _load_pptx_text(file_path: str) -> tuple:
        """纯Python加载PPTX文本"""
        with zipfile.ZipFile(file_path, 'r') as zf:
            pres_xml = zf.read('ppt/presentation.xml').decode('utf-8', errors='replace')
            pres_root = ET.fromstring(pres_xml.encode('utf-8'))

            slide_ids = []
            ns_p = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
            ns_r = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
            for sldId in pres_root.iter(f'{ns_p}sldId'):
                rid = sldId.get(f'{ns_r}id')
                if rid:
                    slide_ids.append(rid)

            lines = []
            for i in range(1, len(slide_ids) + 1):
                slide_path = f'ppt/slides/slide{i}.xml'
                if slide_path in zf.namelist():
                    lines.append(f"--- 幻灯片 {i} ---")
                    slide_xml = zf.read(slide_path).decode('utf-8', errors='replace')
                    slide_root = ET.fromstring(slide_xml.encode('utf-8'))
                    ns_a = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
                    for t in slide_root.iter(f'{ns_a}t'):
                        if t.text and t.text.strip():
                            lines.append(t.text.strip())

            return '\n\n'.join(lines), True

    @staticmethod
    def _save_pptx_edit(file_path: str, new_content: str) -> dict:
        """纯Python保存PPTX编辑（支持多slide重建）"""
        try:
            backup_path = str(file_path) + ".backup"
            shutil.copy2(file_path, backup_path)
            import tempfile
            tmpdir = tempfile.mkdtemp()

            with zipfile.ZipFile(file_path, 'r') as zf:
                zf.extractall(tmpdir)

            # 解析幻灯片内容
            slides_content = []
            current_slide = None
            current_lines = []

            for line in new_content.split('\n'):
                stripped = line.strip()
                if re.match(r'^---\s*幻灯片\s*\d+\s*---$', stripped):
                    if current_slide is not None:
                        slides_content.append((current_slide, current_lines))
                    current_slide = stripped
                    current_lines = []
                elif stripped:
                    current_lines.append(stripped)

            if current_slide is not None:
                slides_content.append((current_slide, current_lines))

            if not slides_content:
                slides_content = [("--- 幻灯片 1 ---", current_lines)]

            ns_p = 'http://schemas.openxmlformats.org/presentationml/2006/main'
            ns_a = 'http://schemas.openxmlformats.org/drawingml/2006/main'
            ET.register_namespace('p', ns_p)
            ET.register_namespace('a', ns_a)

            slides_dir = os.path.join(tmpdir, 'ppt', 'slides')
            if os.path.exists(slides_dir):
                for f_name in os.listdir(slides_dir):
                    if f_name.startswith('slide') and f_name.endswith('.xml'):
                        os.remove(os.path.join(slides_dir, f_name))

            for slide_idx, (_, slide_lines) in enumerate(slides_content):
                slide_path = os.path.join(slides_dir, f'slide{slide_idx + 1}.xml')
                shapes_xml = []

                for line in slide_lines:
                    shapes_xml.append(
                        f'<p:sp>'
                        f'<p:nvSpPr><p:cNvPr id="{slide_idx * 100 + len(shapes_xml) + 2}" name="TextBox {len(shapes_xml) + 1}"/>'
                        f'<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
                        f'<p:spPr><a:xfrm><a:off x="457200" y="{274638 + len(shapes_xml) * 457200}"/>'
                        f'<a:ext cx="8229600" cy="457200"/><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
                        f'<a:noFill/><a:ln><a:noFill/></a:ln></a:xfrm></p:spPr>'
                        f'<p:txBody><a:bodyPr/><a:lstStyle/>'
                        f'<a:p><a:r><a:rPr lang="zh-CN" dirty="0"/><a:t>{_xml_escape(line)}</a:t></a:r></a:p>'
                        f'</p:txBody></p:sp>'
                    )

                slide_xml = (
                    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    f'<p:sld xmlns:p="{ns_p}" xmlns:a="{ns_a}" '
                    f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                    f'<p:cSld><p:spTree>'
                    f'<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
                    f'<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
                    f'<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
                    f'{"".join(shapes_xml)}'
                    f'</p:spTree></p:cSld></p:sld>'
                )
                with open(slide_path, 'w', encoding='utf-8') as f:
                    f.write(slide_xml)

            # 更新presentation.xml
            pres_path = os.path.join(tmpdir, 'ppt', 'presentation.xml')
            ns_r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
            sld_ids = []
            for i in range(len(slides_content)):
                sld_ids.append(
                    f'<p:sldId id="{256 + i}" r:id="rId{i + 1}"/>'
                )

            pres_xml = (
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<p:presentation xmlns:p="{ns_p}" xmlns:a="{ns_a}" xmlns:r="{ns_r}">'
                f'<p:sldIdLst>{"".join(sld_ids)}</p:sldIdLst>'
                f'</p:presentation>'
            )
            with open(pres_path, 'w', encoding='utf-8') as f:
                f.write(pres_xml)

            # 更新presentation.xml.rels
            pres_rels_path = os.path.join(tmpdir, 'ppt', '_rels', 'presentation.xml.rels')
            rels_parts = []
            for i in range(len(slides_content)):
                rels_parts.append(
                    f'<Relationship Id="rId{i + 1}" '
                    f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
                    f'Target="slides/slide{i + 1}.xml"/>'
                )
            # 添加theme
            rels_parts.append(
                f'<Relationship Id="rId{len(slides_content) + 1}" '
                f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" '
                f'Target="theme/theme1.xml"/>'
            )

            rels_xml = (
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f'{"".join(rels_parts)}'
                f'</Relationships>'
            )
            os.makedirs(os.path.dirname(pres_rels_path), exist_ok=True)
            with open(pres_rels_path, 'w', encoding='utf-8') as f:
                f.write(rels_xml)

            os.remove(file_path)
            with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for dirpath, dirnames, filenames in os.walk(tmpdir):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        arcname = os.path.relpath(filepath, tmpdir)
                        zf.write(filepath, arcname)

            shutil.rmtree(tmpdir)
            os.remove(backup_path)
            return {"success": True, "saved_path": file_path, "message": "已保存到原PPTX文件"}
        except Exception as e:
            log.warning(f"PPTX保存失败，回退到txt: {e}")
            return FileEditor._save_parsed_text(file_path, new_content)

    @classmethod
    def _save_office_edit(cls, file_path: str, file_type: str, new_content: str) -> dict:
        """保存Office文件编辑"""
        ft = file_type.lower().lstrip(".")
        if ft in ("docx", "dotx", "dotm"):
            return cls._save_docx_edit(file_path, new_content)
        elif ft in ("xlsx", "xlsm", "xltx", "xlam"):
            return cls._save_xlsx_edit(file_path, new_content)
        elif ft in ("pptx", "potx", "potm"):
            return cls._save_pptx_edit(file_path, new_content)
        else:
            return cls._save_parsed_text(file_path, new_content)

    # ===== OpenDocument处理 (ODT/ODS/ODP) =====

    @classmethod
    def _load_opendoc_for_edit(cls, file_path: str, file_type: str) -> tuple:
        """加载OpenDocument文件供编辑"""
        try:
            ft = file_type.lower().lstrip(".")
            with zipfile.ZipFile(file_path, 'r') as zf:
                if ft == "odt":
                    xml_path = 'content.xml'
                elif ft == "ods":
                    xml_path = 'content.xml'
                elif ft == "odp":
                    xml_path = 'content.xml'
                else:
                    xml_path = 'content.xml'

                if xml_path not in zf.namelist():
                    return "文件内容为空", False

                content_xml = zf.read(xml_path).decode('utf-8', errors='replace')

            root = ET.fromstring(content_xml.encode('utf-8'))
            ns_text = '{http://docbook.org/ns/docbook}'
            ns_office = '{urn:oasis:names:tc:opendocument:xmlns:office:1.0}'
            ns_text_od = '{urn:oasis:names:tc:opendocument:xmlns:text:1.0}'
            ns_table = '{urn:oasis:names:tc:opendocument:xmlns:table:1.0}'

            lines = []

            # 提取段落
            for p in root.iter(f'{ns_text_od}p'):
                texts = []
                for span in p.iter():
                    if span.text:
                        texts.append(span.text)
                line = ''.join(texts).strip()
                if line:
                    lines.append(line)

            # 提取表格
            for table in root.iter(f'{ns_table}table'):
                lines.append("[表格]")
                for row in root.iter(f'{ns_table}table-row'):
                    cells = []
                    for cell in root.iter(f'{ns_table}table-cell'):
                        cell_texts = []
                        for p in cell.iter(f'{ns_text_od}p'):
                            texts = []
                            for span in p.iter():
                                if span.text:
                                    texts.append(span.text)
                            cell_texts.append(''.join(texts).strip())
                        cells.append(' '.join(cell_texts).strip())
                    if any(cells):
                        lines.append(' | '.join(cells))

            if not lines:
                return "文件内容为空", False

            return '\n\n'.join(lines), True
        except Exception as e:
            log.warning(f"OpenDocument加载失败: {e}")
            return cls._load_binary_for_edit(file_path, file_type), False

    @classmethod
    def _save_opendoc_edit(cls, file_path: str, file_type: str, new_content: str) -> dict:
        """保存OpenDocument编辑"""
        try:
            backup_path = str(file_path) + ".backup"
            shutil.copy2(file_path, backup_path)
            import tempfile
            tmpdir = tempfile.mkdtemp()

            with zipfile.ZipFile(file_path, 'r') as zf:
                zf.extractall(tmpdir)

            content_path = os.path.join(tmpdir, 'content.xml')
            if os.path.exists(content_path):
                with open(content_path, 'rb') as f:
                    content_xml = f.read()

                root = ET.fromstring(content_xml)
                ns_body = '{urn:oasis:names:tc:opendocument:xmlns:office:1.0}'
                ns_text = '{urn:oasis:names:tc:opendocument:xmlns:text:1.0}'

                body = root.find(f'{ns_body}body')
                if body is not None:
                    # 清除body内容
                    for child in list(body):
                        body.remove(child)

                    text_elem = ET.SubElement(body, f'{ns_body}text')
                    for line in new_content.split('\n'):
                        line = line.strip()
                        if not line or line == '[表格]':
                            continue
                        p = ET.SubElement(text_elem, f'{ns_text}p')
                        p.text = line

                xml_str = _serialize_xml_with_ns(root)
                with open(content_path, 'w', encoding='utf-8') as f:
                    f.write(xml_str)

            os.remove(file_path)
            with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for dirpath, dirnames, filenames in os.walk(tmpdir):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        arcname = os.path.relpath(filepath, tmpdir)
                        zf.write(filepath, arcname)

            shutil.rmtree(tmpdir)
            os.remove(backup_path)
            return {"success": True, "saved_path": file_path, "message": f"已保存到原{file_type.upper()}文件"}
        except Exception as e:
            log.warning(f"OpenDocument保存失败: {e}")
            return cls._save_parsed_text(file_path, new_content)

    # ===== EPUB处理 =====

    @staticmethod
    def _load_epub_for_edit(file_path: str) -> tuple:
        """纯Python加载EPUB文本"""
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                # 读取内容清单
                lines = []
                content_opf = None

                # 查找content.opf
                for name in zf.namelist():
                    if name.endswith('content.opf'):
                        content_opf = name
                        break

                if content_opf:
                    opf_xml = zf.read(content_opf).decode('utf-8', errors='replace')
                    opf_root = ET.fromstring(opf_xml.encode('utf-8'))
                    ns_opf = '{http://www.idpf.org/2007/opf}'
                    ns_dc = '{http://purl.org/dc/elements/1.1}'

                    # 获取章节文件列表
                    manifest = opf_root.find(f'{ns_opf}manifest')
                    spine = opf_root.find(f'{ns_opf}spine')
                    if manifest is not None and spine is not None:
                        spine_items = []
                        for itemref in spine.iter(f'{ns_opf}itemref'):
                            idref = itemref.get('idref')
                            if idref:
                                spine_items.append(idref)

                        href_map = {}
                        for item in manifest.iter(f'{ns_opf}item'):
                            item_id = item.get('id')
                            href = item.get('href')
                            if item_id and href:
                                href_map[item_id] = href

                        base_dir = os.path.dirname(content_opf)
                        for idref in spine_items:
                            if idref in href_map:
                                chapter_path = os.path.join(base_dir, href_map[idref]).replace('\\', '/')
                                if chapter_path in zf.namelist():
                                    lines.append(f"=== 章节: {idref} ===")
                                    chapter_xml = zf.read(chapter_path).decode('utf-8', errors='replace')
                                    ch_root = ET.fromstring(chapter_xml.encode('utf-8'))
                                    ns_xhtml = '{http://www.w3.org/1999/xhtml}'
                                    for p in ch_root.iter(f'{ns_xhtml}p'):
                                        text = _get_element_text(p).strip()
                                        if text:
                                            lines.append(text)
                                    for h in ch_root.iter():
                                        if h.tag and h.tag.endswith('h1') or h.tag.endswith('h2') or h.tag.endswith('h3'):
                                            text = _get_element_text(h).strip()
                                            if text:
                                                lines.append(f"# {text}")

                if not lines:
                    # 回退：直接扫描所有HTML文件
                    for name in sorted(zf.namelist()):
                        if name.endswith(('.html', '.htm', '.xhtml')):
                            try:
                                chapter_xml = zf.read(name).decode('utf-8', errors='replace')
                                for tag in re.findall(r'<p[^>]*>(.*?)</p>', chapter_xml, re.DOTALL):
                                    text = re.sub(r'<[^>]+>', '', tag).strip()
                                    if text:
                                        lines.append(text)
                            except Exception:
                                continue

                if not lines:
                    return "EPUB内容为空", False

                return '\n\n'.join(lines), True
        except Exception as e:
            log.warning(f"EPUB加载失败: {e}")
            return "EPUB加载失败", False

    @staticmethod
    def _save_epub_edit(file_path: str, new_content: str) -> dict:
        """保存EPUB编辑（重建所有章节）"""
        try:
            backup_path = str(file_path) + ".backup"
            shutil.copy2(file_path, backup_path)
            import tempfile
            tmpdir = tempfile.mkdtemp()

            with zipfile.ZipFile(file_path, 'r') as zf:
                zf.extractall(tmpdir)

            # 查找已有章节文件
            chapter_files = []
            for root_dir, dirs, files in os.walk(tmpdir):
                for fname in files:
                    if fname.endswith(('.html', '.xhtml', '.htm')):
                        full = os.path.join(root_dir, fname)
                        rel = os.path.relpath(full, tmpdir).replace('\\', '/')
                        chapter_files.append((rel, full))

            if chapter_files:
                # 将内容分配到各章节
                all_lines = [l.strip() for l in new_content.split('\n') if l.strip()]
                lines_per_chapter = max(1, len(all_lines) // len(chapter_files))

                for idx, (rel, full_path) in enumerate(chapter_files):
                    start = idx * lines_per_chapter
                    end = start + lines_per_chapter if idx < len(chapter_files) - 1 else len(all_lines)
                    chapter_lines = all_lines[start:end]

                    paragraphs = []
                    for line in chapter_lines:
                        if line.startswith('# '):
                            paragraphs.append(f'<h2>{_xml_escape(line[2:])}</h2>')
                        elif line.startswith('## '):
                            paragraphs.append(f'<h3>{_xml_escape(line[3:])}</h3>')
                        else:
                            paragraphs.append(f'<p>{_xml_escape(line)}</p>')

                    # 读取原始文件获取基本结构
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            original = f.read()
                        # 替换body内容
                        body_match = re.search(r'(<body[^>]*>)(.*?)(</body>)', original, re.DOTALL)
                        if body_match:
                            new_body = f'{body_match.group(1)}{"".join(paragraphs)}{body_match.group(3)}'
                            new_html = original[:body_match.start()] + new_body + original[body_match.end():]
                        else:
                            new_html = (
                                f'<?xml version="1.0" encoding="UTF-8"?>'
                                f'<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
                                f'<body>{"".join(paragraphs)}</body></html>'
                            )
                    except Exception:
                        new_html = (
                            f'<?xml version="1.0" encoding="UTF-8"?>'
                            f'<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
                            f'<body>{"".join(paragraphs)}</body></html>'
                        )

                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write(new_html)

            os.remove(file_path)
            with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for dirpath, dirnames, filenames in os.walk(tmpdir):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        arcname = os.path.relpath(filepath, tmpdir)
                        zf.write(filepath, arcname)

            shutil.rmtree(tmpdir)
            os.remove(backup_path)
            return {"success": True, "saved_path": file_path, "message": "已保存到原EPUB文件"}
        except Exception as e:
            log.warning(f"EPUB保存失败: {e}")
            return FileEditor._save_parsed_text(file_path, new_content)

    # ===== XLSB处理 =====

    @staticmethod
    def _load_xlsb_for_edit(file_path: str) -> tuple:
        """纯Python加载XLSB文本"""
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                # XLSB也是ZIP格式
                lines = []
                # 查找workbook
                wb_path = 'xl/workbook.bin' if 'xl/workbook.bin' in zf.namelist() else None
                # 读取worksheets
                sheet_files = sorted([n for n in zf.namelist() if re.match(r'xl/worksheets/sheet\d+\.xml', n)])

                if not sheet_files:
                    sheet_files = sorted([n for n in zf.namelist() if n.startswith('xl/worksheets/')])

                for i, sf in enumerate(sheet_files):
                    lines.append(f"[工作表: Sheet{i+1}]")
                    sf_xml = zf.read(sf).decode('utf-8', errors='replace')
                    sf_root = ET.fromstring(sf_xml.encode('utf-8'))

                    # 尝试多种命名空间
                    ns_list = [
                        '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}',
                        '{http://purl.oclc.org/ooxml/spreadsheetml/main}',
                        '',
                    ]

                    for ns in ns_list:
                        found = False
                        for row in sf_root.iter(f'{ns}row'):
                            cells = []
                            for cell in row.iter(f'{ns}c'):
                                v = cell.find(f'{ns}v')
                                if v is not None and v.text:
                                    cells.append(v.text)
                                else:
                                    cells.append('')
                            if any(cells):
                                lines.append(' | '.join(cells))
                                found = True
                        if found:
                            break

                    if not lines[-1].startswith('[工作表'):
                        continue
                    lines.append("(空)")

                return '\n\n'.join(lines), True
        except Exception as e:
            log.warning(f"XLSB加载失败: {e}")
            return FileEditor._load_binary_for_edit(file_path, "xlsb"), False

    @staticmethod
    def _save_xlsb_edit(file_path: str, new_content: str) -> dict:
        """保存XLSB编辑"""
        try:
            backup_path = str(file_path) + ".backup"
            shutil.copy2(file_path, backup_path)
            import tempfile
            tmpdir = tempfile.mkdtemp()

            with zipfile.ZipFile(file_path, 'r') as zf:
                zf.extractall(tmpdir)

            sheets_dir = os.path.join(tmpdir, 'xl', 'worksheets')
            os.makedirs(sheets_dir, exist_ok=True)

            sheets_content = []
            current_sheet = None
            current_lines = []

            for line in new_content.split('\n'):
                stripped = line.strip()
                if stripped.startswith('[工作表:') and stripped.endswith(']'):
                    if current_sheet is not None:
                        sheets_content.append((current_sheet, current_lines))
                    current_sheet = stripped[5:-1]
                    current_lines = []
                elif stripped:
                    current_lines.append(stripped)

            if current_sheet is not None:
                sheets_content.append((current_sheet, current_lines))
            if not sheets_content:
                sheets_content = [("Sheet1", current_lines)]

            ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
            for sheet_idx, (_, sheet_lines) in enumerate(sheets_content):
                sheet_path = os.path.join(sheets_dir, f'sheet{sheet_idx + 1}.xml')
                row_num = 1
                rows_xml = []
                for line in sheet_lines:
                    cells = line.split(' | ')
                    row_cells = []
                    for col_idx, ct in enumerate(cells):
                        col_letter = FileEditor._col_to_letter(col_idx)
                        ct = ct.strip()
                        row_cells.append(f'<c r="{col_letter}{row_num}"><v>{ct}</v></c>')
                    rows_xml.append(f'<row r="{row_num}">{"".join(row_cells)}</row>')
                    row_num += 1

                sheet_xml = (
                    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    f'<worksheet xmlns="{ns}"><sheetData>{"".join(rows_xml)}</sheetData></worksheet>'
                )
                with open(sheet_path, 'w', encoding='utf-8') as f:
                    f.write(sheet_xml)

            os.remove(file_path)
            with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for dirpath, dirnames, filenames in os.walk(tmpdir):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        arcname = os.path.relpath(filepath, tmpdir)
                        zf.write(filepath, arcname)

            shutil.rmtree(tmpdir)
            os.remove(backup_path)
            return {"success": True, "saved_path": file_path, "message": "已保存到原XLSB文件"}
        except Exception as e:
            log.warning(f"XLSB保存失败: {e}")
            return FileEditor._save_parsed_text(file_path, new_content)

    # ===== RTF处理 =====

    @staticmethod
    def _load_rtf_for_edit(file_path: str) -> tuple:
        """纯Python加载RTF文本"""
        try:
            with open(file_path, 'rb') as f:
                data = f.read()

            # 快速检测是否是RTF文件
            if not data[:5].lower().startswith(b'{\\rtf'):
                return "文件不是有效的RTF格式", False

            text = data.decode('latin-1', errors='replace')

            # 提取纯文本：移除所有RTF控制词
            result = _extract_rtf_text(text)
            if not result.strip():
                return "RTF内容为空", False

            return result, True
        except Exception as e:
            log.warning(f"RTF加载失败: {e}")
            return FileEditor._load_binary_for_edit(file_path, "rtf"), False

    @staticmethod
    def _save_rtf_edit(file_path: str, new_content: str) -> dict:
        """保存RTF编辑（重建RTF文件）"""
        try:
            backup_path = str(file_path) + ".backup"
            shutil.copy2(file_path, backup_path)

            # 读取原始RTF获取编码和字体信息
            with open(file_path, 'rb') as f:
                original = f.read()

            # 检测RTF编码
            encoding = 'ansi'
            if b'\\ansicpg1252' in original:
                encoding = 'ansi'
            elif b'\\ansicpg936' in original:
                encoding = 'gbk'
            elif b'\\ansicpg65001' in original:
                encoding = 'utf-8'

            # 检测字体表
            font_table = ""
            ft_match = re.search(rb'\{\\fonttbl(.*?)\}', original, re.DOTALL)
            if ft_match:
                font_table = ft_match.group(0).decode('latin-1', errors='replace')

            # 重建RTF
            rtf_parts = []
            rtf_parts.append(r'{\rtf1' + (f'\ansi\ansicpg936' if encoding == 'gbk' else '\ansi'))
            if font_table:
                rtf_parts.append(font_table)

            for line in new_content.split('\n'):
                line = line.strip()
                if not line:
                    rtf_parts.append(r'\par ')
                    continue
                # 转义RTF特殊字符
                escaped = line.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
                rtf_parts.append(escaped + r'\par ')

            rtf_parts.append('}')

            rtf_content = '\n'.join(rtf_parts)
            if encoding == 'gbk':
                rtf_bytes = rtf_content.encode('gbk', errors='replace')
            else:
                rtf_bytes = rtf_content.encode('latin-1', errors='replace')

            with open(file_path, 'wb') as f:
                f.write(rtf_bytes)

            os.remove(backup_path)
            return {"success": True, "saved_path": file_path, "message": "已保存到原RTF文件"}
        except Exception as e:
            log.warning(f"RTF保存失败: {e}")
            return FileEditor._save_parsed_text(file_path, new_content)

    # ===== MHT/MHTML处理 =====

    @staticmethod
    def _load_mht_for_edit(file_path: str) -> tuple:
        """加载MHT/MHTML文件的HTML部分"""
        try:
            with open(file_path, 'rb') as f:
                data = f.read()

            text = data.decode('utf-8', errors='replace')

            # MHT是MIME格式，找到HTML部分
            boundary_match = re.search(r'boundary="([^"]+)"', text)
            if not boundary_match:
                boundary_match = re.search(r'boundary=([^\s;]+)', text)

            if boundary_match:
                boundary = boundary_match.group(1).strip('"')
                parts = text.split(f'--{boundary}')
                for part in parts:
                    # 在当前part中查找Content-Type: text/html
                    lower_part = part.lower()
                    if 'content-type: text/html' not in lower_part and 'content-type:text/html' not in lower_part:
                        continue
                    # 提取HTML内容（在MIME头部空行之后）
                    # 用 \n\n 或 \r\n\r\n 分割头部和body
                    body_match = re.search(r'(?:\r?\n){2}(.*)', part, re.DOTALL)
                    if body_match:
                        html_content = body_match.group(1).strip()
                        # 移除结束边界标记
                        html_content = re.sub(r'^--.*$', '', html_content, flags=re.MULTILINE).strip()
                        # 移除HTML标签提取文本
                        plain = re.sub(r'<[^>]+>', ' ', html_content)
                        plain = re.sub(r'&nbsp;', ' ', plain)
                        plain = re.sub(r'&amp;', '&', plain)
                        plain = re.sub(r'&lt;', '<', plain)
                        plain = re.sub(r'&gt;', '>', plain)
                        plain = re.sub(r'&quot;', '"', plain)
                        plain = re.sub(r'\s+', ' ', plain).strip()
                        if plain:
                            return plain, True
            else:
                # 尝试直接解析为HTML
                html_content = re.sub(r'<[^>]+>', ' ', text)
                html_content = re.sub(r'\s+', ' ', html_content).strip()
                if html_content:
                    return html_content, True

            return "MHT内容为空", False
        except Exception as e:
            log.warning(f"MHT加载失败: {e}")
            return FileEditor._load_binary_for_edit(file_path, "mht"), False

    @staticmethod
    def _save_mht_edit(file_path: str, new_content: str) -> dict:
        """保存MHT编辑"""
        try:
            backup_path = str(file_path) + ".backup"
            shutil.copy2(file_path, backup_path)

            with open(file_path, 'rb') as f:
                original = f.read()

            original_text = original.decode('utf-8', errors='replace')

            # 替换HTML body内容
            body_match = re.search(r'(<body[^>]*>)(.*?)(</body>)', original_text, re.DOTALL | re.IGNORECASE)
            if body_match:
                # 将纯文本转成HTML段落
                paragraphs = []
                for line in new_content.split('\n'):
                    line = line.strip()
                    if line:
                        paragraphs.append(f'<p>{_xml_escape(line)}</p>')

                new_body = f'{body_match.group(1)}{"".join(paragraphs)}{body_match.group(3)}'
                new_text = original_text[:body_match.start()] + new_body + original_text[body_match.end():]
            else:
                new_text = (
                    f'MIME-Version: 1.0\nContent-Type: text/html\n\n'
                    f'<html><body><p>{_xml_escape(new_content)}</p></body></html>'
                )

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_text)

            os.remove(backup_path)
            return {"success": True, "saved_path": file_path, "message": "已保存到原MHT文件"}
        except Exception as e:
            log.warning(f"MHT保存失败: {e}")
            return FileEditor._save_parsed_text(file_path, new_content)

    # ===== 通用二进制格式解析回退 =====

    @staticmethod
    def _load_binary_for_edit(file_path: str, file_type: str) -> str:
        """使用DocumentParser解析二进制文件"""
        try:
            from core.document_parser import DocumentParser
            parser = DocumentParser()
            return parser.parse(file_path, file_type)
        except Exception as e:
            log.warning(f"解析器加载失败: {e}")
            # 最后回退：尝试读取为文本
            try:
                with open(file_path, 'rb') as f:
                    raw = f.read()
                return raw.decode('utf-8', errors='replace')
            except Exception:
                return f"[无法读取文件内容: {e}]"

    # ===== 解析文本回退 =====

    @staticmethod
    def _save_parsed_text(file_path: str, new_content: str) -> dict:
        """保存解析后的文本为_edited.txt文件"""
        try:
            path = Path(file_path)
            txt_path = path.parent / f"{path.stem}_edited.txt"
            counter = 1
            while txt_path.exists():
                txt_path = path.parent / f"{path.stem}_edited_{counter}.txt"
                counter += 1

            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return {"success": True, "saved_path": str(txt_path), "message": f"已保存为文本文件: {txt_path.name}"}
        except Exception as e:
            return {"success": False, "saved_path": "", "message": f"保存失败: {e}"}


# ===== 辅助函数 =====

def _xml_escape(text: str) -> str:
    """XML转义"""
    if not text:
        return ""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))


def _get_element_text(element) -> str:
    """递归获取XML元素及其子元素的文本"""
    parts = []
    if element.text:
        parts.append(element.text)
    for child in element:
        parts.append(_get_element_text(child))
        if child.tail:
            parts.append(child.tail)
    return ''.join(parts)


def _extract_rtf_text(rtf_text: str) -> str:
    """从RTF文本中提取纯文本"""
    # 移除RTF头部信息（第一组大括号内的控制词）
    result = []
    i = 0
    n = len(rtf_text)
    in_group = 0
    skip_control = False

    while i < n:
        ch = rtf_text[i]

        if ch == '{':
            in_group += 1
            i += 1
            continue
        elif ch == '}':
            in_group -= 1
            i += 1
            continue
        elif ch == '\\':
            # RTF控制词
            i += 1
            if i >= n:
                break

            if rtf_text[i] == "'":
                # 十六进制字符
                if i + 2 < n:
                    hex_char = rtf_text[i + 1:i + 3]
                    try:
                        code = int(hex_char, 16)
                        result.append(chr(code))
                    except ValueError:
                        pass
                    i += 3
                continue
            elif rtf_text[i] == '\\':
                result.append('\\')
                i += 1
                continue
            elif rtf_text[i] == '{':
                result.append('{')
                i += 1
                continue
            elif rtf_text[i] == '}':
                result.append('}')
                i += 1
                continue
            elif rtf_text[i] == '~':
                result.append(' ')
                i += 1
                continue
            elif rtf_text[i] == '-':
                # 可选连字符
                i += 1
                continue
            elif rtf_text[i] == '*':
                # 跳过\*标记的组
                # 找到空格或结束
                while i < n and rtf_text[i] not in (' ', '\n', '\r'):
                    i += 1
                continue
            elif rtf_text[i] == 'n' and i + 2 < n and rtf_text[i + 1] == 's':
                # \ns - Unicode字符
                while i < n and rtf_text[i] not in (' ', '\n', '\r', '}'):
                    i += 1
                continue
            else:
                # 普通控制字，跳过直到空格或非字母数字
                while i < n and (rtf_text[i].isalpha() or rtf_text[i].isdigit()):
                    i += 1
                # 跳过数字参数
                while i < n and (rtf_text[i].isdigit() or rtf_text[i] == '-'):
                    i += 1
                # 跳过可能的空格
                if i < n and rtf_text[i] == ' ':
                    i += 1
                continue

        elif ch == '\n' or ch == '\r':
            # 换行转空格
            if result and result[-1] != ' ':
                result.append(' ')
            i += 1
            continue
        elif ch in ('\t', '\x0b', '\x0c'):
            result.append(' ')
            i += 1
            continue
        elif ord(ch) < 32 and ch not in ('\n', '\r', '\t'):
            i += 1
            continue
        else:
            result.append(ch)
            i += 1

    text = ''.join(result)
    # 清理多余空格
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


def _serialize_xml_with_ns(element) -> str:
    """序列化XML元素，保持命名空间前缀"""
    ns_map = {}
    for elem in element.iter():
        tag = elem.tag
        if tag.startswith('{'):
            ns = tag[1:tag.index('}')]
            if ns not in ns_map:
                ns_map[ns] = None
        for attr in elem.attrib:
            if attr.startswith('{'):
                ns = attr[1:attr.index('}')]
                if ns not in ns_map:
                    ns_map[ns] = None

    known_prefixes = {
        'http://schemas.openxmlformats.org/wordprocessingml/2006/main': 'w',
        'http://schemas.openxmlformats.org/spreadsheetml/2006/main': '',
        'http://schemas.openxmlformats.org/presentationml/2006/main': 'p',
        'http://schemas.openxmlformats.org/drawingml/2006/main': 'a',
        'http://schemas.openxmlformats.org/package/2006/relationships': 'r',
        'http://schemas.openxmlformats.org/officeDocument/2006/relationships': 'r',
        'http://schemas.openxmlformats.org/markup-compatibility/2006': 'mc',
        'http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas': 'wpc',
        'http://schemas.openxmlformats.org/package/2006/content-types': '',
        'urn:oasis:names:tc:opendocument:xmlns:office:1.0': 'office',
        'urn:oasis:names:tc:opendocument:xmlns:text:1.0': 'text',
        'urn:oasis:names:tc:opendocument:xmlns:table:1.0': 'table',
    }

    prefix_map = {}
    counter = [0]
    for ns in ns_map:
        if ns in known_prefixes:
            prefix_map[ns] = known_prefixes[ns]
        else:
            prefix_map[ns] = f'ns{counter[0]}'
            counter[0] += 1

    for ns, prefix in prefix_map.items():
        if prefix:
            ET.register_namespace(prefix, ns)

    xml_bytes = ET.tostring(element, encoding='unicode')
    if not xml_bytes.startswith('<?xml'):
        xml_bytes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + xml_bytes

    return xml_bytes
