from flask import Blueprint, request, render_template, jsonify
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config
from core.api_client import APIClient

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/", methods=["GET"])
def settings_page():
    from flask import render_template
    settings = config.load_settings()
    providers = APIClient.list_providers()
    return render_template("settings.html", settings=settings, providers=providers)


@settings_bp.route("/api/get", methods=["GET"])
def get_settings():
    settings = config.load_settings()
    return jsonify(settings)


@settings_bp.route("/api/save", methods=["POST"])
def save_settings():
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效的数据"}), 400

    current = config.load_settings()
    current.update(data)
    config.save_settings(current)

    return jsonify({"message": "设置已保存"})


@settings_bp.route("/api/test-api", methods=["POST"])
def test_api():
    data = request.get_json()
    provider = data.get("provider", "qwen")
    api_key = data.get("api_key", "")
    base_url = data.get("base_url", "")
    model = data.get("model", "")

    if not api_key:
        return jsonify({"error": "请输入API Key"}), 400

    try:
        client = APIClient(provider=provider, api_key=api_key, base_url=base_url, model=model)
        result = client.chat([{"role": "user", "content": "你好，请回复OK"}], max_tokens=10)
        return jsonify({"message": "连接成功", "response": result})
    except Exception as e:
        return jsonify({"error": "连接失败: %s" % str(e)}), 500


@settings_bp.route("/api/providers", methods=["GET"])
def list_providers():
    return jsonify(APIClient.list_providers())
