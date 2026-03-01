"""
Tests for auth.py — password hashing, session helpers, decorators.
These are pure unit tests; no database required for password functions.
"""

import pytest
import auth


# ── Password utilities ────────────────────────────────────────────────────────

class TestPasswordHashing:
    def test_hash_produces_bcrypt_string(self):
        h = auth.hash_password("hello")
        assert h.startswith("$2b$")

    def test_check_correct_password(self):
        h = auth.hash_password("correct-horse")
        assert auth.check_password("correct-horse", h) is True

    def test_check_wrong_password(self):
        h = auth.hash_password("correct-horse")
        assert auth.check_password("wrong-horse", h) is False

    def test_check_empty_password(self):
        h = auth.hash_password("nonempty")
        assert auth.check_password("", h) is False

    def test_each_hash_is_unique(self):
        """bcrypt uses random salt — same input yields different hashes."""
        h1 = auth.hash_password("same")
        h2 = auth.hash_password("same")
        assert h1 != h2

    def test_changeme_default_password(self):
        """Verify the hard-coded default admin password hash used during provisioning."""
        default_hash = "$2b$12$01bbF/OdljvkfJ7nRT6amux/bmlPs/jho4JWjRANfppro9OErhKmu"
        assert auth.check_password("changeme", default_hash) is True

    def test_changeme_wrong_input(self):
        default_hash = "$2b$12$01bbF/OdljvkfJ7nRT6amux/bmlPs/jho4JWjRANfppro9OErhKmu"
        assert auth.check_password("Changeme", default_hash) is False


# ── Session helpers ───────────────────────────────────────────────────────────

class TestClubUserSession:
    def test_login_sets_session_keys(self, app):
        user = {
            "id": 42, "username": "alice", "full_name": "Alice Smith",
            "is_admin": False, "can_manage_statements": False,
        }
        with app.test_request_context():
            from flask import session
            auth.login_user(user, club_short_name="myclub")
            assert session["user_id"]   == 42
            assert session["username"]  == "alice"
            assert session["is_admin"]  is False
            assert session["club_short_name"] == "myclub"

    def test_login_clears_previous_session(self, app):
        with app.test_request_context():
            from flask import session
            session["stale_key"] = "old_value"
            auth.login_user(
                {"id": 1, "username": "u", "full_name": "U",
                 "is_admin": False, "can_manage_statements": False}
            )
            assert "stale_key" not in session

    def test_logout_clears_session(self, app):
        with app.test_request_context():
            from flask import session
            session["user_id"] = 99
            auth.logout_user()
            assert "user_id" not in session

    def test_current_user_returns_dict_when_logged_in(self, app):
        with app.test_request_context():
            from flask import session
            session["user_id"]   = 7
            session["username"]  = "bob"
            session["full_name"] = "Bob Jones"
            session["is_admin"]  = True
            session["can_manage_statements"] = False
            user = auth.current_user()
            assert user["id"] == 7
            assert user["username"] == "bob"
            assert user["is_admin"] is True

    def test_current_user_returns_none_when_not_logged_in(self, app):
        with app.test_request_context():
            assert auth.current_user() is None


class TestSuperAdminSession:
    def test_login_super_admin_sets_session(self, app):
        admin = {"id": 1, "username": "sysop", "full_name": "System Operator"}
        with app.test_request_context():
            from flask import session
            auth.login_super_admin(admin)
            assert session["super_admin_id"]       == 1
            assert session["super_admin_username"] == "sysop"

    def test_current_super_admin_returns_none_without_session(self, app):
        with app.test_request_context():
            assert auth.current_super_admin() is None

    def test_current_super_admin_returns_dict(self, app):
        with app.test_request_context():
            from flask import session
            session["super_admin_id"]        = 5
            session["super_admin_username"]  = "sysop"
            session["super_admin_full_name"] = "System Operator"
            admin = auth.current_super_admin()
            assert admin["id"] == 5


# ── Decorators via HTTP ───────────────────────────────────────────────────────

class TestDecorators:
    def test_login_required_redirects_unauthenticated(self, client):
        resp = client.get("/calendar", follow_redirects=False)
        assert resp.status_code in (302, 301)
        assert "/login" in resp.headers["Location"]

    def test_admin_required_blocks_regular_user(self, member_client, club_settings):
        resp = member_client.get("/admin/users", follow_redirects=False)
        assert resp.status_code == 403

    def test_admin_required_allows_admin(self, auth_client, club_settings):
        resp = auth_client.get("/admin/users")
        assert resp.status_code == 200

    def test_superadmin_required_redirects_unauthenticated(self, client):
        resp = client.get("/superadmin/", follow_redirects=False)
        assert resp.status_code in (302, 301)

    def test_superadmin_required_allows_super_admin(self, superadmin_client):
        resp = superadmin_client.get("/superadmin/")
        assert resp.status_code == 200
