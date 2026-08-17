# Google Sheets Sync

The app treats the database as the source of truth. Google Sheets is a reporting/export copy.

## Required Settings

```text
PQR_GOOGLE_SHEET_ID=your-sheet-id
PQR_GOOGLE_SHEET_TAB=Data
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"..."}
```

The destination Sheet must be shared with the service account email found in the JSON credentials.

## How Sync Works

- A PQR submission tries to sync immediately.
- A PQR update queues and syncs the same report row in Google Sheets. The app stores the local report ID in column R so later edits update the existing Sheet row instead of appending duplicates.
- `run_worker.py` retries pending Google Sheet rows.
- The worker also keeps PHIVOLCS events updated.
- Failed Sheet syncs stay in the database with `sheet_sync_status='pending'` or `failed`.

## Worker

Start manually:

```powershell
.\scripts\start_worker.ps1
```

Register autostart:

```powershell
.\scripts\register_worker_task.ps1 -DbPath "D:\PQR\data\pqr.db" -LogDir "D:\PQR\logs" -Production
```

Recommended intervals:

```text
PQR_PHIVOLCS_SYNC_SECONDS=15
PQR_GOOGLE_SYNC_SECONDS=60
```

## Important Rule

Do not let stations submit directly to Google Sheets. Stations should submit through the web app only, so duplicate checks, station rules, 1M exemptions, event clustering, and audit logs all stay consistent.
