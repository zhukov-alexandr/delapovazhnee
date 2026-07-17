"""Application settings loaded from environment variables (.env supported)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# --- Leaderboard anti-cheat tuning (see docs/…/leaderboard-anti-cheat) --------
# The ceiling is derived from real observed play (~1 point / 1000 ms). Two
# independent bounds enforce it: the interval path (MAX_DELTA per tick, at most
# one tick per MIN_TICK_INTERVAL_MS) and the tighter elapsed path
# (MAX_POINTS_PER_SEC * elapsed + GRACE). Keep both.
MAX_DELTA = 50               # max points accepted per tick chunk ("+50")
MIN_TICK_INTERVAL_MS = 1000  # >= 1s between accepted ticks (per token)
MAX_POINTS_PER_SEC = 2.0     # elapsed-path ceiling (generous vs observed ~1.0)
GRACE = 20                   # absorb burst/latency at the very start
# Sliding-window idle timeout: a token dies TOKEN_TTL_MS after its LAST activity
# (mint, tick, or game-end), not after mint. An actively played run keeps
# itself alive indefinitely — even a multi-hour game — because ticks refresh
# the window; only an idle/abandoned token expires. Anti-banking is enforced by
# the game-end freeze (ended_at stops scoring + pins the ceiling), so the TTL is
# purely for cleaning up dead tokens.
TOKEN_TTL_MS = 600_000       # 10 min of inactivity
ABS_SCORE_CAP = 1_000_000    # existing hard ceiling, kept as a final backstop
# Per-caller mint limits on POST /api/game/start (rolling 1-minute / 1-hour).
START_LIMIT_PER_MIN = 5
START_LIMIT_PER_HOUR = 30


@dataclass(frozen=True)
class Settings:
    db_path: str
    presave_url: str
    admin_user: str
    admin_pass: str
    secret_key: str
    public_base_url: str | None = None
    app_version: str = "dev"   # deploy tag (APP_VERSION, baked at build): cache-buster + shown in-page


def load_settings() -> Settings:
    """Build Settings from the process environment; loads a local .env if present."""
    load_dotenv()  # no-op if there is no .env file
    return Settings(
        db_path=os.getenv("DB_PATH") or "db/stats.db",
        presave_url=os.getenv("PRESAVE_URL", ""),
        admin_user=os.getenv("ADMIN_USER", "admin"),
        admin_pass=os.getenv("ADMIN_PASS", ""),
        secret_key=os.getenv("SECRET_KEY", "dev-insecure-key"),
        public_base_url=os.getenv("PUBLIC_BASE_URL") or None,
        app_version=os.getenv("APP_VERSION") or "dev",
    )
