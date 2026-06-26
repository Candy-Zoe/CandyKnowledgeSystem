import threading
from flask import Blueprint, request, render_template, jsonify
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config
from core.database import DatabaseManager

finetune_bp = Blueprint("finetune", __name__)

db = DatabaseManager(str(config.DB_PATH))

_training_lock = threading.Lock()
_training_status = {"running": False, "progress": "", "error": None}


def _run_training(job_id, model_name, base_model, epochs, lora_rank):
    global _training_status
    try:
        _training_status = {"running": True, "progress": "加载基础模型...", "error": None}
        db.update_finetune_job(job_id, status="running", started_at=__import__("datetime").datetime.now().isoformat())

        from core.finetune_engine import FinetuneEngine
        engine = FinetuneEngine(db)

        _training_status["progress"] = "准备训练数据..."
        split = engine.prepare_training_data()

        _training_status["progress"] = "开始训练..."
        output_path = engine.train(model_name, base_model, epochs, lora_rank)

        _training_status["progress"] = "训练完成！"
        db.update_finetune_job(job_id, status="completed", output_path=output_path,
                               completed_at=__import__("datetime").datetime.now().isoformat())

    except Exception as e:
        _training_status = {"running": False, "progress": "", "error": str(e)}
        db.update_finetune_job(job_id, status="failed", error_message=str(e))
    finally:
        _training_status["running"] = False


@finetune_bp.route("/", methods=["GET"])
def finetune_page():
    from flask import render_template
    pairs = db.list_training_pairs()
    jobs = db.list_finetune_jobs()
    return render_template("finetune.html", pairs=pairs, jobs=jobs)


@finetune_bp.route("/api/training-pairs", methods=["GET"])
def list_pairs():
    pairs = db.list_training_pairs()
    return jsonify(pairs)


@finetune_bp.route("/api/training-pairs", methods=["POST"])
def create_pair():
    data = request.get_json()
    question = data.get("question", "").strip()
    answer = data.get("answer", "").strip()
    if not question or not answer:
        return jsonify({"error": "请填写问题和回答"}), 400
    pair_id = db.create_training_pair(question, answer, is_generated=False)
    return jsonify({"id": pair_id, "message": "添加成功"})


@finetune_bp.route("/api/training-pairs/<int:pair_id>", methods=["DELETE"])
def delete_pair(pair_id):
    db.delete_training_pair(pair_id)
    return jsonify({"message": "已删除"})


@finetune_bp.route("/api/generate-pairs", methods=["POST"])
def generate_pairs():
    from core.text_processor import TextProcessor
    processor = TextProcessor()
    docs = db.list_documents(status="completed")
    total_generated = 0
    for doc in docs:
        chunks = db.get_chunks_by_document(doc["id"])
        pairs = processor.generate_training_pairs(chunks)
        for p in pairs:
            db.create_training_pair(p["question"], p["answer"], p.get("source_chunk_ids"), doc["id"], is_generated=True)
            total_generated += 1
    return jsonify({"message": "已生成 %d 条训练数据" % total_generated})


@finetune_bp.route("/api/start", methods=["POST"])
def start_finetune():
    global _training_status
    if _training_status["running"]:
        return jsonify({"error": "已有训练任务在进行中"}), 400

    data = request.get_json()
    model_name = data.get("model_name", "my_model")
    base_model = data.get("base_model", config.DEFAULT_BASE_MODEL)
    epochs = data.get("epochs", config.DEFAULT_EPOCHS)
    lora_rank = data.get("lora_rank", config.DEFAULT_LORA_RANK)

    pairs = db.list_training_pairs()
    if len(pairs) < 5:
        return jsonify({"error": "至少需要5条训练数据，当前只有%d条" % len(pairs)}), 400

    job_id = db.create_finetune_job(model_name, base_model, len(pairs), epochs, lora_rank)

    thread = threading.Thread(target=_run_training, args=(job_id, model_name, base_model, epochs, lora_rank))
    thread.daemon = True
    thread.start()

    return jsonify({"job_id": job_id, "message": "训练任务已启动"})


@finetune_bp.route("/api/status", methods=["GET"])
def training_status():
    return jsonify(_training_status)


@finetune_bp.route("/api/jobs", methods=["GET"])
def list_jobs():
    jobs = db.list_finetune_jobs()
    return jsonify(jobs)


@finetune_bp.route("/api/models", methods=["GET"])
def list_models():
    from pathlib import Path
    models = []
    model_dir = Path(config.MODEL_DIR)
    if model_dir.exists():
        for p in model_dir.iterdir():
            if p.is_dir() and (p / "adapter_config.json").exists():
                models.append({"name": p.name, "path": str(p)})
    return jsonify(models)
