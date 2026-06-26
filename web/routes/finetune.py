from flask import Blueprint, request, render_template, jsonify
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config
from core.database import DatabaseManager

finetune_bp = Blueprint("finetune", __name__)

db = DatabaseManager(str(config.DB_PATH))


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
        return jsonify({"error": "Question and answer required"}), 400
    pair_id = db.create_training_pair(question, answer, is_generated=False)
    return jsonify({"id": pair_id, "message": "Created"})


@finetune_bp.route("/api/training-pairs/<int:pair_id>", methods=["DELETE"])
def delete_pair(pair_id):
    db.delete_training_pair(pair_id)
    return jsonify({"message": "Deleted"})


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
    return jsonify({"message": f"Generated {total_generated} training pairs"})


@finetune_bp.route("/api/start", methods=["POST"])
def start_finetune():
    data = request.get_json()
    model_name = data.get("model_name", "finetuned_model")
    base_model = data.get("base_model", config.DEFAULT_BASE_MODEL)
    epochs = data.get("epochs", config.DEFAULT_EPOCHS)
    lora_rank = data.get("lora_rank", config.DEFAULT_LORA_RANK)

    pairs = db.list_training_pairs()
    if len(pairs) < 10:
        return jsonify({"error": "Need at least 10 training pairs"}), 400

    job_id = db.create_finetune_job(model_name, base_model, len(pairs), epochs, lora_rank)
    return jsonify({"job_id": job_id, "message": "Fine-tuning job created (queued)"})


@finetune_bp.route("/api/jobs", methods=["GET"])
def list_jobs():
    jobs = db.list_finetune_jobs()
    return jsonify(jobs)
