import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import get_db


EVENT_FINGERPRINT_FIELDS = (
    "event_datetime_utc",
    "reference_location",
    "magnitude",
    "depth_km",
    "latitude",
    "longitude",
)


def event_fingerprint(row):
    return tuple(row[field] for field in EVENT_FINGERPRINT_FIELDS)


def canonical_event_key(row):
    return str(row["event_key"]).removesuffix("_1")


def choose_canonical(rows):
    return sorted(rows, key=lambda row: (row["created_at"] or "", row["id"]))[0]


def cleanup_duplicate_events(dry_run=True):
    conn = get_db()
    try:
        events = conn.execute(
            """
            SELECT id, event_key, event_datetime_utc, latitude, longitude, depth_km,
                   magnitude, reference_location, region_code, source, status, created_at
            FROM earthquake_events
            ORDER BY created_at, id
            """
        ).fetchall()
        groups = defaultdict(list)
        for row in events:
            groups[event_fingerprint(row)].append(row)

        duplicate_groups = [rows for rows in groups.values() if len(rows) > 1]
        result = {
            "duplicate_groups": len(duplicate_groups),
            "events_deleted": 0,
            "required_moved": 0,
            "required_deleted": 0,
            "reports_moved": 0,
            "reports_deleted": 0,
            "canonical_keys_updated": 0,
        }

        for rows in duplicate_groups:
            canonical = choose_canonical(rows)
            canonical_id = canonical["id"]
            duplicate_ids = [row["id"] for row in rows if row["id"] != canonical_id]

            target_key = canonical_event_key(canonical)
            should_update_key = canonical["event_key"] != target_key
            if should_update_key:
                print(f"EVENT KEY {canonical['event_key']} -> {target_key}")
            print(
                f"MERGE {len(rows)} rows into event {canonical_id} "
                f"({target_key}) from duplicate IDs {duplicate_ids}"
            )

            for duplicate_id in duplicate_ids:
                required_rows = conn.execute(
                    """
                    SELECT id, station_id, status
                    FROM pqr_required_submissions
                    WHERE event_id = ?
                    """,
                    (duplicate_id,),
                ).fetchall()
                for required in required_rows:
                    existing = conn.execute(
                        """
                        SELECT id, status
                        FROM pqr_required_submissions
                        WHERE event_id = ? AND station_id = ?
                        """,
                        (canonical_id, required["station_id"]),
                    ).fetchone()
                    if existing:
                        result["required_deleted"] += 1
                        if existing["status"] != "submitted" and required["status"] == "submitted":
                            if not dry_run:
                                conn.execute(
                                    "UPDATE pqr_required_submissions SET status = 'submitted' WHERE id = ?",
                                    (existing["id"],),
                                )
                        if not dry_run:
                            conn.execute(
                                "DELETE FROM pqr_required_submissions WHERE id = ?",
                                (required["id"],),
                            )
                    else:
                        result["required_moved"] += 1
                        if not dry_run:
                            conn.execute(
                                "UPDATE pqr_required_submissions SET event_id = ? WHERE id = ?",
                                (canonical_id, required["id"]),
                            )

                report_rows = conn.execute(
                    """
                    SELECT id, station_id
                    FROM pqr_reports
                    WHERE event_id = ?
                    """,
                    (duplicate_id,),
                ).fetchall()
                for report in report_rows:
                    existing = conn.execute(
                        """
                        SELECT id
                        FROM pqr_reports
                        WHERE event_id = ? AND station_id = ?
                        """,
                        (canonical_id, report["station_id"]),
                    ).fetchone()
                    if existing:
                        result["reports_deleted"] += 1
                        if not dry_run:
                            conn.execute(
                                "UPDATE pqr_audit_logs SET report_id = ? WHERE report_id = ?",
                                (existing["id"], report["id"]),
                            )
                            conn.execute("DELETE FROM pqr_reports WHERE id = ?", (report["id"],))
                    else:
                        result["reports_moved"] += 1
                        if not dry_run:
                            conn.execute(
                                "UPDATE pqr_reports SET event_id = ? WHERE id = ?",
                                (canonical_id, report["id"]),
                            )

                result["events_deleted"] += 1
                if not dry_run:
                    conn.execute("DELETE FROM earthquake_events WHERE id = ?", (duplicate_id,))

            if should_update_key:
                result["canonical_keys_updated"] += 1
                if not dry_run:
                    conn.execute(
                        "UPDATE earthquake_events SET event_key = ? WHERE id = ?",
                        (target_key, canonical_id),
                    )

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Merge duplicate earthquake_events rows with identical event data.")
    parser.add_argument("--apply", action="store_true", help="Apply changes. Without this flag, runs as dry-run.")
    args = parser.parse_args()
    result = cleanup_duplicate_events(dry_run=not args.apply)
    mode = "APPLIED" if args.apply else "DRY RUN"
    print(mode)
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
