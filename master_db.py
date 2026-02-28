"""
Master database connection and query functions for FleetNests.
Connects to the fleetnests_master database for club registry, super-admins,
billing, and shared templates.

Independent of club-specific databases — all club data lives in club_resolver.py / db.py.
"""

import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager


def _get_master_connection():
    """Return a psycopg2 connection to the master database."""
    conn = psycopg2.connect(
        os.environ["MASTER_DATABASE_URL"],
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    return conn


@contextmanager
def get_master_db():
    """Context manager: yields master DB connection, commits on success."""
    conn = _get_master_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _execute(query, params=None, fetch=True):
    with get_master_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if fetch:
                return cur.fetchall()
            return None


def _fetchone(query, params=None):
    with get_master_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()


def _insert(query, params=None):
    with get_master_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            try:
                return cur.fetchone()
            except psycopg2.ProgrammingError:
                return None


# ---------------------------------------------------------------------------
# Club registry
# ---------------------------------------------------------------------------

def get_club_by_short_name(short_name: str) -> dict | None:
    """Return the club row for a given short_name, or None if not found / inactive."""
    return _fetchone(
        "SELECT * FROM clubs WHERE short_name = %s AND is_active = TRUE",
        (short_name,),
    )


def get_all_clubs() -> list:
    return _execute("SELECT * FROM clubs ORDER BY name")


def create_club(name: str, short_name: str, vehicle_type: str,
                db_name: str, db_user: str, subdomain: str,
                contact_email: str, timezone: str) -> dict | None:
    return _insert(
        "INSERT INTO clubs (name, short_name, vehicle_type, db_name, db_user, "
        "subdomain, contact_email, timezone) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (name, short_name, vehicle_type, db_name, db_user,
         subdomain, contact_email, timezone),
    )


def update_club(club_id: int, **fields):
    """Update arbitrary fields on a club row."""
    if not fields:
        return
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    _execute(
        f"UPDATE clubs SET {set_clause} WHERE id = %s",
        (*fields.values(), club_id),
        fetch=False,
    )


def deactivate_club(club_id: int):
    _execute(
        "UPDATE clubs SET is_active = FALSE WHERE id = %s",
        (club_id,), fetch=False,
    )


# ---------------------------------------------------------------------------
# Super-admin accounts
# ---------------------------------------------------------------------------

def get_super_admin_by_username(username: str) -> dict | None:
    return _fetchone(
        "SELECT * FROM super_admins WHERE username = %s AND is_active = TRUE",
        (username,),
    )


def create_super_admin(username: str, full_name: str, email: str,
                       password_hash: str) -> dict | None:
    return _insert(
        "INSERT INTO super_admins (username, full_name, email, password_hash) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (username, full_name, email, password_hash),
    )


# ---------------------------------------------------------------------------
# Vehicle templates (shared checklists)
# ---------------------------------------------------------------------------

def get_default_template(vehicle_type: str) -> dict | None:
    """Return the default checklist template for a vehicle type."""
    return _fetchone(
        "SELECT * FROM vehicle_templates "
        "WHERE vehicle_type = %s AND is_default = TRUE "
        "ORDER BY id LIMIT 1",
        (vehicle_type,),
    )


def get_all_templates() -> list:
    return _execute("SELECT * FROM vehicle_templates ORDER BY vehicle_type, name")


# ---------------------------------------------------------------------------
# Master audit log
# ---------------------------------------------------------------------------

def log_master_action(admin_id: int | None, action: str,
                      target_type: str = None, target_id: int = None,
                      detail: dict = None):
    """Append an immutable master audit entry. Never raises."""
    import json
    try:
        _insert(
            "INSERT INTO master_audit_log (admin_id, action, target_type, target_id, detail) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (admin_id, action, target_type, target_id,
             json.dumps(detail) if detail else None),
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Demo leads (sample site email capture)
# ---------------------------------------------------------------------------

def save_demo_lead(email: str, club_short_name: str, club_name: str,
                   ip_address: str = None, user_agent: str = None) -> bool:
    """Save a prospect email from a sample site. Returns True on success."""
    try:
        _insert(
            "INSERT INTO demo_leads (email, club_short_name, club_name, ip_address, user_agent) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (email.lower().strip(), club_short_name, club_name, ip_address, user_agent),
        )
        return True
    except Exception:
        return False


def get_demo_leads(club_short_name: str = None) -> list:
    """Return all demo leads, optionally filtered by club."""
    import psycopg2.extras
    with get_master_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if club_short_name:
            cur.execute(
                "SELECT * FROM demo_leads WHERE club_short_name=%s ORDER BY created_at DESC",
                (club_short_name,),
            )
        else:
            cur.execute("SELECT * FROM demo_leads ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]
