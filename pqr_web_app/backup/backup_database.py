import argparse
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = APP_DIR / "database" / "pqr.db"
DEFAULT_BACKUP_DIR = Path(os.environ.get("PQR_BACKUP_DIR", r"D:\PQR\backups"))


def timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_sqlite(source_path, backup_dir):
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"SQLite database not found: {source}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / f"pqr_sqlite_{timestamp()}.db"
    source_conn = sqlite3.connect(source)
    try:
        destination_conn = sqlite3.connect(destination)
        try:
            source_conn.backup(destination_conn)
        finally:
            destination_conn.close()
    finally:
        source_conn.close()
    return destination


def backup_postgres(database_url, backup_dir):
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / f"pqr_postgres_{timestamp()}.dump"
    command = ["pg_dump", "--format=custom", "--file", str(destination), database_url]
    subprocess.run(command, check=True)
    return destination


def main():
    parser = argparse.ArgumentParser(description="Back up the PQR database.")
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    parser.add_argument("--sqlite-path", default=os.environ.get("PQR_SQLITE_PATH", str(DEFAULT_SQLITE_PATH)))
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    args = parser.parse_args()

    backup_dir = Path(args.backup_dir)
    if args.database_url.strip():
        destination = backup_postgres(args.database_url.strip(), backup_dir)
    else:
        destination = backup_sqlite(args.sqlite_path, backup_dir)

    latest = backup_dir / destination.name.replace(destination.stem, "latest")
    shutil.copy2(destination, latest)
    print(f"Backup created: {destination}")
    print(f"Latest copy: {latest}")


if __name__ == "__main__":
    main()
