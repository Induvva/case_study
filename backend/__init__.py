"""Backend package - creates the Flask application.

Three layers live in this project:
  frontend/  -> HTML templates, CSS and JavaScript (what the user sees)
  backend/   -> Flask: page routes, REST API and business logic
  database/  -> SQLite schema;  datasets/ -> CSV files that fill the database
"""
import os
import secrets

from flask import Flask

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, "frontend", "templates"),
        static_folder=os.path.join(BASE_DIR, "frontend", "static"),
    )
    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["DATABASE"] = os.environ.get(
        "DATABASE_PATH", os.path.join(BASE_DIR, "railway.db")
    )

    from . import api, database, routes

    database.init_app(app)
    routes.register(app)
    app.register_blueprint(api.bp)
    database.init_db()
    return app
