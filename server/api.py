"""Public API: event ingestion + presave redirect/return endpoints."""
from __future__ import annotations

from typing import Literal
from fastapi import APIRouter, Query, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel, Field

from server.config import Settings
from server.db import get_conn, insert_event, insert_score, top_scores
from server.moderation import check_name
from server.settings import get_settings

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


class ScoreIn(BaseModel):
    name: str = Field(default="", max_length=24)
    score: int = Field(ge=0, le=1_000_000)
    character: int = Field(default=-1, ge=-1, le=3)
    time_ms: int = Field(default=0, ge=0, le=86_400_000)  # in-game play time (anti-cheat)


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

    # --- Leaderboard: name + score, persisted in the scores table (survives
    # redeploys via the dbdata volume, same as events). ---
    @router.post("/api/score")
    def post_score(s: ScoreIn):
        ok, reason = check_name(s.name)
        if not ok:
            raise HTTPException(status_code=400, detail=reason)
        name = (s.name or "").strip()[:24] or "Аноним"
        conn = _conn()
        try:
            insert_score(conn, name, s.score, s.character, s.time_ms)
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

    @router.get("/presave/return/{service}/{sid}/{variant}")
    def presave_return(request: Request, service: str, sid: str, variant: str):
        # Path params (not query) so the redirectUrl we hand band.link carries NO
        # query string. On a successful save band.link appends its own
        # "?<service>Presaved=<upc>" marker with a LITERAL "?"; if our URL already
        # had a query the result is a corrupt double-"?" (v becomes "B?..."). A
        # bare-path URL keeps that marker as a clean query we can read.
        if variant not in ("A", "B"):
            raise HTTPException(status_code=400, detail="bad variant")
        if service not in PRESAVE_SERVICES:
            service = "unknown"
        # band.link redirects here only after the user completes the save,
        # tagging the URL "…Presaved=<upc>". Treat that marker as the success
        # signal; a bare return (no marker) is a cancel and is not counted.
        saved = any("presav" in k.lower() for k in request.query_params.keys())
        if saved:
            conn = _conn()
            try:
                insert_event(conn, sid, variant, "presave_done", {"service": service})
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
