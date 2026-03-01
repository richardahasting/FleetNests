"""
FleetNests Test Configuration
==============================
Shared fixtures for the entire test suite.

Test databases:
  - fleetnests_test_master  → master DB (clubs, orders, super_admins)
  - fleetnests_test_club    → single club DB (users, reservations, etc.)

Test user: fn_test_user / FnTest2026!

The app runs in single-club mode (CLUB_SHORT_NAME + DATABASE_URL env vars)
for route tests. Master DB tests use MASTER_DATABASE_URL directly.
"""

import os
import sys
import pytest
import psycopg2
import psycopg2.extras

# Ensure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Connection strings ────────────────────────────────────────────────────────
TEST_MASTER_DSN = "postgresql://fn_test_user:FnTest2026!@127.0.0.1/fleetnests_test_master"
TEST_CLUB_DSN   = "postgresql://fn_test_user:FnTest2026!@127.0.0.1/fleetnests_test_club"

# ── Environment setup (before any import of app modules) ──────────────────────
os.environ.update({
    "TESTING":              "1",
    "SECRET_KEY":           "test-secret-key-not-for-production",
    "DATABASE_URL":         TEST_CLUB_DSN,
    "MASTER_DATABASE_URL":  TEST_MASTER_DSN,
    "CLUB_SHORT_NAME":      "testclub",
    "EMAIL_ENABLED":        "false",
    "FLASK_ENV":            "testing",
    "SESSION_COOKIE_SECURE": "false",
})


# ── Low-level DB helpers ──────────────────────────────────────────────────────

def _conn(dsn):
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = True
    return conn


def _truncate_club_tables(conn):
    """Clear all data from the test club DB between tests."""
    tables = [
        "audit_log", "feedback_submissions", "club_photos", "vehicle_photos",
        "club_branding", "statements", "incident_reports", "fuel_log",
        "maintenance_records", "maintenance_schedules", "waitlist",
        "blackout_dates", "message_photos", "messages", "trip_logs",
        "reservations", "users", "vehicles", "club_settings",
    ]
    with conn.cursor() as cur:
        for t in tables:
            cur.execute(f"TRUNCATE TABLE {t} CASCADE")


def _truncate_master_tables(conn):
    """Clear all data from the test master DB between tests."""
    tables = ["master_audit_log", "subscriptions", "orders", "clubs", "super_admins"]
    with conn.cursor() as cur:
        for t in tables:
            cur.execute(f"TRUNCATE TABLE {t} CASCADE")
        # Keep vehicle_templates seeded (they're reference data)


# ── Session-scoped DB connections ─────────────────────────────────────────────

@pytest.fixture(scope="session")
def master_db_conn():
    conn = _conn(TEST_MASTER_DSN)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def club_db_conn():
    conn = _conn(TEST_CLUB_DSN)
    yield conn
    conn.close()


# ── Per-test cleanup ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_dbs(club_db_conn, master_db_conn):
    """Wipe all test data before each test for isolation, then re-seed
    the testclub master record so the club resolver can find it."""
    _truncate_club_tables(club_db_conn)
    _truncate_master_tables(master_db_conn)

    # Re-register testclub so club_resolver can find it on every request.
    with master_db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO clubs (name, short_name, vehicle_type, db_name, db_user, "
            "db_password, subdomain, contact_email) "
            "VALUES ('Test Club', 'testclub', 'boat', 'fleetnests_test_club', "
            "'fn_test_user', 'FnTest2026!', 'testclub', 'admin@testclub.com')"
        )
    import club_resolver
    club_resolver.invalidate_cache("testclub")
    yield


# ── Flask app & test client ───────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    from app import create_app
    application = create_app()
    application.config["TESTING"] = True
    application.config["WTF_CSRF_ENABLED"] = False
    application.config["SERVER_NAME"] = None
    return application


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture
def auth_client(app, admin_user):
    """Test client pre-authenticated as the admin user."""
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]   = admin_user["id"]
            sess["username"]  = admin_user["username"]
            sess["full_name"] = admin_user["full_name"]
            sess["is_admin"]  = True
            sess["can_manage_statements"] = True
        yield c


@pytest.fixture
def member_client(app, member_user):
    """Test client pre-authenticated as a regular member."""
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]   = member_user["id"]
            sess["username"]  = member_user["username"]
            sess["full_name"] = member_user["full_name"]
            sess["is_admin"]  = False
            sess["can_manage_statements"] = False
        yield c


@pytest.fixture
def superadmin_client(app, super_admin):
    """Test client pre-authenticated as a super-admin."""
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["super_admin_id"]        = super_admin["id"]
            sess["super_admin_username"]  = super_admin["username"]
            sess["super_admin_full_name"] = super_admin["full_name"]
        yield c


# ── Seed data fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def vehicle(club_db_conn):
    """A test boat vehicle."""
    with club_db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO vehicles (name, vehicle_type, is_active) "
            "VALUES (%s, %s, TRUE) RETURNING *",
            ("Test Boat", "boat"),
        )
        return dict(cur.fetchone())


@pytest.fixture
def club_settings(club_db_conn, vehicle):
    """Seed minimal club_settings so routes don't blow up."""
    settings = [
        ("club_name",          "Test Club"),
        ("vehicle_type",       "boat"),
        ("require_approval",   "false"),
        ("timezone",           "America/Chicago"),
        ("default_vehicle_id", str(vehicle["id"])),
    ]
    with club_db_conn.cursor() as cur:
        for key, val in settings:
            cur.execute(
                "INSERT INTO club_settings (key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (key, val),
            )
    return dict(settings)


@pytest.fixture
def admin_user(club_db_conn):
    """An admin user with a known password ('Password1!')."""
    import bcrypt
    pw_hash = bcrypt.hashpw(b"Password1!", bcrypt.gensalt()).decode()
    with club_db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (username, full_name, email, password_hash, is_admin) "
            "VALUES (%s, %s, %s, %s, TRUE) RETURNING *",
            ("testadmin", "Test Admin", "admin@testclub.com", pw_hash),
        )
        return dict(cur.fetchone())


@pytest.fixture
def member_user(club_db_conn):
    """A regular member with a known password ('Password1!')."""
    import bcrypt
    pw_hash = bcrypt.hashpw(b"Password1!", bcrypt.gensalt()).decode()
    with club_db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (username, full_name, email, password_hash, is_admin) "
            "VALUES (%s, %s, %s, %s, FALSE) RETURNING *",
            ("testmember", "Test Member", "member@testclub.com", pw_hash),
        )
        return dict(cur.fetchone())


@pytest.fixture
def changeme_user(club_db_conn):
    """A user still using the default 'changeme' password (new club admin)."""
    import bcrypt
    pw_hash = bcrypt.hashpw(b"changeme", bcrypt.gensalt()).decode()
    with club_db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (username, full_name, email, password_hash, is_admin) "
            "VALUES (%s, %s, %s, %s, TRUE) RETURNING *",
            ("newadmin", "New Admin", "new@testclub.com", pw_hash),
        )
        return dict(cur.fetchone())


@pytest.fixture
def reservation(club_db_conn, member_user, vehicle):
    """An active reservation for tomorrow."""
    from datetime import date, timedelta
    tomorrow = date.today() + timedelta(days=1)
    start = f"{tomorrow} 09:00:00"
    end   = f"{tomorrow} 17:00:00"
    with club_db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO reservations (user_id, vehicle_id, date, start_time, end_time, status) "
            "VALUES (%s, %s, %s, %s, %s, 'active') RETURNING *",
            (member_user["id"], vehicle["id"], tomorrow, start, end),
        )
        return dict(cur.fetchone())


@pytest.fixture
def super_admin(master_db_conn):
    """A super-admin user in the master DB."""
    import bcrypt
    pw_hash = bcrypt.hashpw(b"SuperPass1!", bcrypt.gensalt()).decode()
    with master_db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO super_admins (username, full_name, email, password_hash) "
            "VALUES (%s, %s, %s, %s) RETURNING *",
            ("superadmin", "Super Admin", "super@fleetnests.com", pw_hash),
        )
        return dict(cur.fetchone())


@pytest.fixture
def test_club(master_db_conn):
    """Returns the testclub already seeded by clean_dbs (avoids duplicate insert)."""
    with master_db_conn.cursor() as cur:
        cur.execute("SELECT * FROM clubs WHERE short_name = 'testclub'")
        return dict(cur.fetchone())


@pytest.fixture
def pending_order(master_db_conn):
    """An unpaid order waiting for provisioning."""
    with master_db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO orders (club_name, contact_name, contact_email, tier, "
            "craft_count, amount_cents, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
            ("Harbour Yacht Club", "Jane Smith", "jane@harbour.com",
             "subdomain", 3, 14900, "paid"),
        )
        return dict(cur.fetchone())
