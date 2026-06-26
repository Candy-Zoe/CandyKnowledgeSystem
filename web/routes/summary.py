import uuid
from flask import Blueprint, request, render_template, jsonify
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config
from core.database import DatabaseManager

summary_bp = Blueprint("summary", __name__)
db = DatabaseManager(str(config.DB_PATH))


@summary_bp.route("/", methods=["GET"])
def summary_page():
    from flask import render_template
    docs = db.list_documents(status="completed")
    summaries = {}
    for doc in docs:
        s = db.get_summary(doc["id"])
        if s:
            summaries[doc["id"]] = s
    return render_template("summary.html", documents=docs, summaries=summaries)


@summary_bp.route("/api/generate/<int:doc_id>", methods=["POST"])
def generate_summary(doc_id):
    doc = db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "文档不存在"}), 404

    content = db.get_document_content(doc_id)
    if not content:
        return jsonify({"error": "文档内容为空"}), 400

    sentences = [s.strip() for s in content.replace("\n", " ").split("。") if len(s.strip()) > 10]
    summary = "。".join(sentences[:5]) + "。" if len(sentences) >= 5 else "。".join(sentences) + "。"

    db.save_summary(doc_id, summary)
    return jsonify({"summary": summary, "message": "摘要已生成"})


@summary_bp.route("/api/<int:doc_id>", methods=["GET"])
def get_summary(doc_id):
    summary = db.get_summary(doc_id)
    if summary:
        return jsonify({"summary": summary})
    return jsonify({"summary": None})
