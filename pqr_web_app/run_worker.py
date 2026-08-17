import argparse
import os
import time
from datetime import datetime, timezone

os.environ.setdefault("PQR_SQLITE_PATH", os.environ.get("PQR_DEFAULT_SQLITE_PATH", r"D:\PQR\data\pqr.db"))

from app import init_db, run_google_sheet_import, run_phivolcs_sync, sync_pending_google_reports


def interval_seconds(env_name, default_value):
    try:
        return max(int(os.environ.get(env_name, default_value)), 15)
    except ValueError:
        return default_value


def log(*parts):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(timestamp, *parts, flush=True)


def run_once():
    phivolcs_result = run_phivolcs_sync()
    log(
        "PHIVOLCS:",
        phivolcs_result["status"],
        "imported=" + str(phivolcs_result["imported_count"]),
        phivolcs_result["error_message"],
    )
    sheet_result = sync_pending_google_reports()
    log(
        "Google Sheets:",
        sheet_result["status"],
        "appended=" + str(sheet_result["appended_count"]),
        sheet_result["error_message"],
    )
    import_result = run_google_sheet_import()
    log(
        "Google Sheets Import:",
        import_result["status"],
        "imported=" + str(import_result["stats"]["imported"]),
        "skipped=" + str(import_result["stats"]["skipped"]),
        "invalid=" + str(import_result["stats"]["invalid"]),
        import_result["error_message"],
    )


def run_forever():
    phivolcs_interval = interval_seconds("PQR_PHIVOLCS_SYNC_SECONDS", 15)
    google_interval = interval_seconds("PQR_GOOGLE_SYNC_SECONDS", 60)
    google_import_interval = interval_seconds("PQR_GOOGLE_IMPORT_SECONDS", 900)
    next_phivolcs_at = 0
    next_google_at = 0
    next_google_import_at = 0

    log(
        f"PQR background worker started. PHIVOLCS every {phivolcs_interval}s; "
        f"Google Sheets sync every {google_interval}s; "
        f"Google Sheets import every {google_import_interval}s."
    )
    while True:
        now = time.monotonic()
        if now >= next_phivolcs_at:
            result = run_phivolcs_sync()
            log(
                "PHIVOLCS:",
                result["status"],
                "imported=" + str(result["imported_count"]),
                result["error_message"],
            )
            next_phivolcs_at = time.monotonic() + phivolcs_interval

        now = time.monotonic()
        if now >= next_google_at:
            result = sync_pending_google_reports()
            log(
                "Google Sheets:",
                result["status"],
                "appended=" + str(result["appended_count"]),
                result["error_message"],
            )
            next_google_at = time.monotonic() + google_interval

        now = time.monotonic()
        if now >= next_google_import_at:
            result = run_google_sheet_import()
            log(
                "Google Sheets Import:",
                result["status"],
                "imported=" + str(result["stats"]["imported"]),
                "skipped=" + str(result["stats"]["skipped"]),
                "invalid=" + str(result["stats"]["invalid"]),
                result["error_message"],
            )
            next_google_import_at = time.monotonic() + google_import_interval

        time.sleep(5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run PQR background sync worker.")
    parser.add_argument("--once", action="store_true", help="Run each background job once and exit.")
    args = parser.parse_args()

    init_db()
    if args.once:
        run_once()
    else:
        run_forever()
