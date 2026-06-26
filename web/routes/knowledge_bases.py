from flask import Blueprint, request, render_template, jsonify
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config
from core.database import DatabaseManager

kb_bp = Blueprint("knowledge_bases", __name__)
db = DatabaseManager(str(config.DB_PATH))


@kb_bp.route("/", methods=["GET"])
def kb_page():
    from flask import render_template
    kbs = db.list_knowledge_bases()
    for kb in kbs:
        stats = db.get_stats(kb["id"])
        kb["doc_count"] = stats["document_count"]
        kb["chunk_count"] = stats["chunk_count"]
    return render_template("knowledge_bases.html", knowledge_bases=kbs)


@kb_bp.route("/api/list", methods=["GET"])
def list_kbs():
    return jsonify(db.list_knowledge_bases())


@kb_bp.route("/api/create", methods=["POST"])
def create_kb():
    data = request.get_json()
    name = data.get("name", "").strip()
    desc = data.get("description", "")
    if not name:
        return jsonify({"error": "请输入知识库名称"}), 400
    kb_id = db.create_knowledge_base(name, desc)
    return jsonify({"id": kb_id, "message": "知识库已创建"})


@kb_bp.route("/api/<int:kb_id>", methods=["DELETE"])
def delete_kb(kb_id):
    db.delete_knowledge_base(kb_id)
    return jsonify({"message": "知识库已删除"})


@kb_bp.route("/api/<int:kb_id>/stats", methods=["GET"])
def kb_stats(kb_id):
    return jsonify(db.get_stats(kb_id))
