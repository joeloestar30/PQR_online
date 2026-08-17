# PQR Web App Build Spec

## Objective

Build a web version of the Preliminary Quake Report workflow while preserving the current Google Sheets behavior: Submit, Search, Update, Clear, pending-PQR monitoring, and auditability.

The first production-ready version uses Flask and SQLite. The data model is intentionally portable to PostgreSQL.

## Exact Data Fields

### Stations

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `station_code` | text | yes | Short code, unique. Example: `BBP`. |
| `station_name` | text | yes | Full station name. |
| `region_code` | text | yes | One of `NL`, `SL`, `VIS`, `MIN`. |
| `is_active` | boolean integer | yes | `1` active, `0` inactive. |

### Earthquake Events

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `event_key` | text | yes | PHIVOLCS first-column Date-Time (Philippine Time) converted to UTC as `YYYYMMDDHHMM`; append `_Location (Province)` for same-minute duplicates when the PHIVOLCS reference location provides it. |
| `event_datetime_utc` | text | yes | ISO-8601 UTC timestamp, stored as `YYYY-MM-DDTHH:MM:SSZ`. Source input is PHIVOLCS Date-Time (Philippine Time). |
| `latitude` | real | no | PHIVOLCS latitude. |
| `longitude` | real | no | PHIVOLCS longitude. |
| `depth_km` | real | no | PHIVOLCS depth. |
| `magnitude` | real | no | PHIVOLCS magnitude. |
| `reference_location` | text | yes | Reference location from PHIVOLCS. |
| `region_code` | text | yes | One of `NL`, `SL`, `VIS`, `MIN`. |
| `source` | text | yes | Default `PHIVOLCS`. |
| `status` | text | yes | `open`, `closed`, or `cancelled`. |

### PQR Reports

These preserve the current `Data` sheet columns.

| Current Sheet Column | Database Field | Type | Required |
| --- | --- | --- | --- |
| A Name | `station_id` via station | integer | yes |
| B Station officers Initial | `officer_initials` | text | yes |
| C Event Time (UTC) | `event_id` via event | integer | yes |
| D P-Polarity | `p_polarity` | text | no |
| E P-Arrival | `p_arrival` | text UTC/time | no |
| F S | `s_marker` | text | no |
| G S-Arrival | `s_arrival` | text UTC/time | no |
| H Amplitude | `amplitude` | real | no |
| I Duration | `duration` | real | no |
| J Type | `event_type` | text | no |
| K Reserved/blank | `reserved_k` | text | no |
| L Remarks | `remarks` | text | yes |
| M Observed Intensities | `observed_intensities` | text | no |
| N Instrumental Intensities | `instrumental_intensities` | text | no |
| O Verified Areas without Intensities | `verified_areas_without_intensities` | text | no |
| P Submitted | `submitted_at` | text UTC | yes |
| Q Updated | `updated_at` | text UTC | no |

One report is allowed per event and station: `UNIQUE(event_id, station_id)`.

## User Roles

| Role | Capabilities |
| --- | --- |
| `admin` | Manage users, stations, events, imports, reports, audit logs, and exports. |
| `duty_officer` | Create events, submit PQRs, update PQRs inside the 22-hour window, view dashboard, import/export. |
| `station_user` | Submit and update PQRs for assigned station inside the 22-hour window; view own station reports. |
| `reviewer` | Read dashboard, reports, pending submissions, and audit logs; export data. |
| `read_only` | Read dashboard and reports only. |

The scaffold includes simple local login seeded with development users. A production deployment should connect this to PHIVOLCS identity management or Google Workspace SSO.

## Timezone Rules

1. Store all event times, submitted times, updated times, and audit times in UTC.
2. Use ISO-8601 UTC strings internally: `YYYY-MM-DDTHH:MM:SSZ`.
3. The 22-hour update window is calculated from `earthquake_events.event_datetime_utc`.
4. Input forms accept PHIVOLCS Date-Time (Philippine Time) values from `https://earthquake.phivolcs.dost.gov.ph/`.
5. The first PHIVOLCS column, Date-Time (Philippine Time), is converted to UTC for `event_key` using `YYYYMMDDHHMM`.
6. Example: `2026-06-30 08:15` Philippine Time becomes UTC event key `202606300015`.
7. Existing Google Sheet event keys such as `202606290151` are treated as already-converted UTC keys during import unless a Philippine Time source column is provided.
8. The UI may display UTC first, with local display added later. UTC remains the source of truth.

## Migration / Import Path

### Phase A: Existing Google Sheets Stabilization

1. Keep the current Google Sheet online.
2. Harden Apps Script with duplicate checks, validation, dynamic row lookup, audit logging, and 22-hour enforcement.
3. Export the current `Data` sheet as CSV.
4. Export or copy the BBP/event list sheet as CSV.
5. Export station list as CSV or seed it manually.

### Phase B: Web App Import

1. Import stations into `stations`.
2. Import BBP/event-list rows into `earthquake_events`, or use the built-in PHIVOLCS parser at `/events/list`.
3. Generate missing `event_key` values by converting PHIVOLCS Date-Time (Philippine Time) to UTC `YYYYMMDDHHMM`.
4. Import Data sheet rows into `pqr_reports`.
5. Upsert events and stations when imported PQR rows refer to unknown keys.
6. Build `pqr_required_submissions` from event region and active stations.
7. Verify duplicate PQR rows before final import.
8. Keep the Google Sheet read-only for a short transition period.

The scaffold includes `scripts/import_sheet_csv.py` for Data-sheet CSV imports.

## PHIVOLCS Automatic Parsing

The app fetches `https://earthquake.phivolcs.dost.gov.ph/` when the user opens Events List and parses the public earthquake table columns:

```text
Date-Time (Philippine Time), Latitude, Longitude, Depth, Magnitude, Location
```

Parsed events are filtered to the active 22-hour PQR window and previewed before import. The Date-Time column is converted from Philippine Time to UTC `YYYYMMDDHHMM`. If two events share the same converted UTC minute, the app appends a location suffix, for example:

```text
202606300011_Lubang (Occidental Mindoro)
202606300011_Capoocan (Leyte)
```

## Google Sheets Submission Sync

When the user clicks **Submit Selected PQR(s)** on the PQR Submission page, each successfully saved local PQR report is queued for Google Sheets sync. The background worker appends queued reports to:

```text
Spreadsheet ID: 1wRTj-K2aSzPh5cHRdE5Si-oVxFQ0jJk12PKjhzXVc3s
Tab sheet: Data
Range: Data!A:Q
```

The appended columns match the existing Data sheet layout: station code, station officer initials, event key, P/S parameters, remarks, intensity fields, submitted time, and updated time.

The app uses a Google service account. Configure either `GOOGLE_SERVICE_ACCOUNT_FILE` with the path to the JSON key file, or `GOOGLE_SERVICE_ACCOUNT_JSON` with the full JSON content. The target spreadsheet must be shared with the service account email as an editor.

## Background Worker

For multi-user use, run the web app and background worker as separate processes:

```powershell
python run_prod.py
python run_worker.py
```

The worker automatically:

```text
- Syncs recent PHIVOLCS events into the local database.
- Closes expired events and reconciles required submissions.
- Retries pending or failed Google Sheets appends.
```

Default intervals:

```text
PQR_PHIVOLCS_SYNC_SECONDS=15
PQR_GOOGLE_SYNC_SECONDS=60
```

Use `python run_worker.py --once` to run one cycle and exit.

## Complete Runnable Structure

```text
pqr_web_app/
|-- app.py
|-- requirements.txt
|-- BUILD_SPEC.md
|-- database/
|   |-- schema.sql
|   `-- pqr.db
|-- modules/
|   |-- auth.py
|   |-- db.py
|   |-- imports.py
|   |-- timeutils.py
|   `-- validation.py
|-- scripts/
|   `-- import_sheet_csv.py
|-- templates/
|   |-- base.html
|   |-- dashboard.html
|   |-- event_form.html
|   |-- login.html
|   |-- pqr_edit.html
|   |-- pqr_form.html
|   `-- pqr_list.html
`-- static/
    `-- css/
        `-- style.css
```

## Development Runbook

```powershell
cd "C:\Users\joelo\Documents\PQR project\pqr_web_app"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

Seeded development users:

| Username | Password | Role |
| --- | --- | --- |
| `admin` | `admin123` | `admin` |
| `duty` | `duty123` | `duty_officer` |
| `bbp` | `bbp123` | `station_user` |
| `reviewer` | `reviewer123` | `reviewer` |

Change these before real deployment.
