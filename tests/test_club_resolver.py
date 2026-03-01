"""
Tests for club_resolver.py — subdomain parsing, DSN building, cache invalidation.
"""

import pytest
from unittest.mock import patch
import club_resolver


class TestResolveShortName:
    """_resolve_short_name() extracts club slug from Host header."""

    def test_standard_subdomain(self):
        assert club_resolver._resolve_short_name("bentley.fleetnests.com") == "bentley"

    def test_subdomain_with_port(self):
        assert club_resolver._resolve_short_name("myclub.fleetnests.com:8080") == "myclub"

    def test_localhost_two_parts_returns_none(self):
        """myclub.localhost has only 2 parts — resolver needs 3+ for safety."""
        assert club_resolver._resolve_short_name("myclub.localhost") is None

    def test_three_part_local(self):
        assert club_resolver._resolve_short_name("myclub.fn.local") == "myclub"

    def test_bare_domain_returns_none(self):
        assert club_resolver._resolve_short_name("fleetnests.com") is None

    def test_www_returns_none(self):
        assert club_resolver._resolve_short_name("www.fleetnests.com") is None

    def test_api_subdomain_returns_none(self):
        assert club_resolver._resolve_short_name("api.fleetnests.com") is None

    def test_superadmin_subdomain_returns_none(self):
        assert club_resolver._resolve_short_name("superadmin.fleetnests.com") is None

    def test_admin_subdomain_returns_none(self):
        assert club_resolver._resolve_short_name("admin.fleetnests.com") is None

    def test_bare_localhost_returns_none(self):
        assert club_resolver._resolve_short_name("localhost") is None

    def test_hyphenated_short_name(self):
        assert club_resolver._resolve_short_name("sail-away.fleetnests.com") == "sail-away"

    def test_uppercase_normalized(self):
        """Host header should be lowercased before matching."""
        assert club_resolver._resolve_short_name("MyClub.FleetNests.com") == "myclub"


class TestBuildDsn:
    """_build_dsn() builds the correct PostgreSQL DSN."""

    def test_env_var_takes_priority(self, monkeypatch):
        monkeypatch.setenv("DB_PASS_CLUB_TESTCLUB_USER", "envpassword")
        club = {
            "db_user": "club_testclub_user",
            "db_name": "club-testclub",
            "db_password": "dbpassword",
        }
        dsn = club_resolver._build_dsn(club)
        assert "envpassword" in dsn
        assert "dbpassword" not in dsn

    def test_falls_back_to_master_db_password(self, monkeypatch):
        monkeypatch.delenv("DB_PASS_CLUB_TESTCLUB_USER", raising=False)
        monkeypatch.setenv("PG_HOST", "127.0.0.1")
        monkeypatch.setenv("PG_PORT", "5432")
        club = {
            "db_user": "club_testclub_user",
            "db_name": "club-testclub",
            "db_password": "storedpassword",
        }
        dsn = club_resolver._build_dsn(club)
        assert "storedpassword" in dsn
        assert "club_testclub_user" in dsn
        assert "club-testclub" in dsn

    def test_falls_back_to_database_url(self, monkeypatch):
        monkeypatch.delenv("DB_PASS_CLUB_TESTCLUB_USER", raising=False)
        monkeypatch.setenv("DATABASE_URL", "postgresql://fallback/db")
        club = {
            "db_user": "club_testclub_user",
            "db_name": "club-testclub",
            "db_password": None,
        }
        dsn = club_resolver._build_dsn(club)
        assert dsn == "postgresql://fallback/db"

    def test_no_db_user_returns_database_url(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://single/club")
        club = {"db_user": None, "db_name": None}
        assert club_resolver._build_dsn(club) == "postgresql://single/club"

    def test_dsn_format(self, monkeypatch):
        monkeypatch.delenv("DB_PASS_CLUB_MYCLUB_USER", raising=False)
        monkeypatch.setenv("PG_HOST", "db.example.com")
        monkeypatch.setenv("PG_PORT", "5433")
        club = {
            "db_user": "club_myclub_user",
            "db_name": "club-myclub",
            "db_password": "pass123",
        }
        dsn = club_resolver._build_dsn(club)
        assert dsn == "postgresql://club_myclub_user:pass123@db.example.com:5433/club-myclub"


class TestCache:
    """Club cache invalidation."""

    def setup_method(self):
        club_resolver._club_cache.clear()

    def test_invalidate_specific_club(self):
        club_resolver._club_cache["alpha"] = {"id": 1}
        club_resolver._club_cache["beta"]  = {"id": 2}
        club_resolver.invalidate_cache("alpha")
        assert "alpha" not in club_resolver._club_cache
        assert "beta"  in  club_resolver._club_cache

    def test_invalidate_all(self):
        club_resolver._club_cache["a"] = {}
        club_resolver._club_cache["b"] = {}
        club_resolver.invalidate_cache()
        assert len(club_resolver._club_cache) == 0

    def test_load_club_uses_cache(self, monkeypatch):
        """Second call should NOT hit master DB."""
        cached = {"id": 99, "short_name": "cached", "is_active": True,
                  "db_user": None, "db_password": None}
        club_resolver._club_cache["cached"] = cached
        with patch("master_db.get_club_by_short_name") as mock_get:
            result = club_resolver._load_club("cached")
            mock_get.assert_not_called()
        assert result["id"] == 99
