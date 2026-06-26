import os
import uuid
from flask import Blueprint, request, render_template, jsonify
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config
from core.database import DatabaseManager

ocr_bp = Blueprint("ocr", __name__)
db = DatabaseManager(str(config.DB_PATH))


@ocr_bp.route("/", methods=["GET"])
def ocr_page():
    from flask import render_template
    return render_template("ocr.html")


@ocr_bp.route("/api/extract", methods=["POST"])
def extract_text():
    file = request.files.get("image")
    if not file:
        return jsonify({"error": "请上传图片"}), 400

    filename = "%s%s" % (uuid.uuid4().hex, Path(file.filename).suffix)
    file_path = str(config.UPLOAD_DIR / filename)
    file.save(file_path)

    try:
        from PIL import Image
        import pytesseract
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img, lang="chi_sim+eng")
        if text.strip():
            db.save_ocr_result(file_path, text)
            return jsonify({"text": text, "message": "OCR识别成功"})
    except ImportError:
        pass
    except Exception:
        pass

    return jsonify({"text": "", "message": "未能识别文字，请安装pytesseract: pip install pytesseract"})


@ocr_bp.route("/api/history", methods=["GET"])
def ocr_history():
    conn = db.get_connection()
    rows = conn.execute("SELECT * FROM ocr_results ORDER BY created_at DESC LIMIT 50").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])
