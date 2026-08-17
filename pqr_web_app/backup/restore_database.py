import argparse
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = APP_DIR / "database" / "pqr.db"


def timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def validate_sqlite_backup(path):
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA integrity_check").fetchone()
    finally:
        conn.close()


def restore_sqlite(backup_path, target_path, force):
    backup = Path(backup_path)
    target = Path(target_path)
    if not backup.exists():
        raise FileNotFoundError(f"Backup file not found: {backup}")
    validate_sqlite_backup(backup)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        safety_copy = target.with_name(f"{target.stem}_before_restore_{timestamp()}{target.suffix}")
        shutil.copy2(target, safety_copy)
        if not force:
            raise RuntimeError(
                f"Current database was copied to {safety_copy}. "
                "Re-run with --force to overwrite the active database."
            )
    shutil.copy2(backup, target)
    return target


def restore_postgres(backup_path, database_url, clean):
    backup = Path(backup_path)
    if not backup.exists():
        raise FileNotFoundError(f"Backup file not found: {backup}")
    command = ["pg_restore", "--dbname", database_url]
    if clean:
        command.append("--clean")
    command.append(str(backup))
    subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser(description="Restore a PQR database backup.")
    parser.add_argument("backup_file")
    parser.add_argument("--sqlite-path", default=os.environ.get("PQR_SQLITE_PATH", str(DEFAULT_SQLITE_PATH)))
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--force", action="store_true", help="Overwrite the active SQLite database.")
    parser.add_argument("--clean", action="store_true", help="Drop PostgreSQL objects before restore.")
    args = parser.parse_args()

    if args.database_url.strip():
        restore_postgres(args.backup_file, args.database_url.strip(), args.clean)
        print("PostgreSQL restore completed.")
    else:
        target = restore_sqlite(args.backup_file, args.sqlite_path, args.force)
        print(f"SQLite restore completed: {target}")


if __name__ == "__main__":
    main()
