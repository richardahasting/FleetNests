"""
Database connection module for ClubReserve.

Supports per-request DSN switching for multi-tenant operation:
  - club_resolver.py calls set_club_dsn(dsn) in before_request
  - get_connection() reads the request-scoped DSN from Flask g
  - Falls back to DATABASE_URL env var for single-club / dev mode

Completely independent of any specific club schema.
"""

import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager


def set_club_dsn(dsn: str):
    """Store the club-specific DSN on Flask's g for this request."""
    try:
        from flask import g
        g.club_dsn = dsn
    except RuntimeError:
        # Outside request context (e.g. scripts, tests) — no-op
        pass


def _get_dsn() -> str:
    """
    Return the DSN for the current request's club DB.
    Falls back to DATABASE_URL for single-club / dev deployments.
    """
    try:
        from flask import g
        dsn = getattr(g, "club_dsn", None)
        if dsn:
            return dsn
    except RuntimeError:
        pass
    return os.environ.get("DATABASE_URL", "")


def get_connection():
    """Return a new psycopg2 connection for the current club, timezone = Central."""
    dsn = _get_dsn()
    if not dsn:
        raise RuntimeError(
            "No database DSN available. Set DATABASE_URL or ensure club_resolver "
            "is wired in before_request."
        )
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'America/Chicago'")
    return conn


@contextmanager
def get_db():
    """Context manager: yields a connection, commits on success, rolls back on error."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute(query, params=None, fetch=True):
    """
    Run a query and return results.

    fetch=True  → read-only (no commit), returns list of rows
    fetch=False → write operation, commits, returns None
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if fetch:
                return cur.fetchall()
            return None


def fetchone(query, params=None):
    """Run a query and return a single row (or None)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()


def insert(query, params=None):
    """
    Execute an INSERT/UPDATE/DELETE and return the first row of any RETURNING clause.
    Always commits.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            try:
                return cur.fetchone()
            except psycopg2.ProgrammingError:
                return None
