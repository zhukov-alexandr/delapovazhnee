"""Tests for game settings store and public config API."""
import pytest
from server.db import get_conn
from server.settings import get_settings, set_settings, DEFAULTS


class TestDefaults:
    """Test that defaults are returned when settings table is empty."""

    def test_get_settings_empty_returns_defaults(self, settings):
        """When no settings are stored, get_settings returns DEFAULTS."""
        conn = get_conn(settings.db_path)
        try:
            result = get_settings(conn)
            assert result == DEFAULTS
            assert result["points_per_line"] == 5
            assert result["speed_mult"] == 1.0
        finally:
            conn.close()


class TestSetAndGet:
    """Test set_settings and get_settings roundtrips."""

    def test_set_and_get_roundtrip(self, settings):
        """Setting values and getting them back works correctly."""
        conn = get_conn(settings.db_path)
        try:
            # Set some values
            result = set_settings(conn, {"points_per_line": 10, "speed_mult": 0.8})
            assert result["points_per_line"] == 10
            assert result["speed_mult"] == 0.8

            # Get them back
            result = get_settings(conn)
            assert result["points_per_line"] == 10
            assert result["speed_mult"] == 0.8
        finally:
            conn.close()

    def test_set_partial_preserves_other_values(self, settings):
        """Setting only one key preserves others at their current value."""
        conn = get_conn(settings.db_path)
        try:
            # Set both initially
            set_settings(conn, {"points_per_line": 10, "speed_mult": 0.8})

            # Set only points_per_line
            result = set_settings(conn, {"points_per_line": 20})
            assert result["points_per_line"] == 20
            assert result["speed_mult"] == 0.8

            # Verify both persisted
            result = get_settings(conn)
            assert result["points_per_line"] == 20
            assert result["speed_mult"] == 0.8
        finally:
            conn.close()


class TestClampingAndCoercion:
    """Test validation, clamping, and type coercion."""

    def test_clamp_speed_mult_high(self, settings):
        """speed_mult > 1.2 is clamped to 1.2."""
        conn = get_conn(settings.db_path)
        try:
            result = set_settings(conn, {"speed_mult": 5.0})
            assert result["speed_mult"] == 1.2
        finally:
            conn.close()

    def test_clamp_speed_mult_low(self, settings):
        """speed_mult < 0.6 is clamped to 0.6."""
        conn = get_conn(settings.db_path)
        try:
            result = set_settings(conn, {"speed_mult": 0.1})
            assert result["speed_mult"] == 0.6
        finally:
            conn.close()

    def test_clamp_points_per_line_min(self, settings):
        """points_per_line < 1 is clamped to 1."""
        conn = get_conn(settings.db_path)
        try:
            result = set_settings(conn, {"points_per_line": 0})
            assert result["points_per_line"] == 1
        finally:
            conn.close()

    def test_points_per_line_is_int(self, settings):
        """points_per_line is returned as int."""
        conn = get_conn(settings.db_path)
        try:
            set_settings(conn, {"points_per_line": 7})
            result = get_settings(conn)
            assert isinstance(result["points_per_line"], int)
            assert result["points_per_line"] == 7
        finally:
            conn.close()

    def test_speed_mult_is_float(self, settings):
        """speed_mult is returned as float."""
        conn = get_conn(settings.db_path)
        try:
            set_settings(conn, {"speed_mult": 1.0})
            result = get_settings(conn)
            assert isinstance(result["speed_mult"], float)
            assert result["speed_mult"] == 1.0
        finally:
            conn.close()

    def test_coerce_bad_stored_value_uses_default(self, settings):
        """If a stored value cannot be coerced, fall back to default."""
        conn = get_conn(settings.db_path)
        try:
            # Directly insert garbage into the database
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ("speed_mult", "not_a_number")
            )
            conn.commit()

            # get_settings should fall back to default
            result = get_settings(conn)
            assert result["speed_mult"] == DEFAULTS["speed_mult"]
        finally:
            conn.close()


class TestPublicConfigAPI:
    """Test the GET /api/config endpoint."""

    def test_config_endpoint_returns_json(self, client):
        """GET /api/config returns JSON with both settings keys."""
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "points_per_line" in data
        assert "speed_mult" in data
        assert isinstance(data["points_per_line"], int)
        assert isinstance(data["speed_mult"], float)

    def test_config_endpoint_returns_defaults_when_empty(self, client):
        """GET /api/config returns defaults when settings table is empty."""
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert data["points_per_line"] == DEFAULTS["points_per_line"]
        assert data["speed_mult"] == DEFAULTS["speed_mult"]

    def test_config_endpoint_public_no_auth(self, client):
        """GET /api/config is public and does not require authentication."""
        response = client.get("/api/config")
        assert response.status_code == 200


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_get_settings_with_missing_key_uses_default(self, settings):
        """If a key is not in the database, its default is used."""
        conn = get_conn(settings.db_path)
        try:
            # Set only one key
            set_settings(conn, {"points_per_line": 10})

            # Get should return both keys
            result = get_settings(conn)
            assert result["points_per_line"] == 10
            assert result["speed_mult"] == DEFAULTS["speed_mult"]
        finally:
            conn.close()

    def test_set_ignores_unknown_keys(self, settings):
        """set_settings ignores keys not in DEFAULTS."""
        conn = get_conn(settings.db_path)
        try:
            result = set_settings(conn, {
                "points_per_line": 10,
                "unknown_key": "should_be_ignored"
            })
            # Should only have the expected keys
            assert set(result.keys()) == set(DEFAULTS.keys())
        finally:
            conn.close()

    def test_speed_mult_boundary_values(self, settings):
        """Test boundary values for speed_mult."""
        conn = get_conn(settings.db_path)
        try:
            # Test exactly 0.6
            result = set_settings(conn, {"speed_mult": 0.6})
            assert result["speed_mult"] == 0.6

            # Test exactly 1.2
            result = set_settings(conn, {"speed_mult": 1.2})
            assert result["speed_mult"] == 1.2

            # Test value in the middle
            result = set_settings(conn, {"speed_mult": 0.9})
            assert result["speed_mult"] == 0.9
        finally:
            conn.close()
