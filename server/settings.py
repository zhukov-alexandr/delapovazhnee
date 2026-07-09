"""Game settings store with type coercion and validation."""
from __future__ import annotations

import sqlite3

DEFAULTS = {
    "points_per_line": 5,
    "speed_mult": 1.0,
    "music_volume": 0.28,
}


def get_settings(conn: sqlite3.Connection) -> dict:
    """Read all settings from database, merge over DEFAULTS, and coerce types.

    Falls back to defaults for any missing or unparseable values.
    """
    result = DEFAULTS.copy()

    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    for row in rows:
        key, value = row["key"], row["value"]
        if key not in DEFAULTS:
            # Ignore unknown keys
            continue

        # Coerce to the correct type based on the default value
        try:
            if key == "points_per_line":
                result[key] = int(value)
            elif key == "speed_mult":
                result[key] = float(value)
            elif key == "music_volume":
                result[key] = float(value)
        except (ValueError, TypeError):
            # If coercion fails, use the default
            result[key] = DEFAULTS[key]

    return result


def set_settings(conn: sqlite3.Connection, updates: dict) -> dict:
    """Validate, clamp, and upsert settings. Return the full merged settings.

    Validation:
    - points_per_line: int, min 1
    - speed_mult: float, clamped to [0.6, 1.2]
    - music_volume: float, clamped to [0.0, 1.0]
    """
    # Validate and clamp each provided key
    to_upsert = {}

    if "points_per_line" in updates:
        val = updates["points_per_line"]
        try:
            val = int(val)
        except (ValueError, TypeError):
            val = DEFAULTS["points_per_line"]
        val = max(val, 1)  # Clamp to >= 1
        to_upsert["points_per_line"] = val

    if "speed_mult" in updates:
        val = updates["speed_mult"]
        try:
            val = float(val)
        except (ValueError, TypeError):
            val = DEFAULTS["speed_mult"]
        val = max(0.6, min(val, 1.2))  # Clamp to [0.6, 1.2]
        to_upsert["speed_mult"] = val

    if "music_volume" in updates:
        val = updates["music_volume"]
        try:
            val = float(val)
        except (ValueError, TypeError):
            val = DEFAULTS["music_volume"]
        val = max(0.0, min(val, 1.0))  # Clamp to [0.0, 1.0]
        to_upsert["music_volume"] = val

    # Upsert each key
    for key, value in to_upsert.items():
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=?",
            (key, str(value), str(value))
        )
    conn.commit()

    # Return the full merged settings
    return get_settings(conn)
