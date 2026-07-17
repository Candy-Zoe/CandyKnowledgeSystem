"""
MHTML/MHT 解析器（纯Python实现）

MHTML是MIME HTML格式，将网页及其资源打包为单个文件。
基于 multipart/related MIME 结构。

解析策略：
1. 直接用字节方式解析MIME结构（避免编码问题）
2. 找到 text/html 部分
3. 自动检测编码并转为纯文本
"""
import email
from email import policy
from pathlib import Path
from core.parsers.txt_parser import TxtParser
from core.parsers.text_utils import clean_text


class MhtParser:
    """MHTML归档解析器"""

    def parse(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        try:
            return self._parse_bytes(file_path)
        except Exception as e:
            # 回退：尝试直接作为文本读取
            try:
                with open(file_path, "rb") as f:
                    raw = f.read()
                # 检查 BOM
                if raw[:2] == b"\xff\xfe":
                    text = raw.decode("utf-16-le", errors="replace")
                elif raw[:2] == b"\xfe\xff":
                    text = raw.decode("utf-16-be", errors="replace")
                elif raw[:3] == b"\xef\xbb\xbf":
                    text = raw.decode("utf-8-sig", errors="replace")
                else:
                    text = raw.decode("utf-8", errors="replace")
                return clean_text(TxtParser.html_to_text(text))
            except Exception:
                return f"[MHTML解析失败: {e}]"

    def _parse_bytes(self, file_path: str) -> str:
        """用字节方式解析MIME结构"""
        with open(file_path, "rb") as f:
            raw = f.read()

        # 使用 email.message_from_bytes 直接处理原始字节
        # 这样各部分的编码由 email 库自动处理
        try:
            msg = email.message_from_bytes(raw, policy=policy.compat32)
        except Exception:
            # 回退到先解码为字符串
            msg = self._fallback_parse(raw)

        # 查找HTML部分
        html_parts = []
        text_parts = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type in ("text/html", "application/xhtml+xml"):
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            html = payload.decode(charset, errors="replace")
                            html_parts.append(html)
                    except Exception:
                        pass
                elif content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            plain = payload.decode(charset, errors="replace")
                            text_parts.append(plain)
                    except Exception:
                        pass
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                content = payload.decode(charset, errors="replace")
                html_parts.append(content)

        if not html_parts and not text_parts:
            return "[MHTML解析：未找到文本内容]"

        # 将内容转为纯文本
        all_texts = []
        for html in html_parts:
            text = TxtParser.html_to_text(html)
            if text.strip():
                all_texts.append(text)

        for plain in text_parts:
            if plain.strip():
                all_texts.append(plain)

        return clean_text("\n\n".join(all_texts))

    def _fallback_parse(self, raw: bytes):
        """回退解析：先尝试多种编码解码为字符串"""
        # 检查 BOM
        if raw[:2] == b"\xff\xfe":
            text = raw.decode("utf-16-le", errors="replace")
        elif raw[:2] == b"\xfe\xff":
            text = raw.decode("utf-16-be", errors="replace")
        elif raw[:3] == b"\xef\xbb\xbf":
            text = raw.decode("utf-8-sig", errors="replace")
        else:
            text = None
            for enc in ["utf-8", "gbk", "gb18030", "big5", "shift_jis", "euc_jp", "latin-1"]:
                try:
                    text = raw.decode(enc, errors="strict")
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            if text is None:
                text = raw.decode("utf-8", errors="replace")
        return email.message_from_string(text)
