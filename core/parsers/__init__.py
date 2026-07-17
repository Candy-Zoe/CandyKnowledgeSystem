"""
CandyKnowledgeSystem 文档解析器包

提供多种文档格式的纯Python解析支持，尽量减少外部依赖：
- PDF: 优先PyMuPDF，提供纯Python回退
- DOCX: 基于zip+xml自实现
- PPTX: 基于zip+xml自实现
- XLSX: 基于zip+xml自实现
- DOC(旧版): OLE文本提取
- PPT(旧版): OLE文本提取
- TXT/MD/HTML/CSV: 纯Python标准库
- EPUB: ZIP+XHTML解析
- RTF: 富文本格式解析
- ODT/ODS/ODP: OpenDocument解析
- JSON/XML/YAML/TOML/INI: 数据文件解析
- ZIP: 压缩包内文本提取
- JPG/PNG: 图片OCR（需外部库）
- MHT/MHTML: MIME HTML解析
"""

from .pdf_parser import PDFParser, parse_pdf
from .docx_parser import DocxParser
from .pptx_parser import PptxParser
from .xlsx_parser import XlsxParser
from .ole_parser import OleDocParser, OlePptParser, OleXlsParser
from .txt_parser import TxtParser
from .epub_parser import EpubParser
from .rtf_parser import RtfParser
from .opendoc_parser import OpenDocParser
from .data_parser import DataParser
from .archive_parser import ArchiveParser
from .image_parser import ImageParser
from .mht_parser import MhtParser

__all__ = [
    "PDFParser", "parse_pdf",
    "DocxParser",
    "PptxParser",
    "XlsxParser",
    "OleDocParser", "OlePptParser", "OleXlsParser",
    "TxtParser",
    "EpubParser",
    "RtfParser",
    "OpenDocParser",
    "DataParser",
    "ArchiveParser",
    "ImageParser",
    "MhtParser",
]
