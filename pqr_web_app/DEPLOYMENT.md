# PQR Web App Deployment

This app can run locally with SQLite, then switch to PostgreSQL in production by setting `DATABASE_URL`.

## Recommended Production Setup

- Web service: `gunicorn app:app`
- Worker service: `python run_worker.py`
- Database: Supabase PostgreSQL
- Google Sheets credentials: environment variable, not a committed JSON file

For the Desktop/LAN pilot, use `scripts/start_server.ps1` with SQLite stored on `D:\PQR\data\pqr.db`. This keeps the original `run_dev.py` workflow intact while moving operational data to the larger drive.

## Required Environment Variables

```text
SECRET_KEY=change-this-long-random-value
FLASK_ENV=production
DATABASE_URL=postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require
PQR_ADMIN_USERNAME=admin
PQR_ADMIN_PASSWORD=change-this-before-first-deploy
PQR_ADMIN_DISPLAY_NAME=Administrator
PQR_ADMIN_EMAIL=admin@example.com
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"..."}
PQR_GOOGLE_SHEET_ID=1wRTj-K2aSzPh5cHRdE5Si-oVxFQ0jJk12PKjhzXVc3s
PQR_GOOGLE_SHEET_TAB=Data
PQR_PHIVOLCS_SYNC_SECONDS=15
PQR_GOOGLE_SYNC_SECONDS=60
```

For local development, omit `DATABASE_URL` and the app will use `database/pqr.db`.

For the Desktop/LAN server, omit `DATABASE_URL` and set:

```text
PQR_SQLITE_PATH=D:\PQR\data\pqr.db
```

In production, the app refuses to start when `SECRET_KEY` is missing or shorter than 32 characters. On a fresh production database, it also refuses to create default demo users. Set `PQR_ADMIN_PASSWORD` to create the first admin account.

## Desktop/LAN Server

```powershell
cd "C:\Users\joelo\Documents\PQR project\pqr_web_app"
$env:SECRET_KEY = "replace-with-a-long-random-secret-at-least-32-characters"
$env:PQR_ADMIN_PASSWORD = "replace-with-a-strong-admin-password"
$env:PQR_GOOGLE_SHEET_ID = "your-google-sheet-id"
$env:GOOGLE_SERVICE_ACCOUNT_JSON = '{"type":"service_account","project_id":"..."}'
.\scripts\start_server.ps1 -Production
.\scripts\start_worker.ps1 -DbPath "D:\PQR\data\pqr.db" -LogDir "D:\PQR\logs" -Production
```

See `docs/server_setup.md` for the full Desktop setup and backup workflow.

## GitHub

Create the GitHub repository from the `pqr_web_app` folder, or use the project root and set each host's root directory to `pqr_web_app`.

Do not commit `.env`, `credentials.json`, local SQLite database files, logs, or `.venv`.

## Supabase

1. Create a Supabase project.
2. Open Project Settings -> Database -> Connection string.
3. Copy the Session pooler URI and replace the password placeholder.
4. Add `?sslmode=require` if it is not already present.
5. Use that value as `DATABASE_URL` in both the web service and worker.

The app initializes the PostgreSQL schema at startup and creates the first admin user from `PQR_ADMIN_*` environment variables when the database is empty.

## Render

1. Push `pqr_web_app` to a GitHub repository, or push the project root and set the Render root directory to `pqr_web_app`.
2. In Render, create a Blueprint from `render.yaml`, or create services manually.
3. Set `DATABASE_URL` to the Supabase Postgres connection string on both the web service and worker.
4. Add `GOOGLE_SERVICE_ACCOUNT_JSON` as a secret environment variable on both services.
5. Add `PQR_GOOGLE_SHEET_ID` on both services.
6. Share the destination Google Sheet with the service account email from the JSON credentials.
7. Set `PQR_ADMIN_PASSWORD` before the first deploy.

Manual Render services:

```text
Build Command: pip install -r requirements.txt
Web Start Command: gunicorn app:app
Worker Start Command: python run_worker.py
Health Check Path: /healthz
```

## Railway

1. Create a Railway project from the GitHub repository.
2. Create a web service from the repo with root directory `pqr_web_app` if the repo root is the parent project folder.
3. Set `DATABASE_URL` to the Supabase Postgres connection string.
4. Add the required environment variables above.
5. Configure the web service start command:

```text
gunicorn app:app
```

6. Add a second service from the same repo for the worker with:

```text
python run_worker.py
```

7. Set the same `DATABASE_URL`, `SECRET_KEY`, Google Sheets variables, and sync interval variables on the worker service.

## Notes

- Do not upload `credentials.json` to GitHub or the hosting provider.
- The worker is what keeps PHIVOLCS imports and retry Google Sheet sync running automatically.
- New PQR submissions also attempt one immediate Google Sheets sync during form submit.

## Local Windows Worker Autostart

Register the background worker to start automatically when you log in:

```powershell
cd "C:\Users\joelo\Documents\PQR project\pqr_web_app"
.\scripts\register_worker_task.ps1
```

The script first tries to register a Windows Scheduled Task. If Windows denies that permission, it creates a non-admin Startup folder launcher instead. Both paths call `scripts\start_worker.ps1`, which avoids starting a duplicate worker if one is already running. By default, the worker syncs PHIVOLCS every 15 seconds.

## Production Readiness Checklist

1. Web service is deployed and reachable by HTTPS.
2. Worker service is running.
3. PostgreSQL `DATABASE_URL` is configured.
4. `SECRET_KEY` is set to a strong random value.
5. `PQR_ADMIN_PASSWORD` is not a default password.
6. Google Sheet is shared with the service account email.
7. Only trusted users have `admin` or `duty_officer` roles.

## Smoke Test

Run this after setting production environment variables:

```text
python scripts/smoke_deployment.py
```

The smoke test checks environment variables, database initialization, seeded stations, active admin presence, and Google Sheets credential configuration.
