"""
Schema validation tests — verify that all required tables and columns exist
in both the master and club databases. Catches migration drift early.
"""

import pytest
import psycopg2
import psycopg2.extras
TEST_MASTER_DSN = "postgresql://fn_test_user:FnTest2026!@127.0.0.1/fleetnests_test_master"
TEST_CLUB_DSN   = "postgresql://fn_test_user:FnTest2026!@127.0.0.1/fleetnests_test_club"


def _tables(dsn):
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        tables = {r["tablename"] for r in cur.fetchall()}
    conn.close()
    return tables


def _columns(dsn, table):
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        )
        cols = {r["column_name"] for r in cur.fetchall()}
    conn.close()
    return cols


# ── Master DB schema ──────────────────────────────────────────────────────────

MASTER_TABLES = {
    "clubs", "super_admins", "subscriptions",
    "vehicle_templates", "master_audit_log", "orders",
}

class TestMasterSchema:
    def test_all_master_tables_exist(self):
        tables = _tables(TEST_MASTER_DSN)
        missing = MASTER_TABLES - tables
        assert not missing, f"Missing master tables: {missing}"

    def test_clubs_has_db_password(self):
        """Critical for no-restart new club flow."""
        assert "db_password" in _columns(TEST_MASTER_DSN, "clubs")

    def test_clubs_has_provisioned_at(self):
        assert "provisioned_at" in _columns(TEST_MASTER_DSN, "clubs")

    def test_orders_has_provisioned_at(self):
        """Critical for marking orders as provisioned."""
        assert "provisioned_at" in _columns(TEST_MASTER_DSN, "orders")

    def test_clubs_required_columns(self):
        cols = _columns(TEST_MASTER_DSN, "clubs")
        for col in ("id", "name", "short_name", "vehicle_type", "db_name",
                    "db_user", "subdomain", "contact_email", "timezone",
                    "is_active", "db_password"):
            assert col in cols, f"Missing clubs.{col}"

    def test_orders_required_columns(self):
        cols = _columns(TEST_MASTER_DSN, "orders")
        for col in ("id", "club_name", "contact_name", "contact_email",
                    "tier", "status", "provisioned_at", "created_at"):
            assert col in cols, f"Missing orders.{col}"

    def test_super_admins_required_columns(self):
        cols = _columns(TEST_MASTER_DSN, "super_admins")
        for col in ("id", "username", "password_hash", "is_active"):
            assert col in cols, f"Missing super_admins.{col}"


# ── Club DB schema ────────────────────────────────────────────────────────────

CLUB_TABLES = {
    "vehicles", "users", "reservations", "messages", "message_photos",
    "waitlist", "blackout_dates", "trip_logs", "fuel_log",
    "maintenance_records", "maintenance_schedules", "incident_reports",
    "audit_log", "club_settings", "statements", "feedback_submissions",
    "club_branding", "club_photos", "vehicle_photos",
}

class TestClubSchema:
    def test_all_club_tables_exist(self):
        tables = _tables(TEST_CLUB_DSN)
        missing = CLUB_TABLES - tables
        assert not missing, f"Missing club tables: {missing}"

    def test_users_has_password_reset_token(self):
        """Critical for welcome email / first-login flow."""
        assert "password_reset_token" in _columns(TEST_CLUB_DSN, "users")

    def test_users_has_password_reset_expires(self):
        assert "password_reset_expires" in _columns(TEST_CLUB_DSN, "users")

    def test_users_required_columns(self):
        cols = _columns(TEST_CLUB_DSN, "users")
        for col in ("id", "username", "full_name", "email", "password_hash",
                    "is_admin", "is_active", "password_reset_token",
                    "password_reset_expires", "email_verify_token",
                    "ical_token", "display_name", "can_manage_statements"):
            assert col in cols, f"Missing users.{col}"

    def test_reservations_required_columns(self):
        cols = _columns(TEST_CLUB_DSN, "reservations")
        for col in ("id", "user_id", "vehicle_id", "date",
                    "start_time", "end_time", "status"):
            assert col in cols, f"Missing reservations.{col}"

    def test_vehicles_required_columns(self):
        cols = _columns(TEST_CLUB_DSN, "vehicles")
        for col in ("id", "name", "vehicle_type", "is_active"):
            assert col in cols, f"Missing vehicles.{col}"

    def test_trip_logs_required_columns(self):
        cols = _columns(TEST_CLUB_DSN, "trip_logs")
        for col in ("id", "res_id", "checkout_time"):
            assert col in cols, f"Missing trip_logs.{col}"

    def test_club_settings_key_value(self):
        cols = _columns(TEST_CLUB_DSN, "club_settings")
        assert "key"   in cols
        assert "value" in cols
