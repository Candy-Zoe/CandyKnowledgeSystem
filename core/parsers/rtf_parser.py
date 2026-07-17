"""
RTF 解析器（纯Python实现，增强版）

RTF (Rich Text Format) 是微软的富文本格式。
基本结构：\\命令 参数 文本
文本通常在 { ... } 组中。

增强特性：
- 自动识别编码（\\ansicpg、\\deff、\\fonttbl中的代码页）
- 正确处理 \\'hh 十六进制转义（使用正确代码页解码）
- 正确处理 \\uN 后面的替代字符（通过 \\ucN 指定数量）
- 跳过更多内部组（\\fonttbl、\\colortbl、\\stylesheet、\\pict、\\object等）
- 处理 \\tab、\\par、\\line、\\row 等控制字
- \\* 精细化处理，只跳过已知目的关键词
"""
import re
import codecs
from pathlib import Path

from .text_utils import clean_text


class RtfParser:
    """RTF富文本解析器（增强版）"""

    # 常见RTF代码页映射
    CODEPAGE_MAP = {
        437: "cp437", 708: "cp708", 709: "cp709", 710: "cp710", 711: "cp711",
        720: "cp720", 819: "latin-1", 850: "cp850", 852: "cp852", 860: "cp860",
        862: "cp862", 863: "cp863", 864: "cp864", 865: "cp865", 866: "cp866",
        874: "cp874", 932: "cp932", 936: "gbk", 949: "cp949", 950: "cp950",
        1250: "cp1250", 1251: "cp1251", 1252: "cp1252", 1253: "cp1253",
        1254: "cp1254", 1255: "cp1255", 1256: "cp1256", 1257: "cp1257",
        1258: "cp1258", 1361: "johab",
    }

    # \\* 已知的目的关键词列表，遇到这些关键词时跳过整个组
    KNOWN_DEST_KEYWORDS = [
        "\\pn",        # 段落编号
        "\\pntext",    # 段落编号文本
        "\\pncxa",     # 自定义编号
        "\\bkmkstart", # 书签开始
        "\\bkmkend",   # 书签结束
        "\\bkmkpub",   # 书签发布
        "\\shpinst",   # 形状实例
        "\\shprslt",   # 形状结果
        "\\sp",        # 形状属性
        "\\sn",        # 形状属性名
        "\\sv",        # 形状属性值
        "\\shp",       # 形状定义
        "\\shpgrp",    # 形状组
        "\\shptxt",    # 形状文本
        "\\nonshppict",# 非形状图片
        "\\objclass",  # 对象类
        "\\objdata",   # 对象数据
        "\\result",    # 结果
        "\\xmlopen",   # XML开放标签
        "\\xmlclose",  # XML关闭标签
        "\\xmlattr",   # XML属性
    ]

    def parse(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        with open(file_path, "rb") as f:
            raw = f.read()

        # 检测RTF标记
        if not raw.startswith(b"{") and b"\\rtf" not in raw[:50]:
            return self._decode_as_plain_text(raw)

        try:
            # 先用latin-1解码（保证所有字节都能转为字符）
            text = raw.decode("latin-1", errors="replace")
        except Exception:
            return self._decode_as_plain_text(raw)

        extracted = self._extract_text_from_rtf(text, raw)
        # 通用文本清洗
        return clean_text(extracted)

    def _decode_as_plain_text(self, raw: bytes) -> str:
        """作为普通文本解码"""
        for enc in ["utf-8", "utf-8-sig", "gbk", "gb2312", "gb18030", "big5"]:
            try:
                return raw.decode(enc, errors="strict")
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", errors="replace")

    def _extract_text_from_rtf(self, rtf_text: str, raw_bytes: bytes = None) -> str:
        """从RTF文本中提取纯文本"""
        # 第一遍：探测编码
        codepage = self._detect_codepage(rtf_text)
        encoding = self.CODEPAGE_MAP.get(codepage, "cp1252")

        # 解析 \\ucN，获取Unicode替代字符数量（默认为1）
        unicode_alt_count = self._detect_uc_count(rtf_text)

        result = []
        i = 0
        length = len(rtf_text)
        # 跟踪组深度，用于跳过某些组的内容
        skip_depth = 0
        current_depth = 0
        # 是否处于 \\* 开头的组中，需要进一步判断目的关键词
        in_asterisk_group = False
        asterisk_group_depth = 0

        while i < length:
            c = rtf_text[i]

            if c == "{":
                current_depth += 1
                # 检查组是否是应该跳过的类型
                # 向前看几个字符判断组的类型
                lookahead = rtf_text[i+1:i+20]
                if self._should_skip_group(lookahead):
                    skip_depth = current_depth
                # 检查是否是 \\* 开头的组
                elif lookahead.startswith("\\*"):
                    in_asterisk_group = True
                    asterisk_group_depth = current_depth
                    # 向前看更远，判断 \\* 后面紧跟的目的关键词
                    keyword = self._detect_asterisk_keyword(rtf_text, i + 2)
                    if keyword is not None:
                        # 已知的目的关键词，跳过整个组
                        skip_depth = current_depth
                        in_asterisk_group = False
                i += 1
                continue

            elif c == "}":
                if skip_depth == current_depth:
                    skip_depth = 0
                # 如果离开 \\* 组，重置标记
                if in_asterisk_group and asterisk_group_depth == current_depth:
                    in_asterisk_group = False
                current_depth -= 1
                i += 1
                continue

            if skip_depth > 0 and current_depth >= skip_depth:
                i += 1
                continue

            if c == "\\":
                handled, new_i = self._handle_backslash(
                    rtf_text, i, length, result, encoding, unicode_alt_count
                )
                if handled:
                    i = new_i
                    continue

            elif c == "\r" or c == "\n":
                i += 1
                continue

            else:
                result.append(c)
                i += 1

        text = "".join(result)
        return self._cleanup_text(text)

    def _detect_uc_count(self, rtf_text: str) -> int:
        """探测 \\ucN 控制字，获取Unicode替代字符数量

        \\ucN 表示 \\uN 控制字后面跟 N 个字节的替代字符。
        默认值为1。
        """
        m = re.search(r"\\uc(\d+)", rtf_text)
        if m:
            try:
                val = int(m.group(1))
                if val >= 0:
                    return val
            except ValueError:
                pass
        return 1

    def _detect_asterisk_keyword(self, rtf_text: str, pos: int) -> str | None:
        """检测 \\* 后面紧跟的目的关键词

        从给定位置开始，读取控制字名称。
        如果该关键词在已知列表中，返回关键词名；否则返回 None。
        """
        i = pos
        length = len(rtf_text)
        # 跳过空白
        while i < length and rtf_text[i] == " ":
            i += 1
        # 读取控制字（反斜杠 + 字母）
        if i < length and rtf_text[i] == "\\":
            i += 1  # 跳过反斜杠
            cmd_start = i
            while i < length and rtf_text[i].isalpha():
                i += 1
            cmd = rtf_text[cmd_start:i]
            # 构造完整关键词（含反斜杠前缀）
            full_keyword = "\\" + cmd
            if full_keyword in self.KNOWN_DEST_KEYWORDS:
                return full_keyword
        return None

    def _detect_codepage(self, rtf_text: str) -> int:
        """探测RTF文件的代码页"""
        # 查找 \\ansicpgN
        m = re.search(r"\\ansicpg(\d+)", rtf_text)
        if m:
            return int(m.group(1))
        # 查找 \\deffN 对应的字体代码页
        m = re.search(r"\\deff(\d+)", rtf_text)
        if m:
            # 尝试从fonttbl中获取字体代码页
            fonttbl_match = re.search(r"\\f(\d+).*?\\fcharset(\d+)", rtf_text)
            if fonttbl_match:
                fcharset = int(fonttbl_match.group(2))
                # fcharset到代码页的映射（简化）
                charset_map = {
                    0: 1252, 1: 1252, 2: 1252, 77: 10000, 78: 10001, 79: 10003,
                    80: 10008, 81: 10002, 83: 10005, 84: 10004, 85: 10006,
                    86: 10081, 87: 10021, 88: 10029, 89: 10007, 128: 932,
                    129: 949, 130: 1361, 134: 936, 136: 950, 161: 1253,
                    162: 1254, 163: 1258, 177: 1255, 178: 1256, 186: 1257,
                    204: 1251, 222: 874, 238: 1250, 254: 437,
                }
                return charset_map.get(fcharset, 1252)
        return 1252  # 默认Windows-1252

    def _should_skip_group(self, lookahead: str) -> bool:
        """判断一个组是否应该被跳过"""
        skip_commands = [
            "\\fonttbl", "\\colortbl", "\\stylesheet", "\\listtable",
            "\\listoverridetable", "\\info", "\\pict", "\\object",
            "\\datastore", "\\pgptbl", "\\shttable",
        ]
        for cmd in skip_commands:
            if lookahead.startswith(cmd):
                return True
        return False

    def _handle_backslash(self, text: str, i: int, length: int,
                          result: list, encoding: str, uc_count: int):
        """处理反斜杠开头的控制字或转义序列"""
        if i + 1 >= length:
            return False, i

        next_c = text[i + 1]

        # 转义字符
        if next_c in "{}\\":
            result.append(next_c)
            return True, i + 2
        elif next_c == "~":
            result.append(" ")  # 非断空格
            return True, i + 2
        elif next_c == "-":
            result.append("-")  # 可选连字符
            return True, i + 2
        elif next_c == "*":
            # \\* 本身不产生输出，只做标记（由外层处理组的跳过逻辑）
            return True, i + 2
        elif next_c == "'":
            # \\'hh 十六进制转义 - 使用正确编码解码
            if i + 3 < length:
                try:
                    hex_val = text[i + 2:i + 4]
                    byte_val = int(hex_val, 16)
                    try:
                        decoded = bytes([byte_val]).decode(encoding, errors="replace")
                        result.append(decoded)
                    except (LookupError, UnicodeDecodeError):
                        result.append(chr(byte_val))
                except ValueError:
                    pass
                return True, i + 4

        # 读取控制字
        cmd_start = i + 1
        cmd_end = cmd_start
        while cmd_end < length and text[cmd_end].isalpha():
            cmd_end += 1
        cmd = text[cmd_start:cmd_end]

        # 读取可选数字参数
        num_start = cmd_end
        if num_start < length and text[num_start] == "-":
            num_start += 1
        num_end = num_start
        while num_end < length and text[num_end].isdigit():
            num_end += 1

        param = None
        if num_end > cmd_end:
            try:
                param = int(text[cmd_end:num_end])
            except ValueError:
                pass

        # 处理空格分隔符
        if num_end < length and text[num_end] == " ":
            num_end += 1

        # 处理控制字
        if cmd in ("par", "line", "row"):
            result.append("\n")
        elif cmd == "tab":
            result.append("\t")
        elif cmd == "u" and param is not None:
            try:
                if param < 0:
                    param += 65536
                result.append(chr(param))
            except ValueError:
                pass
            # \\uN 后面有 \\ucN（默认1）个替代字符字节，需要跳过
            alt_end = num_end
            skip_count = 0
            while skip_count < uc_count and alt_end < length:
                ch = text[alt_end]
                if ch in " \\{}\r\n":
                    break
                alt_end += 1
                skip_count += 1
            return True, alt_end
        elif cmd == "uc":
            # \\ucN 仅更新替代字符数量，由外层 uc_count 控制
            pass
        elif cmd in ("b", "i", "ul", "strike", "sub", "super", "nosupersub",
                     "v", "fs", "f", "cf", "cb", "highlight",
                     "pard", "s", "qc", "ql", "qr", "qj"):
            # 格式控制，忽略
            pass
        elif cmd in ("field", "fldinst", "fldrslt"):
            # 跳过字段
            pass
        elif cmd == "ansi":
            pass
        elif cmd == "ansicpg":
            pass
        elif cmd == "deff":
            pass
        elif cmd == "rtf":
            pass
        elif cmd == "fonttbl":
            pass
        elif cmd == "cell":
            result.append(" | ")

        return True, num_end

    def _cleanup_text(self, text: str) -> str:
        """清理提取的文本"""
        # 合并多个空行为一个
        lines = text.split("\n")
        cleaned = []
        prev_empty = False
        for line in lines:
            stripped = line.rstrip()
            is_empty = not stripped
            if is_empty and prev_empty:
                continue
            cleaned.append(stripped)
            prev_empty = is_empty

        text = "\n".join(cleaned).strip()

        # 去除空字符
        text = text.replace("\x00", "")

        # 只去除行首看起来像RTF控制字的残留（以反斜杠开头）
        # 之前的 r"^[a-z]+\d*\s*" 太激进，会误删正常文本行
        text = re.sub(r"^\\[a-z]+\d*\s*", "", text, flags=re.MULTILINE)

        return text
