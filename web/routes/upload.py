import os
import uuid
import threading
from flask import Blueprint, request, render_template, jsonify, current_app
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config
from core.database import DatabaseManager
from core.document_parser import DocumentParser
from core.text_processor import TextProcessor
from core.embedding_engine import EmbeddingEngine

upload_bp = Blueprint("upload", __name__)

db = DatabaseManager(str(config.DB_PATH))


def process_document(doc_id, file_path, file_type):
    try:
        db.update_document_status(doc_id, "processing")
        text = DocumentParser.parse(file_path, file_type)
        if not text.strip():
            db.update_document_status(doc_id, "error", "No text content extracted")
            return

        processor = TextProcessor(config.CHUNK_SIZE, config.CHUNK_OVERLAP)
        chunks = processor.chunk_text(text)

        embedding_engine = EmbeddingEngine(config.EMBEDDING_MODEL)
        texts = [c["content"] for c in chunks]
        embeddings = embedding_engine.embed_batch(texts)

        for i, chunk in enumerate(chunks):
            chunk["embedding"] = embeddings[i]

        db.create_chunks(doc_id, chunks)
        db.update_document_chunks(doc_id, len(chunks))
        db.update_document_status(doc_id, "completed")
    except Exception as e:
        db.update_document_status(doc_id, "error", str(e))


@upload_bp.route("/", methods=["GET"])
def upload_page():
    from flask import render_template
    return render_template("upload.html")


@upload_bp.route("/", methods=["POST"])
def upload_files():
    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "No files selected"}), 400

    results = []
    for file in files:
        if file.filename == "":
            continue

        original_name = file.filename
        file_type = Path(original_name).suffix.lstrip(".")
        if file_type not in ("pdf", "docx", "doc", "txt"):
            results.append({"filename": original_name, "error": f"Unsupported type: .{file_type}"})
            continue

        unique_name = f"{uuid.uuid4().hex}.{file_type}"
        file_path = str(config.UPLOAD_DIR / unique_name)
        file.save(file_path)

        file_size = os.path.getsize(file_path)
        doc_id = db.create_document(unique_name, original_name, file_type, file_size, file_path)

        thread = threading.Thread(target=process_document, args=(doc_id, file_path, file_type))
        thread.daemon = True
        thread.start()

        results.append({"filename": original_name, "doc_id": doc_id, "status": "queued"})

    return jsonify({"message": f"Uploaded {len(results)} file(s)", "results": results})
