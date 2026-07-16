"""SQLite access for the single append-only events table."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    session_id TEXT NOT NULL,
    variant    TEXT NOT NULL,
    event_type TEXT NOT NULL,
    meta       TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_variant_type ON events(variant, event_type);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS scores (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts    TEXT NOT NULL,
    name  TEXT NOT NULL,
    score INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scores_score ON scores(score DESC);
-- Anti-cheat play tokens: one in-place-updated row per game run. The server
-- accumulates the running total here (never trusting a client-sent final),
-- keyed by an HMAC token minted at game start. See docs/…/leaderboard-anti-cheat.
CREATE TABLE IF NOT EXISTS play_tokens (
    token       TEXT PRIMARY KEY,   -- HMAC hex; also the nonce carrier
    sid         TEXT NOT NULL,      -- dp_sid this token was issued to
    ip          TEXT NOT NULL DEFAULT '',  -- client IP at mint (per-IP start rate limit)
    issued_at   TEXT NOT NULL,      -- server ISO ts (authoritative clock)
    last_tick   TEXT NOT NULL,      -- server ts of last accepted delta (rate limit)
    score       INTEGER NOT NULL DEFAULT 0,  -- server-accumulated running total
    character   INTEGER NOT NULL DEFAULT -1,
    tick_count  INTEGER NOT NULL DEFAULT 0,
    finalized   INTEGER NOT NULL DEFAULT 0   -- 1 once written to scores; token dead
);
CREATE INDEX IF NOT EXISTS idx_play_tokens_issued ON play_tokens(issued_at);
"""


def get_conn(db_path: str) -> sqlite3.Connection:
    """Open a connection with Row access; WAL for concurrent reads on file DBs.

    Creates the parent directory (e.g. db/) so sqlite can create the file.
    """
    if db_path != ":memory:":
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if db_path != ":memory:":
        # WAL: concurrent readers don't block the single writer.
        conn.execute("PRAGMA journal_mode=WAL")
        # busy_timeout: when the write lock is held, wait up to 5s for it instead
        # of failing the request immediately with "database is locked". This is
        # what lets bursty concurrent writes (score saves + A/B events) queue
        # rather than 500 under a traffic spike.
        conn.execute("PRAGMA busy_timeout=5000")
        # synchronous=NORMAL is safe under WAL (a crash can only lose the last
        # commits, never corrupt the DB) and drops an fsync per commit, which is
        # the main per-write cost — big throughput win for our commit-per-request
        # pattern.
        conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    # Migrations: older DBs have a scores table without these columns.
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(scores)").fetchall()}
    if "character" not in cols:
        conn.execute("ALTER TABLE scores ADD COLUMN character INTEGER NOT NULL DEFAULT -1")
    if "time_ms" not in cols:
        conn.execute("ALTER TABLE scores ADD COLUMN time_ms INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(ts: str) -> datetime:
    """Parse a `_now_iso()` timestamp back to an aware UTC datetime."""
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def insert_event(conn, session_id: str, variant: str, event_type: str, meta: dict) -> int:
    cur = conn.execute(
        "INSERT INTO events (ts, session_id, variant, event_type, meta) VALUES (?, ?, ?, ?, ?)",
        (_now_iso(), session_id, variant, event_type, json.dumps(meta or {}, ensure_ascii=False)),
    )
    conn.commit()
    return cur.lastrowid


def fetch_all_events(conn) -> list:
    return conn.execute("SELECT * FROM events ORDER BY id").fetchall()


def insert_score(conn, name: str, score: int, character: int = -1, time_ms: int = 0) -> int:
    cur = conn.execute(
        "INSERT INTO scores (ts, name, score, character, time_ms) VALUES (?, ?, ?, ?, ?)",
        (_now_iso(), name, score, character, time_ms),
    )
    conn.commit()
    return cur.lastrowid


def top_scores(conn, limit: int = 10, character: int | None = None) -> list:
    # One row per NAME — that player's best (max score; earlier submission wins
    # ties), so the public top-10 isn't filled by one player's repeat runs.
    # Filter by character (0-3) for the per-character tabs; None = overall.
    # The picked row carries the character/time of the best run itself.
    if character is None:
        return conn.execute(
            """
            SELECT name, score, character, time_ms FROM scores s
            WHERE s.id = (SELECT s2.id FROM scores s2 WHERE s2.name = s.name
                          ORDER BY s2.score DESC, s2.id ASC LIMIT 1)
            ORDER BY s.score DESC, s.id ASC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return conn.execute(
        """
        SELECT name, score, character, time_ms FROM scores s
        WHERE s.character = ?
          AND s.id = (SELECT s2.id FROM scores s2 WHERE s2.name = s.name AND s2.character = ?
                      ORDER BY s2.score DESC, s2.id ASC LIMIT 1)
        ORDER BY s.score DESC, s.id ASC LIMIT ?
        """,
        (character, character, limit),
    ).fetchall()


def clear_scores(conn) -> None:
    """Wipe the leaderboard (admin: «обнулить все рекорды»)."""
    conn.execute("DELETE FROM scores")
    conn.commit()


def delete_score(conn, score_id: int) -> int:
    """Delete one leaderboard row by id (admin). Returns rows deleted (0 or 1)."""
    cur = conn.execute("DELETE FROM scores WHERE id = ?", (score_id,))
    conn.commit()
    return cur.rowcount


def clear_events(conn) -> None:
    """Wipe all analytics events (admin «начать тест заново» — resets both A/B tests)."""
    conn.execute("DELETE FROM events")
    conn.commit()


# --- Anti-cheat play tokens ------------------------------------------------

def create_play_token(conn, token: str, sid: str, character: int = -1, ip: str = "") -> None:
    """Insert a fresh play-token row with score 0. issued_at == last_tick == now."""
    now = _now_iso()
    conn.execute(
        "INSERT INTO play_tokens (token, sid, ip, issued_at, last_tick, score, character) "
        "VALUES (?, ?, ?, ?, ?, 0, ?)",
        (token, sid, ip, now, now, character),
    )
    conn.commit()


def get_play_token(conn, token: str):
    """Return the play-token row, or None if the token was never issued."""
    return conn.execute(
        "SELECT * FROM play_tokens WHERE token = ?", (token,)
    ).fetchone()


def add_token_delta(conn, token: str, delta: int, server_ts: str) -> int:
    """Add `delta` to the token's running total, bump last_tick/tick_count.

    Returns the new running total. Caller is responsible for all validation
    (cap, rate limit, elapsed backstop) BEFORE calling this.
    """
    conn.execute(
        "UPDATE play_tokens SET score = score + ?, last_tick = ?, "
        "tick_count = tick_count + 1 WHERE token = ?",
        (delta, server_ts, token),
    )
    conn.commit()
    row = conn.execute(
        "SELECT score FROM play_tokens WHERE token = ?", (token,)
    ).fetchone()
    return row["score"]


def finalize_play_token(conn, token: str) -> None:
    """Mark a token used (single-use). A replayed finalize then fails lookup."""
    conn.execute("UPDATE play_tokens SET finalized = 1 WHERE token = ?", (token,))
    conn.commit()


def prune_play_tokens(conn, cutoff_iso: str) -> int:
    """Delete non-finalized tokens issued before `cutoff_iso`. Returns rows removed.

    Cheap housekeeping so the table doesn't grow unbounded from abandoned runs.
    Finalized tokens are kept as replay guards (they're small and single-use).
    """
    cur = conn.execute(
        "DELETE FROM play_tokens WHERE finalized = 0 AND issued_at < ?", (cutoff_iso,)
    )
    conn.commit()
    return cur.rowcount


def count_recent_tokens_for_sid(conn, sid: str, since_iso: str) -> int:
    """How many tokens this sid minted at/after `since_iso` (start rate limit)."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM play_tokens WHERE sid = ? AND issued_at >= ?",
        (sid, since_iso),
    ).fetchone()
    return row["n"]


def count_recent_tokens_for_ip(conn, ip: str, since_iso: str) -> int:
    """How many tokens this IP minted at/after `since_iso` (start rate limit)."""
    if not ip:
        return 0
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM play_tokens WHERE ip = ? AND issued_at >= ?",
        (ip, since_iso),
    ).fetchone()
    return row["n"]
