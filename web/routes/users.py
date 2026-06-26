import hashlib
from flask import Blueprint, request, render_template, jsonify, session
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config
from core.database import DatabaseManager

users_bp = Blueprint("users", __name__)
db = DatabaseManager(str(config.DB_PATH))


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


@users_bp.route("/", methods=["GET"])
def users_page():
    from flask import render_template
    users = db.list_users()
    return render_template("users.html", users=users)


@users_bp.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    role = data.get("role", "user")

    if not username or not password:
        return jsonify({"error": "请填写用户名和密码"}), 400

    if db.get_user(username):
        return jsonify({"error": "用户名已存在"}), 400

    user_id = db.create_user(username, hash_password(password), role)
    return jsonify({"id": user_id, "message": "注册成功"})


@users_bp.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username", "")
    password = data.get("password", "")

    user = db.get_user(username)
    if not user or user["password_hash"] != hash_password(password):
        return jsonify({"error": "用户名或密码错误"}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]
    return jsonify({"message": "登录成功", "user": {"id": user["id"], "username": user["username"], "role": user["role"]}})


@users_bp.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "已退出登录"})


@users_bp.route("/api/me", methods=["GET"])
def me():
    if "user_id" in session:
        return jsonify({"logged_in": True, "user_id": session["user_id"], "username": session["username"], "role": session["role"]})
    return jsonify({"logged_in": False})


@users_bp.route("/api/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    if session.get("role") != "admin":
        return jsonify({"error": "需要管理员权限"}), 403
    db.delete_user(user_id)
    return jsonify({"message": "用户已删除"})
