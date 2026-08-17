import csv
import hashlib
import json

from modules.timeutils import (
    normalize_timestamp_to_utc_iso,
    parse_datetime_local_as_utc,
    parse_event_key_to_utc,
    phivolcs_datetime_to_utc_key,
    utc_now,
)

MISSING_OFFICER_PLACEHOLDER = "IMPORTED-NO-OFFICER"
MISSING_OFFICER_ONLY_PROBLEM = "Missing station officer initials"


def import_data_sheet_csv(conn, csv_path, default_region="NL"):
    with open(csv_path, newline="", encoding="utf-8-sig") as file:
        return import_data_sheet_rows(conn, csv.DictReader(file), default_region=default_region)


def import_data_sheet_rows(conn, rows, default_region="NL", invalid_recorder=None, sync_run_id=None):
    stats = {
        "imported": 0,
        "skipped": 0,
        "skipped_duplicates": 0,
        "skipped_app_submitted": 0,
        "invalid": 0,
        "created_events": 0,
        "created_stations": 0,
    }
    import_time = utc_now()
    for raw_index, raw_row in enumerate(rows, start=2):
        row = normalize_import_row(raw_row)
        sheet_row_number = _sheet_row_number(raw_row, raw_index)
        report_id = row.get("report_id", "").strip()
        if report_id:
            stats["skipped"] += 1
            stats["skipped_app_submitted"] += 1
            continue

        invalid_reasons = import_row_invalid_reasons(row)

        if invalid_reasons:
            if can_accept_missing_officer_only(invalid_reasons):
                row["officer"] = MISSING_OFFICER_PLACEHOLDER
            else:
                stats["skipped"] += 1
                stats["invalid"] += 1
                if invalid_recorder:
                    invalid_recorder(conn, sync_run_id, sheet_row_number, raw_row, row, "; ".join(invalid_reasons))
                continue

        if not invalid_reasons:
            pass
        elif not can_accept_missing_officer_only(invalid_reasons):
            stats["skipped"] += 1
            stats["invalid"] += 1
            if invalid_recorder:
                invalid_recorder(conn, sync_run_id, sheet_row_number, raw_row, row, "; ".join(invalid_reasons))
            continue

        station_code = row.get("station_code", "").strip()
        event_key = row.get("event_key", "").strip()
        remarks = row.get("remarks", "").strip()
        officer = row.get("officer", "").strip()
        station_id, created_station = ensure_station(conn, station_code, default_region, return_created=True)
        event_id, created_event = ensure_event(conn, event_key, default_region, return_created=True)
        stats["created_stations"] += 1 if created_station else 0
        stats["created_events"] += 1 if created_event else 0
        submitted_at = normalize_timestamp_to_utc_iso(row.get("submitted"), fallback=import_time)
        updated_at = normalize_timestamp_to_utc_iso(row.get("updated"))
        existing_report = conn.execute(
            """
            SELECT id
            FROM pqr_reports
            WHERE event_id = ? AND station_id = ?
            """,
            (event_id, station_id),
        ).fetchone()
        if existing_report:
            stats["skipped"] += 1
            stats["skipped_duplicates"] += 1
            continue

        conn.execute(
            """
            INSERT INTO pqr_reports (
                event_id, station_id, officer_initials, p_polarity, p_arrival,
                s_marker, s_arrival, amplitude, duration, event_type, reserved_k,
                remarks, observed_intensities, instrumental_intensities,
                verified_areas_without_intensities, submitted_at, updated_at,
                sheet_sync_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'synced')
            """,
            (
                event_id,
                station_id,
                officer,
                row.get("p_polarity"),
                row.get("p_arrival"),
                row.get("s_marker"),
                row.get("s_arrival"),
                row.get("amplitude") or None,
                row.get("duration") or None,
                row.get("event_type"),
                row.get("reserved_k") or None,
                remarks,
                row.get("observed_intensities"),
                row.get("instrumental_intensities"),
                row.get("verified_areas_without_intensities"),
                submitted_at,
                updated_at,
            ),
        )
        stats["imported"] += 1
    return stats


def can_accept_missing_officer_only(reasons):
    return list(reasons) == [MISSING_OFFICER_ONLY_PROBLEM]


def import_row_invalid_reasons(row):
    reasons = []
    if not row.get("station_code", "").strip():
        reasons.append("Missing station code")
    if not row.get("officer", "").strip():
        reasons.append("Missing station officer initials")
    if not row.get("remarks", "").strip():
        reasons.append("Missing remarks")
    event_key = row.get("event_key", "").strip()
    if not event_key:
        reasons.append("Missing event time")
    elif not is_valid_import_event_key(event_key):
        reasons.append("Invalid event time (expected YYYYMMDDHHMM)")
    return reasons


def import_row_hash(row):
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, ensure_ascii=True, default=str).encode("utf-8")
    ).hexdigest()


def _sheet_row_number(raw_row, fallback):
    try:
        return int(raw_row.get("__sheet_row_number") or fallback)
    except (AttributeError, TypeError, ValueError):
        return fallback


def normalize_import_row(row):
    return {
        "station_code": get_first(row, "Name", "Station Code", "Station"),
        "officer": get_first(row, "Station officers Initial", "Station Officer Initials", "Officer Initials"),
        "event_key": get_first(row, "Event Time (UTC)", "Event Key (UTC)", "Event Key", "Event ID"),
        "p_polarity": get_first(row, "P-Polarity", "P Polarity"),
        "reserved_k": get_first(row, "Reserved", "Reserved K"),
        "p_arrival": get_first(row, "P-Arrival", "P-Arrival (HHMMSS.SS)", "P-Arrival (s)"),
        "s_marker": get_first(row, "S"),
        "s_arrival": get_first(row, "S-Arrival", "S-Arrival (HHMMSS.SS)", "S-Arrival (s)"),
        "amplitude": get_first(row, "Amplitude"),
        "duration": get_first(row, "Duration", "Duration (s)"),
        "event_type": get_first(row, "Type"),
        "remarks": get_first(row, "Remarks"),
        "observed_intensities": get_first(row, "OBSERVED INTENSITIES", "Observed Intensities"),
        "instrumental_intensities": get_first(row, "INSTRUMENTAL INTENSITIES", "Instrumental Intensities"),
        "verified_areas_without_intensities": get_first(row, "Verified Areas without Intensities"),
        "submitted": get_first(row, "Submitted"),
        "updated": get_first(row, "Updated"),
        "report_id": get_first(row, "Report ID", "ID", "PQR Report ID", "__report_id"),
    }


def get_first(row, *keys):
    for key in keys:
        if key in row and row.get(key) is not None:
            return str(row.get(key) or "").strip()
    lower_map = {str(existing).strip().lower(): existing for existing in row.keys()}
    for key in keys:
        actual = lower_map.get(key.lower())
        if actual is not None and row.get(actual) is not None:
            return str(row.get(actual) or "").strip()
    return ""


def is_valid_import_event_key(event_key):
    compact_key = str(event_key or "").strip()[:12]
    return bool(parse_event_key_to_utc(compact_key))


def ensure_station(conn, station_code, region_code, return_created=False):
    row = conn.execute("SELECT id FROM stations WHERE station_code = ?", (station_code,)).fetchone()
    if row:
        return (row["id"], False) if return_created else row["id"]
    cursor = conn.execute(
        """
        INSERT INTO stations (station_code, station_name, region_code)
        VALUES (?, ?, ?)
        """,
        (station_code, station_code + " Station", region_code),
    )
    return (cursor.lastrowid, True) if return_created else cursor.lastrowid


def ensure_event(conn, event_key, region_code, return_created=False):
    row = conn.execute("SELECT id FROM earthquake_events WHERE event_key = ?", (event_key,)).fetchone()
    if row:
        return (row["id"], False) if return_created else row["id"]
    event_datetime = parse_event_key_to_utc(event_key) or utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    compact_key = str(event_key or "").strip()[:12]
    if len(compact_key) == 12 and compact_key.isdigit():
        row = conn.execute(
            """
            SELECT id
            FROM earthquake_events
            WHERE event_key = ?
               OR event_key LIKE ?
               OR event_datetime_utc = ?
            ORDER BY
                CASE
                    WHEN event_key = ? THEN 0
                    WHEN event_key LIKE ? THEN 1
                    ELSE 2
                END,
                id
            LIMIT 1
            """,
            (compact_key, f"{compact_key}_%", event_datetime, compact_key, f"{compact_key}_%"),
        ).fetchone()
        if row:
            return (row["id"], False) if return_created else row["id"]
    cursor = conn.execute(
        """
        INSERT INTO earthquake_events (
            event_key, event_datetime_utc, reference_location, region_code
        )
        VALUES (?, ?, ?, ?)
        """,
        (event_key, event_datetime, "Imported from Google Sheet", region_code),
    )
    return (cursor.lastrowid, True) if return_created else cursor.lastrowid


def ensure_phivolcs_event(conn, phivolcs_datetime_ph, reference_location, region_code):
    event_key = phivolcs_datetime_to_utc_key(phivolcs_datetime_ph)
    row = conn.execute("SELECT id FROM earthquake_events WHERE event_key = ?", (event_key,)).fetchone()
    if row:
        return row["id"]
    cursor = conn.execute(
        """
        INSERT INTO earthquake_events (
            event_key, event_datetime_utc, reference_location, region_code
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            event_key,
            parse_datetime_local_as_utc(phivolcs_datetime_ph),
            reference_location or "Imported from PHIVOLCS",
            region_code,
        ),
    )
    return cursor.lastrowid
