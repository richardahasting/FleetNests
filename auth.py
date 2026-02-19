"""
Authentication helpers for Bentley Boat Club.
Session-based auth with bcrypt password hashing.
No Flask-Login dependency.
"""

import bcrypt
from functools import wraps
from flask import session, redirect, url_for, flash, abort
import db


# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def check_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def login_user(user: dict):
    """Store minimal user info in the Flask session."""
    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["full_name"] = user["full_name"]
    session["is_admin"] = user["is_admin"]
    session["can_manage_statements"] = bool(user.get("can_manage_statements"))
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


# ---------------------------------------------------------------------------
# DB-backed auth
# ---------------------------------------------------------------------------

def authenticate(login: str, password: str) -> dict | None:
    """Return the user row if credentials are valid and account is active.
    Accepts either username or email address as the login identifier."""
    row = db.fetchone(
        "SELECT * FROM users WHERE (username = %s OR LOWER(email) = LOWER(%s)) AND is_active = TRUE",
        (login, login),
    )
    if row and check_password(password, row["password_hash"]):
        return row
    return None
