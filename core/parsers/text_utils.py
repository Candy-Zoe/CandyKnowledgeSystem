"""
通用文本处理工具

提供所有解析器共用的文本清洗、编码检测等功能
"""
import re
import unicodedata


def clean_text(text: str) -> str:
    """通用文本清洗

    - 去除控制字符（保留换行、制表符）
    - 去除零宽字符
    - 合并连续空白
    - 去除首尾空白行
    """
    if not text:
        return text

    # 去除控制字符（保留 \n \r \t）
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    # 去除零宽字符
    zero_width = [
        '\u200b',  # 零宽空格
        '\u200c', '\u200d',  # 零宽非连接/连接
        '\ufeff',  # BOM
        '\u2028', '\u2029',  # 行/段落分隔符
        '\u00ad',  # 软连字符
        '\u202a', '\u202b', '\u202c', '\u202d', '\u202e',  # 双向控制
    ]
    for ch in zero_width:
        text = text.replace(ch, '')

    # 合并连续空白（保留换行）
    text = re.sub(r'[^\S\n]{3,}', ' ', text)

    # 合并连续空行（最多保留2个换行）
    text = re.sub(r'\n{4,}', '\n\n\n', text)

    # 去除行首行尾空白
    lines = [line.rstrip() for line in text.split('\n')]
    text = '\n'.join(lines)

    return text.strip()


def is_meaningful_text(text: str, min_ratio: float = 0.3) -> bool:
    """判断文本是否有意义（非乱码）

    Args:
        text: 待检测文本
        min_ratio: 中文字符+英文字母+数字 的最低占比
    """
    if not text or len(text.strip()) == 0:
        return False
    meaningful = sum(
        1 for ch in text
        if ('\u4e00' <= ch <= '\u9fff') or ch.isalpha() or ch.isdigit()
    )
    return (meaningful / len(text)) >= min_ratio


def truncate_text(text: str, max_chars: int = 50000) -> str:
    """截断过长文本"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n... (文本过长，已截断，共 {len(text)} 字符)"


def normalize_whitespace(text: str) -> str:
    """规范化空白字符"""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[ \t]+', ' ', text)
    return text


def remove_garbage_patterns(text: str) -> str:
    """去除常见乱码模式"""
    # 去除连续的替换字符 �
    text = re.sub(r'\ufffd{3,}', '', text)
    # 去除连续的非文本符号
    text = re.sub(r'[^\w\u4e00-\u9fff\s.,;:!?\'"()\-\+=/@#%&*，。；：！？、""''（）【】《》]+', '', text)
    return text


def format_table_text(headers: list, rows: list, max_rows: int = 500) -> str:
    """格式化表格数据为文本"""
    lines = []
    if headers:
        lines.append(" | ".join(str(h) if h else "" for h in headers))
    for i, row in enumerate(rows[:max_rows]):
        cells = [str(c) if c is not None else "" for c in row]
        lines.append(" | ".join(cells))
    if len(rows) > max_rows:
        lines.append(f"... 共 {len(rows)} 行数据（已截取前 {max_rows} 行）")
    return "\n".join(lines)
