import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from modules.db import get_db, init_db, is_postgres
from modules.google_sheets import google_sheets_configured


REQUIRED_PRODUCTION_ENV = (
    "SECRET_KEY",
    "DATABASE_URL",
    "PQR_GOOGLE_SHEET_ID",
    "PQR_GOOGLE_SHEET_TAB",
)


def fail(message):
    print(f"FAIL: {message}")
    return 1


def ok(message):
    print(f"OK: {message}")


def main():
    if os.environ.get("FLASK_ENV") == "production":
        missing = [name for name in REQUIRED_PRODUCTION_ENV if not os.environ.get(name)]
        if missing:
            return fail("Missing environment variables: " + ", ".join(missing))
        if len(os.environ["SECRET_KEY"]) < 32:
            return fail("SECRET_KEY must be at least 32 characters.")
        if not is_postgres():
            return fail("Production should use PostgreSQL DATABASE_URL.")
        ok("Production environment variables are present.")
    else:
        ok("Running non-production smoke test.")

    init_db()
    conn = get_db()
    try:
        user_count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
        station_count = conn.execute("SELECT COUNT(*) AS count FROM stations").fetchone()["count"]
        admin_count = conn.execute(
            "SELECT COUNT(*) AS count FROM users WHERE role = 'admin' AND is_active = 1"
        ).fetchone()["count"]
    finally:
        conn.close()

    if station_count < 30:
        return fail(f"Expected seeded PQR stations, found {station_count}.")
    ok(f"Stations available: {station_count}")

    if user_count < 1:
        return fail("No users exist.")
    ok(f"Users available: {user_count}")

    if admin_count < 1:
        return fail("No active admin user exists.")
    ok(f"Active admin users: {admin_count}")

    if google_sheets_configured():
        ok("Google Sheets credentials are configured.")
    else:
        return fail("Google Sheets credentials are not configured.")

    print("Smoke deployment checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
