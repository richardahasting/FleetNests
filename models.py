"""
Database query functions for FleetNests.
All business logic lives here. Vehicle-type constants moved to vehicle_types.py.
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

def default_member_name(full_name: str) -> str:
    """Derive default member name from full name: 'Richard Hasting' → 'The Hasting family'."""
    last = full_name.strip().rsplit(" ", 1)[-1]
    return f"The {last} family"


def get_display_name(user: dict) -> str:
    """Return the name shown publicly for this user (family display name, or full name)."""
    if user.get("family_account_id"):
        primary = get_user_by_id(user["family_account_id"])
        if primary:
            return primary.get("display_name") or primary["full_name"]
    return user.get("display_name") or user["full_name"]


def get_effective_user_id(user: dict) -> int:
    """Return the account ID used for reservations (primary if family sub-member)."""
    return user.get("family_account_id") or user["id"]


def get_all_active_users():
    return db.execute(
        "SELECT id, username, full_name, display_name, family_account_id, "
        "email, is_admin, created_at "
        "FROM users WHERE is_active = TRUE ORDER BY full_name"
    )


def get_user_by_id(user_id: int):
    return db.fetchone("SELECT * FROM users WHERE id = %s", (user_id,))


def create_user(username: str, full_name: str, email: str,
                password_hash: str, is_admin: bool = False,
                max_consecutive_days: int = 3, max_pending: int = 3):
    member_name = default_member_name(full_name)
    return db.insert(
        "INSERT INTO users (username, full_name, email, password_hash, is_admin, "
        "max_consecutive_days, max_pending, display_name) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (username, full_name, email, password_hash, is_admin,
         max_consecutive_days, max_pending, member_name),
    )


def deactivate_user(user_id: int):
    db.execute(
        "UPDATE users SET is_active = FALSE WHERE id = %s",
        (user_id,),
        fetch=False,
    )


def update_user_profile(user_id: int, display_name: str | None, family_account_id: int | None):
    db.execute(
        "UPDATE users SET display_name = %s, family_account_id = %s WHERE id = %s",
        (display_name or None, family_account_id or None, user_id),
        fetch=False,
    )


def update_member_name(user_id: int, member_name: str):
    db.execute(
        "UPDATE users SET display_name = %s WHERE id = %s",
        (member_name or None, user_id),
        fetch=False,
    )


def update_family_credentials(user_id: int, email2: str | None, password_hash2: str | None):
    db.execute(
        "UPDATE users SET email2 = %s, password_hash2 = %s WHERE id = %s",
        (email2 or None, password_hash2 or None, user_id),
        fetch=False,
    )


def update_password(user_id: int, password_hash: str):
    db.execute(
        "UPDATE users SET password_hash = %s WHERE id = %s",
        (password_hash, user_id),
        fetch=False,
    )


def create_password_token(user_id: int, expires_hours: int = 72) -> str:
    import secrets as _secrets
    token = _secrets.token_urlsafe(32)
    expires = now_ct() + timedelta(hours=expires_hours)
    db.execute(
        "UPDATE users SET password_reset_token = %s, password_reset_expires = %s WHERE id = %s",
        (token, expires, user_id),
        fetch=False,
    )
    return token


def consume_password_token(token: str):
    """Validate token, clear it, return user row or None if invalid/expired."""
    row = db.fetchone(
        "SELECT * FROM users WHERE password_reset_token = %s AND is_active = TRUE",
        (token,),
    )
    if not row:
        return None
    if row["password_reset_expires"] and now_ct() > row["password_reset_expires"]:
        return None
    db.execute(
        "UPDATE users SET password_reset_token = NULL, password_reset_expires = NULL WHERE id = %s",
        (row["id"],),
        fetch=False,
    )
    return row


def get_user_by_password_token(token: str):
    """Read-only lookup for token validity check (does not consume the token)."""
    row = db.fetchone(
        "SELECT * FROM users WHERE password_reset_token = %s AND is_active = TRUE",
        (token,),
    )
    if not row:
        return None
    if row["password_reset_expires"] and now_ct() > row["password_reset_expires"]:
        return None
    return row


def get_user_limits(user_id: int) -> dict:
    row = db.fetchone(
        "SELECT max_consecutive_days, max_pending FROM users WHERE id = %s",
        (user_id,),
    )
    return {"max_consecutive": row["max_consecutive_days"] or 3, "max_pending": row["max_pending"] or 3}


# ---------------------------------------------------------------------------
# Reservation queries
# ---------------------------------------------------------------------------

def get_reservations_range(start: date, end: date) -> list:
    """Return all active reservations between start and end dates (inclusive)."""
    return db.execute(
        "SELECT r.id, r.date, r.start_time, r.end_time, r.status, r.user_id, "
        "COALESCE(u.display_name, u.full_name) AS full_name "
        "FROM reservations r "
        "JOIN users u ON u.id = r.user_id "
        "WHERE r.date BETWEEN %s AND %s AND r.status IN ('active','pending_approval') "
        "ORDER BY r.start_time",
        (start, end),
    )


def get_reservations_for_date(res_date: date) -> list:
    """Return all active/pending reservations for a specific day, ordered by start time."""
    return db.execute(
        "SELECT r.id, r.start_time, r.end_time, r.user_id, r.status, r.notes, u.full_name, u.username "
        "FROM reservations r "
        "JOIN users u ON u.id = r.user_id "
        "WHERE r.date = %s AND r.status IN ('active', 'pending_approval') "
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


def validate_reservation(user_id: int, start_dt: datetime, end_dt: datetime,
                          vehicle_id: int = None, vehicle_noun: str = "vehicle") -> str | None:
    """
    Check all business rules for a new reservation.
    Returns an error string on failure, or None if valid.

    Rules enforced:
      1. Minimum 2 hours, maximum 6 hours duration
      2. Start must be in the future
      3. Start and end must be on the same calendar day
      4. No overlap with any existing active reservation for this vehicle
      5. No overlap with a blackout date for this vehicle (or club-wide)
      6. User must have fewer pending reservations than their per-member limit
      7. Adding this date must not create a run exceeding the per-member consecutive-day limit
    """
    hours = (end_dt - start_dt).total_seconds() / 3600

    if end_dt <= start_dt:
        return "End time must be after start time."

    if start_dt.minute % 30 != 0 or start_dt.second != 0:
        return "Start time must be on a 30-minute interval (e.g. 9:00, 9:30, 10:00)."

    if end_dt.minute % 30 != 0 or end_dt.second != 0:
        return "End time must be on a 30-minute interval (e.g. 9:00, 9:30, 10:00)."

    if hours < 2:
        return f"Minimum reservation length is 2 hours (you selected {hours:.1f}h)."

    if hours > 6:
        return f"Maximum reservation length is 6 hours (you selected {hours:.1f}h)."

    if start_dt < now_ct():
        return "Start time cannot be in the past."

    if start_dt.date() > date.today() + timedelta(days=60):
        return "Reservations cannot be made more than 60 days in advance."

    if start_dt.date() != end_dt.date():
        return "Reservations must start and end on the same calendar day."

    # Overlap check: scoped to this vehicle if vehicle_id provided
    if vehicle_id:
        overlap = db.fetchone(
            "SELECT r.id, COALESCE(u.display_name, u.full_name) AS display_name FROM reservations r "
            "JOIN users u ON u.id = r.user_id "
            "WHERE r.vehicle_id = %s AND r.status IN ('active','pending_approval') "
            "AND r.start_time < %s AND r.end_time > %s",
            (vehicle_id, end_dt, start_dt),
        )
    else:
        overlap = db.fetchone(
            "SELECT r.id, COALESCE(u.display_name, u.full_name) AS display_name FROM reservations r "
            "JOIN users u ON u.id = r.user_id "
            "WHERE r.status IN ('active','pending_approval') AND r.start_time < %s AND r.end_time > %s",
            (end_dt, start_dt),
        )
    if overlap:
        return f"That time overlaps with {overlap['display_name']}'s reservation."

    # Blackout check — vehicle-specific OR club-wide (vehicle_id IS NULL)
    if vehicle_id:
        blackout = db.fetchone(
            "SELECT id, reason FROM blackout_dates "
            "WHERE (vehicle_id = %s OR vehicle_id IS NULL) "
            "AND start_time < %s AND end_time > %s",
            (vehicle_id, end_dt, start_dt),
        )
    else:
        blackout = db.fetchone(
            "SELECT id, reason FROM blackout_dates WHERE start_time < %s AND end_time > %s",
            (end_dt, start_dt),
        )
    if blackout:
        return f"The {vehicle_noun} is unavailable during that time: {blackout['reason']}."

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


def is_day_fully_booked(reservations: list, min_gap_minutes: int = 120) -> bool:
    """
    Return True only if there is no contiguous gap of at least min_gap_minutes
    anywhere within a 24-hour window on the reservation day.
    """
    if not reservations:
        return False
    # Use the reservation date to build midnight boundaries
    day_start = reservations[0]["start_time"].replace(hour=0, minute=0, second=0, microsecond=0)
    day_end   = day_start.replace(hour=23, minute=59, second=59)
    sorted_res = sorted(reservations, key=lambda r: r["start_time"])
    cursor = day_start
    for res in sorted_res:
        gap = (res["start_time"] - cursor).total_seconds() / 60
        if gap >= min_gap_minutes:
            return False
        cursor = max(cursor, res["end_time"])
    return (day_end - cursor).total_seconds() / 60 < min_gap_minutes


def make_reservation(user_id: int, start_dt: datetime, end_dt: datetime,
                     notes: str | None = None, status: str = 'active',
                     vehicle_id: int = None):
    """Insert a new reservation atomically, re-checking for overlap inside the transaction."""
    notes = (notes or "").strip() or None
    with db.get_db() as conn:
        with conn.cursor() as cur:
            # Lock to prevent concurrent overlapping inserts (TOCTOU race condition)
            cur.execute("LOCK TABLE reservations IN SHARE ROW EXCLUSIVE MODE")
            # Re-check overlap inside the same transaction
            if vehicle_id:
                cur.execute(
                    "SELECT id FROM reservations "
                    "WHERE vehicle_id = %s AND status IN ('active','pending_approval') "
                    "AND start_time < %s AND end_time > %s",
                    (vehicle_id, end_dt, start_dt),
                )
            else:
                cur.execute(
                    "SELECT id FROM reservations "
                    "WHERE status IN ('active','pending_approval') "
                    "AND start_time < %s AND end_time > %s",
                    (end_dt, start_dt),
                )
            if cur.fetchone():
                return None  # Overlap detected under lock — caller should treat as error
            cur.execute(
                "INSERT INTO reservations (user_id, vehicle_id, date, start_time, end_time, notes, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (user_id, vehicle_id, start_dt.date(), start_dt, end_dt, notes, status),
            )
            return cur.fetchone()


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

# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

def get_all_statements() -> list:
    return db.execute(
        "SELECT s.id, s.display_name, s.filename, s.file_size, s.uploaded_at, "
        "u.full_name AS uploaded_by "
        "FROM statements s LEFT JOIN users u ON u.id = s.uploaded_by "
        "ORDER BY s.uploaded_at DESC"
    )


def get_statement_by_id(statement_id: int):
    return db.fetchone("SELECT * FROM statements WHERE id = %s", (statement_id,))


def create_statement(display_name: str, filename: str, file_data: bytes, uploaded_by: int) -> int:
    row = db.fetchone(
        "INSERT INTO statements (display_name, filename, file_data, file_size, uploaded_by) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (display_name, filename, file_data, len(file_data), uploaded_by),
    )
    return row["id"]


def delete_statement(statement_id: int):
    db.execute("DELETE FROM statements WHERE id = %s", (statement_id,), fetch=False)


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


# ---------------------------------------------------------------------------
# Trip logs
# ---------------------------------------------------------------------------

# Checklist constants, fuel levels, and contact info have moved to vehicle_types.py.
# Use vehicle_types.build_checkout_context(vehicle_type, settings) in routes.


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------

def get_all_vehicles() -> list:
    return db.execute(
        "SELECT * FROM vehicles WHERE is_active = TRUE ORDER BY name"
    )


def get_vehicle_by_id(vehicle_id: int):
    return db.fetchone("SELECT * FROM vehicles WHERE id = %s", (vehicle_id,))


def get_default_vehicle_id() -> int | None:
    """Return the id of the first active vehicle (used when vehicle_id not specified)."""
    row = db.fetchone(
        "SELECT id FROM vehicles WHERE is_active = TRUE ORDER BY id LIMIT 1"
    )
    return row["id"] if row else None


# ---------------------------------------------------------------------------
# Club settings
# ---------------------------------------------------------------------------

def get_club_setting(key: str, default: str = None) -> str | None:
    row = db.fetchone("SELECT value FROM club_settings WHERE key = %s", (key,))
    return row["value"] if row else default


def update_club_setting(key: str, value: str):
    db.execute(
        "INSERT INTO club_settings (key, value) VALUES (%s, %s) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()",
        (key, value), fetch=False,
    )


def get_all_club_settings() -> dict:
    """Return all club_settings as a plain dict."""
    rows = db.execute("SELECT key, value FROM club_settings")
    return {row["key"]: row["value"] for row in rows} if rows else {}


def get_trip_log(res_id: int):
    return db.fetchone("SELECT * FROM trip_logs WHERE res_id = %s", (res_id,))


def create_checkout(res_id: int, user_id: int, checkout_time,
                    primary_hours_out, fuel_level_out: str,
                    condition_out: str, checklist_items: list,
                    vehicle_id: int = None):
    import json
    return db.insert(
        "INSERT INTO trip_logs "
        "(res_id, vehicle_id, user_id, checkout_time, primary_hours_out, fuel_level_out, "
        " condition_out, checklist_items) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (res_id, vehicle_id, user_id, checkout_time, primary_hours_out, fuel_level_out,
         condition_out or None, json.dumps(checklist_items)),
    )


def update_checkin(res_id: int, checkin_time, primary_hours_in,
                   fuel_added_gallons, fuel_added_cost, condition_in: str):
    db.execute(
        "UPDATE trip_logs SET checkin_time=%s, primary_hours_in=%s, "
        "fuel_added_gallons=%s, fuel_added_cost=%s, condition_in=%s "
        "WHERE res_id=%s",
        (checkin_time, primary_hours_in, fuel_added_gallons or None,
         fuel_added_cost or None, condition_in or None, res_id),
        fetch=False,
    )


def get_all_trip_logs() -> list:
    return db.execute(
        "SELECT t.*, r.date AS res_date, r.start_time, r.end_time, "
        "       u.full_name, u.username "
        "FROM trip_logs t "
        "JOIN reservations r ON r.id = t.res_id "
        "JOIN users u ON u.id = t.user_id "
        "ORDER BY t.checkout_time DESC"
    )


def get_trip_logs_for_user(user_id: int) -> list:
    return db.execute(
        "SELECT * FROM trip_logs WHERE user_id = %s",
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


# ---------------------------------------------------------------------------
# Profile management
# ---------------------------------------------------------------------------

def update_profile(user_id: int, phone: str):
    db.execute(
        "UPDATE users SET phone = %s WHERE id = %s",
        (phone or None, user_id),
        fetch=False,
    )


def update_avatar(user_id: int, data: bytes, content_type: str):
    db.execute(
        "UPDATE users SET avatar = %s, avatar_content_type = %s WHERE id = %s",
        (data, content_type, user_id),
        fetch=False,
    )


def get_avatar(user_id: int):
    return db.fetchone(
        "SELECT avatar, avatar_content_type FROM users WHERE id = %s",
        (user_id,),
    )


def initiate_email_change(user_id: int, new_email: str, token: str, expires):
    db.execute(
        "UPDATE users SET pending_email = %s, email_verify_token = %s, "
        "email_verify_expires = %s WHERE id = %s",
        (new_email, token, expires, user_id),
        fetch=False,
    )


def confirm_email_change(token: str):
    """Find a pending email change by token, validate expiry, apply it.
    Returns the updated user row on success, None if invalid or expired."""
    row = db.fetchone(
        "SELECT * FROM users WHERE email_verify_token = %s AND is_active = TRUE",
        (token,),
    )
    if not row:
        return None
    if row["email_verify_expires"] and now_ct() > row["email_verify_expires"]:
        return None
    db.execute(
        "UPDATE users SET email = pending_email, pending_email = NULL, "
        "email_verify_token = NULL, email_verify_expires = NULL WHERE id = %s",
        (row["id"],),
        fetch=False,
    )
    return row


# ---------------------------------------------------------------------------
# Message photos
# ---------------------------------------------------------------------------

def get_message_photos(message_id: int) -> list:
    return db.execute(
        "SELECT id, content_type, filename FROM message_photos WHERE message_id = %s ORDER BY id",
        (message_id,),
    )


def get_message_photo_data(photo_id: int):
    return db.fetchone(
        "SELECT photo_data, content_type FROM message_photos WHERE id = %s",
        (photo_id,),
    )


def add_message_photo(message_id: int, data: bytes, content_type: str, filename: str):
    return db.insert(
        "INSERT INTO message_photos (message_id, photo_data, content_type, filename) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (message_id, data, content_type, filename or None),
    )


# ---------------------------------------------------------------------------
# Feedback submissions
# ---------------------------------------------------------------------------

def save_feedback_submission(user_id: int, text: str, attachment_path: str | None,
                              attachment_name: str | None, attachment_type: str | None,
                              routed_to: str, github_issue_url: str | None = None):
    return db.insert(
        "INSERT INTO feedback_submissions "
        "(user_id, text, attachment_path, attachment_name, attachment_type, routed_to, github_issue_url) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (user_id, text, attachment_path or None, attachment_name or None,
         attachment_type or None, routed_to, github_issue_url or None),
    )


def get_all_feedback_submissions() -> list:
    return db.execute(
        "SELECT f.*, u.full_name, u.username "
        "FROM feedback_submissions f "
        "JOIN users u ON u.id = f.user_id "
        "ORDER BY f.submitted_at DESC"
    )


# ---------------------------------------------------------------------------
# Club branding
# ---------------------------------------------------------------------------

def get_branding() -> dict:
    """Return the single club_branding row (colors, logo, hero)."""
    row = db.fetchone("SELECT * FROM club_branding LIMIT 1")
    if not row:
        return {"primary_color": "#0A2342", "accent_color": "#C9A84C",
                "logo_data": None, "logo_content_type": None,
                "hero_data": None, "hero_content_type": None}
    return dict(row)


def update_branding_colors(primary_color: str, accent_color: str):
    db.execute(
        "UPDATE club_branding SET primary_color = %s, accent_color = %s, updated_at = NOW()",
        (primary_color, accent_color), fetch=False,
    )


def update_branding_logo(data: bytes, content_type: str):
    db.execute(
        "UPDATE club_branding SET logo_data = %s, logo_content_type = %s, updated_at = NOW()",
        (data, content_type), fetch=False,
    )


def update_branding_hero(data: bytes, content_type: str):
    db.execute(
        "UPDATE club_branding SET hero_data = %s, hero_content_type = %s, updated_at = NOW()",
        (data, content_type), fetch=False,
    )


def delete_branding_logo():
    db.execute(
        "UPDATE club_branding SET logo_data = NULL, logo_content_type = NULL, updated_at = NOW()",
        fetch=False,
    )


def delete_branding_hero():
    db.execute(
        "UPDATE club_branding SET hero_data = NULL, hero_content_type = NULL, updated_at = NOW()",
        fetch=False,
    )


# ---------------------------------------------------------------------------
# Club photo gallery
# ---------------------------------------------------------------------------

def get_club_photos() -> list:
    return db.execute(
        "SELECT id, title, content_type, sort_order, uploaded_at "
        "FROM club_photos ORDER BY sort_order, uploaded_at"
    )


def get_club_photo(photo_id: int) -> dict | None:
    return db.fetchone("SELECT * FROM club_photos WHERE id = %s", (photo_id,))


def add_club_photo(title: str | None, data: bytes, content_type: str,
                   uploaded_by: int, sort_order: int = 0) -> int:
    row = db.insert(
        "INSERT INTO club_photos (title, photo_data, content_type, sort_order, uploaded_by) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (title or None, data, content_type, sort_order, uploaded_by),
    )
    return row["id"]


def delete_club_photo(photo_id: int):
    db.execute("DELETE FROM club_photos WHERE id = %s", (photo_id,), fetch=False)


# ---------------------------------------------------------------------------
# Vehicle photos
# ---------------------------------------------------------------------------

def get_vehicle_photos() -> list:
    return db.execute(
        "SELECT id, caption, content_type, is_primary, uploaded_at "
        "FROM vehicle_photos ORDER BY is_primary DESC, uploaded_at"
    )


def get_vehicle_photo(photo_id: int) -> dict | None:
    return db.fetchone("SELECT * FROM vehicle_photos WHERE id = %s", (photo_id,))


def get_primary_vehicle_photo() -> dict | None:
    return db.fetchone(
        "SELECT * FROM vehicle_photos WHERE is_primary = TRUE LIMIT 1"
    )


def add_vehicle_photo(caption: str | None, data: bytes, content_type: str,
                      is_primary: bool = False) -> int:
    if is_primary:
        db.execute("UPDATE vehicle_photos SET is_primary = FALSE", fetch=False)
    row = db.insert(
        "INSERT INTO vehicle_photos (caption, photo_data, content_type, is_primary) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (caption or None, data, content_type, is_primary),
    )
    return row["id"]


def set_primary_vehicle_photo(photo_id: int):
    db.execute("UPDATE vehicle_photos SET is_primary = FALSE", fetch=False)
    db.execute(
        "UPDATE vehicle_photos SET is_primary = TRUE WHERE id = %s",
        (photo_id,), fetch=False,
    )


def delete_vehicle_photo(photo_id: int):
    db.execute("DELETE FROM vehicle_photos WHERE id = %s", (photo_id,), fetch=False)
