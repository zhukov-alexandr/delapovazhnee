"""Public API: event ingestion + presave redirect/return endpoints."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Query, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel, Field

from server.ab import SID_COOKIE
from server.config import (
    Settings,
    MAX_DELTA,
    MIN_TICK_INTERVAL_MS,
    MAX_POINTS_PER_SEC,
    GRACE,
    TOKEN_TTL_MS,
    ABS_SCORE_CAP,
    START_LIMIT_PER_MIN,
    START_LIMIT_PER_HOUR,
)
from server.db import (
    get_conn,
    insert_event,
    insert_score,
    top_scores,
    create_play_token,
    get_play_token,
    add_token_delta,
    end_play_token,
    finalize_play_token,
    prune_play_tokens,
    count_recent_tokens_for_sid,
    count_recent_tokens_for_ip,
    _now_iso,
    parse_iso,
)
from server.moderation import check_name
from server.settings import get_settings


def _mint_token(secret: str, sid: str, issued_at: str) -> str:
    """HMAC-signed opaque token: `<nonce>.<sig>`. Re-verified server-side."""
    nonce = secrets.token_hex(16)
    body = f"{sid}|{nonce}|{issued_at}"
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{nonce}.{sig}"


def _client_ip(request: Request) -> str:
    """First hop of X-Forwarded-For (set by Caddy), else the socket peer."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""

Variant = Literal["A", "B"]
EventType = Literal[
    "visit", "game_start", "game_over", "cta_view", "cta_click",
    "streaming_click", "presave_done",
]

# Streaming services shown in the in-game presave modal (ids match
# static/js/config.js PRESAVE.SERVICES). "mts" == КИОН Музыка.
PRESAVE_SERVICES = {"yandex", "spotify", "vkmusic", "applemusic", "mts"}


class EventIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    variant: Variant
    event_type: EventType
    meta: dict = {}


class StartIn(BaseModel):
    character: int = Field(default=-1, ge=-1, le=3)


class TickIn(BaseModel):
    token: str = Field(min_length=1, max_length=128)
    delta: int = Field(ge=1, le=ABS_SCORE_CAP)  # server re-clamps to MAX_DELTA


class EndIn(BaseModel):
    token: str = Field(min_length=1, max_length=128)


class ScoreIn(BaseModel):
    # Score/character/time now come from the server-accumulated token row —
    # never from the client. The client only names the run it finalizes.
    token: str = Field(min_length=1, max_length=128)
    name: str = Field(default="", max_length=24)


def build_api_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    def _conn():
        return get_conn(settings.db_path)

    @router.post("/api/event")
    def post_event(ev: EventIn):  # sync -> runs in threadpool, safe with sqlite
        conn = _conn()
        try:
            insert_event(conn, ev.session_id, ev.variant, ev.event_type, ev.meta)
        finally:
            conn.close()
        return {"ok": True}

    # --- Leaderboard anti-cheat: signed play token + server-side accumulation.
    # A game run is: mint a token (/api/game/start) → flush capped deltas as you
    # play (/api/game/tick) → name + finalize the server-accumulated total
    # (/api/score). The client never supplies a trusted score. See the design
    # doc under docs/superpowers/specs. ---

    def _validate_live_token(conn, token: str, request: Request):
        """Return (row, now, issued_dt) for a usable token, or raise HTTPException.

        Enforces: exists, not finalized, not expired, and bound to this dp_sid.
        Shared by /api/game/tick and /api/score (finalize).
        """
        row = get_play_token(conn, token)
        if row is None or row["finalized"]:
            raise HTTPException(status_code=400, detail="invalid token")
        sid = request.cookies.get(SID_COOKIE)
        if not sid or sid != row["sid"]:
            raise HTTPException(status_code=400, detail="token session mismatch")
        now = _now_iso()
        issued_dt = parse_iso(row["issued_at"])
        # Sliding window: expiry is measured from the last activity (last_tick,
        # which is bumped on every tick and on game-end), not from mint — so an
        # actively played run never expires mid-game.
        idle_ms = (parse_iso(now) - parse_iso(row["last_tick"])).total_seconds() * 1000
        if idle_ms > TOKEN_TTL_MS:
            raise HTTPException(status_code=400, detail="token expired")
        return row, now, issued_dt

    @router.post("/api/game/start")
    def post_game_start(body: StartIn, request: Request):
        sid = request.cookies.get(SID_COOKIE)
        if not sid:
            # Real players always carry dp_sid from the `/` page load; a bare
            # curl does not. No session → no token.
            raise HTTPException(status_code=400, detail="no session")
        ip = _client_ip(request)
        conn = _conn()
        try:
            # Rate-limit minting per sid AND per IP so tokens can't be bulk-minted.
            now_dt = parse_iso(_now_iso())
            min_ago = (now_dt - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            hour_ago = (now_dt - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            if (count_recent_tokens_for_sid(conn, sid, min_ago) >= START_LIMIT_PER_MIN
                    or count_recent_tokens_for_ip(conn, ip, min_ago) >= START_LIMIT_PER_MIN
                    or count_recent_tokens_for_sid(conn, sid, hour_ago) >= START_LIMIT_PER_HOUR
                    or count_recent_tokens_for_ip(conn, ip, hour_ago) >= START_LIMIT_PER_HOUR):
                raise HTTPException(status_code=429, detail="too many games")
            # Lazily prune abandoned (non-finalized, expired) tokens.
            cutoff = (now_dt - timedelta(milliseconds=TOKEN_TTL_MS)).strftime("%Y-%m-%dT%H:%M:%SZ")
            prune_play_tokens(conn, cutoff)
            issued_at = _now_iso()
            token = _mint_token(settings.secret_key, sid, issued_at)
            create_play_token(conn, token, sid, body.character, ip)
        finally:
            conn.close()
        return {"token": token}

    @router.post("/api/game/tick")
    def post_game_tick(body: TickIn, request: Request):
        conn = _conn()
        try:
            row, now, issued_dt = _validate_live_token(conn, body.token, request)
            # A run that has ended no longer accepts score (anti-banking): you
            # can't idle on the game-over screen and keep ticking.
            if row["ended_at"]:
                raise HTTPException(status_code=400, detail="game ended")
            # Chunk cap: a single tick can never move the total by more than MAX_DELTA.
            if body.delta < 1 or body.delta > MAX_DELTA:
                raise HTTPException(status_code=400, detail="delta out of range")
            # Elapsed backstop: the running total can never exceed what real time
            # allows (max_points/sec * elapsed + grace). The interval limit and
            # this ceiling are BOTH enforced atomically inside add_token_delta's
            # UPDATE, so concurrent ticks can't race past them.
            elapsed_s = (parse_iso(now) - issued_dt).total_seconds()
            max_score = int(elapsed_s * MAX_POINTS_PER_SEC + GRACE)
            total = add_token_delta(
                conn, body.token, body.delta, now, MIN_TICK_INTERVAL_MS, max_score
            )
            if total is None:
                # Rejected by the interval limit or the elapsed ceiling.
                raise HTTPException(status_code=429, detail="score too fast")
        finally:
            conn.close()
        return {"score": total}

    # --- Game end: freeze the token so scoring stops and the elapsed ceiling is
    # pinned to the real play duration. Idempotent; safe to call on abandon. ---
    @router.post("/api/game/end")
    def post_game_end(body: EndIn, request: Request):
        conn = _conn()
        try:
            row, now, _issued_dt = _validate_live_token(conn, body.token, request)
            if not row["ended_at"]:
                end_play_token(conn, body.token, now)
        finally:
            conn.close()
        return {"ok": True}

    # --- Finalize: name the run and write the SERVER-accumulated total to the
    # leaderboard. Score/character/time come from the token row, not the body. ---
    @router.post("/api/score")
    def post_score(s: ScoreIn, request: Request):
        ok, reason = check_name(s.name)
        if not ok:
            raise HTTPException(status_code=400, detail=reason)
        name = (s.name or "").strip()[:24] or "Аноним"
        conn = _conn()
        try:
            row, now, issued_dt = _validate_live_token(conn, s.token, request)
            # Freeze the run if the client didn't already call /api/game/end, so
            # the elapsed clock can't keep growing while the player sits on the
            # save screen. The play duration is issued_at -> ended_at.
            if not row["ended_at"]:
                end_play_token(conn, s.token, now)
                ended_at = now
            else:
                ended_at = row["ended_at"]
            score = min(int(row["score"]), ABS_SCORE_CAP)
            character = row["character"]
            elapsed_ms = int((parse_iso(ended_at) - issued_dt).total_seconds() * 1000)
            # Final sanity: re-apply the elapsed ceiling one last time, pinned to
            # the real play duration (not "now").
            if score > (elapsed_ms / 1000) * MAX_POINTS_PER_SEC + GRACE:
                score = int((elapsed_ms / 1000) * MAX_POINTS_PER_SEC + GRACE)
            insert_score(conn, name, score, character, elapsed_ms)
            # Single-use: the token is now dead; a replay fails validation.
            finalize_play_token(conn, s.token)
        finally:
            conn.close()
        return {"ok": True}

    @router.get("/api/scores")
    def get_scores(character: int | None = Query(default=None, ge=0, le=3)):
        conn = _conn()
        try:
            rows = top_scores(conn, 10, character)
        finally:
            conn.close()
        return {"scores": [
            {"name": r["name"], "score": r["score"],
             "character": r["character"], "time_ms": r["time_ms"]}
            for r in rows
        ]}

    @router.get("/go/presave")
    def go_presave(
        v: str = Query(...),
        src: str = Query("button"),
        sid: str = Query(""),
    ):
        if v not in ("A", "B"):
            raise HTTPException(status_code=400, detail="bad variant")
        if src not in ("button", "qr"):
            src = "button"
        conn = _conn()
        try:
            insert_event(conn, sid, v, "cta_click", {"src": src})
        finally:
            conn.close()
        return RedirectResponse(settings.presave_url, status_code=302)

    # Legacy 3-segment return URL (no source) — defaults src to "button".
    @router.get("/presave/return/{service}/{sid}/{variant}")
    def presave_return_legacy(request: Request, service: str, sid: str, variant: str):
        return _presave_return(request, service, sid, variant, "button")

    # `src` = where the presave was started: "button" (start/game-over CTA) or
    # "life_lost" (the in-game «Ой» popup) — lets us count in-game presaves.
    @router.get("/presave/return/{service}/{sid}/{variant}/{src}")
    def presave_return(request: Request, service: str, sid: str, variant: str, src: str):
        return _presave_return(request, service, sid, variant, src)

    def _presave_return(request: Request, service: str, sid: str, variant: str, src: str):
        # Path params (not query) so the redirectUrl we hand band.link carries NO
        # query string. On a successful save band.link appends its own
        # "?<service>Presaved=<upc>" marker with a LITERAL "?"; if our URL already
        # had a query the result is a corrupt double-"?" (v becomes "B?..."). A
        # bare-path URL keeps that marker as a clean query we can read.
        if variant not in ("A", "B"):
            raise HTTPException(status_code=400, detail="bad variant")
        if service not in PRESAVE_SERVICES:
            service = "unknown"
        src = src if src in ("button", "life_lost", "song_complete") else "button"
        # band.link redirects here only after the user completes the save,
        # tagging the URL "…Presaved=<upc>". Treat that marker as the success
        # signal; a bare return (no marker) is a cancel and is not counted.
        saved = any("presav" in k.lower() for k in request.query_params.keys())
        if saved:
            conn = _conn()
            try:
                insert_event(conn, sid, variant, "presave_done", {"service": service, "src": src})
            finally:
                conn.close()
        post = (
            "try{if(window.opener){window.opener.postMessage({dp:\"presave_done\",service:\""
            + service + "\"},\"*\")}}catch(e){};"
        ) if saved else ""
        msg = "Сохранено! Возвращайся в игру." if saved else "Возвращайся в игру."
        html = (
            "<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>Пресейв</title></head>"
            "<body style=\"font-family:sans-serif;text-align:center;padding:40px 16px;\">"
            "<p>" + msg + "</p>"
            "<script>"
            + post +
            "setTimeout(function(){try{window.close()}catch(e){}},400)"
            "</script>"
            "</body></html>"
        )
        return HTMLResponse(html)

    @router.get("/api/config")
    def get_config():
        """Public config endpoint: returns current game settings."""
        conn = _conn()
        try:
            config = get_settings(conn)
            return {
                "points_per_line": config["points_per_line"],
                "speed_mult": config["speed_mult"],
                "music_volume": config["music_volume"],
            }
        finally:
            conn.close()

    return router
