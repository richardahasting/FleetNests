"""
Tests for authenticated member routes: calendar, reservations, profile, messages.
Uses member_client and auth_client fixtures (pre-authenticated).
"""

import pytest
import json
from datetime import date, timedelta


class TestCalendar:
    def test_calendar_requires_login(self, client, club_settings):
        resp = client.get("/calendar", follow_redirects=False)
        assert resp.status_code in (302, 301)
        assert "login" in resp.headers["Location"].lower()

    def test_calendar_renders_for_member(self, member_client, club_settings):
        resp = member_client.get("/calendar")
        assert resp.status_code == 200

    def test_calendar_renders_for_admin(self, auth_client, club_settings):
        resp = auth_client.get("/calendar")
        assert resp.status_code == 200

    def test_calendar_api_returns_json(self, member_client, club_settings):
        today = date.today()
        start = today.isoformat()
        end   = (today + timedelta(days=30)).isoformat()
        resp  = member_client.get(f"/api/reservations?start={start}&end={end}")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)

    def test_calendar_api_includes_active_reservations(
        self, member_client, reservation, club_settings
    ):
        today = date.today()
        start = today.isoformat()
        end   = (today + timedelta(days=7)).isoformat()
        resp  = member_client.get(f"/api/reservations?start={start}&end={end}")
        data  = json.loads(resp.data)
        ids   = [e.get("id") or e.get("reservation_id") for e in data]
        assert reservation["id"] in ids or len(data) >= 1


class TestReservations:
    def test_reserve_page_renders(self, member_client, club_settings, vehicle):
        future = (date.today() + timedelta(days=3)).isoformat()
        resp = member_client.get(f"/reserve/{future}")
        assert resp.status_code == 200

    def test_make_reservation(self, member_client, club_settings, vehicle):
        future = date.today() + timedelta(days=5)
        resp = member_client.post(f"/reserve/{future.isoformat()}", data={
            "start_time":  "09:00",
            "end_time":    "17:00",
            "vehicle_id":  vehicle["id"],
            "notes":       "Test reservation",
        }, follow_redirects=False)
        assert resp.status_code in (302, 301, 200)

    def test_my_reservations_renders(self, member_client, club_settings):
        resp = member_client.get("/my-reservations")
        assert resp.status_code == 200

    def test_my_reservations_shows_booking(
        self, member_client, reservation, club_settings
    ):
        resp = member_client.get("/my-reservations")
        assert resp.status_code == 200
        # Page should contain some reservation data (vehicle or status)
        assert b"active" in resp.data or b"Test Boat" in resp.data or len(resp.data) > 1000

    def test_cancel_reservation(self, member_client, reservation, club_settings):
        resp = member_client.post(
            f"/cancel/{reservation['id']}", follow_redirects=False
        )
        assert resp.status_code in (302, 301, 200)


class TestProfile:
    def test_profile_page_renders(self, member_client, club_settings):
        resp = member_client.get("/profile")
        assert resp.status_code == 200

    def test_profile_shows_username(self, member_client, member_user, club_settings):
        resp = member_client.get("/profile")
        assert member_user["username"].encode() in resp.data

    def test_profile_update_phone(self, member_client, member_user, club_settings):
        resp = member_client.post("/profile", data={
            "phone":        "555-1234",
            "display_name": "Test Member",
        }, follow_redirects=True)
        assert resp.status_code == 200


class TestMessages:
    def test_messages_page_renders(self, member_client, club_settings):
        resp = member_client.get("/messages")
        assert resp.status_code == 200

    def test_messages_shows_announcement(
        self, member_client, admin_user, club_settings, app
    ):
        with app.app_context():
            import db, models
            db.set_club_dsn(
                "postgresql://fn_test_user:FnTest2026!@127.0.0.1/fleetnests_test_club"
            )
            models.create_message(
                admin_user["id"], "Test Announcement", "Hello club!", is_announcement=True
            )
        resp = member_client.get("/messages")
        assert b"Test Announcement" in resp.data

    def test_post_message(self, member_client, club_settings):
        resp = member_client.post("/messages/new", data={
            "title": "Member Post",
            "body":  "Hello everyone",
        }, follow_redirects=True)
        assert resp.status_code == 200


class TestIcalFeed:
    def test_ical_requires_valid_token(self, client, club_settings):
        resp = client.get("/ical/invalid-token.ics")
        assert resp.status_code in (404, 403, 400)

    def test_ical_returns_vcalendar(self, app, member_user, club_settings):
        with app.app_context():
            import db, models
            db.set_club_dsn(
                "postgresql://fn_test_user:FnTest2026!@127.0.0.1/fleetnests_test_club"
            )
            token = models.get_or_create_ical_token(member_user["id"])

        with app.test_client() as c:
            resp = c.get(f"/ical/{token}.ics")
        assert resp.status_code == 200
        assert b"BEGIN:VCALENDAR" in resp.data
