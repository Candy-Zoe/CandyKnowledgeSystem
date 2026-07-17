"""
压缩包解析器（纯Python实现）

支持格式：
- ZIP: 遍历提取所有文本文件内容
- 对RAR/7Z等提供提示（需要外部库）

解析策略：
1. 遍历压缩包内所有文件
2. 识别文本文件（按扩展名）
3. 提取文本内容并合并
"""
import zipfile
import os
import re
from pathlib import Path
from core.parsers.txt_parser import TxtParser


class ArchiveParser:
    """压缩包解析器"""

    # 视为文本文件的扩展名
    TEXT_EXTENSIONS = {
        "txt", "md", "html", "htm", "xml", "json", "yaml", "yml", "toml",
        "ini", "conf", "cfg", "properties", "log", "csv", "tsv",
        "py", "js", "java", "c", "cpp", "h", "hpp", "cs", "go", "rs",
        "rb", "php", "swift", "kt", "scala", "r", "m", "mm",
        "sql", "sh", "bat", "cmd", "ps1", "bash", "zsh",
        "css", "scss", "sass", "less", "vue", "jsx", "tsx",
        "dockerfile", "makefile", "cmake", "gradle",
        "tex", "bib", "rst", "adoc", "org",
    }

    def parse_zip(self, file_path: str) -> str:
        """解析ZIP压缩包，提取所有文本文件"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        if not zipfile.is_zipfile(file_path):
            raise ValueError(f"不是有效的ZIP文件: {file_path}")

        with zipfile.ZipFile(file_path, "r") as zf:
            all_texts = []
            for info in zf.infolist():
                if info.is_dir():
                    continue

                name = info.filename
                ext = os.path.splitext(name)[1].lower().lstrip(".")

                # 跳过明显的二进制文件和超大文件
                if ext in {"exe", "dll", "so", "dylib", "bin", "dat",
                           "jpg", "jpeg", "png", "gif", "bmp", "ico", "webp",
                           "mp3", "mp4", "avi", "mkv", "mov", "wmv",
                           "zip", "rar", "7z", "gz", "bz2", "xz",
                           "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx"}:
                    continue

                if info.file_size > 5 * 1024 * 1024:  # 跳过超过5MB的文件
                    continue

                # 检查是否为文本文件
                is_text = ext in self.TEXT_EXTENSIONS or not ext

                if not is_text:
                    # 尝试通过MIME或内容检测
                    try:
                        with zf.open(name) as f:
                            header = f.read(1024)
                        # 如果包含大量空字节，认为是二进制
                        if header.count(b"\x00") > 5:
                            continue
                        # 尝试解码为文本
                        try:
                            header.decode("utf-8", errors="strict")
                            is_text = True
                        except UnicodeDecodeError:
                            continue
                    except Exception:
                        continue

                if is_text:
                    try:
                        with zf.open(name) as f:
                            raw = f.read()
                        text = self._decode_text(raw)
                        if text.strip():
                            all_texts.append(f"[文件: {name}]\n{text[:10000]}")
                            if len(text) > 10000:
                                all_texts.append(f"... ({len(text)} 字符，已截断)")
                    except Exception:
                        pass

            return "\n\n".join(all_texts)

    def _decode_text(self, raw: bytes) -> str:
        """尝试多种编码解码"""
        for enc in ["utf-8", "utf-8-sig", "gbk", "gb2312", "gb18030", "latin-1"]:
            try:
                return raw.decode(enc, errors="strict")
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", errors="replace")
