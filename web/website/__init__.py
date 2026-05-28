import os

from flask import Flask

from website import classifier
from website.auth import auth as auth_bp
from website.errors import register_error_handlers
from website.models import close_conn, init_db
from website.views import views as views_bp


MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB cap on request body


def create_app():
    app = Flask(__name__)
    app.url_map.strict_slashes = False
    app.config["SECRET_KEY"] = os.environ.get("JWT_SECRET", "dev-only-change-me")
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

    register_error_handlers(app)
    init_db()
    classifier.boot()

    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)

    app.teardown_appcontext(close_conn)

    return app
