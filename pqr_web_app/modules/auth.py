from functools import wraps

from flask import flash, redirect, session
from werkzeug.security import check_password_hash

from modules.db import get_db

ROLE_PERMISSIONS = {
    "admin": {"manage", "create_event", "submit", "update", "review", "export"},
    "duty_officer": {"create_event", "submit", "update", "review", "export"},
    "station_user": {"submit", "update", "review_own"},
    "reviewer": {"review", "export"},
    "read_only": {"review"},
}
DUTY_OFFICER_PERMISSIONS = ROLE_PERMISSIONS["duty_officer"]
EFFECTIVE_DUTY_STATION_CODE = "QVP"


def authenticate(username, password):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? AND is_active = 1",
        (username,),
    ).fetchone()
    conn.close()
    if user and check_password_hash(user["password_hash"], password):
        return dict(user)
    return None


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not user:
        return None
    user = dict(user)
    if is_effective_duty_officer(user):
        user["effective_role"] = "duty_officer"
    else:
        user["effective_role"] = user["role"]
    return user


def has_effective_duty_station(user):
    if not user or not user.get("id"):
        return False
    conn = get_db()
    row = conn.execute(
        """
        SELECT 1
        FROM users
        LEFT JOIN stations AS primary_station
            ON primary_station.id = users.station_id
        LEFT JOIN user_station_assignments
            ON user_station_assignments.user_id = users.id
        LEFT JOIN stations AS assigned_station
            ON assigned_station.id = user_station_assignments.station_id
        WHERE users.id = ?
          AND users.is_active = 1
          AND (
            primary_station.station_code = ?
            OR assigned_station.station_code = ?
          )
        LIMIT 1
        """,
        (user["id"], EFFECTIVE_DUTY_STATION_CODE, EFFECTIVE_DUTY_STATION_CODE),
    ).fetchone()
    conn.close()
    return bool(row)


def is_effective_duty_officer(user):
    if not user:
        return False
    return user.get("role") == "duty_officer" or has_effective_duty_station(user)


def effective_role_label(user):
    role = (user or {}).get("effective_role") or (user or {}).get("role") or ""
    return role.replace("_", " ").title()


def can(user, permission):
    if not user:
        return False
    if permission in ROLE_PERMISSIONS.get(user["role"], set()):
        return True
    return is_effective_duty_officer(user) and permission in DUTY_OFFICER_PERMISSIONS


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect("/login")
        return view(*args, **kwargs)

    return wrapped


def permission_required(permission):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not can(user, permission):
                flash("You do not have permission for that action.")
                return redirect("/dashboard")
            return view(*args, **kwargs)

        return wrapped

    return decorator
