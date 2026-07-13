"""
PDF解析器测试脚本
用法: python test_pdf_parser.py <pdf文件路径>
"""
import sys
from core.pdf_parser import PDFParser, parse_pdf, validate_pdf


def test_pdf(file_path):
    print(f"\n{'='*60}")
    print(f"测试PDF文件: {file_path}")
    print(f"{'='*60}")

    # 1. 验证PDF
    print("\n[1] 验证PDF文件...")
    check = validate_pdf(file_path)
    print(f"    有效: {check['valid']}")
    if check['issues']:
        print(f"    问题: {check['issues']}")
    if check['info']:
        print(f"    页数: {check['info'].get('page_count', 'N/A')}")
        print(f"    大小: {check['info'].get('size_mb', 'N/A')} MB")
        print(f"    平均字符/页: {check['info'].get('avg_chars_per_page', 'N/A')}")
        print(f"    可能是扫描版: {check['info'].get('is_likely_scanned', 'N/A')}")

    if not check['valid']:
        print("\nPDF验证失败，跳过解析测试")
        return

    # 2. 解析PDF
    print("\n[2] 解析PDF...")
    parser = PDFParser(use_ocr=True)
    result = parser.parse(file_path)

    print(f"    总页数: {result.page_count}")
    print(f"    解析页数: {len(result.pages)}")
    print(f"    总字符数: {result.total_chars}")
    print(f"    是否为空: {result.is_empty}")

    if result.errors:
        print(f"    错误: {result.errors}")
    if result.warnings:
        print(f"    警告: {result.warnings}")

    # 3. 显示每页信息
    print("\n[3] 每页解析详情:")
    for page in result.pages:
        text_len = len(page.text) if page.text else 0
        tables_count = len(page.tables)
        print(f"    第{page.page_number}页: "
              f"文本={text_len}字符, "
              f"表格={tables_count}个, "
              f"图片={page.images_count}张, "
              f"方法={page.method}")

    # 4. 显示前500字符文本预览
    print("\n[4] 文本预览(前500字符):")
    print("-" * 40)
    preview = result.full_text[:500] if result.full_text else "(无文本)"
    print(preview)
    if len(result.full_text) > 500:
        print(f"... (共{result.total_chars}字符)")
    print("-" * 40)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python test_pdf_parser.py <pdf文件路径>")
        sys.exit(1)

    test_pdf(sys.argv[1])
