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
    from web.routes.settings import settings_bp
    from web.routes.conversations import conversations_bp
    from web.routes.knowledge_bases import kb_bp
    from web.routes.summary import summary_bp
    from web.routes.batch_qa import batch_bp
    from web.routes.scheduler import scheduler_bp
    from web.routes.stats import stats_bp
    from web.routes.ocr import ocr_bp
    from web.routes.users import users_bp

    app.register_blueprint(upload_bp, url_prefix="/upload")
    app.register_blueprint(documents_bp, url_prefix="/documents")
    app.register_blueprint(qa_bp, url_prefix="/qa")
    app.register_blueprint(finetune_bp, url_prefix="/finetune")
    app.register_blueprint(settings_bp, url_prefix="/settings")
    app.register_blueprint(conversations_bp, url_prefix="/conversations")
    app.register_blueprint(kb_bp, url_prefix="/knowledge-bases")
    app.register_blueprint(summary_bp, url_prefix="/summary")
    app.register_blueprint(batch_bp, url_prefix="/batch-qa")
    app.register_blueprint(scheduler_bp, url_prefix="/scheduler")
    app.register_blueprint(stats_bp, url_prefix="/stats")
    app.register_blueprint(ocr_bp, url_prefix="/ocr")
    app.register_blueprint(users_bp, url_prefix="/users")

    @app.route("/")
    def index():
        from flask import render_template
        return render_template("index.html")

    return app
