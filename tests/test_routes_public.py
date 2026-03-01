"""
Tests for public routes: login, logout, password reset.
These don't require authentication.
"""

import pytest
from unittest.mock import patch


class TestLoginPage:
    def test_login_page_renders(self, client, club_settings):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert b"login" in resp.data.lower()

    def test_login_success_redirects_to_calendar(self, client, admin_user, club_settings):
        resp = client.post("/login", data={
            "username": "testadmin",
            "password": "Password1!",
        }, follow_redirects=False)
        assert resp.status_code in (302, 301)
        assert "calendar" in resp.headers["Location"].lower()

    def test_login_wrong_password(self, client, admin_user, club_settings):
        resp = client.post("/login", data={
            "username": "testadmin",
            "password": "wrongpassword",
        }, follow_redirects=True)
        assert resp.status_code == 200
        # Should show error, not redirect to calendar
        assert b"login" in resp.data.lower()

    def test_login_unknown_user(self, client, club_settings):
        resp = client.post("/login", data={
            "username": "nobody",
            "password": "Password1!",
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_login_with_email(self, client, admin_user, club_settings):
        """Login accepts email as well as username."""
        resp = client.post("/login", data={
            "username": "admin@testclub.com",
            "password": "Password1!",
        }, follow_redirects=False)
        assert resp.status_code in (302, 301)

    def test_login_inactive_user_denied(self, client, member_user, club_settings, club_db_conn):
        """Inactive users cannot log in."""
        with club_db_conn.cursor() as cur:
            cur.execute("UPDATE users SET is_active = FALSE WHERE id = %s", (member_user["id"],))
        resp = client.post("/login", data={
            "username": "testmember", "password": "Password1!"
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"calendar" not in resp.data.lower()

    def test_first_login_changeme_redirects_to_set_password(
        self, client, changeme_user, club_settings
    ):
        """Users with default 'changeme' password are forced to set a new one."""
        resp = client.post("/login", data={
            "username": "newadmin",
            "password": "changeme",
        }, follow_redirects=False)
        assert resp.status_code in (302, 301)
        assert "set-password" in resp.headers["Location"].lower()


class TestLogout:
    def test_logout_clears_session(self, auth_client, club_settings):
        # First verify we're logged in
        resp = auth_client.get("/calendar")
        assert resp.status_code == 200

        # Logout
        resp = auth_client.get("/logout", follow_redirects=False)
        assert resp.status_code in (302, 301)

        # Calendar now requires login
        resp = auth_client.get("/calendar", follow_redirects=False)
        assert resp.status_code in (302, 301)
        assert "login" in resp.headers["Location"].lower()


class TestPasswordReset:
    def test_forgot_password_page_renders(self, client, club_settings):
        resp = client.get("/forgot-password")
        assert resp.status_code == 200

    def test_forgot_password_submit_valid_email(self, client, member_user, club_settings):
        with patch("email_notify.notify_password_reset", return_value=True):
            resp = client.post("/forgot-password", data={
                "email": "member@testclub.com"
            }, follow_redirects=True)
        assert resp.status_code == 200

    def test_forgot_password_unknown_email_no_error_leak(self, client, club_settings):
        """Security: don't reveal whether email exists."""
        resp = client.post("/forgot-password", data={
            "email": "unknown@example.com"
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_set_password_valid_token(self, client, member_user, club_settings):
        import models
        with client.application.app_context():
            import db
            db.set_club_dsn(
                "postgresql://fn_test_user:FnTest2026!@127.0.0.1/fleetnests_test_club"
            )
            token = models.create_password_token(member_user["id"])

        resp = client.get(f"/set-password/{token}")
        assert resp.status_code == 200

    def test_set_password_invalid_token(self, client, club_settings):
        resp = client.get("/set-password/invalid-token-xyz")
        # Should show error or redirect, not crash
        assert resp.status_code in (200, 302, 404)

    def test_set_password_post_changes_password(self, client, member_user, club_settings):
        import models, auth as _auth
        with client.application.app_context():
            import db
            db.set_club_dsn(
                "postgresql://fn_test_user:FnTest2026!@127.0.0.1/fleetnests_test_club"
            )
            token = models.create_password_token(member_user["id"])

        resp = client.post(f"/set-password/{token}", data={
            "new_password":     "NewSecure1!",
            "confirm_password": "NewSecure1!",
        }, follow_redirects=False)
        assert resp.status_code in (302, 301)

        # Old password no longer works
        with client.application.app_context():
            import db
            db.set_club_dsn(
                "postgresql://fn_test_user:FnTest2026!@127.0.0.1/fleetnests_test_club"
            )
            assert _auth.authenticate("testmember", "Password1!") is None
            assert _auth.authenticate("testmember", "NewSecure1!") is not None
