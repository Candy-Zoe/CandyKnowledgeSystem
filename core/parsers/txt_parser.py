"""
纯文本/Markdown/HTML/CSV 解析器
仅使用Python标准库
"""
import re
import csv
import io
import html
from pathlib import Path


class TxtParser:
    """纯文本解析器"""

    @staticmethod
    def parse_txt(file_path: str) -> str:
        """解析TXT文件，自动检测编码"""
        with open(file_path, "rb") as f:
            raw = f.read()

        # 尝试常见编码
        for encoding in ["utf-8", "utf-8-sig", "gbk", "gb2312", "gb18030", "big5", "latin-1"]:
            try:
                return raw.decode(encoding, errors="strict")
            except (UnicodeDecodeError, LookupError):
                continue

        # 如果都失败，使用utf-8 with replace
        return raw.decode("utf-8", errors="replace")

    @staticmethod
    def parse_md(file_path: str) -> str:
        """解析Markdown文件"""
        return TxtParser.parse_txt(file_path)

    @staticmethod
    def parse_html(file_path: str) -> str:
        """解析HTML文件，提取纯文本"""
        text = TxtParser.parse_txt(file_path)
        return TxtParser.html_to_text(text)

    @staticmethod
    def html_to_text(html_content: str) -> str:
        """将HTML内容转为纯文本"""
        # 移除script和style标签及其内容
        html_content = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r"<style[^>]*>.*?</style>", "", html_content, flags=re.DOTALL | re.IGNORECASE)

        # 将块级标签替换为换行
        block_tags = ["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "pre", "blockquote"]
        for tag in block_tags:
            html_content = re.sub(rf"</{tag}\s*>", "\n", html_content, flags=re.IGNORECASE)
            html_content = re.sub(rf"<{tag}[^>]*>", "", html_content, flags=re.IGNORECASE)

        # br标签替换为换行
        html_content = re.sub(r"<br\s*/?>", "\n", html_content, flags=re.IGNORECASE)

        # 移除所有剩余标签
        html_content = re.sub(r"<[^>]+>", "", html_content)

        # 解码HTML实体
        html_content = html.unescape(html_content)

        # 清理多余空白
        lines = [line.strip() for line in html_content.split("\n")]
        html_content = "\n".join(line for line in lines if line)

        return html_content

    @staticmethod
    def parse_csv(file_path: str) -> str:
        """解析CSV文件"""
        with open(file_path, "rb") as f:
            raw = f.read()

        # 尝试编码
        text = None
        for encoding in ["utf-8", "utf-8-sig", "gbk", "gb2312", "gb18030"]:
            try:
                text = raw.decode(encoding, errors="strict")
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if text is None:
            text = raw.decode("utf-8", errors="replace")

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return ""

        lines = []
        for i, row in enumerate(rows[:1001]):
            line = " | ".join(cell.strip() for cell in row)
            if i == 0:
                lines.append("[表头] " + line)
            else:
                lines.append(line)

        if len(rows) > 1001:
            lines.append(f"... 共{len(rows)-1}行数据（已截取前1000行）")

        return "\n".join(lines)
