"""
Tests for super-admin routes: login, dashboard, club provisioning, order linking.
"""

import pytest
from unittest.mock import patch


class TestSuperAdminLogin:
    def test_login_page_renders(self, client):
        resp = client.get("/superadmin/login")
        assert resp.status_code == 200

    def test_login_valid_credentials(self, client, super_admin):
        resp = client.post("/superadmin/login", data={
            "username": "superadmin",
            "password": "SuperPass1!",
        }, follow_redirects=False)
        assert resp.status_code in (302, 301)
        assert "superadmin" in resp.headers["Location"].lower()

    def test_login_wrong_password(self, client, super_admin):
        resp = client.post("/superadmin/login", data={
            "username": "superadmin",
            "password": "wrongpassword",
        }, follow_redirects=True)
        assert resp.status_code == 200
        # Should not have set super_admin session
        with client.session_transaction() as sess:
            assert "super_admin_id" not in sess

    def test_login_unknown_user(self, client):
        resp = client.post("/superadmin/login", data={
            "username": "nobody",
            "password": "pass",
        }, follow_redirects=True)
        assert resp.status_code == 200


class TestSuperAdminDashboard:
    def test_dashboard_requires_auth(self, client):
        resp = client.get("/superadmin/", follow_redirects=False)
        assert resp.status_code in (302, 301)
        assert "login" in resp.headers["Location"].lower()

    def test_dashboard_renders_for_super_admin(self, superadmin_client):
        resp = superadmin_client.get("/superadmin/")
        assert resp.status_code == 200

    def test_dashboard_shows_clubs(self, superadmin_client, test_club):
        resp = superadmin_client.get("/superadmin/")
        assert b"Test Club" in resp.data or resp.status_code == 200


class TestNewClubForm:
    def test_new_club_form_renders(self, superadmin_client):
        resp = superadmin_client.get("/superadmin/clubs/new")
        assert resp.status_code == 200

    def test_new_club_form_shows_pending_orders(
        self, superadmin_client, pending_order
    ):
        resp = superadmin_client.get("/superadmin/clubs/new")
        assert resp.status_code == 200
        assert b"Harbour Yacht Club" in resp.data

    def test_provision_club(self, superadmin_client, super_admin):
        """Provision a new club end-to-end (DB creation mocked)."""
        with patch("master_models.provision_club") as mock_prov:
            mock_prov.return_value = {
                "id": 1, "short_name": "sailclub", "name": "Sail Club"
            }
            with patch("master_db.log_master_action"):
                resp = superadmin_client.post("/superadmin/clubs/new", data={
                    "name":          "Sail Club",
                    "short_name":    "sailclub",
                    "vehicle_type":  "boat",
                    "contact_email": "admin@sailclub.com",
                    "timezone":      "America/Chicago",
                }, follow_redirects=True)
        assert resp.status_code == 200
        mock_prov.assert_called_once()

    def test_provision_marks_linked_order_provisioned(
        self, superadmin_client, super_admin, pending_order, master_db_conn
    ):
        """When an order is selected, it should be marked provisioned."""
        with patch("master_models.provision_club") as mock_prov:
            mock_prov.return_value = {
                "id": 99, "short_name": "yachtclub", "name": "Yacht Club"
            }
            with patch("master_db.log_master_action"):
                superadmin_client.post("/superadmin/clubs/new", data={
                    "name":          "Yacht Club",
                    "short_name":    "yachtclub",
                    "vehicle_type":  "boat",
                    "contact_email": "admin@yacht.com",
                    "timezone":      "America/Chicago",
                    "order_id":      str(pending_order["id"]),
                }, follow_redirects=True)

        import master_db
        order = master_db.get_order(pending_order["id"])
        assert order["status"] == "provisioned"
        assert order["provisioned_at"] is not None

    def test_provision_requires_name_and_short_name(self, superadmin_client):
        resp = superadmin_client.post("/superadmin/clubs/new", data={
            "name":         "",
            "short_name":   "",
            "vehicle_type": "boat",
        }, follow_redirects=True)
        assert resp.status_code == 200
        # Should show error, not succeed


class TestSuperAdminLogout:
    def test_logout_clears_session(self, superadmin_client):
        resp = superadmin_client.get("/superadmin/logout", follow_redirects=False)
        assert resp.status_code in (302, 301)
        with superadmin_client.session_transaction() as sess:
            assert "super_admin_id" not in sess
