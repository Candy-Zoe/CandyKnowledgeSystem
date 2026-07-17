"""
OLE 文档解析器（纯Python实现，增强版）

用于解析旧版Office文档：
- .doc (Word 97-2003)
- .ppt (PowerPoint 97-2003)
- .xls (Excel 97-2003)

这些格式基于OLE2 Compound File Binary Format (CFBF)。
本模块实现简化的CFBF解析器，提取文本内容。

增强特性：
- 多层回退策略：结构化解析 -> 二进制扫描 -> 编码探测
- 支持UTF-16LE、GBK、GB2312、ASCII等多种编码自动识别
- 智能段落边界检测
- 所有解析结果经过 clean_text() 清洗
- CONTINUE记录处理（XLS共享字符串表续接）
- PPT记录头正确步进解析
"""
import struct
import re
import logging
from pathlib import Path

from core.parsers.text_utils import clean_text

logger = logging.getLogger(__name__)


class _OleFileReader:
    """简化的OLE文件读取器"""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.data = None
        self.sector_size = 512
        self.mini_sector_size = 64
        self.fat = []
        self.mini_fat = []
        self.directory = []
        self.root_entry = None
        self.mini_stream = b""

    def open(self):
        with open(self.file_path, "rb") as f:
            self.data = f.read()

        if len(self.data) < 512:
            raise ValueError("文件太小，不是有效的OLE文件")

        header = self.data[:512]
        sig = header[:8]
        if sig != b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1":
            raise ValueError("不是有效的OLE文件（签名不匹配）")

        ssz = struct.unpack("<H", header[30:32])[0]
        self.sector_size = 2 ** ssz
        sssz = struct.unpack("<H", header[32:34])[0]
        self.mini_sector_size = 2 ** sssz

        num_fat_sectors = struct.unpack("<I", header[44:48])[0]
        first_dir_sector_sid = struct.unpack("<I", header[48:52])[0]
        first_mini_fat_sector_sid = struct.unpack("<i", header[60:64])[0]
        num_mini_fat_sectors = struct.unpack("<I", header[64:68])[0]

        # 读取FAT链
        self.fat = []
        fat_sectors = list(struct.unpack("<109I", header[76:512]))
        fat_sectors = [s for s in fat_sectors if s != 0xFFFFFFFF]

        for sector_did in fat_sectors[:num_fat_sectors]:
            sector_offset = 512 + sector_did * self.sector_size
            sector_data = self.data[sector_offset:sector_offset + self.sector_size]
            entries = list(struct.unpack(f"<{self.sector_size // 4}I", sector_data))
            self.fat.extend(entries)

        # 读取目录
        self.directory = []
        current_sid = first_dir_sector_sid
        while current_sid != 0xFFFFFFFE:
            sector_offset = 512 + current_sid * self.sector_size
            sector_data = self.data[sector_offset:sector_offset + self.sector_size]
            for i in range(self.sector_size // 128):
                entry_data = sector_data[i * 128:(i + 1) * 128]
                entry = self._parse_dir_entry(entry_data)
                if entry["name"] != "" or entry["type"] != 0:
                    self.directory.append(entry)
            current_sid = self.fat[current_sid] if current_sid < len(self.fat) else 0xFFFFFFFE

        for entry in self.directory:
            if entry["type"] == 5:
                self.root_entry = entry
                break

        # 读取迷你流和迷你FAT
        if self.root_entry and first_mini_fat_sector_sid != -1:
            self.mini_stream = self._read_stream(self.root_entry)
            self.mini_fat = []
            current_sid = first_mini_fat_sector_sid
            while current_sid != 0xFFFFFFFE:
                sector_offset = 512 + current_sid * self.sector_size
                sector_data = self.data[sector_offset:sector_offset + self.sector_size]
                entries = list(struct.unpack(f"<{self.sector_size // 4}I", sector_data))
                self.mini_fat.extend(entries)
                current_sid = self.fat[current_sid] if current_sid < len(self.fat) else 0xFFFFFFFE

    def _parse_dir_entry(self, data: bytes) -> dict:
        name_bytes = data[:64]
        name_len = struct.unpack("<H", data[64:66])[0]
        name = name_bytes[:name_len - 2].decode("utf-16-le", errors="replace") if name_len > 2 else ""
        entry_type = data[66]
        start_sid = struct.unpack("<I", data[116:120])[0]
        size = struct.unpack("<Q", data[120:128])[0]
        return {"name": name, "type": entry_type, "start_sid": start_sid, "size": size}

    def _read_stream(self, entry: dict) -> bytes:
        if entry["size"] == 0:
            return b""
        if entry["size"] < 4096 and entry != self.root_entry:
            return self._read_mini_stream(entry)
        return self._read_normal_stream(entry)

    def _read_normal_stream(self, entry: dict) -> bytes:
        chunks = []
        current_sid = entry["start_sid"]
        remaining = entry["size"]
        while current_sid != 0xFFFFFFFE and remaining > 0:
            offset = 512 + current_sid * self.sector_size
            to_read = min(self.sector_size, remaining)
            chunks.append(self.data[offset:offset + to_read])
            remaining -= to_read
            current_sid = self.fat[current_sid] if current_sid < len(self.fat) else 0xFFFFFFFE
        return b"".join(chunks)

    def _read_mini_stream(self, entry: dict) -> bytes:
        chunks = []
        current_sid = entry["start_sid"]
        remaining = entry["size"]
        while current_sid != 0xFFFFFFFE and remaining > 0:
            offset = current_sid * self.mini_sector_size
            to_read = min(self.mini_sector_size, remaining)
            if offset + to_read <= len(self.mini_stream):
                chunks.append(self.mini_stream[offset:offset + to_read])
            remaining -= to_read
            current_sid = self.mini_fat[current_sid] if current_sid < len(self.mini_fat) else 0xFFFFFFFE
        return b"".join(chunks)

    def find_stream(self, name: str) -> bytes:
        for entry in self.directory:
            if entry["name"].lower() == name.lower() and entry["type"] == 2:
                return self._read_stream(entry)
        return b""

    def list_streams(self) -> list:
        return [e["name"] for e in self.directory if e["type"] == 2]


class _BinaryTextExtractor:
    """通用二进制文本提取器（用于OLE回退）"""

    @staticmethod
    def extract(data: bytes) -> str:
        """使用多种策略从二进制数据中提取可读文本"""
        all_texts = []

        # 策略1: UTF-16LE扫描（Word/PPT常用）
        utf16_texts = _BinaryTextExtractor._extract_utf16(data)
        if utf16_texts:
            all_texts.extend(utf16_texts)

        # 策略2: GBK/GB2312扫描
        gbk_texts = _BinaryTextExtractor._extract_gbk(data)
        if gbk_texts:
            all_texts.extend(gbk_texts)

        # 策略3: ASCII扫描（跳过控制字符）
        ascii_texts = _BinaryTextExtractor._extract_ascii(data)
        if ascii_texts:
            all_texts.extend(ascii_texts)

        # 去重合并
        return _BinaryTextExtractor._merge_and_deduplicate(all_texts)

    @staticmethod
    def _extract_utf16(data: bytes) -> list:
        """从二进制中扫描UTF-16LE文本块"""
        texts = []
        try:
            # 整个文件作为UTF-16LE解码
            text = data.decode("utf-16-le", errors="ignore")
            # 提取有意义的文本段落（中文字符+可打印ASCII）
            pattern = re.compile(
                r"[\u4e00-\u9fff\uff00-\uffef\u3000-\u303f\u2000-\u206f"
                r"a-zA-Z0-9_\-.,;:!?@#$%&*()\[\]{}<>/\\|+=~`'\"\s]{4,}"
            )
            for match in pattern.finditer(text):
                t = match.group().strip()
                if t and len(t) >= 4:
                    # 过滤掉纯ASCII垃圾（如URL片段、GUID等）
                    if _BinaryTextExtractor._is_meaningful(t):
                        texts.append(t)
        except Exception:
            pass
        return texts

    @staticmethod
    def _extract_gbk(data: bytes) -> list:
        """从二进制中扫描GBK文本块"""
        texts = []
        try:
            text = data.decode("gbk", errors="ignore")
            pattern = re.compile(
                r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef"
                r"a-zA-Z0-9_\-.,;:!?@#$%&*()\[\]{}<>/\\|+=~`'\"\s]{4,}"
            )
            for match in pattern.finditer(text):
                t = match.group().strip()
                if t and len(t) >= 4 and _BinaryTextExtractor._is_meaningful(t):
                    texts.append(t)
        except Exception:
            pass
        return texts

    @staticmethod
    def _extract_ascii(data: bytes) -> list:
        """扫描ASCII可打印文本"""
        texts = []
        i = 0
        min_len = 5
        while i < len(data):
            # 找连续可打印字符
            if data[i] >= 0x20 and data[i] < 0x7F:
                start = i
                while i < len(data) and data[i] >= 0x20 and data[i] < 0x7F:
                    i += 1
                length = i - start
                if length >= min_len:
                    chunk = data[start:i].decode("latin-1", errors="replace")
                    # 过滤（需要包含至少一个字母或数字）
                    if any(c.isalnum() for c in chunk):
                        texts.append(chunk)
            else:
                i += 1
        return texts

    @staticmethod
    def _is_meaningful(text: str) -> bool:
        """判断文本是否有意义（过滤GUID、URL、十六进制串等垃圾）"""
        # 如果超过80%是十六进制字符，可能是垃圾
        hex_chars = sum(1 for c in text if c in "0123456789abcdefABCDEF")
        if len(text) > 10 and hex_chars / len(text) > 0.8:
            return False
        # 过滤GUID格式
        if re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", text):
            return False
        # 过滤看起来像URL路径的长串
        if text.count("/") > len(text) // 4:
            return False
        return True

    @staticmethod
    def _merge_and_deduplicate(texts: list) -> str:
        """合并文本片段并去重"""
        if not texts:
            return ""

        seen = set()
        unique = []
        for t in texts:
            t = t.strip()
            if not t or t in seen:
                continue
            seen.add(t)
            unique.append(t)

        # 尝试将短片段按相邻关系合并
        if len(unique) < 200:
            return "\n".join(unique)

        # 太多片段时只保留较长的
        unique.sort(key=len, reverse=True)
        return "\n".join(unique[:500])


class OleDocParser:
    """旧版DOC文件解析器（增强版）"""

    def parse(self, file_path: str) -> str:
        try:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")

            try:
                ole = _OleFileReader(file_path)
                ole.open()

                word_stream = ole.find_stream("WordDocument")
                if not word_stream:
                    streams = ole.list_streams()
                    for s in streams:
                        if "word" in s.lower():
                            word_stream = ole.find_stream(s)
                            break

                if word_stream and len(word_stream) > 100:
                    result = self._extract_text_from_word_stream(word_stream)
                    if result and len(result) > 20:
                        return clean_text(result)

            except Exception as e:
                logger.warning(f"OLE结构化解析DOC失败: {e}")

            # 回退：通用二进制文本提取
            return clean_text(_BinaryTextExtractor.extract(self._read_file_bytes(file_path)))

        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"DOC解析异常: {e}")
            # 最终回退：二进制扫描
            return clean_text(_BinaryTextExtractor.extract(self._read_file_bytes(file_path)))

    def _read_file_bytes(self, file_path: str) -> bytes:
        with open(file_path, "rb") as f:
            return f.read()

    def _extract_text_from_word_stream(self, data: bytes) -> str:
        """从WordDocument流提取文本（增强版）"""
        if len(data) < 100:
            return ""

        # 检查FIB签名
        w_ident = struct.unpack("<H", data[0:2])[0]
        if w_ident != 0xA5EC:
            return ""

        texts = []

        # 尝试从常见文本区域提取UTF-16LE文本
        text_regions = [
            (0x200, min(len(data), 0x100000)),  # 前1MB
        ]

        for start, end in text_regions:
            region = data[start:end]
            if not region:
                continue
            try:
                decoded = region.decode("utf-16-le", errors="ignore")
                pattern = re.compile(
                    r"[\u4e00-\u9fff\uff00-\uffef\u3000-\u303f"
                    r"a-zA-Z0-9_\-.,;:!?@#$%&*()\[\]{}<>/\\|+=~`'\"\s]{3,}"
                )
                for m in pattern.finditer(decoded):
                    t = m.group().strip()
                    if _BinaryTextExtractor._is_meaningful(t):
                        texts.append(t)
            except Exception:
                pass

        # 尝试GBK解码整个流
        try:
            decoded = data.decode("gbk", errors="ignore")
            pattern = re.compile(
                r"[\u4e00-\u9fff\u3000-\u303f"
                r"a-zA-Z0-9_\-.,;:!?@#$%&*()\[\]{}<>/\\|+=~`'\"\s]{3,}"
            )
            for m in pattern.finditer(decoded):
                t = m.group().strip()
                if _BinaryTextExtractor._is_meaningful(t):
                    texts.append(t)
        except Exception:
            pass

        return _BinaryTextExtractor._merge_and_deduplicate(texts)


class OlePptParser:
    """旧版PPT文件解析器（增强版）"""

    def parse(self, file_path: str) -> str:
        try:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")

            try:
                ole = _OleFileReader(file_path)
                ole.open()

                ppt_stream = ole.find_stream("PowerPoint Document")
                if not ppt_stream:
                    streams = ole.list_streams()
                    for s in streams:
                        if "powerpoint" in s.lower():
                            ppt_stream = ole.find_stream(s)
                            break

                if ppt_stream and len(ppt_stream) > 100:
                    result = self._extract_text_from_ppt_stream(ppt_stream)
                    if result and len(result) > 20:
                        return clean_text(result)

            except Exception as e:
                logger.warning(f"OLE结构化解析PPT失败: {e}")

            return clean_text(_BinaryTextExtractor.extract(self._read_file_bytes(file_path)))

        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"PPT解析异常: {e}")
            return clean_text(_BinaryTextExtractor.extract(self._read_file_bytes(file_path)))

    def _read_file_bytes(self, file_path: str) -> bytes:
        with open(file_path, "rb") as f:
            return f.read()

    def _extract_text_from_ppt_stream(self, data: bytes) -> str:
        """从PPT流提取文本（增强版）

        正确解析PPT记录头：2字节类型 + 2字节版本 + 4字节长度 = 8字节头
        解析后按 pos += 8 + rec_len 步进到下一条记录
        """
        texts = []

        # PPT中的文本Atom类型：0x0FA0 (TextCharsAtom) 和 0x0FA1 (TextBytesAtom)
        pos = 0
        while pos < len(data) - 8:
            # 读取记录头：2字节类型 + 2字节版本 + 4字节长度
            rec_type = struct.unpack("<H", data[pos:pos+2])[0]
            # rec_version = struct.unpack("<H", data[pos+2:pos+4])[0]  # 版本号，暂不使用
            rec_len = struct.unpack("<I", data[pos+4:pos+8])[0]

            # 安全检查：记录长度不能超出数据范围
            if pos + 8 + rec_len > len(data):
                # 如果接近文件末尾，尝试只读取可用数据
                if pos + 8 <= len(data):
                    rec_len = min(rec_len, len(data) - pos - 8)
                else:
                    break

            # TextCharsAtom = 0x0FA0 (Unicode)
            if rec_type == 0x0FA0:
                try:
                    text = data[pos+8:pos+8+rec_len].decode("utf-16-le", errors="ignore")
                    if text.strip() and len(text.strip()) > 1:
                        texts.append(text.strip())
                except Exception:
                    pass
                pos += 8 + rec_len
                continue

            # TextBytesAtom = 0x0FA1 (ANSI)
            if rec_type == 0x0FA1:
                try:
                    text = data[pos+8:pos+8+rec_len].decode("latin-1", errors="ignore")
                    if text.strip() and len(text.strip()) > 1:
                        texts.append(text.strip())
                except Exception:
                    pass
                pos += 8 + rec_len
                continue

            # 正确步进：跳过当前记录（8字节头 + 记录体）
            pos += 8 + rec_len

        if texts:
            return _BinaryTextExtractor._merge_and_deduplicate(texts)

        # 回退：通用扫描
        return _BinaryTextExtractor.extract(data)


class OleXlsParser:
    """旧版XLS文件解析器（增强版）"""

    def parse(self, file_path: str) -> str:
        try:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")

            try:
                ole = _OleFileReader(file_path)
                ole.open()

                workbook = ole.find_stream("Workbook")
                if not workbook:
                    workbook = ole.find_stream("Book")

                if workbook and len(workbook) > 100:
                    result = self._extract_text_from_workbook(workbook)
                    if result and len(result) > 20:
                        return clean_text(result)

            except Exception as e:
                logger.warning(f"OLE结构化解析XLS失败: {e}")

            return clean_text(_BinaryTextExtractor.extract(self._read_file_bytes(file_path)))

        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"XLS解析异常: {e}")
            return clean_text(_BinaryTextExtractor.extract(self._read_file_bytes(file_path)))

    def _read_file_bytes(self, file_path: str) -> bytes:
        with open(file_path, "rb") as f:
            return f.read()

    def _extract_text_from_workbook(self, data: bytes) -> str:
        """从Excel BIFF结构提取文本（增强版）

        支持CONTINUE记录 (0x003C)：当SST记录过长时，BIFF格式会用
        CONTINUE记录续接数据，需将其追加到前一个SST记录的字符串数据中。
        """
        texts = []
        pos = 0
        # SST记录的未完成字符串数据，等待CONTINUE记录续接
        sst_remainder = b""

        while pos < len(data) - 4:
            rec_type = struct.unpack("<H", data[pos:pos+2])[0]
            rec_len = struct.unpack("<H", data[pos+2:pos+4])[0]

            if pos + 4 + rec_len > len(data):
                break

            rec_data = data[pos+4:pos+4+rec_len]

            # CONTINUE = 0x003C，将其数据追加到前一个SST的字符串数据中
            if rec_type == 0x003C:
                if sst_remainder:
                    # 将CONTINUE数据追加到SST残余数据后继续解析
                    combined = sst_remainder + rec_data
                    self._parse_sst_strings(combined, texts)
                    sst_remainder = b""
                pos += 4 + rec_len
                continue

            # 如果有残余SST数据但不是CONTINUE，先处理残余
            if sst_remainder:
                self._parse_sst_strings(sst_remainder, texts)
                sst_remainder = b""

            # LABEL = 0x0204 (BIFF3-BIFF8)
            if rec_type == 0x0204 and len(rec_data) > 6:
                str_len = struct.unpack("<H", rec_data[4:6])[0]
                if str_len > 0 and len(rec_data) > 6:
                    opts = rec_data[6]
                    if opts & 1:  # Unicode
                        if len(rec_data) >= 7 + str_len * 2:
                            s = rec_data[7:7+str_len*2].decode("utf-16-le", errors="ignore")
                            texts.append(s)
                    else:
                        if len(rec_data) >= 7 + str_len:
                            s = rec_data[7:7+str_len].decode("latin-1", errors="ignore")
                            texts.append(s)

            # STRING = 0x0207 (公式字符串结果)
            elif rec_type == 0x0207 and len(rec_data) > 2:
                str_len = struct.unpack("<H", rec_data[0:2])[0]
                if str_len > 0 and len(rec_data) > 2:
                    opts = rec_data[2] if len(rec_data) > 2 else 0
                    if opts & 1:
                        s = rec_data[3:3+str_len*2].decode("utf-16-le", errors="ignore")
                    else:
                        s = rec_data[3:3+str_len].decode("latin-1", errors="ignore")
                    texts.append(s)

            # SST = 0x00FC (共享字符串表，BIFF8)
            elif rec_type == 0x00FC and len(rec_data) > 8:
                try:
                    total_refs = struct.unpack("<I", rec_data[0:4])[0]
                    total_strs = struct.unpack("<I", rec_data[4:8])[0]
                    str_pos = 8
                    extracted_count = 0
                    for _ in range(min(total_strs, 5000)):  # 限制数量
                        if str_pos + 2 > len(rec_data):
                            break
                        str_len = struct.unpack("<H", rec_data[str_pos:str_pos+2])[0]
                        str_pos += 2
                        if str_pos >= len(rec_data):
                            break
                        opts = rec_data[str_pos]
                        str_pos += 1

                        # 计算字符串数据所需字节数
                        char_bytes = str_len * 2 if opts & 1 else str_len

                        if str_pos + char_bytes > len(rec_data):
                            # 数据不完整，保存残余数据等待CONTINUE记录
                            sst_remainder = rec_data[str_pos:]
                            break

                        if opts & 1:  # Unicode
                            s = rec_data[str_pos:str_pos+str_len*2].decode("utf-16-le", errors="ignore")
                            texts.append(s)
                        else:
                            s = rec_data[str_pos:str_pos+str_len].decode("latin-1", errors="ignore")
                            texts.append(s)
                        str_pos += char_bytes
                        extracted_count += 1

                        # 跳过可选的富文本/拼音信息
                        if opts & 4:  # Rich text
                            if str_pos + 4 <= len(rec_data):
                                rt_len = struct.unpack("<H", rec_data[str_pos:str_pos+2])[0]
                                str_pos += 4 + rt_len * 4
                        if opts & 8:  # Far East phonetic
                            if str_pos + 4 <= len(rec_data):
                                fe_len = struct.unpack("<I", rec_data[str_pos:str_pos+4])[0]
                                str_pos += 4 + fe_len
                except Exception:
                    pass

            pos += 4 + rec_len

        # 处理最后残余的SST数据
        if sst_remainder:
            self._parse_sst_strings(sst_remainder, texts)

        if texts:
            return _BinaryTextExtractor._merge_and_deduplicate(texts)

        return _BinaryTextExtractor.extract(data)

    @staticmethod
    def _parse_sst_strings(data: bytes, texts: list):
        """解析SST续接数据（来自CONTINUE记录或截断的SST数据）

        尝试从拼接的数据中提取剩余的字符串。
        """
        try:
            str_pos = 0
            while str_pos < len(data):
                if str_pos + 2 > len(data):
                    break
                str_len = struct.unpack("<H", data[str_pos:str_pos+2])[0]
                str_pos += 2
                if str_pos >= len(data):
                    break
                opts = data[str_pos]
                str_pos += 1

                char_bytes = str_len * 2 if opts & 1 else str_len

                if str_pos + char_bytes > len(data):
                    break

                if opts & 1:
                    s = data[str_pos:str_pos+char_bytes].decode("utf-16-le", errors="ignore")
                else:
                    s = data[str_pos:str_pos+char_bytes].decode("latin-1", errors="ignore")
                if s.strip():
                    texts.append(s)
                str_pos += char_bytes

                # 跳过可选的富文本/拼音信息
                if opts & 4:  # Rich text
                    if str_pos + 4 <= len(data):
                        rt_len = struct.unpack("<H", data[str_pos:str_pos+2])[0]
                        str_pos += 4 + rt_len * 4
                if opts & 8:  # Far East phonetic
                    if str_pos + 4 <= len(data):
                        fe_len = struct.unpack("<I", data[str_pos:str_pos+4])[0]
                        str_pos += 4 + fe_len
        except Exception:
            pass
