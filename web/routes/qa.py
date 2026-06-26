from flask import Blueprint, request, render_template, jsonify
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config
from core.database import DatabaseManager
from core.embedding_engine import EmbeddingEngine

qa_bp = Blueprint("qa", __name__)

db = DatabaseManager(str(config.DB_PATH))


@qa_bp.route("/", methods=["GET"])
def qa_page():
    from flask import render_template
    return render_template("qa.html")


@qa_bp.route("/api/query", methods=["POST"])
def query():
    data = request.get_json()
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "No question provided"}), 400

    chunks = db.get_all_chunks_with_embeddings()
    if not chunks:
        return jsonify({"answer": "知识库中暂无数据，请先上传文档。", "sources": []})

    embedding_engine = EmbeddingEngine(config.EMBEDDING_MODEL)
    query_emb = embedding_engine.embed_text(question)

    results = embedding_engine.search_similar(query_emb, chunks, top_k=config.TOP_K, threshold=config.SIMILARITY_THRESHOLD)

    if not results:
        return jsonify({"answer": "未找到相关知识，请尝试其他问题。", "sources": []})

    context_parts = []
    sources = []
    for i, r in enumerate(results):
        chunk = r["chunk"]
        score = r["score"]
        context_parts.append(f"[{i+1}] {chunk['content']}")
        sources.append({
            "chunk_id": chunk["id"],
            "document": chunk.get("original_name", "Unknown"),
            "content_preview": chunk["content"][:300],
            "score": round(score, 4)
        })

    context = "\n\n".join(context_parts)
    answer = f"根据知识库中的相关内容，以下是回答：\n\n{context}\n\n以上是检索到的相关内容，请基于这些信息回答问题。"

    return jsonify({"answer": answer, "sources": sources})
