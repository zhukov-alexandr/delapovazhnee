"""Leaderboard anti-cheat: signed play token + server-side score accumulation.

Mirrors the design doc §11. The token flow is: /api/game/start (mint) →
/api/game/tick (capped, rate-limited "+N") → /api/score (finalize the
server-accumulated total; single-use).
"""
from datetime import datetime, timedelta, timezone

from server.config import MAX_DELTA, MAX_POINTS_PER_SEC, GRACE, TOKEN_TTL_MS
from server.db import get_conn


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _start(client, sid="sid-1", ip="10.1.1.1", character=0):
    client.cookies.set("dp_sid", sid)
    r = client.post(
        "/api/game/start", json={"character": character},
        headers={"X-Forwarded-For": ip},
    )
    return r


def _backdate(settings, token, seconds):
    """Move a token's issued_at into the past so the elapsed ceiling admits ticks."""
    conn = get_conn(settings.db_path)
    try:
        issued = _iso(datetime.now(timezone.utc) - timedelta(seconds=seconds))
        conn.execute("UPDATE play_tokens SET issued_at = ? WHERE token = ?", (issued, token))
        conn.commit()
    finally:
        conn.close()


# --- Happy path ------------------------------------------------------------

def test_mint_tick_finalize_accumulates(client, settings):
    token = _start(client).json()["token"]
    _backdate(settings, token, 60)  # 60s of headroom for the elapsed ceiling
    # Three ticks; tick_count>0 gate means we must backdate last_tick too, so
    # push each through by resetting last_tick into the past between calls.
    total = 0
    for delta in (50, 30, 20):
        conn = get_conn(settings.db_path)
        conn.execute(
            "UPDATE play_tokens SET last_tick = ? WHERE token = ?",
            (_iso(datetime.now(timezone.utc) - timedelta(seconds=5)), token),
        )
        conn.commit(); conn.close()
        r = client.post("/api/game/tick", json={"token": token, "delta": delta})
        assert r.status_code == 200, r.text
        total += delta
        assert r.json()["score"] == total
    r = client.post("/api/score", json={"token": token, "name": "Ann"})
    assert r.status_code == 200
    s = client.get("/api/scores").json()["scores"][0]
    assert s["name"] == "Ann" and s["score"] == 100 and s["character"] == 0


# --- Single-use finalize ---------------------------------------------------

def test_finalize_is_single_use(client, settings):
    token = _start(client).json()["token"]
    _backdate(settings, token, 60)
    assert client.post("/api/score", json={"token": token, "name": "A"}).status_code == 200
    # Replay with the same token → rejected (now finalized).
    r = client.post("/api/score", json={"token": token, "name": "A"})
    assert r.status_code == 400


# --- Expiry ----------------------------------------------------------------

def test_expired_token_rejected_on_tick_and_finalize(client, settings):
    token = _start(client).json()["token"]
    _backdate(settings, token, TOKEN_TTL_MS / 1000 + 60)  # older than TTL
    assert client.post("/api/game/tick", json={"token": token, "delta": 1}).status_code == 400
    assert client.post("/api/score", json={"token": token, "name": "A"}).status_code == 400


# --- Chunk cap -------------------------------------------------------------

def test_delta_over_cap_rejected(client, settings):
    token = _start(client).json()["token"]
    _backdate(settings, token, 60)
    r = client.post("/api/game/tick", json={"token": token, "delta": MAX_DELTA + 1})
    assert r.status_code == 400


# --- Interval rate limit ---------------------------------------------------

def test_ticks_faster_than_interval_rejected(client, settings):
    token = _start(client).json()["token"]
    _backdate(settings, token, 60)
    # First tick is exempt (tick_count == 0); it succeeds.
    assert client.post("/api/game/tick", json={"token": token, "delta": 1}).status_code == 200
    # Pin last_tick to "now" with tick_count>0 so the interval gate applies
    # deterministically (avoids straddling a whole-second boundary in real time).
    conn = get_conn(settings.db_path)
    conn.execute(
        "UPDATE play_tokens SET last_tick = ?, tick_count = 1 WHERE token = ?",
        (_iso(datetime.now(timezone.utc)), token),
    )
    conn.commit(); conn.close()
    r = client.post("/api/game/tick", json={"token": token, "delta": 1})
    assert r.status_code == 429


# --- Elapsed backstop ------------------------------------------------------

def test_elapsed_backstop_rejects_outrunning_score(client, settings):
    token = _start(client).json()["token"]
    # Barely any elapsed time: ceiling ≈ GRACE. A large tick outruns it even
    # though the delta is within MAX_DELTA and the interval is fine.
    _backdate(settings, token, 1)
    r = client.post("/api/game/tick", json={"token": token, "delta": MAX_DELTA})
    # 1s * 2.0 + 20 = 22 < 50 → rejected.
    assert r.status_code == 429


# --- Missing / mismatched session -----------------------------------------

def test_start_requires_session_cookie(client):
    client.cookies.clear()
    assert client.post("/api/game/start", json={"character": 0}).status_code == 400


def test_tick_rejects_sid_mismatch(client, settings):
    token = _start(client, sid="owner").json()["token"]
    _backdate(settings, token, 60)
    client.cookies.set("dp_sid", "someone-else")
    r = client.post("/api/game/tick", json={"token": token, "delta": 1})
    assert r.status_code == 400


def test_finalize_rejects_sid_mismatch(client, settings):
    token = _start(client, sid="owner").json()["token"]
    _backdate(settings, token, 60)
    client.cookies.set("dp_sid", "someone-else")
    r = client.post("/api/score", json={"token": token, "name": "A"})
    assert r.status_code == 400


def test_score_rejects_unknown_token(client):
    client.cookies.set("dp_sid", "sid-x")
    r = client.post("/api/score", json={"token": "nope.deadbeef", "name": "A"})
    assert r.status_code == 400


# --- Regression guard: the original vuln (raw client score) ----------------

def test_old_raw_score_shape_rejected(client):
    """Direct POST /api/score in the old shape (raw score, no token) → rejected."""
    client.cookies.set("dp_sid", "sid-x")
    r = client.post("/api/score", json={"name": "hacker", "score": 999999, "character": 0})
    assert r.status_code == 422  # missing required `token` → validation error


# --- Start mint rate limit -------------------------------------------------

def test_start_rate_limited_per_sid(client):
    client.cookies.set("dp_sid", "spammer")
    codes = [
        client.post("/api/game/start", json={"character": 0},
                    headers={"X-Forwarded-For": f"10.9.9.{i}"}).status_code
        for i in range(7)
    ]
    assert 429 in codes  # 5/min ceiling trips within 7 mints
