import os
import uuid
import threading
import time
from flask import Blueprint, request, render_template, jsonify
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config
from core.database import DatabaseManager

scheduler_bp = Blueprint("scheduler", __name__)
db = DatabaseManager(str(config.DB_PATH))

_running_tasks = {}
_stop_events = {}


def _run_task(task_id, folder_path, interval_minutes):
    from core.document_parser import DocumentParser
    from core.text_processor import TextProcessor
    from core.embedding_engine import EmbeddingEngine

    processor = TextProcessor(config.CHUNK_SIZE, config.CHUNK_OVERLAP, strategy="semantic")
    emb_engine = EmbeddingEngine(config.EMBEDDING_MODEL)
    supported = (".pdf", ".docx", ".doc", ".txt", ".md", ".html", ".htm", ".csv", ".xlsx", ".xls")

    while not _stop_events.get(task_id, threading.Event()).is_set():
        try:
            if os.path.isdir(folder_path):
                for f in os.listdir(folder_path):
                    fp = os.path.join(folder_path, f)
                    if os.path.isfile(fp) and Path(f).suffix.lower() in supported:
                        file_type = Path(f).suffix.lstrip(".")
                        import shutil
                        unique_name = "%s.%s" % (uuid.uuid4().hex, file_type)
                        dest = str(config.UPLOAD_DIR / unique_name)
                        shutil.copy2(fp, dest)
                        file_size = os.path.getsize(dest)
                        doc_id = db.create_document(unique_name, f, file_type, file_size, dest)

                        try:
                            db.update_document_status(doc_id, "processing")
                            text = DocumentParser.parse(dest, file_type)
                            if text.strip():
                                chunks = processor.chunk_text(text)
                                texts = [c["content"] for c in chunks]
                                embeddings = emb_engine.embed_batch(texts, batch_size=32)
                                for i, chunk in enumerate(chunks):
                                    chunk["embedding"] = embeddings[i]
                                db.create_chunks(doc_id, chunks)
                                db.update_document_chunks(doc_id, len(chunks))
                                db.update_document_status(doc_id, "completed")
                        except Exception as e:
                            db.update_document_status(doc_id, "error", str(e))

            db.update_scheduled_task(task_id, last_run=time.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            pass

        _stop_events.get(task_id, threading.Event()).wait(interval_minutes * 60)


@scheduler_bp.route("/", methods=["GET"])
def scheduler_page():
    from flask import render_template
    tasks = db.list_scheduled_tasks()
    return render_template("scheduler.html", tasks=tasks, running=_running_tasks)


@scheduler_bp.route("/api/create", methods=["POST"])
def create_task():
    data = request.get_json()
    name = data.get("name", "").strip()
    folder = data.get("folder_path", "").strip()
    interval = data.get("interval_minutes", 60)
    if not name or not folder:
        return jsonify({"error": "请填写任务名称和文件夹路径"}), 400
    task_id = db.create_scheduled_task(name, folder, interval)
    return jsonify({"id": task_id, "message": "定时任务已创建"})


@scheduler_bp.route("/api/<int:task_id>/start", methods=["POST"])
def start_task(task_id):
    tasks = db.list_scheduled_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return jsonify({"error": "任务不存在"}), 404

    if task_id in _running_tasks:
        return jsonify({"error": "任务已在运行"}), 400

    stop_event = threading.Event()
    _stop_events[task_id] = stop_event
    thread = threading.Thread(target=_run_task, args=(task_id, task["folder_path"], task["interval_minutes"]))
    thread.daemon = True
    thread.start()
    _running_tasks[task_id] = thread

    return jsonify({"message": "任务已启动"})


@scheduler_bp.route("/api/<int:task_id>/stop", methods=["POST"])
def stop_task(task_id):
    if task_id in _stop_events:
        _stop_events[task_id].set()
        _stop_events.pop(task_id, None)
        _running_tasks.pop(task_id, None)
        return jsonify({"message": "任务已停止"})
    return jsonify({"error": "任务未在运行"}), 400


@scheduler_bp.route("/api/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    if task_id in _stop_events:
        _stop_events[task_id].set()
        _stop_events.pop(task_id, None)
        _running_tasks.pop(task_id, None)
    db.delete_scheduled_task(task_id)
    return jsonify({"message": "任务已删除"})
