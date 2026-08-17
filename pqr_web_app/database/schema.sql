PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    email TEXT,
    role TEXT NOT NULL CHECK(role IN ('admin', 'duty_officer', 'station_user', 'reviewer', 'read_only')),
    station_id INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    password_changed_at TEXT,
    password_reset_at TEXT,
    last_login_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (station_id) REFERENCES stations(id)
);

CREATE TABLE IF NOT EXISTS stations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_code TEXT UNIQUE NOT NULL,
    station_name TEXT NOT NULL,
    region_code TEXT NOT NULL CHECK(region_code IN ('NL', 'SL', 'VIS', 'MIN')),
    cluster_name TEXT,
    station_type TEXT NOT NULL DEFAULT 'SCSS',
    include_in_pqr_compliance INTEGER NOT NULL DEFAULT 1,
    is_one_manned INTEGER NOT NULL DEFAULT 0,
    station_status TEXT NOT NULL DEFAULT 'Regular Station',
    is_active INTEGER NOT NULL DEFAULT 1
);

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

CREATE TABLE IF NOT EXISTS earthquake_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key TEXT UNIQUE NOT NULL,
    event_datetime_utc TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    depth_km REAL,
    magnitude REAL,
    reference_location TEXT NOT NULL,
    region_code TEXT NOT NULL CHECK(region_code IN ('NL', 'SL', 'VIS', 'MIN')),
    source TEXT NOT NULL DEFAULT 'PHIVOLCS',
    source_url TEXT,
    reported_intensities TEXT,
    instrumental_intensities TEXT,
    intensity_note TEXT,
    intensity_checked_at TEXT,
    is_felt INTEGER NOT NULL DEFAULT 0,
    felt_source TEXT,
    felt_checked_at TEXT,
    felt_override INTEGER,
    exclude_from_pqr_rating INTEGER NOT NULL DEFAULT 0,
    pqr_rating_exclusion_reason TEXT,
    pqr_rating_excluded_at TEXT,
    pqr_rating_excluded_by INTEGER,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pqr_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    station_id INTEGER NOT NULL,
    officer_initials TEXT NOT NULL,
    p_polarity TEXT,
    p_arrival TEXT,
    s_marker TEXT,
    s_arrival TEXT,
    amplitude REAL,
    duration REAL,
    event_type TEXT,
    reserved_k TEXT,
    remarks TEXT NOT NULL,
    observed_intensities TEXT,
    instrumental_intensities TEXT,
    verified_areas_without_intensities TEXT,
    status TEXT NOT NULL DEFAULT 'submitted',
    submitted_at TEXT NOT NULL,
    updated_at TEXT,
    created_by INTEGER,
    updated_by INTEGER,
    sheet_sync_status TEXT NOT NULL DEFAULT 'pending',
    sheet_synced_at TEXT,
    sheet_sync_error TEXT,
    FOREIGN KEY (event_id) REFERENCES earthquake_events(id),
    FOREIGN KEY (station_id) REFERENCES stations(id),
    FOREIGN KEY (created_by) REFERENCES users(id),
    FOREIGN KEY (updated_by) REFERENCES users(id),
    UNIQUE(event_id, station_id)
);

CREATE TABLE IF NOT EXISTS pqr_required_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    station_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    FOREIGN KEY (event_id) REFERENCES earthquake_events(id),
    FOREIGN KEY (station_id) REFERENCES stations(id),
    UNIQUE(event_id, station_id)
);

CREATE TABLE IF NOT EXISTS pqr_audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    updated_by INTEGER,
    field_changed TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    reason TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (report_id) REFERENCES pqr_reports(id),
    FOREIGN KEY (updated_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    imported_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    invalid_count INTEGER NOT NULL DEFAULT 0,
    summary TEXT,
    error_message TEXT
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

CREATE INDEX IF NOT EXISTS idx_events_status_time
ON earthquake_events(status, event_datetime_utc);

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

CREATE INDEX IF NOT EXISTS idx_audit_report_time
ON pqr_audit_logs(report_id, updated_at);

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

CREATE INDEX IF NOT EXISTS idx_messages_targets
ON messages(is_active, target_role, target_user_id, target_station_id, created_at);

CREATE INDEX IF NOT EXISTS idx_message_reads_user
ON message_reads(user_id, message_key);

CREATE INDEX IF NOT EXISTS idx_message_replies_message
ON message_replies(message_id, created_at);

CREATE INDEX IF NOT EXISTS idx_user_station_assignments_user
ON user_station_assignments(user_id, station_id);

CREATE INDEX IF NOT EXISTS idx_user_station_assignments_station
ON user_station_assignments(station_id, user_id);
