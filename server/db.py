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
        conn.execute("PRAGMA journal_mode=WAL")
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
    # Highest score first; earlier submissions (lower id) win ties. Filter by
    # character (0-3) for the per-character leaderboard tabs; None = overall.
    if character is None:
        return conn.execute(
            "SELECT name, score, character, time_ms FROM scores "
            "ORDER BY score DESC, id ASC LIMIT ?",
            (limit,),
        ).fetchall()
    return conn.execute(
        "SELECT name, score, character, time_ms FROM scores WHERE character = ? "
        "ORDER BY score DESC, id ASC LIMIT ?",
        (character, limit),
    ).fetchall()


def clear_scores(conn) -> None:
    """Wipe the leaderboard (admin: «обнулить все рекорды»)."""
    conn.execute("DELETE FROM scores")
    conn.commit()


def clear_events(conn) -> None:
    """Wipe all analytics events (admin «начать тест заново» — resets both A/B tests)."""
    conn.execute("DELETE FROM events")
    conn.commit()
