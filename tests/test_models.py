"""
Tests for models.py — business logic against the test club DB.
All tests run inside a Flask app context so db.py can resolve the DSN.
"""

import pytest
from datetime import date, datetime, timedelta
import models
import auth


@pytest.fixture(autouse=True)
def app_ctx(app):
    """Push an app context for every test so db.py works."""
    with app.app_context():
        import db
        db.set_club_dsn(
            "postgresql://fn_test_user:FnTest2026!@127.0.0.1/fleetnests_test_club"
        )
        yield


# ── Users ─────────────────────────────────────────────────────────────────────

class TestUserModels:
    def test_get_all_active_users_empty(self):
        assert models.get_all_active_users() == []

    def test_get_all_active_users(self, admin_user):
        users = models.get_all_active_users()
        assert any(u["username"] == "testadmin" for u in users)

    def test_get_user_by_id(self, admin_user):
        user = models.get_user_by_id(admin_user["id"])
        assert user is not None
        assert user["username"] == "testadmin"

    def test_get_user_by_id_missing(self):
        assert models.get_user_by_id(99999) is None

    def test_create_user(self):
        pw = auth.hash_password("NewPass1!")
        row = models.create_user("newuser", "New User", "new@test.com", pw)
        assert row["id"] is not None
        user = models.get_user_by_id(row["id"])
        assert user["username"] == "newuser"
        assert user["is_admin"] is False

    def test_deactivate_user(self, member_user):
        models.deactivate_user(member_user["id"])
        user = models.get_user_by_id(member_user["id"])
        assert user["is_active"] is False

    def test_inactive_user_not_in_active_list(self, member_user):
        models.deactivate_user(member_user["id"])
        users = models.get_all_active_users()
        assert not any(u["id"] == member_user["id"] for u in users)


# ── Password reset tokens ─────────────────────────────────────────────────────

class TestPasswordTokens:
    def test_create_password_token(self, member_user):
        token = models.create_password_token(member_user["id"])
        assert token is not None
        assert len(token) > 20  # urlsafe_b64encode output

    def test_get_user_by_valid_token(self, member_user):
        token = models.create_password_token(member_user["id"])
        user = models.get_user_by_password_token(token)
        assert user is not None
        assert user["id"] == member_user["id"]

    def test_get_user_by_invalid_token(self):
        assert models.get_user_by_password_token("nonexistent-token") is None

    def test_consume_token_clears_it(self, member_user):
        token = models.create_password_token(member_user["id"])
        models.consume_password_token(token)
        assert models.get_user_by_password_token(token) is None

    def test_update_password(self, member_user):
        new_hash = auth.hash_password("NewPassword1!")
        models.update_password(member_user["id"], new_hash)
        assert auth.authenticate("testmember", "NewPassword1!") is not None


# ── Reservations ──────────────────────────────────────────────────────────────

class TestReservationModels:
    def test_make_reservation(self, member_user, vehicle, club_settings):
        tomorrow = date.today() + timedelta(days=2)
        start = datetime.combine(tomorrow, datetime.min.time()).replace(hour=9)
        end   = datetime.combine(tomorrow, datetime.min.time()).replace(hour=17)
        res = models.make_reservation(
            member_user["id"], start, end,
            notes="test notes", vehicle_id=vehicle["id"]
        )
        assert res is not None
        assert res["id"] is not None

    def test_get_user_reservations(self, member_user, reservation):
        result = models.get_user_reservations(member_user["id"])
        assert len(result["upcoming"]) >= 1

    def test_cancel_reservation_by_user(self, member_user, reservation):
        models.cancel_reservation(reservation["id"], member_user["id"])
        res = models.get_reservation_by_id(reservation["id"])
        assert res["status"] == "cancelled"

    def test_cancel_reservation_wrong_user_denied(self, admin_user, reservation):
        """A user can't cancel another user's reservation (unless admin)."""
        result = models.cancel_reservation(reservation["id"], admin_user["id"], is_admin=False)
        # Should return None/False or leave reservation active
        res = models.get_reservation_by_id(reservation["id"])
        assert res["status"] == "active"

    def test_admin_can_cancel_any_reservation(self, admin_user, reservation):
        models.cancel_reservation(reservation["id"], admin_user["id"], is_admin=True)
        res = models.get_reservation_by_id(reservation["id"])
        assert res["status"] == "cancelled"

    def test_get_reservation_by_id(self, reservation):
        res = models.get_reservation_by_id(reservation["id"])
        assert res is not None
        assert res["id"] == reservation["id"]

    def test_get_reservation_by_id_missing(self):
        assert models.get_reservation_by_id(99999) is None


# ── Messages ──────────────────────────────────────────────────────────────────

class TestMessageModels:
    def test_create_and_get_message(self, admin_user):
        row = models.create_message(admin_user["id"], "Hello", "Body text")
        msg = models.get_message_by_id(row["id"])
        assert msg["title"] == "Hello"
        messages = models.get_messages()
        assert any(m["id"] == msg["id"] for m in messages)

    def test_delete_message_by_author(self, admin_user):
        row = models.create_message(admin_user["id"], "To delete", "body")
        models.delete_message(row["id"], admin_user["id"])
        messages = models.get_messages()
        assert not any(m["id"] == msg["id"] for m in messages)


# ── Blackout dates ────────────────────────────────────────────────────────────

class TestBlackoutModels:
    def test_create_and_get_blackout(self, admin_user, vehicle):
        from datetime import date, timedelta
        start = datetime.now() + timedelta(days=5)
        end   = datetime.now() + timedelta(days=7)
        b = models.create_blackout(start, end, "Maintenance", admin_user["id"], vehicle["id"])
        assert b is not None
        blackouts = models.get_all_blackouts()
        assert any(bl["id"] == b["id"] for bl in blackouts)

    def test_delete_blackout(self, admin_user, vehicle):
        start = datetime.now() + timedelta(days=10)
        end   = datetime.now() + timedelta(days=11)
        b = models.create_blackout(start, end, "Test", admin_user["id"], vehicle["id"])
        models.delete_blackout(b["id"])
        blackouts = models.get_all_blackouts()
        assert not any(bl["id"] == b["id"] for bl in blackouts)


# ── Club settings ─────────────────────────────────────────────────────────────

class TestClubSettings:
    def test_get_setting_with_default(self):
        val = models.get_club_setting("nonexistent_key", "default_value")
        assert val == "default_value"

    def test_update_and_get_setting(self):
        models.update_club_setting("test_key", "test_value")
        assert models.get_club_setting("test_key") == "test_value"

    def test_overwrite_setting(self):
        models.update_club_setting("my_key", "first")
        models.update_club_setting("my_key", "second")
        assert models.get_club_setting("my_key") == "second"


# ── Waitlist ──────────────────────────────────────────────────────────────────

class TestWaitlistModels:
    def test_add_to_waitlist(self, member_user):
        desired = date.today() + timedelta(days=3)
        models.add_to_waitlist(member_user["id"], desired, "would love this day")
        wl = models.get_waitlist_for_date(desired)
        assert any(w["user_id"] == member_user["id"] for w in wl)

    def test_is_on_waitlist(self, member_user):
        desired = date.today() + timedelta(days=4)
        assert not models.is_on_waitlist(member_user["id"], desired)
        models.add_to_waitlist(member_user["id"], desired)
        assert models.is_on_waitlist(member_user["id"], desired)

    def test_remove_from_waitlist(self, member_user):
        desired = date.today() + timedelta(days=5)
        models.add_to_waitlist(member_user["id"], desired)
        models.remove_from_waitlist(member_user["id"], desired)
        assert not models.is_on_waitlist(member_user["id"], desired)
