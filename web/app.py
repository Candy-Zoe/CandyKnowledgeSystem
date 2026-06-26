from flask import Flask
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_SIZE

    from web.routes.upload import upload_bp
    from web.routes.documents import documents_bp
    from web.routes.qa import qa_bp
    from web.routes.finetune import finetune_bp

    app.register_blueprint(upload_bp, url_prefix="/upload")
    app.register_blueprint(documents_bp, url_prefix="/documents")
    app.register_blueprint(qa_bp, url_prefix="/qa")
    app.register_blueprint(finetune_bp, url_prefix="/finetune")

    @app.route("/")
    def index():
        from flask import render_template
        return render_template("index.html")

    return app
