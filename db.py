"""
Standalone database connection module for Bentley Boat Club.
Completely independent — does not share code with any other project.
"""

import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager


def get_connection():
    """Return a new psycopg2 connection from DATABASE_URL, session timezone = Central."""
    conn = psycopg2.connect(
        os.environ["DATABASE_URL"],
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
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
            # For write operations, commit is handled by get_db context manager
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
