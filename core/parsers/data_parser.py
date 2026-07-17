"""
数据文件解析器（纯Python实现）

支持格式：
- JSON: 提取所有字符串值
- XML: 提取标签文本内容
- YAML: 提取文本（保留结构注释）
- TOML: 提取键值对文本
- INI/CONF/CFG/PROPERTIES: 提取配置项
"""
import json
import re
import io
from pathlib import Path
from core.parsers.txt_parser import TxtParser


class DataParser:
    """数据/配置文件解析器"""

    def parse_json(self, file_path: str) -> str:
        """解析JSON文件，提取所有字符串值和键"""
        text = TxtParser.parse_txt(file_path)
        try:
            data = json.loads(text)
            lines = self._extract_json_values(data)
            return "\n".join(lines)
        except json.JSONDecodeError:
            # 如果不是标准JSON，作为文本返回
            return text

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

    def parse_xml(self, file_path: str) -> str:
        """解析XML文件，提取文本内容"""
        text = TxtParser.parse_txt(file_path)
        # 移除XML声明和DOCTYPE
        text = re.sub(r"<\?xml[^?]*\?>", "", text)
        text = re.sub(r"<!DOCTYPE[^>]*>", "", text, flags=re.DOTALL)
        text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", lambda m: m.group(1), text, flags=re.DOTALL)

        # 提取标签之间的文本
        results = []
        # 匹配 >text<
        for m in re.finditer(r">([^<]{2,})<", text):
            t = m.group(1).strip()
            if t:
                # 去除多余空白
                t = re.sub(r"\s+", " ", t)
                results.append(t)

        return "\n".join(results)

    def parse_yaml(self, file_path: str) -> str:
        """解析YAML文件，提取文本内容"""
        text = TxtParser.parse_txt(file_path)
        lines = text.split("\n")
        results = []

        for line in lines:
            stripped = line.strip()
            # 跳过注释和空行，但保留列表项和键值对
            if not stripped or stripped.startswith("#"):
                continue
            # 去除注释
            if " #" in stripped:
                stripped = stripped.split(" #", 1)[0].strip()
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

    def parse_toml(self, file_path: str) -> str:
        """解析TOML文件"""
        text = TxtParser.parse_txt(file_path)
        lines = text.split("\n")
        results = []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # 节标题 [section]
            if stripped.startswith("[") and stripped.endswith("]"):
                results.append(f"\n[节] {stripped[1:-1]}")
                continue
            # 键值对
            if "=" in stripped:
                parts = stripped.split("=", 1)
                key = parts[0].strip()
                val = parts[1].strip()
                # 去除注释
                if " #" in val:
                    val = val.split(" #", 1)[0].strip()
                val = val.strip("'\"")
                if val:
                    results.append(f"{key}: {val}")

        return "\n".join(results)

    def parse_ini(self, file_path: str) -> str:
        """解析INI/CONF/CFG文件"""
        text = TxtParser.parse_txt(file_path)
        lines = text.split("\n")
        results = []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith((";", "#")):
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                results.append(f"\n[节] {stripped[1:-1]}")
                continue
            if "=" in stripped or ":" in stripped:
                sep = "=" if "=" in stripped else ":"
                parts = stripped.split(sep, 1)
                key = parts[0].strip()
                val = parts[1].strip() if len(parts) > 1 else ""
                # 去除行尾注释
                for c in ";#":
                    if c in val:
                        val = val.split(c, 1)[0].strip()
                if val:
                    results.append(f"{key}: {val}")
                else:
                    results.append(key)

        return "\n".join(results)

    def parse_properties(self, file_path: str) -> str:
        """解析Java Properties文件"""
        return self.parse_ini(file_path)

    def parse_log(self, file_path: str) -> str:
        """解析LOG日志文件"""
        return TxtParser.parse_txt(file_path)
