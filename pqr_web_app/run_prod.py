import os

from waitress import serve

os.environ.setdefault("PQR_SQLITE_PATH", os.environ.get("PQR_DEFAULT_SQLITE_PATH", r"D:\PQR\data\pqr.db"))

from app import app


if __name__ == "__main__":
    host = os.environ.get("PQR_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("PQR_PORT", "8000")))
    threads = int(os.environ.get("PQR_THREADS", "8"))
    serve(app, host=host, port=port, threads=threads)
