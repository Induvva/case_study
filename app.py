"""Entry point of the Railway Reservation System.

Frontend  -> frontend/   (templates, CSS, JavaScript)
Backend   -> backend/    (Flask pages + REST API under /api)
Database  -> database/   (SQLite schema) filled from datasets/*.csv
"""
import os

from backend import create_app
from backend.database import init_db  # noqa: F401  (re-exported for the tests)
from backend.services import validate_booking  # noqa: F401  (re-exported for the tests)

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
