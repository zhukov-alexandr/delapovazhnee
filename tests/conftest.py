import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from server.config import Settings
from server.db import get_conn, init_db
from main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        db_path=str(tmp_path / "test.db"),
        presave_url="https://presave.example/target",
        admin_user="admin",
        admin_pass="secret",
        secret_key="test-secret-key",
        public_base_url="http://testserver",
    )


@pytest.fixture(autouse=True)
def init_test_db(settings):
    """Initialize the test database schema for all tests."""
    conn = get_conn(settings.db_path)
    try:
        init_db(conn)
    finally:
        conn.close()


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def save_score(settings):
    """Post a leaderboard entry through the full anti-cheat token flow.

    Real gameplay drips capped deltas over wall-clock seconds; a test can't wait,
    so this backdates the token's issued_at just enough for the elapsed ceiling
    (MAX_POINTS_PER_SEC * elapsed + GRACE) to admit `score`, then finalizes.
    Returns the /api/score Response.
    """
    from server.config import MAX_POINTS_PER_SEC, GRACE

    calls = {"n": 0}

    def _save(client, name="", score=0, character=-1):
        calls["n"] += 1
        # Unique sid + forwarded IP per call so the per-sid/per-IP mint limits
        # (which target abuse) don't trip a test that legitimately saves many.
        sid = "sid-" + str(calls["n"])
        ip = "10.0.0." + str(calls["n"])
        client.cookies.set("dp_sid", sid)
        headers = {"X-Forwarded-For": ip}
        token = client.post(
            "/api/game/start", json={"character": character}, headers=headers
        ).json()["token"]
        conn = get_conn(settings.db_path)
        try:
            # Backdate issue time so the elapsed ceiling permits `score`, and set
            # the server-accumulated total directly (bypassing per-tick pacing).
            need_s = max(0, (score - GRACE)) / MAX_POINTS_PER_SEC + 5
            issued = _iso(datetime.now(timezone.utc) - timedelta(seconds=need_s))
            conn.execute(
                "UPDATE play_tokens SET score = ?, issued_at = ? WHERE token = ?",
                (score, issued, token),
            )
            conn.commit()
        finally:
            conn.close()
        return client.post(
            "/api/score", json={"token": token, "name": name}, headers=headers
        )

    return _save
