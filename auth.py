"""
Authentication helpers for FleetNests.
Session-based auth with bcrypt password hashing.
Supports both club-level users and super-admins (master DB).
No Flask-Login dependency.
"""

import bcrypt
from functools import wraps
from flask import session, redirect, url_for, flash, abort, g
import db


# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def check_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# Club user session helpers
# ---------------------------------------------------------------------------

def login_user(user: dict, club_short_name: str = None):
    """Store minimal user info in the Flask session."""
    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["full_name"] = user["full_name"]
    session["is_admin"] = user["is_admin"]
    session["can_manage_statements"] = bool(user.get("can_manage_statements"))
    if club_short_name:
        session["club_short_name"] = club_short_name
    session.permanent = True


def logout_user():
    session.clear()


def current_user() -> dict | None:
    """Return a dict of current user session data, or None if not logged in."""
    if "user_id" not in session:
        return None
    return {
        "id": session["user_id"],
        "username": session["username"],
        "full_name": session["full_name"],
        "is_admin": session["is_admin"],
        "can_manage_statements": session.get("can_manage_statements", False),
    }


# ---------------------------------------------------------------------------
# Super-admin session helpers
# ---------------------------------------------------------------------------

def login_super_admin(admin: dict):
    """Store super-admin info in session (replaces any club user session)."""
    session.clear()
    session["super_admin_id"] = admin["id"]
    session["super_admin_username"] = admin["username"]
    session["super_admin_full_name"] = admin["full_name"]
    session.permanent = True


def logout_super_admin():
    session.clear()


def current_super_admin() -> dict | None:
    """Return super-admin session dict, or None."""
    if "super_admin_id" not in session:
        return None
    return {
        "id": session["super_admin_id"],
        "username": session["super_admin_username"],
        "full_name": session["super_admin_full_name"],
    }


def authenticate_super_admin(username: str, password: str) -> dict | None:
    """Validate super-admin credentials against the master DB."""
    import master_db
    admin = master_db.get_super_admin_by_username(username)
    if admin and check_password(password, admin["password_hash"]):
        return dict(admin)
    return None


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user():
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def statements_manager_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        if not user.get("can_manage_statements"):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        if not user["is_admin"]:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def superadmin_required(f):
    """Decorator for super-admin routes (master DB admin only)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_super_admin():
            flash("Super-admin login required.", "warning")
            return redirect(url_for("superadmin_login"))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# DB-backed auth (club users)
# ---------------------------------------------------------------------------

def authenticate(login: str, password: str) -> dict | None:
    """Return the user row if credentials are valid and account is active.
    Accepts username, primary email, or secondary email (email2) as the login identifier.
    Secondary email is checked against password_hash2."""
    login_lower = login.lower()
    row = db.fetchone(
        "SELECT * FROM users WHERE (username = %s OR LOWER(email) = %s) AND is_active = TRUE",
        (login, login_lower),
    )
    if row and check_password(password, row["password_hash"]):
        return row
    # Check secondary email + secondary password
    row2 = db.fetchone(
        "SELECT * FROM users WHERE LOWER(email2) = %s AND is_active = TRUE AND password_hash2 IS NOT NULL",
        (login_lower,),
    )
    if row2 and check_password(password, row2["password_hash2"]):
        return row2
    return None
