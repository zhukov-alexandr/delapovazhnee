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


def insert_score(conn, name: str, score: int) -> int:
    cur = conn.execute(
        "INSERT INTO scores (ts, name, score) VALUES (?, ?, ?)",
        (_now_iso(), name, score),
    )
    conn.commit()
    return cur.lastrowid


def top_scores(conn, limit: int = 10) -> list:
    # Highest score first; earlier submissions (lower id) win ties.
    return conn.execute(
        "SELECT name, score FROM scores ORDER BY score DESC, id ASC LIMIT ?",
        (limit,),
    ).fetchall()
