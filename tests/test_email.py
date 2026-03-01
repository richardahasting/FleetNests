"""
Tests for email_notify.py — verify correct email composition and graceful
failures. SMTP is always mocked; no real mail is sent.
"""

import pytest
import email as _email_module
from unittest.mock import patch, MagicMock
import email_notify


def _decode_message(raw: str) -> str:
    """Decode a MIME message string to plain text."""
    msg = _email_module.message_from_string(raw)
    payload = msg.get_payload(decode=True)
    return payload.decode("utf-8") if payload else raw


@pytest.fixture(autouse=True)
def email_enabled(monkeypatch):
    """Enable email for these tests (module-level constant must be patched directly)."""
    monkeypatch.setattr("email_notify.EMAIL_ENABLED", True)
    monkeypatch.setattr("email_notify.SMTP_HOST", "localhost")
    monkeypatch.setattr("email_notify.SMTP_PORT", 25)
    monkeypatch.setenv("EMAIL_FROM", "noreply@fleetnests.com")
    monkeypatch.setenv("APP_URL", "https://fleetnests.com")


def _mock_smtp():
    """Context manager mock for smtplib.SMTP."""
    smtp_inst = MagicMock()
    smtp_inst.__enter__.return_value = smtp_inst
    return patch("smtplib.SMTP", return_value=smtp_inst), smtp_inst


class TestNotifyClubProvisioned:
    def test_sends_welcome_email(self):
        ctx, smtp = _mock_smtp()
        with ctx:
            result = email_notify.notify_club_provisioned(
                contact_email="admin@newclub.com",
                club_name="New Club",
                short_name="newclub",
                token="abc123token",
            )
        assert result is True
        smtp.sendmail.assert_called_once()

    def test_email_contains_set_password_link(self):
        ctx, smtp = _mock_smtp()
        with ctx:
            email_notify.notify_club_provisioned(
                "admin@newclub.com", "New Club", "newclub", "mytoken123"
            )
        raw = smtp.sendmail.call_args[0][2]
        body = _decode_message(raw)
        assert "set-password" in body
        assert "mytoken123"   in body

    def test_email_contains_club_url(self):
        ctx, smtp = _mock_smtp()
        with ctx:
            email_notify.notify_club_provisioned(
                "admin@newclub.com", "My Club", "myclub", "tok"
            )
        body = _decode_message(smtp.sendmail.call_args[0][2])
        assert "myclub" in body

    def test_skips_when_email_disabled(self, monkeypatch):
        monkeypatch.setattr("email_notify.EMAIL_ENABLED", False)
        ctx, smtp = _mock_smtp()
        with ctx:
            result = email_notify.notify_club_provisioned(
                "admin@club.com", "Club", "club", "tok"
            )
        assert result is False
        smtp.sendmail.assert_not_called()

    def test_skips_when_no_contact_email(self):
        ctx, smtp = _mock_smtp()
        with ctx:
            result = email_notify.notify_club_provisioned(
                contact_email="",
                club_name="Club", short_name="club", token="tok",
            )
        assert result is False

    def test_returns_false_on_smtp_error(self):
        with patch("smtplib.SMTP", side_effect=ConnectionRefusedError("no server")):
            result = email_notify.notify_club_provisioned(
                "admin@club.com", "Club", "club", "tok"
            )
        assert result is False


class TestNotifyPasswordReset:
    def test_sends_reset_email(self, app, member_user, club_settings):
        ctx, smtp = _mock_smtp()
        user = dict(member_user)
        user["email"] = "member@testclub.com"
        with app.app_context():
            with ctx:
                result = email_notify.notify_password_reset(user, "resettoken")
        assert result is True

    def test_reset_email_contains_token(self, app, member_user, club_settings):
        ctx, smtp = _mock_smtp()
        user = dict(member_user)
        user["email"] = "member@testclub.com"
        with app.app_context():
            with ctx:
                email_notify.notify_password_reset(user, "unique-reset-tok")
        body = _decode_message(smtp.sendmail.call_args[0][2])
        assert "unique-reset-tok" in body


class TestNotifyReservationConfirmed:
    def test_sends_confirmation_email(self, app, member_user, reservation, club_settings):
        ctx, smtp = _mock_smtp()
        user = dict(member_user)
        user["email"] = "member@testclub.com"
        with app.app_context():
            import db
            db.set_club_dsn(
                "postgresql://fn_test_user:FnTest2026!@127.0.0.1/fleetnests_test_club"
            )
            with ctx:
                result = email_notify.notify_reservation_confirmed(user, reservation)
        assert result is True

    def test_skips_user_without_email(self, app, reservation, club_settings):
        ctx, smtp = _mock_smtp()
        user = {"id": 1, "full_name": "No Email", "email": None}
        with app.app_context():
            with ctx:
                result = email_notify.notify_reservation_confirmed(user, reservation)
        assert result is False
        smtp.sendmail.assert_not_called()


class TestEmailDisabledGlobally:
    def test_all_notifications_skip_when_disabled(self, monkeypatch):
        monkeypatch.setattr("email_notify.EMAIL_ENABLED", False)
        ctx, smtp = _mock_smtp()
        with ctx:
            email_notify.notify_club_provisioned("a@b.com", "C", "c", "t")
        smtp.sendmail.assert_not_called()
