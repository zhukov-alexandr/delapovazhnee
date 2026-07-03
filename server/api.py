"""Public API: event ingestion (presave redirect and QR are added in later tasks)."""
from __future__ import annotations

from typing import Literal
from fastapi import APIRouter, Query, HTTPException, Request
from fastapi.responses import RedirectResponse, Response, HTMLResponse
from pydantic import BaseModel, Field

from server.config import Settings
from server.db import get_conn, insert_event
from server.qr import build_presave_url, make_qr_png
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

    @router.get("/presave/return")
    def presave_return(
        service: str = Query("unknown"),
        sid: str = Query(""),
        v: str = Query(...),
    ):
        if v not in ("A", "B"):
            raise HTTPException(status_code=400, detail="bad variant")
        if service not in PRESAVE_SERVICES:
            service = "unknown"
        conn = _conn()
        try:
            insert_event(conn, sid, v, "presave_done", {"service": service})
        finally:
            conn.close()
        html = (
            "<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>Сохранено</title></head>"
            "<body style=\"font-family:sans-serif;text-align:center;padding:40px 16px;\">"
            "<p>Сохранено! Возвращайся в игру.</p>"
            "<script>"
            "try{if(window.opener){window.opener.postMessage({dp:\"presave_done\",service:\""
            + service +
            "\"},\"*\")}}catch(e){};"
            "setTimeout(function(){try{window.close()}catch(e){}},400)"
            "</script>"
            "</body></html>"
        )
        return HTMLResponse(html)

    @router.get("/qr")
    def qr(request: Request, v: str = Query(...), sid: str = Query("")):
        if v not in ("A", "B"):
            raise HTTPException(status_code=400, detail="bad variant")
        base = settings.public_base_url or str(request.base_url)
        target = build_presave_url(base, v, sid, "qr")
        png = make_qr_png(target)
        return Response(png, media_type="image/png",
                        headers={"Cache-Control": "no-store"})

    @router.get("/api/config")
    def get_config():
        """Public config endpoint: returns current game settings."""
        conn = _conn()
        try:
            config = get_settings(conn)
            return {
                "points_per_line": config["points_per_line"],
                "speed_mult": config["speed_mult"],
            }
        finally:
            conn.close()

    return router
