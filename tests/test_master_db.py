"""
Tests for master_db.py — club registry, orders, super-admin CRUD.
"""

import pytest
import master_db


@pytest.fixture(autouse=True)
def master_env(monkeypatch):
    """Point master_db at the test master database."""
    monkeypatch.setenv(
        "MASTER_DATABASE_URL",
        "postgresql://fn_test_user:FnTest2026!@127.0.0.1/fleetnests_test_master",
    )


class TestClubCRUD:
    def test_create_club(self):
        club = master_db.create_club(
            name="Harbour Sailing",
            short_name="harbour",
            vehicle_type="boat",
            db_name="club-harbour",
            db_user="club_harbour_user",
            subdomain="harbour",
            contact_email="admin@harbour.com",
            timezone="America/New_York",
            db_password="harbour_secret",
        )
        assert club["id"] is not None
        assert club["short_name"] == "harbour"
        assert club["db_password"] == "harbour_secret"

    def test_create_club_stores_db_password(self):
        """Critical: password must be stored so new clubs work without .env edit."""
        club = master_db.create_club(
            name="Test Flyers",
            short_name="testflyers",
            vehicle_type="plane",
            db_name="club-testflyers",
            db_user="club_testflyers_user",
            subdomain="testflyers",
            contact_email="pilot@testflyers.com",
            timezone="America/Chicago",
            db_password="secret123",
        )
        fetched = master_db.get_club_by_short_name("testflyers")
        assert fetched["db_password"] == "secret123"

    def test_get_club_by_short_name(self, test_club):
        club = master_db.get_club_by_short_name("testclub")
        assert club is not None
        assert club["name"] == "Test Club"

    def test_get_club_by_short_name_not_found(self):
        assert master_db.get_club_by_short_name("doesnotexist") is None

    def test_get_club_by_id(self, test_club):
        club = master_db.get_club_by_id(test_club["id"])
        assert club is not None
        assert club["short_name"] == "testclub"

    def test_get_all_clubs_includes_new_club(self, test_club):
        clubs = master_db.get_all_clubs()
        assert any(c["short_name"] == "testclub" for c in clubs)

    def test_deactivate_club(self, test_club):
        master_db.deactivate_club(test_club["id"])
        club = master_db.get_club_by_id(test_club["id"])
        assert club["is_active"] is False


class TestOrderCRUD:
    def test_create_order(self):
        order_id = master_db.create_order(
            club_name="Blue Marina",
            contact_name="Alice",
            contact_email="alice@marina.com",
            tier="subdomain",
            craft_count=2,
            amount_cents=9900,
            early_bird=False,
            is_trial=False,
        )
        assert order_id is not None
        order = master_db.get_order(order_id)
        assert order["status"] == "pending"

    def test_get_order(self, pending_order):
        order = master_db.get_order(pending_order["id"])
        assert order is not None
        assert order["club_name"] == "Harbour Yacht Club"

    def test_get_provisionable_orders_includes_paid(self, pending_order):
        orders = master_db.get_provisionable_orders()
        assert any(o["id"] == pending_order["id"] for o in orders)

    def test_get_provisionable_orders_excludes_already_provisioned(
        self, master_db_conn
    ):
        with master_db_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO orders (club_name, contact_name, contact_email, tier, "
                "craft_count, amount_cents, status, provisioned_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'provisioned', NOW()) RETURNING id",
                ("Already Done", "Bob", "bob@done.com", "subdomain", 1, 4900),
            )
            done_id = cur.fetchone()["id"]

        orders = master_db.get_provisionable_orders()
        assert not any(o["id"] == done_id for o in orders)

    def test_mark_order_provisioned(self, pending_order):
        master_db.mark_order_provisioned(pending_order["id"])
        order = master_db.get_order(pending_order["id"])
        assert order["status"] == "provisioned"
        assert order["provisioned_at"] is not None

    def test_update_order_payment(self, pending_order):
        master_db.update_order_payment(
            pending_order["id"], "stripe", "cs_test_123", "paid"
        )
        order = master_db.get_order(pending_order["id"])
        assert order["payment_method"] == "stripe"
        assert order["payment_id"]     == "cs_test_123"
        assert order["status"]         == "paid"


class TestSuperAdminCRUD:
    def test_create_super_admin(self):
        import auth
        pw_hash = auth.hash_password("AdminPass1!")
        result = master_db.create_super_admin(
            "sysop", "System Operator", "sysop@fleetnests.com", pw_hash
        )
        assert result["id"] is not None
        admin = master_db.get_super_admin_by_username("sysop")
        assert admin["username"] == "sysop"

    def test_get_super_admin_by_username(self, super_admin):
        admin = master_db.get_super_admin_by_username("superadmin")
        assert admin is not None
        assert admin["full_name"] == "Super Admin"

    def test_get_super_admin_not_found(self):
        assert master_db.get_super_admin_by_username("nobody") is None

    def test_authenticate_super_admin(self, super_admin):
        import auth
        admin = auth.authenticate_super_admin("superadmin", "SuperPass1!")
        assert admin is not None

    def test_authenticate_super_admin_wrong_password(self, super_admin):
        import auth
        assert auth.authenticate_super_admin("superadmin", "wrongpass") is None


class TestVehicleTemplates:
    def test_get_default_boat_template(self):
        tmpl = master_db.get_default_template("boat")
        assert tmpl is not None
        assert tmpl["vehicle_type"] == "boat"
        assert len(tmpl["checklist_items"]) > 0

    def test_get_default_plane_template(self):
        tmpl = master_db.get_default_template("plane")
        assert tmpl is not None
        assert tmpl["vehicle_type"] == "plane"

    def test_get_all_templates(self):
        templates = master_db.get_all_templates()
        types = {t["vehicle_type"] for t in templates}
        assert "boat"  in types
        assert "plane" in types
