from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    APP_LOCAL_TZ = ZoneInfo("Asia/Manila")
except Exception:
    APP_LOCAL_TZ = timezone(timedelta(hours=8), "Asia/Manila")
UPDATE_WINDOW_HOURS = 22


def utc_now():
    return datetime.now(timezone.utc)


def to_utc_iso(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=APP_LOCAL_TZ)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_datetime_local_as_utc(value):
    if not value:
        return None
    text = str(value).strip()
    formats = [
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M",
        "%d %B %Y - %I:%M %p",
        "%d %b %Y - %I:%M %p",
        "%d %B %Y %I:%M %p",
        "%d %b %Y %I:%M %p",
    ]
    dt = None
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            break
        except ValueError:
            pass
    if dt is None:
        raise ValueError(f"Unsupported PHIVOLCS date-time format: {value}")
    return to_utc_iso(dt)


def phivolcs_datetime_to_utc_key(value):
    """Convert PHIVOLCS Date-Time (Philippine Time) to YYYYMMDDHHMM UTC key."""
    utc_iso = parse_datetime_local_as_utc(value)
    return utc_iso_to_event_key(utc_iso)


def utc_iso_to_event_key(value):
    if not value:
        return ""
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[:12]


def utc_iso_to_pst_display(value):
    """Format a UTC ISO timestamp as Philippine Standard Time for display."""
    dt = parse_utc_iso(value)
    if not dt:
        return ""
    return dt.astimezone(APP_LOCAL_TZ).strftime("%Y-%m-%d %I:%M %p")


def parse_event_key_to_utc(event_key):
    key = str(event_key or "").strip()[:12]
    if len(key) != 12 or not key.isdigit():
        return None
    try:
        dt = datetime.strptime(key, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return to_utc_iso(dt)


def parse_utc_iso(value):
    if not value:
        return None
    text = str(value).strip()
    if not text or text.startswith("#"):
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        pass

    formats = [
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=APP_LOCAL_TZ).astimezone(timezone.utc)
        except ValueError:
            pass
    return None


def normalize_timestamp_to_utc_iso(value, fallback=None):
    parsed = parse_utc_iso(value)
    if parsed:
        return to_utc_iso(parsed)
    if fallback is not None:
        return to_utc_iso(fallback)
    return None


def within_update_window(event_datetime_utc):
    event_time = parse_utc_iso(event_datetime_utc)
    if not event_time:
        return False
    elapsed = utc_now() - event_time
    return elapsed.total_seconds() <= UPDATE_WINDOW_HOURS * 3600
