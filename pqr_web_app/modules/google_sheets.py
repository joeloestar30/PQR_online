import json
import os
import time
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SPREADSHEET_ID = "1wRTj-K2aSzPh5cHRdE5Si-oVxFQ0jJk12PKjhzXVc3s"
DEFAULT_SHEET_NAME = "Data"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def google_sheets_configured():
    return bool(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or _credentials_file())


def fetch_pqr_sheet_import_rows():
    if not google_sheets_configured():
        raise RuntimeError(
            "Google Sheets credentials are not configured. Set GOOGLE_SERVICE_ACCOUNT_JSON "
            "or GOOGLE_SERVICE_ACCOUNT_FILE, then share the spreadsheet with that service account."
        )
    service = build("sheets", "v4", credentials=_credentials(), cache_discovery=False)
    spreadsheet_id = os.environ.get("PQR_GOOGLE_SHEET_ID", DEFAULT_SPREADSHEET_ID)
    sheet_name = os.environ.get("PQR_GOOGLE_SHEET_TAB", DEFAULT_SHEET_NAME)
    values = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!A:R",
    ).execute().get("values", [])
    if not values:
        return []
    headers = _sheet_import_headers(values[0])
    rows = []
    for sheet_row_number, value_row in enumerate(values[1:], start=2):
        padded = list(value_row) + [""] * max(0, len(headers) - len(value_row))
        row = {headers[index]: padded[index] for index in range(len(headers))}
        if any(str(value).strip() for value in row.values()):
            row["__sheet_row_number"] = sheet_row_number
            rows.append(row)
    return rows


def _sheet_import_headers(header_row):
    fallback = [
        "Name",
        "Station officers Initial",
        "Event Time (UTC)",
        "P-Polarity",
        "Reserved",
        "P-Arrival",
        "S",
        "S-Arrival",
        "Amplitude",
        "Duration",
        "Type",
        "Remarks",
        "OBSERVED INTENSITIES",
        "INSTRUMENTAL INTENSITIES",
        "Verified Areas without Intensities",
        "Submitted",
        "Updated",
        "Report ID",
    ]
    headers = []
    for index, fallback_header in enumerate(fallback):
        header = str(header_row[index]).strip() if index < len(header_row) else ""
        headers.append(header or fallback_header)
    return headers


def append_pqr_reports_to_sheet(conn, report_ids):
    if not report_ids:
        return 0
    if not google_sheets_configured():
        raise RuntimeError(
            "Google Sheets credentials are not configured. Set GOOGLE_SERVICE_ACCOUNT_JSON "
            "or GOOGLE_SERVICE_ACCOUNT_FILE, then share the spreadsheet with that service account."
        )

    rows = fetch_sheet_rows(conn, report_ids)
    if not rows:
        return 0

    service = build("sheets", "v4", credentials=_credentials(), cache_discovery=False)
    spreadsheet_id = os.environ.get("PQR_GOOGLE_SHEET_ID", DEFAULT_SPREADSHEET_ID)
    sheet_name = os.environ.get("PQR_GOOGLE_SHEET_TAB", DEFAULT_SHEET_NAME)

    existing_rows = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!A:R",
    ).execute().get("values", [])
    report_row_index = _sheet_row_index_by_report_id(existing_rows)

    append_rows = []
    update_data = []
    synced_count = 0

    for row in rows:
        report_id = str(row[-1])
        sheet_row = report_row_index.get(report_id)
        if sheet_row is None:
            sheet_row = _find_sheet_row_by_station_event(existing_rows, row)
        if sheet_row is None:
            append_rows.append(row)
        else:
            update_data.append({
                "range": f"'{sheet_name}'!A{sheet_row}:R{sheet_row}",
                "values": [row],
            })

    for chunk in _chunks(update_data, _batch_size()):
        _execute_with_retry(
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "valueInputOption": "USER_ENTERED",
                    "data": chunk,
                },
            )
        )
        synced_count += len(chunk)

    for chunk in _chunks(append_rows, _batch_size()):
        _execute_with_retry(
            service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=f"'{sheet_name}'!A:R",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": chunk},
            )
        )
        synced_count += len(chunk)

    return synced_count


def fetch_sheet_rows(conn, report_ids):
    placeholders = ",".join("?" for _ in report_ids)
    rows = conn.execute(
        f"""
        SELECT pqr_reports.id, stations.station_code, pqr_reports.officer_initials,
               earthquake_events.event_key, pqr_reports.p_polarity, pqr_reports.p_arrival,
               pqr_reports.s_marker, pqr_reports.s_arrival, pqr_reports.amplitude,
               pqr_reports.duration, pqr_reports.event_type, pqr_reports.reserved_k,
               pqr_reports.remarks, pqr_reports.observed_intensities,
               pqr_reports.instrumental_intensities,
               pqr_reports.verified_areas_without_intensities,
               pqr_reports.submitted_at, pqr_reports.updated_at
        FROM pqr_reports
        JOIN earthquake_events ON earthquake_events.id = pqr_reports.event_id
        JOIN stations ON stations.id = pqr_reports.station_id
        WHERE pqr_reports.id IN ({placeholders})
        ORDER BY pqr_reports.id
        """,
        tuple(report_ids),
    ).fetchall()
    return [
        [
            row["station_code"],
            row["officer_initials"],
            row["event_key"],
            row["p_polarity"] or "",
            row["reserved_k"] or "",
            row["p_arrival"] or "",
            row["s_marker"] or "",
            row["s_arrival"] or "",
            _sheet_number(row["amplitude"]),
            _sheet_number(row["duration"]),
            row["event_type"] or "",
            row["remarks"],
            row["observed_intensities"] or "",
            row["instrumental_intensities"] or "",
            row["verified_areas_without_intensities"] or "",
            row["submitted_at"],
            row["updated_at"] or "",
            row["id"],
        ]
        for row in rows
    ]


def _sheet_row_index_by_report_id(rows):
    indexes = {}
    for index, row in enumerate(rows, start=1):
        if len(row) >= 18 and str(row[17]).strip():
            indexes[str(row[17]).strip()] = index
    return indexes


def _find_sheet_row_by_station_event(rows, target_row):
    station_code = str(target_row[0]).strip()
    event_key = str(target_row[2]).strip()
    matched_row = None
    for index, row in enumerate(rows, start=1):
        if len(row) >= 3 and str(row[0]).strip() == station_code and str(row[2]).strip() == event_key:
            matched_row = index
    return matched_row


def _chunks(items, size):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def _batch_size():
    try:
        return max(1, min(int(os.environ.get("PQR_GOOGLE_SHEET_BATCH_SIZE", "200")), 500))
    except ValueError:
        return 200


def _execute_with_retry(request):
    try:
        attempts = max(1, int(os.environ.get("PQR_GOOGLE_SHEET_RETRY_ATTEMPTS", "3")))
    except ValueError:
        attempts = 3
    try:
        base_delay = max(0, float(os.environ.get("PQR_GOOGLE_SHEET_RETRY_DELAY", "5")))
    except ValueError:
        base_delay = 5
    for attempt in range(attempts):
        try:
            return request.execute()
        except HttpError as error:
            if error.resp.status not in {429, 500, 502, 503, 504} or attempt == attempts - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))


def _credentials():
    raw_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw_json:
        info = json.loads(raw_json)
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return service_account.Credentials.from_service_account_file(_credentials_file(), scopes=SCOPES)


def _credentials_file():
    explicit_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if explicit_path:
        return explicit_path
    for filename in ("google-service-account.json", "credentials.json"):
        for directory in (BASE_DIR, Path.cwd()):
            default_path = directory / filename
            if default_path.exists():
                return str(default_path)
    return ""


def _sheet_number(value):
    if value is None:
        return ""
    return value
