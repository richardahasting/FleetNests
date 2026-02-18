"""
Database query functions for Bentley Boat Club.
All business logic lives here.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import db

CENTRAL = ZoneInfo("America/Chicago")


def now_ct() -> datetime:
    """Current naive datetime in Central Time (handles CST/CDT automatically)."""
    return datetime.now(CENTRAL).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# User queries
# ---------------------------------------------------------------------------

def get_all_active_users():
    return db.execute(
        "SELECT id, username, full_name, email, is_admin, created_at "
        "FROM users WHERE is_active = TRUE ORDER BY full_name"
    )


def get_user_by_id(user_id: int):
    return db.fetchone("SELECT * FROM users WHERE id = %s", (user_id,))


def create_user(username: str, full_name: str, email: str,
                password_hash: str, is_admin: bool = False,
                max_consecutive_days: int = 3, max_pending: int = 7):
    return db.insert(
        "INSERT INTO users (username, full_name, email, password_hash, is_admin, max_consecutive_days, max_pending) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (username, full_name, email, password_hash, is_admin, max_consecutive_days, max_pending),
    )


def deactivate_user(user_id: int):
    db.execute(
        "UPDATE users SET is_active = FALSE WHERE id = %s",
        (user_id,),
        fetch=False,
    )


def update_password(user_id: int, password_hash: str):
    db.execute(
        "UPDATE users SET password_hash = %s WHERE id = %s",
        (password_hash, user_id),
        fetch=False,
    )


def get_user_limits(user_id: int) -> dict:
    row = db.fetchone(
        "SELECT max_consecutive_days, max_pending FROM users WHERE id = %s",
        (user_id,),
    )
    return {"max_consecutive": row["max_consecutive_days"] or 3, "max_pending": row["max_pending"] or 7}


# ---------------------------------------------------------------------------
# Reservation queries
# ---------------------------------------------------------------------------

def get_reservations_range(start: date, end: date) -> list:
    """Return all active reservations between start and end dates (inclusive)."""
    return db.execute(
        "SELECT r.id, r.date, r.start_time, r.end_time, r.status, r.user_id, u.full_name "
        "FROM reservations r "
        "JOIN users u ON u.id = r.user_id "
        "WHERE r.date BETWEEN %s AND %s AND r.status IN ('active','pending_approval') "
        "ORDER BY r.start_time",
        (start, end),
    )


def get_reservations_for_date(res_date: date) -> list:
    """Return all active reservations for a specific day, ordered by start time."""
    return db.execute(
        "SELECT r.id, r.start_time, r.end_time, r.user_id, r.notes, u.full_name, u.username "
        "FROM reservations r "
        "JOIN users u ON u.id = r.user_id "
        "WHERE r.date = %s AND r.status = 'active' "
        "ORDER BY r.start_time",
        (res_date,),
    )


def get_reservation_by_id(res_id: int):
    return db.fetchone(
        "SELECT r.*, u.full_name, u.username "
        "FROM reservations r "
        "JOIN users u ON u.id = r.user_id "
        "WHERE r.id = %s",
        (res_id,),
    )


def get_user_reservations(user_id: int) -> dict:
    """Return upcoming (asc) and past/cancelled (desc) reservations for a user."""
    upcoming = db.execute(
        "SELECT r.*, u.full_name FROM reservations r "
        "JOIN users u ON u.id = r.user_id "
        "WHERE r.user_id = %s AND r.status = 'active' AND r.start_time >= %s "
        "ORDER BY r.start_time ASC",
        (user_id, now_ct()),
    )
    past = db.execute(
        "SELECT r.*, u.full_name FROM reservations r "
        "JOIN users u ON u.id = r.user_id "
        "WHERE r.user_id = %s AND (r.status = 'cancelled' OR r.start_time < %s) "
        "ORDER BY r.start_time DESC LIMIT 50",
        (user_id, now_ct()),
    )
    return {"upcoming": upcoming, "past": past}


def get_user_future_reservations(user_id: int) -> list:
    """Return distinct future active reservation dates for a user."""
    return db.execute(
        "SELECT DISTINCT date FROM reservations "
        "WHERE user_id = %s AND status IN ('active','pending_approval') AND start_time >= %s "
        "ORDER BY date",
        (user_id, now_ct()),
    )


def get_pending_count(user_id: int) -> int:
    """Count active future reservations (each time slot = 1) for a user."""
    row = db.fetchone(
        "SELECT COUNT(*) AS cnt FROM reservations "
        "WHERE user_id = %s AND status IN ('active','pending_approval') AND start_time >= %s",
        (user_id, now_ct()),
    )
    return int(row["cnt"]) if row else 0


def _has_consecutive_violation(dates: set, max_run: int = 3) -> bool:
    """
    Return True if any run of consecutive calendar days in `dates` exceeds max_run.
    Works on date objects; ignores duplicate dates (a day with two slots still counts once).
    """
    sorted_dates = sorted(dates)
    if not sorted_dates:
        return False
    run = 1
    for i in range(1, len(sorted_dates)):
        if sorted_dates[i] - sorted_dates[i - 1] == timedelta(days=1):
            run += 1
            if run > max_run:
                return True
        else:
            run = 1
    return False


def validate_reservation(user_id: int, start_dt: datetime, end_dt: datetime) -> str | None:
    """
    Check all business rules for a new reservation.
    Returns an error string on failure, or None if valid.

    Rules enforced:
      1. Minimum 4 hours, maximum 12 hours duration
      2. Start must be in the future
      3. Start and end must be on the same calendar day
      4. No overlap with any existing active reservation
      5. No overlap with a blackout date
      6. User must have fewer pending reservations than their per-member limit
      7. Adding this date must not create a run exceeding the per-member consecutive-day limit
    """
    hours = (end_dt - start_dt).total_seconds() / 3600

    if end_dt <= start_dt:
        return "End time must be after start time."

    if hours < 4:
        return f"Minimum reservation length is 4 hours (you selected {hours:.1f}h)."

    if hours > 12:
        return f"Maximum reservation length is 12 hours (you selected {hours:.1f}h)."

    if start_dt < now_ct():
        return "Start time cannot be in the past."

    if start_dt.date() != end_dt.date():
        return "Reservations must start and end on the same calendar day."

    # Overlap check: any active reservation whose window intersects ours
    overlap = db.fetchone(
        "SELECT r.id, u.full_name FROM reservations r "
        "JOIN users u ON u.id = r.user_id "
        "WHERE r.status IN ('active','pending_approval') AND r.start_time < %s AND r.end_time > %s",
        (end_dt, start_dt),
    )
    if overlap:
        return f"That time overlaps with {overlap['full_name']}'s reservation."

    # Blackout check
    blackout = db.fetchone(
        "SELECT id, reason FROM blackout_dates WHERE start_time < %s AND end_time > %s",
        (end_dt, start_dt),
    )
    if blackout:
        return f"The boat is unavailable during that time: {blackout['reason']}."

    limits = get_user_limits(user_id)

    # Pending limit
    if get_pending_count(user_id) >= limits["max_pending"]:
        return f"You already have {limits['max_pending']} upcoming reservations — the maximum allowed."

    # Consecutive day check (date-level; same day with two slots still counts as 1 day)
    future_rows = get_user_future_reservations(user_id)
    existing_dates = {row["date"] for row in future_rows}
    existing_dates.add(start_dt.date())
    if _has_consecutive_violation(existing_dates, max_run=limits["max_consecutive"]):
        return f"This reservation would exceed your {limits['max_consecutive']}-consecutive-day limit."

    return None


def make_reservation(user_id: int, start_dt: datetime, end_dt: datetime,
                     notes: str | None = None, status: str = 'active'):
    """Insert a new reservation. Call validate_reservation first."""
    notes = (notes or "").strip() or None
    return db.insert(
        "INSERT INTO reservations (user_id, date, start_time, end_time, notes, status) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (user_id, start_dt.date(), start_dt, end_dt, notes, status),
    )


def cancel_reservation(res_id: int, user_id: int, is_admin: bool = False) -> bool:
    """
    Cancel a reservation by ID.
    Returns True on success, False if not found or not authorized.
    Admins can cancel any reservation.
    """
    res = get_reservation_by_id(res_id)
    if not res:
        return False
    if not is_admin and res["user_id"] != user_id:
        return False
    db.execute(
        "UPDATE reservations SET status='cancelled', cancelled_at=NOW() WHERE id = %s",
        (res_id,),
        fetch=False,
    )
    return True


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_usage_stats() -> list:
    return db.execute(
        """
        SELECT
            u.full_name,
            COUNT(*) FILTER (WHERE r.status='active' AND r.start_time < current_timestamp AT TIME ZONE 'America/Chicago')  AS past,
            COUNT(*) FILTER (WHERE r.status='active' AND r.start_time >= current_timestamp AT TIME ZONE 'America/Chicago') AS upcoming,
            COUNT(*) FILTER (WHERE r.status='active')                           AS total,
            COUNT(*) FILTER (WHERE r.status='cancelled')                        AS cancelled
        FROM users u
        LEFT JOIN reservations r ON r.user_id = u.id
        WHERE u.is_active = TRUE
        GROUP BY u.full_name
        ORDER BY total DESC, u.full_name
        """
    )


# ---------------------------------------------------------------------------
# Message board
# ---------------------------------------------------------------------------

def get_messages() -> list:
    return db.execute(
        "SELECT m.*, u.full_name, u.username "
        "FROM messages m "
        "JOIN users u ON u.id = m.user_id "
        "ORDER BY m.is_announcement DESC, m.created_at DESC"
    )


def get_message_by_id(msg_id: int):
    return db.fetchone(
        "SELECT m.*, u.full_name, u.username "
        "FROM messages m JOIN users u ON u.id = m.user_id "
        "WHERE m.id = %s",
        (msg_id,),
    )


def create_message(user_id: int, title: str, body: str, is_announcement: bool = False):
    return db.insert(
        "INSERT INTO messages (user_id, title, body, is_announcement) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (user_id, title, body, is_announcement),
    )


def delete_message(msg_id: int, user_id: int, is_admin: bool = False) -> bool:
    msg = get_message_by_id(msg_id)
    if not msg:
        return False
    if not is_admin and msg["user_id"] != user_id:
        return False
    db.execute("DELETE FROM messages WHERE id = %s", (msg_id,), fetch=False)
    return True


# ---------------------------------------------------------------------------
# Blackout dates
# ---------------------------------------------------------------------------

def get_blackouts_range(start, end) -> list:
    return db.execute(
        "SELECT * FROM blackout_dates WHERE start_time < %s AND end_time > %s ORDER BY start_time",
        (end, start),
    )


def get_blackout_by_id(blackout_id: int):
    return db.fetchone("SELECT * FROM blackout_dates WHERE id = %s", (blackout_id,))


def create_blackout(start_dt, end_dt, reason: str, created_by: int):
    return db.insert(
        "INSERT INTO blackout_dates (start_time, end_time, reason, created_by) VALUES (%s,%s,%s,%s) RETURNING id",
        (start_dt, end_dt, reason, created_by),
    )


def delete_blackout(blackout_id: int):
    db.execute("DELETE FROM blackout_dates WHERE id = %s", (blackout_id,), fetch=False)


def get_all_blackouts() -> list:
    return db.execute("SELECT * FROM blackout_dates ORDER BY start_time")


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def log_action(user_id: int, action: str, target_type: str = None,
               target_id: int = None, detail: dict = None):
    """Append an immutable audit entry. Call fire-and-forget; never raises."""
    import json
    try:
        db.insert(
            "INSERT INTO audit_log (user_id, action, target_type, target_id, detail) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (user_id, action, target_type, target_id,
             json.dumps(detail) if detail else None),
        )
    except Exception:
        pass  # audit must never break normal flow


def get_audit_log(limit: int = 200, after_date=None) -> list:
    if after_date:
        return db.execute(
            "SELECT a.*, u.username, u.full_name FROM audit_log a "
            "LEFT JOIN users u ON u.id = a.user_id "
            "WHERE a.created_at >= %s ORDER BY a.created_at DESC LIMIT %s",
            (after_date, limit),
        )
    return db.execute(
        "SELECT a.*, u.username, u.full_name FROM audit_log a "
        "LEFT JOIN users u ON u.id = a.user_id "
        "ORDER BY a.created_at DESC LIMIT %s",
        (limit,),
    )


# ---------------------------------------------------------------------------
# Approval workflow
# ---------------------------------------------------------------------------

def get_pending_approval() -> list:
    """Return reservations awaiting admin approval."""
    return db.execute(
        "SELECT r.*, u.full_name, u.username "
        "FROM reservations r JOIN users u ON u.id = r.user_id "
        "WHERE r.status = 'pending_approval' "
        "ORDER BY r.created_at",
    )


def approve_reservation(res_id: int):
    db.execute(
        "UPDATE reservations SET status='active' WHERE id = %s AND status='pending_approval'",
        (res_id,), fetch=False,
    )


def deny_reservation(res_id: int):
    db.execute(
        "UPDATE reservations SET status='cancelled', cancelled_at=NOW() WHERE id = %s AND status='pending_approval'",
        (res_id,), fetch=False,
    )


# ---------------------------------------------------------------------------
# Incident / damage reports
# ---------------------------------------------------------------------------

def get_all_incidents() -> list:
    return db.execute(
        "SELECT i.*, u.full_name, u.username, r.date AS res_date, "
        "       ru.full_name AS resolver_name "
        "FROM incident_reports i "
        "JOIN users u ON u.id = i.user_id "
        "LEFT JOIN reservations r ON r.id = i.res_id "
        "LEFT JOIN users ru ON ru.id = i.resolved_by "
        "ORDER BY i.created_at DESC"
    )


def get_incidents_for_user(user_id: int) -> list:
    return db.execute(
        "SELECT i.*, r.date AS res_date "
        "FROM incident_reports i "
        "LEFT JOIN reservations r ON r.id = i.res_id "
        "WHERE i.user_id = %s "
        "ORDER BY i.created_at DESC",
        (user_id,),
    )


def create_incident(user_id: int, res_id, report_date, severity: str, description: str):
    return db.insert(
        "INSERT INTO incident_reports (user_id, res_id, report_date, severity, description) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (user_id, res_id or None, report_date, severity, description),
    )


def resolve_incident(incident_id: int, resolved_by: int):
    db.execute(
        "UPDATE incident_reports SET resolved=TRUE, resolved_by=%s, resolved_at=NOW() WHERE id=%s",
        (resolved_by, incident_id), fetch=False,
    )


# ---------------------------------------------------------------------------
# Fuel log
# ---------------------------------------------------------------------------

def create_fuel_entry(user_id: int, res_id, log_date, gallons: float,
                      price_per_gallon=None, total_cost=None, notes: str = None):
    return db.insert(
        "INSERT INTO fuel_log (user_id, res_id, log_date, gallons, price_per_gallon, total_cost, notes) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (user_id, res_id or None, log_date, gallons, price_per_gallon, total_cost, notes or None),
    )


def get_fuel_for_user(user_id: int) -> list:
    return db.execute(
        "SELECT f.*, r.date AS res_date "
        "FROM fuel_log f "
        "LEFT JOIN reservations r ON r.id = f.res_id "
        "WHERE f.user_id = %s "
        "ORDER BY f.log_date DESC",
        (user_id,),
    )


def get_all_fuel_entries() -> list:
    return db.execute(
        "SELECT f.*, u.full_name, u.username, r.date AS res_date "
        "FROM fuel_log f "
        "JOIN users u ON u.id = f.user_id "
        "LEFT JOIN reservations r ON r.id = f.res_id "
        "ORDER BY f.log_date DESC"
    )


def get_fuel_stats() -> list:
    """Per-user fuel totals for the stats page."""
    return db.execute(
        "SELECT u.full_name, "
        "       SUM(f.gallons) AS total_gallons, "
        "       SUM(f.total_cost) AS total_cost, "
        "       COUNT(*) AS entries "
        "FROM fuel_log f "
        "JOIN users u ON u.id = f.user_id "
        "GROUP BY u.full_name "
        "ORDER BY total_gallons DESC NULLS LAST"
    )


# ---------------------------------------------------------------------------
# Waitlist
# ---------------------------------------------------------------------------

def add_to_waitlist(user_id: int, desired_date, notes: str = None):
    """Add user to waitlist for a date. Silently ignores duplicate."""
    try:
        return db.insert(
            "INSERT INTO waitlist (user_id, desired_date, notes) VALUES (%s, %s, %s) "
            "ON CONFLICT (user_id, desired_date) DO NOTHING RETURNING id",
            (user_id, desired_date, notes or None),
        )
    except Exception:
        return None


def remove_from_waitlist(user_id: int, desired_date):
    db.execute(
        "DELETE FROM waitlist WHERE user_id=%s AND desired_date=%s",
        (user_id, desired_date), fetch=False,
    )


def get_waitlist_for_date(desired_date) -> list:
    """All waitlist entries for a specific date, ordered by signup time."""
    return db.execute(
        "SELECT w.*, u.full_name, u.username, u.email "
        "FROM waitlist w JOIN users u ON u.id = w.user_id "
        "WHERE w.desired_date = %s ORDER BY w.created_at",
        (desired_date,),
    )


def get_user_waitlist(user_id: int) -> list:
    return db.execute(
        "SELECT * FROM waitlist WHERE user_id=%s ORDER BY desired_date",
        (user_id,),
    )


def is_on_waitlist(user_id: int, desired_date) -> bool:
    row = db.fetchone(
        "SELECT id FROM waitlist WHERE user_id=%s AND desired_date=%s",
        (user_id, desired_date),
    )
    return row is not None


def notify_and_clear_waitlist(desired_date):
    """Called when a reservation is cancelled. Notify & mark waitlist entries."""
    import email_notify
    entries = get_waitlist_for_date(desired_date)
    for entry in entries:
        user = get_user_by_id(entry["user_id"])
        if user:
            email_notify.notify_waitlist_available(user, desired_date)
        db.execute(
            "UPDATE waitlist SET notified=TRUE WHERE id=%s",
            (entry["id"],), fetch=False,
        )


# ---------------------------------------------------------------------------
# iCal personal feed
# ---------------------------------------------------------------------------

def get_or_create_ical_token(user_id: int) -> str:
    """Return existing iCal token for user, creating one if needed."""
    import secrets
    row = db.fetchone("SELECT ical_token FROM users WHERE id=%s", (user_id,))
    if row and row["ical_token"]:
        return row["ical_token"]
    token = secrets.token_urlsafe(32)
    db.execute(
        "UPDATE users SET ical_token=%s WHERE id=%s",
        (token, user_id), fetch=False,
    )
    return token


def get_user_by_ical_token(token: str):
    return db.fetchone(
        "SELECT * FROM users WHERE ical_token=%s AND is_active=TRUE",
        (token,),
    )


def get_user_ical_reservations(user_id: int) -> list:
    """Future active reservations for iCal export."""
    return db.execute(
        "SELECT r.*, u.full_name FROM reservations r "
        "JOIN users u ON u.id = r.user_id "
        "WHERE r.user_id=%s AND r.status='active' AND r.start_time >= NOW() "
        "ORDER BY r.start_time",
        (user_id,),
    )


def get_all_reservations_for_export(year: int = None) -> list:
    """Full reservation detail for CSV export."""
    if year:
        return db.execute(
            "SELECT r.id, r.date, r.start_time, r.end_time, r.status, r.notes, "
            "       u.full_name, u.username "
            "FROM reservations r JOIN users u ON u.id = r.user_id "
            "WHERE EXTRACT(YEAR FROM r.date) = %s "
            "ORDER BY r.date, r.start_time",
            (year,),
        )
    return db.execute(
        "SELECT r.id, r.date, r.start_time, r.end_time, r.status, r.notes, "
        "       u.full_name, u.username "
        "FROM reservations r JOIN users u ON u.id = r.user_id "
        "ORDER BY r.date, r.start_time"
    )
