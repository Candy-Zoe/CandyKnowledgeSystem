"""
MHTML/MHT 解析器（纯Python实现）

MHTML是MIME HTML格式，将网页及其资源打包为单个文件。
基于 multipart/related MIME 结构。

解析策略：
1. 解析MIME头部
2. 找到文本/html部分
3. 提取HTML内容并转为纯文本
"""
import re
import email
from pathlib import Path
from core.parsers.txt_parser import TxtParser


class MhtParser:
    """MHTML归档解析器"""

    def parse(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        with open(file_path, "rb") as f:
            raw = f.read()

        # 尝试多种编码
        text = None
        for enc in ["utf-8", "gbk", "gb2312", "gb18030", "big5", "latin-1"]:
            try:
                text = raw.decode(enc, errors="strict")
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if text is None:
            text = raw.decode("utf-8", errors="replace")

        # 使用email模块解析MIME结构
        try:
            msg = email.message_from_string(text)
        except Exception:
            # 回退：直接作为HTML处理
            return TxtParser.html_to_text(text)

        # 查找HTML部分
        html_parts = []
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
                            html_parts.append(plain)
                    except Exception:
                        pass
        else:
            # 单部分
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                content = payload.decode(charset, errors="replace")
                html_parts.append(content)

        if not html_parts:
            return "[MHTML解析：未找到HTML内容]"

        # 将HTML转为文本
        all_texts = []
        for html in html_parts:
            text = TxtParser.html_to_text(html)
            if text.strip():
                all_texts.append(text)

        return "\n\n".join(all_texts)
