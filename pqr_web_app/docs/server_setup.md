# PQR Server Setup

This setup keeps the original local developer workflow intact. `run_dev.py` still uses `database/pqr.db` unless you choose a different path.

## Recommended Desktop Layout

Use `C:` for the app and `D:` for data:

```text
C:\Users\joelo\Documents\PQR project\pqr_web_app
D:\PQR\data\pqr.db
D:\PQR\backups
D:\PQR\logs
D:\PQR\exports
```

## Desktop/LAN Pilot

1. Copy `.env.example` to `.env` for your notes.
2. Set these Windows environment variables before production use:

```powershell
$env:SECRET_KEY = "replace-with-a-long-random-secret-at-least-32-characters"
$env:PQR_ADMIN_PASSWORD = "replace-with-a-strong-admin-password"
$env:PQR_ADMIN_EMAIL = "admin@example.com"
$env:PQR_GOOGLE_SHEET_ID = "your-google-sheet-id"
$env:GOOGLE_SERVICE_ACCOUNT_JSON = '{"type":"service_account","project_id":"..."}'
```

3. Start the LAN server and worker together:

```powershell
cd "C:\Users\joelo\Documents\PQR project\pqr_web_app"
.\scripts\start_desktop_stack.ps1 -Production
```

Or start them separately:

```powershell
.\scripts\start_server.ps1 -Production
.\scripts\start_worker.ps1 -DbPath "D:\PQR\data\pqr.db" -LogDir "D:\PQR\logs" -Production
```

4. Open the app from the server:

```text
http://127.0.0.1:8000
```

5. Other computers on the same network should use the Desktop's LAN IP:

```text
http://YOUR-DESKTOP-LAN-IP:8000
```

## Original Local Development

The original setup still works:

```powershell
cd "C:\Users\joelo\Documents\PQR project\pqr_web_app"
.\.venv\Scripts\python.exe run_dev.py
```

That serves the app on the existing development port and uses the original local SQLite database unless `PQR_SQLITE_PATH` is set.

## Docker/PostgreSQL Option

For a more server-like environment:

```powershell
cd "C:\Users\joelo\Documents\PQR project\pqr_web_app"
docker compose up -d --build
```

Before using Docker in production, change the PostgreSQL password in `docker-compose.yml` and set a real `SECRET_KEY`, `PQR_ADMIN_PASSWORD`, Google Sheet ID, and Google service account JSON in `.env`.

## Backups

Create a SQLite backup:

```powershell
.\.venv\Scripts\python.exe backup\backup_database.py --sqlite-path "D:\PQR\data\pqr.db"
```

Restore is intentionally two-step. First run creates a safety copy and stops:

```powershell
.\.venv\Scripts\python.exe backup\restore_database.py "D:\PQR\backups\pqr_sqlite_YYYYMMDD_HHMMSS.db" --sqlite-path "D:\PQR\data\pqr.db"
```

Then re-run with `--force` if the safety copy is correct:

```powershell
.\.venv\Scripts\python.exe backup\restore_database.py "D:\PQR\backups\pqr_sqlite_YYYYMMDD_HHMMSS.db" --sqlite-path "D:\PQR\data\pqr.db" --force
```

## Network Notes

For stations outside your local network, prefer VPN access to this Desktop or move the same app to a hosted server. Avoid exposing plain HTTP directly to the public internet. If it must be public, put HTTPS in front of it with a reverse proxy such as Nginx, Caddy, Cloudflare Tunnel, or an official office gateway.
