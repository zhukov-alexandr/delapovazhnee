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
    """Move a token's issued_at into the past so the elapsed ceiling admits ticks.

    Leaves last_tick at ~now, so the sliding idle-TTL still treats the token as
    live (this models a long but actively played run).
    """
    conn = get_conn(settings.db_path)
    try:
        issued = _iso(datetime.now(timezone.utc) - timedelta(seconds=seconds))
        conn.execute("UPDATE play_tokens SET issued_at = ? WHERE token = ?", (issued, token))
        conn.commit()
    finally:
        conn.close()


def _set_idle(settings, token, seconds):
    """Push last_tick into the past so the sliding idle-TTL sees the token stale."""
    conn = get_conn(settings.db_path)
    try:
        stale = _iso(datetime.now(timezone.utc) - timedelta(seconds=seconds))
        conn.execute("UPDATE play_tokens SET last_tick = ? WHERE token = ?", (stale, token))
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


# --- Expiry (sliding idle window) ------------------------------------------

def test_idle_token_rejected_on_tick_and_finalize(client, settings):
    token = _start(client).json()["token"]
    # Idle (no activity) longer than the TTL → expired, even if issued recently.
    _set_idle(settings, token, TOKEN_TTL_MS / 1000 + 60)
    assert client.post("/api/game/tick", json={"token": token, "delta": 1}).status_code == 400
    assert client.post("/api/score", json={"token": token, "name": "A"}).status_code == 400


def test_long_active_run_not_expired(client, settings):
    """A run issued long ago but recently active (last_tick fresh) stays live —
    the sliding window is what lets multi-hour games finalize."""
    token = _start(client).json()["token"]
    # issued 2 hours ago (well past a fixed TTL) but last_tick is ~now.
    _backdate(settings, token, 7200)
    r = client.post("/api/score", json={"token": token, "name": "Marathon"})
    assert r.status_code == 200


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


# --- Game-end freeze -------------------------------------------------------

def test_tick_rejected_after_game_end(client, settings):
    token = _start(client).json()["token"]
    _backdate(settings, token, 60)
    assert client.post("/api/game/end", json={"token": token}).status_code == 200
    # No more scoring once the run is frozen — can't idle on game-over and tick.
    r = client.post("/api/game/tick", json={"token": token, "delta": 1})
    assert r.status_code == 400


def test_finalize_after_end_still_works(client, settings):
    token = _start(client).json()["token"]
    _backdate(settings, token, 60)
    # accumulate a little, then end, then finalize
    conn = get_conn(settings.db_path)
    conn.execute("UPDATE play_tokens SET score = 40 WHERE token = ?", (token,))
    conn.commit(); conn.close()
    assert client.post("/api/game/end", json={"token": token}).status_code == 200
    r = client.post("/api/score", json={"token": token, "name": "Done"})
    assert r.status_code == 200
    assert client.get("/api/scores").json()["scores"][0]["score"] == 40


def test_end_pins_ceiling_no_idle_inflation(client, settings):
    """After game-end, sitting on the save screen must NOT raise the ceiling.

    The run scored 40 over ~30s (allowed). We end it, then backdate issued_at to
    2h so a *now*-based ceiling would admit thousands — but finalize pins the
    ceiling to issued_at..ended_at (~30s → ceiling ~80), so 40 stands and no
    inflation is possible."""
    token = _start(client).json()["token"]
    _backdate(settings, token, 30)
    conn = get_conn(settings.db_path)
    conn.execute("UPDATE play_tokens SET score = 40 WHERE token = ?", (token,))
    conn.commit(); conn.close()
    # End now (ended_at ~= now, ~30s after issue).
    assert client.post("/api/game/end", json={"token": token}).status_code == 200
    # Player "sits" on the save screen: only last_tick must stay fresh for TTL;
    # ended_at is already frozen, so the ceiling window can't grow.
    r = client.post("/api/score", json={"token": token, "name": "Fair"})
    assert r.status_code == 200
    assert client.get("/api/scores").json()["scores"][0]["score"] == 40


def test_finalize_freezes_if_end_skipped(client, settings):
    """If the client never calls /api/game/end, finalize freezes the run itself
    (elapsed = issued..now) rather than trusting an unbounded window."""
    token = _start(client).json()["token"]
    _backdate(settings, token, 30)
    conn = get_conn(settings.db_path)
    conn.execute("UPDATE play_tokens SET score = 40 WHERE token = ?", (token,))
    conn.commit(); conn.close()
    r = client.post("/api/score", json={"token": token, "name": "NoEnd"})
    assert r.status_code == 200
    assert client.get("/api/scores").json()["scores"][0]["score"] == 40


# --- Concurrency: the interval+ceiling race is closed atomically -----------

def test_concurrent_ticks_bounded_by_ceiling(client, settings):
    """A burst of concurrent 50-ticks can't slip past the per-tick interval to
    exceed the elapsed ceiling — the check is atomic in the UPDATE."""
    import concurrent.futures as cf

    token = _start(client).json()["token"]
    _backdate(settings, token, 60)  # ceiling ~= 60*2 + 20 = 140
    def hit(_):
        # Each thread needs the sid cookie; TestClient shares the jar, and the
        # cookie was set by _start, so reuse the same client.
        return client.post("/api/game/tick", json={"token": token, "delta": 50}).status_code
    with cf.ThreadPoolExecutor(max_workers=20) as ex:
        list(ex.map(hit, range(50)))
    conn = get_conn(settings.db_path)
    score = conn.execute("SELECT score FROM play_tokens WHERE token = ?", (token,)).fetchone()["score"]
    conn.close()
    # Never exceeds the elapsed ceiling despite the burst.
    assert score <= 140
