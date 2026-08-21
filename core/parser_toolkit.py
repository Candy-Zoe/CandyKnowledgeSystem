"""
文档解析工具类集合入口。

这个模块只负责把各类自实现解析器组织成统一接口，方便在 GUI、
脚本或后续服务中复用：

    from core.parser_toolkit import ParserToolkit
    text = ParserToolkit.parse_file("example.docx")
"""
from pathlib import Path

from core.document_parser import DocumentParser


class ParserToolkit:
    """统一文档解析工具类。"""

    @staticmethod
    def supported_types() -> dict:
        return DocumentParser.SUPPORTED_TYPES.copy()

    @staticmethod
    def is_supported(file_path: str) -> bool:
        path = Path(file_path)
        file_type = path.suffix.lower().lstrip(".")
        if not file_type and path.name.lower() in ("dockerfile", "makefile"):
            file_type = path.name.lower()
        return file_type in DocumentParser.SUPPORTED_TYPES

    @staticmethod
    def parse_file(file_path: str, max_pdf_pages=0, page_sleep_ms=0) -> str:
        path = Path(file_path)
        file_type = path.suffix.lower().lstrip(".")
        if not file_type and path.name.lower() in ("dockerfile", "makefile"):
            file_type = path.name.lower()
        parser = DocumentParser(max_pages=max_pdf_pages, page_sleep_ms=page_sleep_ms)
        return parser.parse(str(path), file_type)

    @staticmethod
    def get_metadata(file_path: str) -> dict:
        path = Path(file_path)
        file_type = path.suffix.lower().lstrip(".")
        if not file_type and path.name.lower() in ("dockerfile", "makefile"):
            file_type = path.name.lower()
        return DocumentParser.get_metadata(str(path), file_type)
