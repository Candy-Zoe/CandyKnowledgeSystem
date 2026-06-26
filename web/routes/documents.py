import os
from flask import Blueprint, request, render_template, jsonify, send_file
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config
from core.database import DatabaseManager

documents_bp = Blueprint("documents", __name__)

db = DatabaseManager(str(config.DB_PATH))


@documents_bp.route("/", methods=["GET"])
def documents_page():
    from flask import render_template
    docs = db.list_documents()
    stats = db.get_stats()
    return render_template("documents.html", documents=docs, stats=stats)


@documents_bp.route("/api/list", methods=["GET"])
def list_documents():
    docs = db.list_documents()
    return jsonify(docs)


@documents_bp.route("/api/<int:doc_id>", methods=["GET"])
def get_document(doc_id):
    doc = db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "文档不存在"}), 404
    chunks = db.get_chunks_by_document(doc_id)
    doc["chunks"] = [{"id": c["id"], "chunk_index": c["chunk_index"], "content": c["content"][:500], "token_count": c["token_count"]} for c in chunks]
    return jsonify(doc)


@documents_bp.route("/api/<int:doc_id>/content", methods=["GET"])
def get_document_content(doc_id):
    doc = db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "文档不存在"}), 404
    content = db.get_document_content(doc_id)
    return jsonify({"content": content, "chunk_count": doc.get("total_chunks", 0)})


@documents_bp.route("/api/<int:doc_id>", methods=["DELETE"])
def delete_document(doc_id):
    doc = db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "文档不存在"}), 404
    file_path = doc.get("file_path")
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
    db.delete_document(doc_id)
    return jsonify({"message": "文档已删除"})


@documents_bp.route("/api/search", methods=["GET"])
def search_chunks():
    keyword = request.args.get("q", "").strip()
    doc_id = request.args.get("doc_id", type=int)
    if not keyword:
        return jsonify({"error": "请输入搜索关键词"}), 400
    results = db.search_chunks(keyword, doc_id)
    return jsonify([{
        "id": c["id"],
        "document_id": c["document_id"],
        "document_name": c.get("original_name", ""),
        "chunk_index": c["chunk_index"],
        "content": c["content"][:500],
        "token_count": c["token_count"]
    } for c in results])


@documents_bp.route("/api/stats", methods=["GET"])
def get_stats():
    stats = db.get_stats()
    return jsonify(stats)


@documents_bp.route("/api/export/json", methods=["GET"])
def export_json():
    output_path = str(config.DATA_DIR / "export.json")
    db.export_to_json(output_path)
    return send_file(output_path, as_attachment=True, download_name="knowledge_base.json")


@documents_bp.route("/api/export/sql", methods=["GET"])
def export_sql():
    output_path = str(config.DATA_DIR / "export.sql")
    db.export_to_sql(output_path)
    return send_file(output_path, as_attachment=True, download_name="knowledge_base.sql")


@documents_bp.route("/api/import", methods=["POST"])
def import_data():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "未提供文件"}), 400
    filename = file.filename
    if filename.endswith(".json"):
        import tempfile
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        file.save(tmp.name)
        db.import_from_json(tmp.name)
        os.unlink(tmp.name)
        return jsonify({"message": "导入成功"})
    else:
        return jsonify({"error": "仅支持JSON格式导入"}), 400
