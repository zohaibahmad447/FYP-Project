# WSGI entry for production (e.g. Gunicorn). Do not use for local SSL debug — use run.py instead.
import os

os.environ.setdefault("FLASK_ENV", "production")

from app import create_app, socketio  # noqa: F401 — socketio is initialized in create_app

app = create_app("production")
