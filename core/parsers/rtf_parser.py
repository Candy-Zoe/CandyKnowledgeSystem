"""
RTF 解析器（纯Python实现，增强版）

RTF (Rich Text Format) 是微软的富文本格式。
基本结构：\\命令 参数 文本
文本通常在 { ... } 组中。

增强特性：
- 自动识别编码（\\ansicpg、\\deff、\\fonttbl中的代码页）
- 正确处理 \\'hh 十六进制转义（使用正确代码页解码）
- 正确处理 \\uN 后面的替代字符
- 跳过更多内部组（\\fonttbl、\\colortbl、\\stylesheet、\\pict、\\object等）
- 处理 \\tab、\\par、\\line、\\row 等控制字
"""
import re
import codecs
from pathlib import Path


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

        return self._extract_text_from_rtf(text, raw)

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

        result = []
        i = 0
        length = len(rtf_text)
        # 跟踪组深度，用于跳过某些组的内容
        skip_depth = 0
        current_depth = 0

        while i < length:
            c = rtf_text[i]

            if c == "{":
                current_depth += 1
                # 检查组是否是应该跳过的类型
                # 向前看几个字符判断组的类型
                lookahead = rtf_text[i+1:i+20]
                if self._should_skip_group(lookahead):
                    skip_depth = current_depth
                i += 1
                continue

            elif c == "}":
                if skip_depth == current_depth:
                    skip_depth = 0
                current_depth -= 1
                i += 1
                continue

            if skip_depth > 0 and current_depth >= skip_depth:
                i += 1
                continue

            if c == "\\":
                handled, new_i = self._handle_backslash(rtf_text, i, length, result, encoding)
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

    def _detect_codepage(self, rtf_text: str) -> int:
        """探测RTF文件的代码页"""
        # 查找 \ansicpgN
        m = re.search(r"\\ansicpg(\d+)", rtf_text)
        if m:
            return int(m.group(1))
        # 查找 \deffN 对应的字体代码页
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
            "\\datastore", "\\pgptbl", "\\shttable", "\\*",
        ]
        for cmd in skip_commands:
            if lookahead.startswith(cmd):
                return True
        return False

    def _handle_backslash(self, text: str, i: int, length: int, result: list, encoding: str):
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
            # \* 引入的组跳过
            return True, i + 2
        elif next_c == "'":
            # \'hh 十六进制转义 - 使用正确编码解码
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
            # \uN 后面通常有替代字符，跳过指定数量的字节
            alt_skip = param if param < 0 else param
            # 实际上替代字符数通常是1个，但有些实现不同
            # 向前看直到下一个控制字或空格
            alt_end = num_end
            # 跳过1个替代字符（通常是编码字节）
            if alt_end < length and text[alt_end] not in " \\{}\r\n":
                alt_end += 1
            return True, alt_end
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

        # 修复一些常见残留
        text = text.replace("\x00", "")
        # 去除开头的垃圾控制字残留
        text = re.sub(r"^[a-z]+\d*\s*", "", text, flags=re.MULTILINE)

        return text