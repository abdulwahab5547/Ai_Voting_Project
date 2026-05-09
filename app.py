"""Flask entry point for the Smart Digital Voting Machine."""
from flask import Flask

from config import Config, ensure_dirs
from core.db import init_db
from core.esp32 import esp32
from routes.home import bp as home_bp
from routes.admin import bp as admin_bp
from routes.voter import bp as voter_bp
from routes.booth import bp as booth_bp
from routes.results import bp as results_bp


def create_app() -> Flask:
    ensure_dirs()
    init_db()

    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)

    @app.context_processor
    def inject_globals():
        return {"election_title": Config.ELECTION_TITLE}

    app.register_blueprint(home_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(voter_bp, url_prefix="/voter")
    app.register_blueprint(booth_bp, url_prefix="/booth")
    app.register_blueprint(results_bp, url_prefix="/results")

    esp32.connect()
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
