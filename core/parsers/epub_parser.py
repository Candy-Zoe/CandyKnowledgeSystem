"""
EPUB 解析器（纯Python实现）

EPUB本质是一个ZIP包，内部包含：
- mimetype: 声明类型
- META-INF/container.xml: 容器定义，指向OPF文件
- *.opf: 包文件，列出所有内容文档
- *.xhtml/html/htm: 内容文件
- *.ncx: 目录文件（旧版）

解析策略：
1. 读取container.xml找到OPF路径
2. 读取OPF，获取spine中的阅读顺序
3. 按顺序读取每个内容文件，提取文本
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from core.parsers.txt_parser import TxtParser


class EpubParser:
    """EPUB电子书解析器"""

    def parse(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        if not zipfile.is_zipfile(file_path):
            raise ValueError(f"不是有效的EPUB文件: {file_path}")

        with zipfile.ZipFile(file_path, "r") as zf:
            # 读取 container.xml
            if "META-INF/container.xml" not in zf.namelist():
                raise ValueError(f"缺少META-INF/container.xml")

            with zf.open("META-INF/container.xml") as f:
                container = ET.fromstring(f.read())

            # 找到OPF文件路径（带命名空间和不带命名空间的回退）
            ns = {"ns": "urn:oasis:names:tc:opendocument:xmlns:container"}
            rootfiles = container.findall(".//ns:rootfile", ns)
            if not rootfiles:
                rootfiles = container.findall(".//{*}rootfile")
            if not rootfiles:
                rootfiles = container.findall(".//rootfile")
            opf_path = None
            for rf in rootfiles:
                mtype = rf.get("media-type", "")
                if "opf" in mtype or not opf_path:
                    opf_path = rf.get("full-path", "")
                    if "opf" in mtype:
                        break

            if not opf_path:
                # 回退：在ZIP中搜索.opf文件
                opf_files = [n for n in zf.namelist() if n.endswith(".opf")]
                if opf_files:
                    opf_path = opf_files[0]
                else:
                    raise ValueError("未找到OPF文件")

            # 读取OPF
            with zf.open(opf_path) as f:
                opf = ET.fromstring(f.read())

            opf_ns = {
                "opf": "http://www.idpf.org/2007/opf",
                "dc": "http://purl.org/dc/elements/1.1/",
            }

            # 获取内容文件目录（基于OPF路径）
            opf_dir = "/".join(opf_path.split("/")[:-1])
            if opf_dir:
                opf_dir += "/"

            # 读取manifest
            manifest = {}
            manifest_elem = opf.find("opf:manifest", opf_ns)
            if manifest_elem is None:
                manifest_elem = opf.find("{*}manifest")
            if manifest_elem is None:
                manifest_elem = opf.find("manifest")
            if manifest_elem is not None:
                for item in manifest_elem.findall("opf:item", opf_ns):
                    if item is None:
                        item = manifest_elem.findall("{*}item")
                    item_id = item.get("id", "")
                    href = item.get("href", "")
                    mtype = item.get("media-type", "")
                    manifest[item_id] = {"href": href, "type": mtype}

            # 读取spine（阅读顺序）
            spine_items = []
            spine_elem = opf.find("opf:spine", opf_ns)
            if spine_elem is None:
                spine_elem = opf.find("{*}spine")
            if spine_elem is None:
                spine_elem = opf.find("spine")
            if spine_elem is not None:
                for itemref in spine_elem.findall("opf:itemref", opf_ns):
                    if itemref is None:
                        itemref = spine_elem.findall("{*}itemref")
                    idref = itemref.get("idref", "")
                    if idref in manifest:
                        spine_items.append(manifest[idref]["href"])
            else:
                # 无spine则按manifest中html/xhtml顺序
                for item in manifest.values():
                    if "html" in item["type"] or "xhtml" in item["type"]:
                        spine_items.append(item["href"])

            # 提取元数据
            metadata = opf.find("opf:metadata", opf_ns)
            if metadata is None:
                metadata = opf.find("{*}metadata")
            if metadata is None:
                metadata = opf.find("metadata")
            meta_texts = []
            if metadata is not None:
                for title in metadata.findall("dc:title", opf_ns):
                    if title is None:
                        title = metadata.findall("{*}title")
                    if title.text:
                        meta_texts.append(f"[书名] {title.text}")
                for creator in metadata.findall("dc:creator", opf_ns):
                    if creator is None:
                        creator = metadata.findall("{*}creator")
                    if creator.text:
                        meta_texts.append(f"[作者] {creator.text}")
                for desc in metadata.findall("dc:description", opf_ns):
                    if desc is None:
                        desc = metadata.findall("{*}description")
                    if desc.text:
                        meta_texts.append(f"[简介] {desc.text}")

            # 按顺序读取内容
            all_texts = []
            if meta_texts:
                all_texts.append("\n".join(meta_texts))

            for href in spine_items:
                content_path = (opf_dir + href).lstrip("/")
                if content_path not in zf.namelist():
                    continue
                try:
                    with zf.open(content_path) as f:
                        content = f.read().decode("utf-8", errors="replace")
                    text = TxtParser.html_to_text(content)
                    if text.strip():
                        all_texts.append(text)
                except Exception:
                    pass

            return "\n\n".join(all_texts)
