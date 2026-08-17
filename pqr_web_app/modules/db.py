import os
import re
import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = Path(os.environ.get("PQR_DEFAULT_SQLITE_PATH", r"D:\PQR\data\pqr.db"))
DB_PATH = Path(os.environ.get("PQR_SQLITE_PATH", DEFAULT_SQLITE_PATH))
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"
POSTGRES_SCHEMA_PATH = BASE_DIR / "database" / "schema_postgres.sql"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_PRODUCTION = os.environ.get("FLASK_ENV") == "production"

STATION_CLUSTERS = {
    "North Luzon Cluster": ("BBP", "BCP", "CVP", "PCP", "PIP", "SIP"),
    "South Luzon Cluster": ("GQP", "QVP", "LQP", "PGP", "TGY"),
    "Visayas Cluster": ("JAP", "IAP", "LLP", "SFPB", "MMP", "PLP", "PPR", "RCP", "SNP", "TBP"),
    "Mindanao Cluster": ("BIP", "CTB", "CGP", "DMP", "DCP", "GSP", "KCP", "SCP", "ZCP"),
}

STATION_REGION_BY_CLUSTER = {
    "North Luzon Cluster": "NL",
    "South Luzon Cluster": "SL",
    "Visayas Cluster": "VIS",
    "Mindanao Cluster": "MIN",
}

CLUSTER_EVENT_REGIONS = {
    "North Luzon Cluster": ("NL", "SL"),
    "South Luzon Cluster": ("NL", "SL", "VIS"),
    "Visayas Cluster": ("SL", "VIS", "MIN"),
    "Mindanao Cluster": ("VIS", "MIN"),
}

STATION_CLUSTER_BY_CODE = {
    code: cluster_name
    for cluster_name, station_codes in STATION_CLUSTERS.items()
    for code in station_codes
}

PQR_STATION_CODES = tuple(code for codes in STATION_CLUSTERS.values() for code in codes)

ID_TABLES = {
    "users",
    "stations",
    "earthquake_events",
    "pqr_reports",
    "pqr_required_submissions",
    "pqr_audit_logs",
    "sync_runs",
    "google_sheet_import_invalid_rows",
    "login_audit_logs",
    "user_station_assignments",
    "messages",
    "message_reads",
    "message_replies",
}


def get_db():
    if is_postgres():
        return get_postgres_db()
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def init_db():
    if not is_postgres():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    if is_postgres():
        with open(POSTGRES_SCHEMA_PATH, "r", encoding="utf-8") as file:
            conn.executescript(file.read())
    else:
        conn.execute("PRAGMA journal_mode = WAL")
        with open(SCHEMA_PATH, "r", encoding="utf-8") as file:
            conn.executescript(file.read())
    migrate_db(conn)
    seed_reference_data(conn)
    conn.commit()
    conn.close()


def is_postgres():
    return DATABASE_URL.startswith(("postgres://", "postgresql://"))


def get_postgres_db():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:
        raise RuntimeError("PostgreSQL deployment requires psycopg. Install requirements.txt.") from error
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return PostgresCompatConnection(conn)


def migrate_db(conn):
    ensure_column(conn, "users", "email", "TEXT")
    ensure_column(conn, "users", "must_change_password", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "users", "password_changed_at", "TEXT")
    ensure_column(conn, "users", "password_reset_at", "TEXT")
    ensure_column(conn, "users", "last_login_at", "TEXT")
    ensure_column(conn, "stations", "is_one_manned", "INTEGER NOT NULL DEFAULT 0")
    added_station_cluster = ensure_column(conn, "stations", "cluster_name", "TEXT")
    ensure_column(conn, "stations", "station_type", "TEXT NOT NULL DEFAULT 'SCSS'")
    ensure_column(conn, "stations", "include_in_pqr_compliance", "INTEGER NOT NULL DEFAULT 1")
    added_station_status = ensure_column(
        conn,
        "stations",
        "station_status",
        "TEXT NOT NULL DEFAULT 'Regular Station'",
    )
    if added_station_status:
        conn.execute(
            """
            UPDATE stations
            SET station_status = CASE
                WHEN is_one_manned = 1 THEN '1M'
                ELSE 'Regular Station'
            END
            """
        )
    if added_station_cluster:
        for cluster_name, station_codes in STATION_CLUSTERS.items():
            placeholders = ", ".join("?" for _ in station_codes)
            conn.execute(
                f"""
                UPDATE stations
                SET cluster_name = ?
                WHERE station_code IN ({placeholders})
                """,
                (cluster_name, *station_codes),
            )
        for cluster_name, region_code in STATION_REGION_BY_CLUSTER.items():
            conn.execute(
                """
                UPDATE stations
                SET cluster_name = ?
                WHERE (cluster_name IS NULL OR cluster_name = '')
                  AND region_code = ?
                """,
                (cluster_name, region_code),
            )
    conn.execute(
        """
        UPDATE stations
        SET station_type = 'SCSS',
            include_in_pqr_compliance = 1
        WHERE station_type IS NULL
           OR station_type = ''
        """
    )
    conn.execute(
        """
        UPDATE stations
        SET station_type = 'STSS',
            include_in_pqr_compliance = 0
        WHERE station_code IN ('LSIP', 'KISB')
        """
    )
    ensure_column(conn, "earthquake_events", "source_url", "TEXT")
    ensure_column(conn, "earthquake_events", "reported_intensities", "TEXT")
    ensure_column(conn, "earthquake_events", "instrumental_intensities", "TEXT")
    ensure_column(conn, "earthquake_events", "intensity_note", "TEXT")
    ensure_column(conn, "earthquake_events", "intensity_checked_at", "TEXT")
    ensure_column(conn, "earthquake_events", "is_felt", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "earthquake_events", "felt_source", "TEXT")
    ensure_column(conn, "earthquake_events", "felt_checked_at", "TEXT")
    ensure_column(conn, "earthquake_events", "felt_override", "INTEGER")
    ensure_column(conn, "earthquake_events", "exclude_from_pqr_rating", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "earthquake_events", "pqr_rating_exclusion_reason", "TEXT")
    ensure_column(conn, "earthquake_events", "pqr_rating_excluded_at", "TEXT")
    ensure_column(conn, "earthquake_events", "pqr_rating_excluded_by", "INTEGER")
    added_sync_status = ensure_column(conn, "pqr_reports", "sheet_sync_status", "TEXT NOT NULL DEFAULT 'pending'")
    ensure_column(conn, "pqr_reports", "sheet_synced_at", "TEXT")
    ensure_column(conn, "pqr_reports", "sheet_sync_error", "TEXT")
    ensure_column(conn, "sync_runs", "skipped_count", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "sync_runs", "invalid_count", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "sync_runs", "summary", "TEXT")
    if added_sync_status:
        conn.execute("UPDATE pqr_reports SET sheet_sync_status = 'synced'")
    else:
        conn.execute(
            """
            UPDATE pqr_reports
            SET sheet_sync_status = 'pending'
            WHERE sheet_sync_status IS NULL OR sheet_sync_status = ''
            """
        )
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_events_status_time
        ON earthquake_events(status, event_datetime_utc);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_events_source_url_unique
        ON earthquake_events(source_url)
        WHERE source_url IS NOT NULL AND source_url != '';

        CREATE INDEX IF NOT EXISTS idx_required_event_station_status
        ON pqr_required_submissions(event_id, station_id, status);

        CREATE INDEX IF NOT EXISTS idx_required_station_status
        ON pqr_required_submissions(station_id, status);

        CREATE INDEX IF NOT EXISTS idx_reports_event_station
        ON pqr_reports(event_id, station_id);

        CREATE INDEX IF NOT EXISTS idx_reports_station_submitted
        ON pqr_reports(station_id, submitted_at);

        CREATE INDEX IF NOT EXISTS idx_reports_submitted_at
        ON pqr_reports(submitted_at);

        CREATE INDEX IF NOT EXISTS idx_reports_sheet_sync
        ON pqr_reports(sheet_sync_status, submitted_at);

        CREATE INDEX IF NOT EXISTS idx_audit_report_time
        ON pqr_audit_logs(report_id, updated_at);
        """
    )
    if not has_duplicate_event_fingerprints(conn):
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_events_fingerprint_unique
            ON earthquake_events(
                event_datetime_utc,
                reference_location,
                COALESCE(magnitude, -999),
                COALESCE(depth_km, -999),
                COALESCE(latitude, -999),
                COALESCE(longitude, -999)
            )
            """
        )
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_station_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            station_id INTEGER NOT NULL,
            is_primary INTEGER NOT NULL DEFAULT 0,
            can_submit INTEGER NOT NULL DEFAULT 1,
            can_view INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (station_id) REFERENCES stations(id),
            UNIQUE(user_id, station_id)
        );

        INSERT OR IGNORE INTO user_station_assignments (
            user_id, station_id, is_primary, can_submit, can_view
        )
        SELECT id, station_id, 1, 1, 1
        FROM users
        WHERE station_id IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_user_station_assignments_user
        ON user_station_assignments(user_id, station_id);

        CREATE INDEX IF NOT EXISTS idx_user_station_assignments_station
        ON user_station_assignments(station_id, user_id);

        CREATE TABLE IF NOT EXISTS login_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT NOT NULL,
            role TEXT,
            station_id INTEGER,
            event_type TEXT NOT NULL CHECK(event_type IN ('login_success', 'login_failed', 'logout')),
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (station_id) REFERENCES stations(id)
        );

        CREATE TABLE IF NOT EXISTS google_sheet_import_invalid_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_run_id INTEGER,
            sheet_row_number INTEGER,
            row_hash TEXT NOT NULL UNIQUE,
            raw_data_json TEXT NOT NULL,
            station_code TEXT,
            officer_initials TEXT,
            event_key TEXT,
            remarks TEXT,
            error_reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'resolved', 'ignored')),
            resolved_report_id INTEGER,
            resolved_by INTEGER,
            resolved_at TEXT,
            ignore_reason TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT,
            FOREIGN KEY (sync_run_id) REFERENCES sync_runs(id),
            FOREIGN KEY (resolved_report_id) REFERENCES pqr_reports(id),
            FOREIGN KEY (resolved_by) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_login_audit_created_at
        ON login_audit_logs(created_at);

        CREATE INDEX IF NOT EXISTS idx_invalid_import_status
        ON google_sheet_import_invalid_rows(status, created_at);

        CREATE INDEX IF NOT EXISTS idx_invalid_import_sync
        ON google_sheet_import_invalid_rows(sync_run_id, sheet_row_number);

        CREATE INDEX IF NOT EXISTS idx_login_audit_user
        ON login_audit_logs(user_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_login_audit_event_type
        ON login_audit_logs(event_type, created_at);

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'announcement' CHECK(category IN ('action', 'announcement', 'system', 'review')),
            priority TEXT NOT NULL DEFAULT 'info' CHECK(priority IN ('urgent', 'due_soon', 'info', 'resolved')),
            target_role TEXT CHECK(target_role IN ('admin', 'duty_officer', 'station_user', 'reviewer', 'read_only')),
            target_user_id INTEGER,
            target_station_id INTEGER,
            event_id INTEGER,
            report_id INTEGER,
            action_url TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (target_user_id) REFERENCES users(id),
            FOREIGN KEY (target_station_id) REFERENCES stations(id),
            FOREIGN KEY (event_id) REFERENCES earthquake_events(id),
            FOREIGN KEY (report_id) REFERENCES pqr_reports(id),
            FOREIGN KEY (created_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS message_reads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message_key TEXT NOT NULL,
            read_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, message_key)
        );

        CREATE TABLE IF NOT EXISTS message_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            body TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (message_id) REFERENCES messages(id),
            FOREIGN KEY (created_by) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_messages_targets
        ON messages(is_active, target_role, target_user_id, target_station_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_message_reads_user
        ON message_reads(user_id, message_key);

        CREATE INDEX IF NOT EXISTS idx_message_replies_message
        ON message_replies(message_id, created_at);

        CREATE TABLE IF NOT EXISTS province_region_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            province_name TEXT NOT NULL UNIQUE,
            region_code TEXT NOT NULL CHECK(region_code IN ('NL', 'SL', 'VIS', 'MIN')),
            priority INTEGER NOT NULL DEFAULT 100,
            is_active INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_province_region_rules_active
        ON province_region_rules(is_active, priority, province_name);
        """
    )


def has_duplicate_event_fingerprints(conn):
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM (
            SELECT 1
            FROM earthquake_events
            GROUP BY event_datetime_utc, reference_location, magnitude, depth_km, latitude, longitude
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
        """
    ).fetchone()
    return row["count"] > 0 if isinstance(row, sqlite3.Row) else row[0] > 0


def ensure_column(conn, table_name, column_name, column_definition):
    if isinstance(conn, PostgresCompatConnection):
        row = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = ?
              AND column_name = ?
            """,
            (table_name, column_name),
        ).fetchone()
        if row:
            return False
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
        return True

    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    if column_name in {column["name"] for column in columns}:
        return False
    try:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
    except sqlite3.OperationalError as error:
        if "duplicate column name" in str(error).lower():
            return False
        raise
    return True


class PostgresCompatConnection:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        cursor = self.conn.cursor()
        cursor.execute(*postgres_execute_args(sql, params))
        return PostgresCompatCursor(cursor)

    def executemany(self, sql, seq_of_params):
        cursor = self.conn.cursor()
        cursor.executemany(*postgres_execute_args(sql, seq_of_params))
        return PostgresCompatCursor(cursor)

    def executescript(self, script):
        cursor = self.conn.cursor()
        for statement in split_sql_script(script):
            cursor.execute(transform_postgres_sql(statement))
        return PostgresCompatCursor(cursor)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


class PostgresCompatCursor:
    def __init__(self, cursor):
        self.cursor = cursor
        self.lastrowid = None
        if cursor.description:
            row = cursor.fetchone()
            if row and "id" in row:
                self.lastrowid = row["id"]
            self._prefetched = [] if row is None else [row]
        else:
            self._prefetched = []

    def fetchone(self):
        if self._prefetched:
            return self._prefetched.pop(0)
        return self.cursor.fetchone()

    def fetchall(self):
        rows = self._prefetched + self.cursor.fetchall()
        self._prefetched = []
        return rows


def postgres_execute_args(sql, params):
    transformed = transform_postgres_sql(sql)
    if params is None:
        return (transformed,)
    return (transformed, params)


def split_sql_script(script):
    statements = []
    for statement in script.split(";"):
        stripped = statement.strip()
        if stripped and not stripped.upper().startswith("PRAGMA"):
            statements.append(stripped)
    return statements


def transform_postgres_sql(sql):
    transformed = sql.strip()
    transformed = re.sub(
        r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
        "SERIAL PRIMARY KEY",
        transformed,
        flags=re.IGNORECASE,
    )
    transformed = re.sub(r"\bREAL\b", "DOUBLE PRECISION", transformed, flags=re.IGNORECASE)
    transformed = re.sub(
        r"INSERT\s+OR\s+IGNORE\s+INTO",
        "INSERT INTO",
        transformed,
        flags=re.IGNORECASE,
    )
    if re.search(r"^\s*INSERT\s+INTO", transformed, re.IGNORECASE):
        table_match = re.search(r"^\s*INSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)", transformed, re.IGNORECASE)
        table_name = table_match.group(1) if table_match else ""
        had_ignore = bool(re.search(r"INSERT\s+OR\s+IGNORE\s+INTO", sql, re.IGNORECASE))
        has_returning = bool(re.search(r"\bRETURNING\b", transformed, re.IGNORECASE))
        if had_ignore and "ON CONFLICT" not in transformed.upper():
            transformed += " ON CONFLICT DO NOTHING"
        elif table_name in ID_TABLES and not has_returning:
            transformed += " RETURNING id"
    return transformed.replace("?", "%s")


def seed_reference_data(conn):
    seed_province_region_rules(conn)
    stations = []
    for cluster_name, codes in STATION_CLUSTERS.items():
        region = STATION_REGION_BY_CLUSTER[cluster_name]
        stations.extend((code, f"{code} Station", region) for code in codes)
    stations.extend(
        [
            ("LSIP", "Lipa City, Batangas", "SL"),
            ("DIPO", "Dipolog City", "MIN"),
        ]
    )
    for code, name, region in stations:
        cluster_name = STATION_CLUSTER_BY_CODE.get(code)
        if not cluster_name:
            cluster_name = next(
                (name for name, cluster_region in STATION_REGION_BY_CLUSTER.items() if cluster_region == region),
                None,
            )
        conn.execute(
            """
            INSERT OR IGNORE INTO stations (station_code, station_name, region_code, cluster_name)
            VALUES (?, ?, ?, ?)
            """,
            (code, name, region, cluster_name),
        )
        conn.execute(
            """
            UPDATE stations
            SET cluster_name = COALESCE(NULLIF(cluster_name, ''), ?)
            WHERE station_code = ?
            """,
            (cluster_name, code),
        )

    if IS_PRODUCTION:
        seed_production_admin(conn)
        return

    bbp = conn.execute("SELECT id FROM stations WHERE station_code = 'BBP'").fetchone()
    users = [
        ("admin", "admin123", "Administrator", "admin", None, "admin@phivolcs.local"),
        ("duty", "duty123", "Duty Officer", "duty_officer", None, "duty@phivolcs.local"),
        ("bbp", "bbp123", "BBP Station User", "station_user", bbp["id"] if bbp else None, "bbp@phivolcs.local"),
        ("reviewer", "reviewer123", "Reviewer", "reviewer", None, "reviewer@phivolcs.local"),
    ]
    for username, password, display_name, role, station_id, email in users:
        conn.execute(
            """
            INSERT OR IGNORE INTO users
                (username, password_hash, display_name, role, station_id, email)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (username, generate_password_hash(password), display_name, role, station_id, email),
        )
        conn.execute(
            """
            UPDATE users
            SET email = ?
            WHERE username = ?
              AND (email IS NULL OR email = '')
            """,
            (email, username),
        )
        if station_id:
            user_row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            conn.execute(
                """
                INSERT OR IGNORE INTO user_station_assignments (
                    user_id, station_id, is_primary, can_submit, can_view
                )
                VALUES (?, ?, 1, 1, 1)
                """,
                (user_row["id"], station_id),
            )


def seed_province_region_rules(conn):
    default_rules = [
        ("Masbate", "SL", 10, "Masbate events are handled as South Luzon PQR events."),
    ]
    for province_name, region_code, priority, notes in default_rules:
        conn.execute(
            """
            INSERT OR IGNORE INTO province_region_rules (
                province_name, region_code, priority, is_active, notes
            )
            VALUES (?, ?, ?, 1, ?)
            """,
            (province_name, region_code, priority, notes),
        )


def seed_production_admin(conn):
    existing_user = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
    admin_username = os.environ.get("PQR_ADMIN_USERNAME", "admin").strip()
    admin_password = os.environ.get("PQR_ADMIN_PASSWORD", "")
    admin_display_name = os.environ.get("PQR_ADMIN_DISPLAY_NAME", "Administrator").strip()
    admin_email = os.environ.get("PQR_ADMIN_EMAIL", "").strip()

    if existing_user:
        return
    if len(admin_password) < 12:
        raise RuntimeError(
            "Production database has no users. Set PQR_ADMIN_PASSWORD to at least 12 characters "
            "for the first admin account."
        )

    conn.execute(
        """
        INSERT INTO users (
            username, password_hash, display_name, email, role, station_id, is_active
        )
        VALUES (?, ?, ?, ?, 'admin', NULL, 1)
        """,
        (
            admin_username,
            generate_password_hash(admin_password),
            admin_display_name,
            admin_email,
        ),
    )
