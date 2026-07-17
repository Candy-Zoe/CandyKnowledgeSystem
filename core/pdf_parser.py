"""
PDF 解析器兼容层
将导入重定向到 core.parsers.pdf_parser（增强版）
"""
from core.parsers.pdf_parser import (
    PDFPage,
    PDFResult,
    PDFParser,
    PDFValidator,
    parse_pdf,
    parse_pdf_with_info,
    validate_pdf,
)

__all__ = [
    "PDFPage",
    "PDFResult",
    "PDFParser",
    "PDFValidator",
    "parse_pdf",
    "parse_pdf_with_info",
    "validate_pdf",
]
