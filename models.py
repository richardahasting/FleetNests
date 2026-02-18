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
                password_hash: str, is_admin: bool = False):
    return db.insert(
        "INSERT INTO users (username, full_name, email, password_hash, is_admin) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (username, full_name, email, password_hash, is_admin),
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


# ---------------------------------------------------------------------------
# Reservation queries
# ---------------------------------------------------------------------------

def get_reservations_range(start: date, end: date) -> list:
    """Return all active reservations between start and end dates (inclusive)."""
    return db.execute(
        "SELECT r.id, r.date, r.start_time, r.end_time, r.status, r.user_id, u.full_name "
        "FROM reservations r "
        "JOIN users u ON u.id = r.user_id "
        "WHERE r.date BETWEEN %s AND %s AND r.status = 'active' "
        "ORDER BY r.start_time",
        (start, end),
    )


def get_reservations_for_date(res_date: date) -> list:
    """Return all active reservations for a specific day, ordered by start time."""
    return db.execute(
        "SELECT r.id, r.start_time, r.end_time, r.user_id, u.full_name, u.username "
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


def get_user_future_reservations(user_id: int) -> list:
    """Return distinct future active reservation dates for a user."""
    return db.execute(
        "SELECT DISTINCT date FROM reservations "
        "WHERE user_id = %s AND status = 'active' AND start_time >= %s "
        "ORDER BY date",
        (user_id, now_ct()),
    )


def get_pending_count(user_id: int) -> int:
    """Count active future reservations (each time slot = 1) for a user."""
    row = db.fetchone(
        "SELECT COUNT(*) AS cnt FROM reservations "
        "WHERE user_id = %s AND status = 'active' AND start_time >= %s",
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
      5. User must have < 7 pending reservations
      6. Adding this date must not create a run of > 3 consecutive days
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
        "WHERE r.status = 'active' AND r.start_time < %s AND r.end_time > %s",
        (end_dt, start_dt),
    )
    if overlap:
        return f"That time overlaps with {overlap['full_name']}'s reservation."

    # Pending limit
    if get_pending_count(user_id) >= 7:
        return "You already have 7 upcoming reservations — the maximum allowed."

    # Consecutive day check (date-level; same day with two slots still counts as 1 day)
    future_rows = get_user_future_reservations(user_id)
    existing_dates = {row["date"] for row in future_rows}
    existing_dates.add(start_dt.date())
    if _has_consecutive_violation(existing_dates):
        return "This reservation would exceed the 3-consecutive-day limit."

    return None


def make_reservation(user_id: int, start_dt: datetime, end_dt: datetime):
    """Insert a new active reservation. Call validate_reservation first."""
    return db.insert(
        "INSERT INTO reservations (user_id, date, start_time, end_time) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (user_id, start_dt.date(), start_dt, end_dt),
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
