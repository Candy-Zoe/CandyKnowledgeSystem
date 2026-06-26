from flask import Blueprint, request, render_template, jsonify
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config
from core.database import DatabaseManager

conversations_bp = Blueprint("conversations", __name__)
db = DatabaseManager(str(config.DB_PATH))


@conversations_bp.route("/", methods=["GET"])
def conversations_page():
    from flask import render_template
    convs = db.list_conversations()
    kbs = db.list_knowledge_bases()
    return render_template("conversations.html", conversations=convs, knowledge_bases=kbs)


@conversations_bp.route("/api/list", methods=["GET"])
def list_conversations():
    return jsonify(db.list_conversations())


@conversations_bp.route("/api/create", methods=["POST"])
def create_conversation():
    data = request.get_json()
    title = data.get("title", "新对话")
    kb_id = data.get("kb_id")
    conv_id = db.create_conversation(title, kb_id)
    return jsonify({"id": conv_id, "message": "对话已创建"})


@conversations_bp.route("/api/<int:conv_id>", methods=["GET"])
def get_conversation(conv_id):
    conv = db.get_conversation(conv_id)
    if not conv:
        return jsonify({"error": "对话不存在"}), 404
    conv["messages"] = db.get_messages(conv_id)
    return jsonify(conv)


@conversations_bp.route("/api/<int:conv_id>", methods=["DELETE"])
def delete_conversation(conv_id):
    db.delete_conversation(conv_id)
    return jsonify({"message": "对话已删除"})


@conversations_bp.route("/api/<int:conv_id>/messages", methods=["GET"])
def get_messages(conv_id):
    return jsonify(db.get_messages(conv_id))


@conversations_bp.route("/api/<int:conv_id>/export", methods=["GET"])
def export_conversation(conv_id):
    conv = db.get_conversation(conv_id)
    if not conv:
        return jsonify({"error": "对话不存在"}), 404
    messages = db.get_messages(conv_id)
    lines = ["# %s\n" % conv["title"], ""]
    for msg in messages:
        role = "用户" if msg["role"] == "user" else "助手"
        lines.append("**%s**: %s\n" % (role, msg["content"]))
        if msg.get("sources"):
            lines.append("  *参考来源*:")
            for s in msg["sources"]:
                lines.append("  - %s (相似度: %s)" % (s.get("document", ""), s.get("score", "")))
            lines.append("")
    from flask import Response
    return Response("\n".join(lines), content_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=conversation_%d.md" % conv_id})
