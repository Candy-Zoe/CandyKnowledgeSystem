from flask import Blueprint, request, render_template, jsonify
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config
from core.database import DatabaseManager

stats_bp = Blueprint("stats", __name__)
db = DatabaseManager(str(config.DB_PATH))


@stats_bp.route("/", methods=["GET"])
def stats_page():
    from flask import render_template
    stats = db.get_stats()
    api_stats = db.get_api_stats()
    hot_questions = db.get_hot_questions(10)
    return render_template("stats.html", stats=stats, api_stats=api_stats, hot_questions=hot_questions)


@stats_bp.route("/api/overview", methods=["GET"])
def overview():
    return jsonify(db.get_stats())


@stats_bp.route("/api/api-stats", methods=["GET"])
def api_stats():
    return jsonify(db.get_api_stats())


@stats_bp.route("/api/hot-questions", methods=["GET"])
def hot_questions():
    limit = request.args.get("limit", 10, type=int)
    return jsonify(db.get_hot_questions(limit))
