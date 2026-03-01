"""
Tests for admin-only routes: users, blackouts, approvals, maintenance, settings.
Uses auth_client (admin user pre-authenticated).
"""

import pytest
from datetime import date, timedelta


class TestUserManagement:
    def test_users_list_renders(self, auth_client, club_settings):
        resp = auth_client.get("/admin/users")
        assert resp.status_code == 200

    def test_users_list_shows_admin(self, auth_client, admin_user, club_settings):
        resp = auth_client.get("/admin/users")
        assert admin_user["username"].encode() in resp.data

    def test_new_user_form_renders(self, auth_client, club_settings):
        resp = auth_client.get("/admin/users/new")
        assert resp.status_code == 200

    def test_create_user(self, auth_client, club_settings):
        resp = auth_client.post("/admin/users/new", data={
            "username":  "brandnew",
            "full_name": "Brand New",
            "email":     "brandnew@test.com",
            "password":  "Pass1234!",
            "is_admin":  "",
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_deactivate_user(self, auth_client, member_user, club_settings):
        resp = auth_client.post(
            f"/admin/users/{member_user['id']}/deactivate",
            follow_redirects=True,
        )
        assert resp.status_code == 200

    def test_non_admin_cannot_access_user_management(self, member_client, club_settings):
        resp = member_client.get("/admin/users")
        assert resp.status_code == 403


class TestBlackouts:
    def test_blackouts_list_renders(self, auth_client, club_settings):
        resp = auth_client.get("/admin/blackouts")
        assert resp.status_code == 200

    def test_create_blackout(self, auth_client, club_settings, vehicle):
        future = date.today() + timedelta(days=14)
        resp = auth_client.post("/admin/blackouts/new", data={
            "start_date": future.isoformat(),
            "end_date":   (future + timedelta(days=1)).isoformat(),
            "start_time": "00:00",
            "end_time":   "23:59",
            "reason":     "Annual maintenance",
            "vehicle_id": vehicle["id"],
        }, follow_redirects=True)
        assert resp.status_code == 200


class TestApprovals:
    def test_approvals_list_renders(self, auth_client, club_settings):
        resp = auth_client.get("/admin/approvals")
        assert resp.status_code == 200

    def test_approve_reservation(
        self, auth_client, club_settings, club_db_conn, member_user, vehicle
    ):
        """Create a pending reservation then approve it."""
        tomorrow = date.today() + timedelta(days=1)
        with club_db_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO reservations (user_id, vehicle_id, date, start_time, "
                "end_time, status) VALUES (%s, %s, %s, %s, %s, 'pending_approval') "
                "RETURNING id",
                (member_user["id"], vehicle["id"], tomorrow,
                 f"{tomorrow} 09:00", f"{tomorrow} 17:00"),
            )
            res_id = cur.fetchone()["id"]

        resp = auth_client.post(
            f"/admin/approvals/{res_id}/approve", follow_redirects=True
        )
        assert resp.status_code == 200

        with club_db_conn.cursor() as cur:
            cur.execute("SELECT status FROM reservations WHERE id = %s", (res_id,))
            row = cur.fetchone()
        assert row["status"] == "active"

    def test_deny_reservation(
        self, auth_client, club_settings, club_db_conn, member_user, vehicle
    ):
        tomorrow = date.today() + timedelta(days=2)
        with club_db_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO reservations (user_id, vehicle_id, date, start_time, "
                "end_time, status) VALUES (%s, %s, %s, %s, %s, 'pending_approval') "
                "RETURNING id",
                (member_user["id"], vehicle["id"], tomorrow,
                 f"{tomorrow} 10:00", f"{tomorrow} 16:00"),
            )
            res_id = cur.fetchone()["id"]

        resp = auth_client.post(
            f"/admin/approvals/{res_id}/deny", follow_redirects=True
        )
        assert resp.status_code == 200


class TestMaintenance:
    def test_maintenance_list_renders(self, auth_client, club_settings, vehicle):
        resp = auth_client.get(f"/admin/maintenance")
        assert resp.status_code == 200

    def test_add_maintenance_record(self, auth_client, club_settings, vehicle):
        resp = auth_client.post("/admin/maintenance/records/new", data={
            "vehicle_id":    vehicle["id"],
            "performed_by":  "Bob Mechanic",
            "performed_at":  date.today().isoformat(),
            "category":      "Engine",
            "description":   "Oil change",
            "hours_at_service": "150.5",
        }, follow_redirects=False)
        assert resp.status_code in (302, 301, 200)


class TestSettings:
    def test_settings_page_renders(self, auth_client, club_settings):
        resp = auth_client.get("/admin/settings")
        assert resp.status_code == 200

    def test_update_club_name(self, auth_client, club_settings):
        resp = auth_client.post("/admin/settings", data={
            "club_name":       "New Club Name",
            "require_approval": "false",
            "timezone":        "America/Chicago",
        }, follow_redirects=True)
        assert resp.status_code == 200


class TestAuditLog:
    def test_audit_log_renders(self, auth_client, club_settings):
        resp = auth_client.get("/admin/audit-log")
        assert resp.status_code == 200


class TestFuelTracking:
    def test_fuel_list_renders(self, auth_client, club_settings):
        resp = auth_client.get("/admin/fuel")
        assert resp.status_code == 200
