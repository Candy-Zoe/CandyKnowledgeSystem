"""
数据文件解析器（纯Python实现）

支持格式：
- JSON: 提取所有字符串值
- XML: 使用 ElementTree 递归提取所有文本节点
- YAML: 先尝试 PyYAML，失败时正则回退
- TOML: 先尝试 tomllib/tomli，失败时正则回退
- INI/CONF/CFG: 提取配置项（正确处理引号内的注释字符）
- PROPERTIES: 正确处理 Java Properties 转义序列
"""
import json
import re
import io
import xml.etree.ElementTree as ET
from pathlib import Path
from core.parsers.txt_parser import TxtParser
from core.parsers.text_utils import clean_text


class DataParser:
    """数据/配置文件解析器"""

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def parse_json(self, file_path: str) -> str:
        """解析JSON文件，提取所有字符串值和键"""
        text = TxtParser.parse_txt(file_path)
        try:
            data = json.loads(text)
            lines = self._extract_json_values(data)
            return clean_text("\n".join(lines))
        except json.JSONDecodeError:
            # 如果不是标准JSON，作为文本返回
            return clean_text(text)

    def _extract_json_values(self, obj, prefix="") -> list:
        """递归提取JSON中的字符串值"""
        results = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                key_path = f"{prefix}.{k}" if prefix else k
                if isinstance(v, str):
                    results.append(f"{key_path}: {v}")
                elif isinstance(v, (dict, list)):
                    results.extend(self._extract_json_values(v, key_path))
                else:
                    results.append(f"{key_path}: {v}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                key_path = f"{prefix}[{i}]"
                if isinstance(item, str):
                    results.append(f"{key_path}: {item}")
                elif isinstance(item, (dict, list)):
                    results.extend(self._extract_json_values(item, key_path))
                else:
                    results.append(f"{key_path}: {item}")
        return results

    # ------------------------------------------------------------------
    # XML —— 使用 ElementTree 递归提取
    # ------------------------------------------------------------------

    def parse_xml(self, file_path: str) -> str:
        """解析XML文件，使用 ElementTree 递归提取所有文本节点"""
        text = TxtParser.parse_txt(file_path)
        try:
            root = ET.fromstring(text)
            results = []
            self._extract_xml_texts(root, results)
            return clean_text("\n".join(results))
        except ET.ParseError:
            # 如果 ET 解析失败，回退到正则提取
            return self._parse_xml_regex_fallback(text)

    def _extract_xml_texts(self, elem: ET.Element, results: list, depth: int = 0) -> None:
        """递归提取 XML 元素及其子元素中的文本

        策略：
        - 叶子节点（无子元素且有文本） → 直接提取
        - 混合节点（有子元素也有尾部文本） → 提取尾部文本
        - 纯分支节点 → 仅递归子元素
        """
        # 获取元素自身的文本（开标签与第一个子元素之间的文本）
        if elem.text and elem.text.strip():
            results.append(elem.text.strip())

        # 递归处理所有子元素
        for child in elem:
            self._extract_xml_texts(child, results, depth + 1)

        # 获取尾部文本（闭标签前的文本，常见于混合内容）
        if elem.tail and elem.tail.strip():
            results.append(elem.tail.strip())

    def _parse_xml_regex_fallback(self, text: str) -> str:
        """正则回退：从XML中提取文本（当ET解析失败时使用）"""
        # 移除XML声明和DOCTYPE
        text = re.sub(r"<\?xml[^?]*\?>", "", text)
        text = re.sub(r"<!DOCTYPE[^>]*>", "", text, flags=re.DOTALL)
        # 提取CDATA内容
        text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", lambda m: m.group(1), text, flags=re.DOTALL)

        results = []
        # 匹配标签之间的文本（至少2个字符）
        for m in re.finditer(r">([^<]{2,})<", text):
            t = m.group(1).strip()
            if t:
                t = re.sub(r"\s+", " ", t)
                results.append(t)

        return clean_text("\n".join(results))

    # ------------------------------------------------------------------
    # YAML —— 先尝试 PyYAML，正则回退
    # ------------------------------------------------------------------

    def parse_yaml(self, file_path: str) -> str:
        """解析YAML文件，先尝试 PyYAML，失败时正则回退"""
        text = TxtParser.parse_txt(file_path)

        # 优先尝试 PyYAML
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(text)
            if data is not None:
                lines = self._extract_yaml_values(data)
                return clean_text("\n".join(lines))
        except ImportError:
            pass  # PyYAML 未安装，使用正则回退
        except Exception:
            pass  # YAML解析失败，使用正则回退

        # 正则回退
        return clean_text(self._parse_yaml_regex(text))

    def _extract_yaml_values(self, obj, prefix="") -> list:
        """递归提取 YAML 中的值"""
        results = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                key_path = f"{prefix}.{k}" if prefix else str(k)
                if isinstance(v, str):
                    results.append(f"{key_path}: {v}")
                elif isinstance(v, (dict, list)):
                    results.extend(self._extract_yaml_values(v, key_path))
                elif v is not None:
                    results.append(f"{key_path}: {v}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, str):
                    results.append(item)
                elif isinstance(item, (dict, list)):
                    results.extend(self._extract_yaml_values(item, f"{prefix}[{i}]"))
                elif item is not None:
                    results.append(str(item))
        return results

    def _parse_yaml_regex(self, text: str) -> str:
        """正则方式解析YAML（回退方案）"""
        lines = text.split("\n")
        results = []

        for line in lines:
            stripped = line.strip()
            # 跳过注释和空行，但保留列表项和键值对
            if not stripped or stripped.startswith("#"):
                continue
            # 去除行内注释（注意：引号内的 # 不是注释）
            stripped = self._strip_inline_comment(stripped, "#")
            # 去除YAML标记
            if stripped.startswith("---") or stripped.startswith("..."):
                continue
            # 提取值部分（键: 值）
            if ":" in stripped:
                parts = stripped.split(":", 1)
                key = parts[0].strip()
                val = parts[1].strip() if len(parts) > 1 else ""
                # 去除引号
                val = val.strip("'\"")
                if val:
                    results.append(f"{key}: {val}")
                else:
                    results.append(key)
            else:
                # 列表项
                if stripped.startswith("-"):
                    val = stripped[1:].strip()
                    if val:
                        results.append(val)
                else:
                    results.append(stripped)

        return "\n".join(results)

    # ------------------------------------------------------------------
    # TOML —— 先尝试 tomllib/tomli，正则回退
    # ------------------------------------------------------------------

    def parse_toml(self, file_path: str) -> str:
        """解析TOML文件，先尝试 tomllib/tomli，失败时正则回退"""
        text = TxtParser.parse_txt(file_path)

        # 优先尝试标准库 tomllib（Python 3.11+）
        try:
            import tomllib  # type: ignore

            data = tomllib.loads(text)
            lines = self._extract_toml_values(data)
            return clean_text("\n".join(lines))
        except ImportError:
            pass
        except Exception:
            pass

        # 尝试第三方 tomli
        try:
            import tomli  # type: ignore

            data = tomli.loads(text)
            lines = self._extract_toml_values(data)
            return clean_text("\n".join(lines))
        except ImportError:
            pass
        except Exception:
            pass

        # 正则回退
        return clean_text(self._parse_toml_regex(text))

    def _extract_toml_values(self, obj, prefix="") -> list:
        """递归提取 TOML 中的值"""
        results = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                key_path = f"{prefix}.{k}" if prefix else str(k)
                if isinstance(v, str):
                    results.append(f"{key_path}: {v}")
                elif isinstance(v, (dict, list)):
                    results.extend(self._extract_toml_values(v, key_path))
                elif v is not None:
                    results.append(f"{key_path}: {v}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, str):
                    results.append(item)
                elif isinstance(item, (dict, list)):
                    results.extend(self._extract_toml_values(item, f"{prefix}[{i}]"))
                elif item is not None:
                    results.append(str(item))
        return results

    def _parse_toml_regex(self, text: str) -> str:
        """正则方式解析TOML（回退方案）"""
        lines = text.split("\n")
        results = []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # 节标题 [section] 或 [[array_section]]
            if stripped.startswith("[") and stripped.endswith("]"):
                section_name = stripped.strip("[]").strip()
                results.append(f"\n[节] {section_name}")
                continue
            # 键值对
            if "=" in stripped:
                parts = stripped.split("=", 1)
                key = parts[0].strip()
                val = parts[1].strip() if len(parts) > 1 else ""
                # 去除行内注释（注意引号内的 #）
                val = self._strip_inline_comment(val, "#")
                # 去除引号
                val = val.strip("'\"")
                if val:
                    results.append(f"{key}: {val}")

        return "\n".join(results)

    # ------------------------------------------------------------------
    # INI / CONF / CFG —— 正确处理引号内的注释字符
    # ------------------------------------------------------------------

    def parse_ini(self, file_path: str) -> str:
        """解析INI/CONF/CFG文件，正确处理引号内的分号和井号"""
        text = TxtParser.parse_txt(file_path)
        lines = text.split("\n")
        results = []

        for line in lines:
            stripped = line.strip()
            # 跳过纯注释行和空行
            if not stripped or stripped.startswith((";", "#")):
                continue
            # 节标题
            if stripped.startswith("[") and stripped.endswith("]"):
                results.append(f"\n[节] {stripped[1:-1]}")
                continue
            # 键值对
            if "=" in stripped or ":" in stripped:
                # 优先使用 = 分隔，其次使用 : 分隔
                sep = "=" if "=" in stripped else ":"
                parts = stripped.split(sep, 1)
                key = parts[0].strip()
                val = parts[1].strip() if len(parts) > 1 else ""

                # 去除行尾注释，但要考虑引号内的 ; 和 #
                val = self._strip_inline_comment_ini(val)

                if val:
                    results.append(f"{key}: {val}")
                else:
                    results.append(key)

        return clean_text("\n".join(results))

    # ------------------------------------------------------------------
    # PROPERTIES —— 正确处理 Java Properties 转义序列
    # ------------------------------------------------------------------

    def parse_properties(self, file_path: str) -> str:
        """解析Java Properties文件，正确处理转义序列和续行"""
        text = TxtParser.parse_txt(file_path)
        lines = text.split("\n")

        # 预处理：合并续行（行尾反斜杠表示续行）
        merged_lines = self._merge_properties_continuation(lines)

        results = []
        for line in merged_lines:
            # 跳过注释行和空行
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "!")):
                continue

            # 查找键值分隔符（= 或 :），忽略转义的 = 和 :
            key, val = self._split_properties_line(stripped)
            if key is not None:
                # 解码 Java 转义序列
                val = self._decode_properties_escapes(val)
                key = self._decode_properties_escapes(key)
                if val:
                    results.append(f"{key}: {val}")
                else:
                    results.append(key)

        return clean_text("\n".join(results))

    @staticmethod
    def _merge_properties_continuation(lines: list) -> list:
        """合并 Java Properties 文件中的续行

        当一行以奇数个反斜杠结尾时，表示续行（与下一行合并）
        """
        merged = []
        i = 0
        while i < len(lines):
            line = lines[i]
            # 检查行尾是否有续行标记（奇数个连续反斜杠）
            while _is_continuation_line(line) and i + 1 < len(lines):
                # 去掉行尾的反斜杠，拼上下一行
                line = line.rstrip()[:-1] + lines[i + 1]
                i += 1
            merged.append(line)
            i += 1
        return merged

    def _split_properties_line(self, line: str):
        """分割 Java Properties 行为键和值

        规则：
        - 分隔符是第一个未被转义的 = 或 :
        - 行首空白是键的前导空白，键的尾部空白被忽略
        - 分隔符后的空白是值的前导空白，值的尾部空白被保留
        """
        i = 0
        # 跳过键的前导空白
        while i < len(line) and line[i] in " \t":
            i += 1
        key_start = i

        # 查找分隔符
        while i < len(line):
            ch = line[i]
            if ch == "\\" and i + 1 < len(line):
                # 跳过转义字符
                i += 2
                continue
            if ch in "=:":
                break
            i += 1

        key = line[key_start:i].strip()

        if i < len(line) and line[i] in "=:":
            i += 1  # 跳过分隔符

        # 跳过分隔符后的空白
        while i < len(line) and line[i] in " \t":
            i += 1

        val = line[i:]
        return key, val

    def _decode_properties_escapes(self, s: str) -> str:
        """解码 Java Properties 文件中的转义序列

        支持：
        - \\n → 换行符
        - \\t → 制表符
        - \\r → 回车符
        - \\uXXXX → Unicode字符
        - \\\\ → 反斜杠
        - \\= → 等号
        - \\: → 冒号
        - \\空格 → 空格
        """
        result = []
        i = 0
        while i < len(s):
            if s[i] == "\\" and i + 1 < len(s):
                next_ch = s[i + 1]
                if next_ch == "n":
                    result.append("\n")
                    i += 2
                elif next_ch == "t":
                    result.append("\t")
                    i += 2
                elif next_ch == "r":
                    result.append("\r")
                    i += 2
                elif next_ch == "u" and i + 5 < len(s):
                    # Unicode 转义 \\uXXXX
                    hex_str = s[i + 2: i + 6]
                    try:
                        code_point = int(hex_str, 16)
                        result.append(chr(code_point))
                        i += 6
                    except (ValueError, OverflowError):
                        result.append(s[i])
                        i += 1
                elif next_ch == "\\":
                    result.append("\\")
                    i += 2
                elif next_ch == "=":
                    result.append("=")
                    i += 2
                elif next_ch == ":":
                    result.append(":")
                    i += 2
                elif next_ch == " ":
                    result.append(" ")
                    i += 2
                else:
                    # 未知转义序列，保留原样
                    result.append(s[i])
                    i += 1
            else:
                result.append(s[i])
                i += 1
        return "".join(result)

    # ------------------------------------------------------------------
    # LOG
    # ------------------------------------------------------------------

    def parse_log(self, file_path: str) -> str:
        """解析LOG日志文件"""
        return clean_text(TxtParser.parse_txt(file_path))

    # ------------------------------------------------------------------
    # 通用辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_inline_comment(value: str, comment_char: str) -> str:
        """去除行内注释，但保留引号内的注释字符

        Args:
            value: 值字符串
            comment_char: 注释字符（如 '#' 或 ';'）

        Returns:
            去除注释后的值
        """
        in_single_quote = False
        in_double_quote = False
        for i, ch in enumerate(value):
            if ch == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif ch == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif ch == comment_char and not in_single_quote and not in_double_quote:
                return value[:i].strip()
        return value

    @staticmethod
    def _strip_inline_comment_ini(value: str) -> str:
        """去除INI值中的行内注释，支持 ; 和 #，但保留引号内的字符

        同时处理连续出现的分号/井号（不重复截断）
        """
        # 先用统一的引号感知方法去除 ; 注释
        value = DataParser._strip_inline_comment(value, ";")
        # 再去除 # 注释
        value = DataParser._strip_inline_comment(value, "#")
        return value


def _is_continuation_line(line: str) -> bool:
    """判断是否为 Java Properties 续行

    规则：行尾有奇数个连续反斜杠表示续行
    （偶数个反斜杠表示转义的反斜杠本身，不是续行）
    """
    stripped = line.rstrip()
    if not stripped.endswith("\\"):
        return False
    # 计算行尾连续反斜杠的数量
    count = 0
    for ch in reversed(stripped):
        if ch == "\\":
            count += 1
        else:
            break
    return count % 2 == 1
