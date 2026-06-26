import uuid
import threading
from flask import Blueprint, request, render_template, jsonify
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config
from core.database import DatabaseManager
from core.embedding_engine import EmbeddingEngine
from core.rag_engine import RAGEngine

batch_bp = Blueprint("batch_qa", __name__)
db = DatabaseManager(str(config.DB_PATH))
embedding_engine = EmbeddingEngine(config.EMBEDDING_MODEL)
rag_engine = RAGEngine(db, embedding_engine)


@batch_bp.route("/", methods=["GET"])
def batch_page():
    from flask import render_template
    return render_template("batch_qa.html")


@batch_bp.route("/api/run", methods=["POST"])
def run_batch():
    data = request.get_json()
    questions = data.get("questions", [])
    if not questions:
        return jsonify({"error": "请输入问题"}), 400

    batch_id = uuid.uuid4().hex[:12]

    def process():
        for q in questions:
            result = rag_engine.query(q.strip())
            db.save_batch_result(batch_id, q.strip(), result.get("answer", ""), result.get("sources", []))

    thread = threading.Thread(target=process)
    thread.daemon = True
    thread.start()

    return jsonify({"batch_id": batch_id, "message": "批量问答已开始", "total": len(questions)})


@batch_bp.route("/api/<batch_id>/status", methods=["GET"])
def batch_status(batch_id):
    results = db.get_batch_results(batch_id)
    return jsonify({"completed": len(results), "results": results})


@batch_bp.route("/api/<batch_id>/export", methods=["GET"])
def export_batch(batch_id):
    results = db.get_batch_results(batch_id)
    lines = ["问题,回答,来源"]
    for r in results:
        sources = ", ".join([s.get("document", "") for s in (r.get("sources") or [])])
        answer = r["answer"].replace('"', '""') if r.get("answer") else ""
        question = r["question"].replace('"', '""')
        lines.append('"%s","%s","%s"' % (question, answer, sources))
    from flask import Response
    return Response("\n".join(lines), content_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=batch_%s.csv" % batch_id})
