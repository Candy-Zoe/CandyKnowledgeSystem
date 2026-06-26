import os
import sys
import uuid
import shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from core.database import DatabaseManager
from core.document_parser import DocumentParser
from core.text_processor import TextProcessor
from core.embedding_engine import EmbeddingEngine

SUPPORTED = (".pdf", ".docx", ".doc", ".txt", ".md", ".html", ".htm", ".csv", ".xlsx", ".xls")


def process_file(db, file_path, file_type, embedding_engine, processor):
    original_name = Path(file_path).name
    unique_name = f"{uuid.uuid4().hex}.{file_type}"
    dest = str(config.UPLOAD_DIR / unique_name)

    shutil.copy2(file_path, dest)

    file_size = os.path.getsize(dest)
    metadata = DocumentParser.get_metadata(dest, file_type)
    doc_id = db.create_document(unique_name, original_name, file_type, file_size, dest)

    try:
        db.update_document_status(doc_id, "processing")
        text = DocumentParser.parse(dest, file_type)
        if not text.strip():
            db.update_document_status(doc_id, "error", "无法提取文本内容")
            return
        chunks = processor.chunk_text(text)
        texts = [c["content"] for c in chunks]
        embeddings = embedding_engine.embed_batch(texts, batch_size=32)
        for i, chunk in enumerate(chunks):
            chunk["embedding"] = embeddings[i]
        db.create_chunks(doc_id, chunks)
        db.update_document_chunks(doc_id, len(chunks))
        db.update_document_status(doc_id, "completed")
        print(f"  OK: {original_name} -> {len(chunks)} chunks")
    except Exception as e:
        db.update_document_status(doc_id, "error", str(e))
        print(f"  FAIL: {original_name} -> {e}")


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/batch_import.py <文件夹或文件> [文件夹或文件 ...]")
        print(f"支持的格式: {', '.join(SUPPORTED)}")
        return

    db = DatabaseManager(str(config.DB_PATH))
    processor = TextProcessor(config.CHUNK_SIZE, config.CHUNK_OVERLAP, strategy="semantic")
    embedding_engine = EmbeddingEngine(config.EMBEDDING_MODEL)

    files = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.is_file() and p.suffix.lower() in SUPPORTED:
            files.append(p)
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.suffix.lower() in SUPPORTED:
                    files.append(f)

    print(f"找到 {len(files)} 个文件待导入")
    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] 处理: {f.name}")
        process_file(db, str(f), f.suffix.lstrip("."), embedding_engine, processor)

    stats = db.get_stats()
    print(f"\n导入完成！共 {stats['document_count']} 个文档，{stats['chunk_count']} 个分块")


if __name__ == "__main__":
    main()
