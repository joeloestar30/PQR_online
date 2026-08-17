import os
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("PQR_SQLITE_PATH", os.environ.get("PQR_DEFAULT_SQLITE_PATH", r"D:\PQR\data\pqr.db"))

from app import app

app.config["TEMPLATES_AUTO_RELOAD"] = True


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
