import json
from flask import Blueprint, request, render_template, jsonify, Response
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config
from core.database import DatabaseManager
from core.embedding_engine import EmbeddingEngine
from core.rag_engine import RAGEngine
from core.model_manager import ModelManager

qa_bp = Blueprint("qa", __name__)

db = DatabaseManager(str(config.DB_PATH))
settings = config.load_settings()
embedding_engine = EmbeddingEngine(settings.get("embedding_model", config.EMBEDDING_MODEL))
rag_engine = RAGEngine(db, embedding_engine)
rag_engine.load_settings(settings)
model_manager = ModelManager()


@qa_bp.route("/", methods=["GET"])
def qa_page():
    from flask import render_template
    model_status = rag_engine.get_model_status()
    models = model_manager.list_all_models()
    return render_template("qa.html", model_status=model_status, models=models,
                           retrieval_mode=rag_engine.retrieval_mode)


@qa_bp.route("/api/query", methods=["POST"])
def query():
    data = request.get_json()
    question = data.get("question", "").strip()
    history = data.get("history", [])

    if not question:
        return jsonify({"error": "请输入问题"}), 400

    chunks = db.get_all_chunks_with_embeddings()
    if not chunks:
        return jsonify({"answer": "知识库中暂无数据，请先上传文档。", "sources": [], "model_loaded": False})

    result = rag_engine.query(question, history=history)
    result["model_loaded"] = rag_engine.is_model_loaded()
    return jsonify(result)


@qa_bp.route("/api/query/stream", methods=["POST"])
def query_stream():
    data = request.get_json()
    question = data.get("question", "").strip()
    history = data.get("history", [])

    if not question:
        return jsonify({"error": "请输入问题"}), 400

    chunks = db.get_all_chunks_with_embeddings()
    if not chunks:
        def empty():
            yield json.dumps({"type": "answer", "content": "知识库中暂无数据，请先上传文档。"}) + "\n"
        return Response(empty(), content_type="text/event-stream")

    def generate():
        for item in rag_engine.query_stream(question, history=history):
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return Response(generate(), content_type="text/event-stream")


@qa_bp.route("/api/model/status", methods=["GET"])
def model_status():
    return jsonify(rag_engine.get_model_status())


@qa_bp.route("/api/model/load", methods=["POST"])
def load_model():
    data = request.get_json()
    model_path = data.get("model_path", "")
    model_type = data.get("model_type", "finetuned")

    if not model_path:
        return jsonify({"error": "请指定模型路径"}), 400

    try:
        rag_engine.load_model(model_path, model_type)
        return jsonify({"message": "模型加载成功", "status": rag_engine.get_model_status()})
    except Exception as e:
        return jsonify({"error": "模型加载失败: %s" % str(e)}), 500


@qa_bp.route("/api/model/unload", methods=["POST"])
def unload_model():
    rag_engine.unload_model()
    return jsonify({"message": "模型已卸载"})


@qa_bp.route("/api/models", methods=["GET"])
def list_models():
    models = model_manager.list_all_models()
    return jsonify(models)


@qa_bp.route("/api/models/upload", methods=["POST"])
def upload_model():
    files = request.files.getlist("files")
    model_name = request.form.get("model_name", "").strip()

    if not model_name:
        return jsonify({"error": "请输入模型名称"}), 400

    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "请选择模型文件"}), 400

    try:
        saved = model_manager.save_uploaded_model_files(files, model_name)
        return jsonify({"message": "模型上传成功", "files": saved, "path": model_manager.get_model_path(model_name, "custom")})
    except Exception as e:
        return jsonify({"error": "上传失败: %s" % str(e)}), 500


@qa_bp.route("/api/models/<model_name>", methods=["DELETE"])
def delete_model(model_name):
    model_type = request.args.get("type", "custom")
    if model_manager.delete_model(model_name, model_type):
        return jsonify({"message": "模型已删除"})
    return jsonify({"error": "模型不存在"}), 404


@qa_bp.route("/api/retrieval/mode", methods=["POST"])
def set_retrieval_mode():
    data = request.get_json()
    mode = data.get("mode", "vector")
    if rag_engine.set_retrieval_mode(mode):
        return jsonify({"message": "检索模式已切换为: %s" % mode, "mode": mode})
    return jsonify({"error": "无效的检索模式"}), 400


@qa_bp.route("/api/retrieval/mode", methods=["GET"])
def get_retrieval_mode():
    return jsonify({"mode": rag_engine.retrieval_mode})


@qa_bp.route("/api/settings/reload", methods=["POST"])
def reload_settings():
    new_settings = config.load_settings()
    rag_engine.load_settings(new_settings)
    return jsonify({"message": "设置已重新加载"})
