"""Admin auth, metrics dashboard, and raw-events CSV export."""
from __future__ import annotations

import csv
import io
import secrets
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from server.config import Settings
from server.db import get_conn, fetch_all_events, clear_scores, clear_events
from server.metrics import compute_dashboard, compute_presave_dashboard
from server.settings import get_settings, set_settings


def build_admin_router(settings: Settings, templates: Jinja2Templates) -> APIRouter:
    router = APIRouter(prefix="/admin")

    def is_admin(request: Request) -> bool:
        return bool(request.session.get("admin"))

    @router.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return templates.TemplateResponse(request, "admin_login.html", {"error": False})

    @router.post("/login")
    def login(request: Request, username: str = Form(...), password: str = Form(...)):
        ok = (secrets.compare_digest(username, settings.admin_user)
              and secrets.compare_digest(password, settings.admin_pass))
        if not ok:
            return templates.TemplateResponse(
                request, "admin_login.html", {"error": True}, status_code=200)
        request.session["admin"] = True
        return RedirectResponse("/admin", status_code=303)

    @router.get("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/admin/login", status_code=303)

    @router.get("", response_class=HTMLResponse)
    def dashboard(request: Request, reset: int = 0):
        if not is_admin(request):
            return RedirectResponse("/admin/login", status_code=302)
        conn = get_conn(settings.db_path)
        try:
            data = compute_dashboard(conn)
        finally:
            conn.close()
        return templates.TemplateResponse(
            request, "admin.html", {"d": data, "active": "ab", "reset": bool(reset)})

    @router.get("/presave", response_class=HTMLResponse)
    def presave_dashboard(request: Request, reset: int = 0):
        if not is_admin(request):
            return RedirectResponse("/admin/login", status_code=302)
        conn = get_conn(settings.db_path)
        try:
            data = compute_presave_dashboard(conn)
        finally:
            conn.close()
        return templates.TemplateResponse(
            request, "admin_presave.html",
            {"d": data, "active": "presave", "reset": bool(reset)})

    # Reset the A/B test: wipe all analytics events (both dashboards read them).
    @router.post("/events/reset")
    def events_reset(request: Request, next: str = Form(default="/admin")):
        if not is_admin(request):
            return RedirectResponse("/admin/login", status_code=302)
        conn = get_conn(settings.db_path)
        try:
            clear_events(conn)
        finally:
            conn.close()
        target = next if next in ("/admin", "/admin/presave") else "/admin"
        return RedirectResponse(target + "?reset=1", status_code=303)

    # Reset the leaderboard: wipe all saved scores.
    @router.post("/scores/reset")
    def scores_reset(request: Request):
        if not is_admin(request):
            return RedirectResponse("/admin/login", status_code=302)
        conn = get_conn(settings.db_path)
        try:
            clear_scores(conn)
        finally:
            conn.close()
        return RedirectResponse("/admin/settings?reset=1", status_code=303)

    @router.get("/settings", response_class=HTMLResponse)
    def settings_form(request: Request, saved: int = 0, reset: int = 0):
        if not is_admin(request):
            return RedirectResponse("/admin/login", status_code=302)
        conn = get_conn(settings.db_path)
        try:
            cfg = get_settings(conn)
        finally:
            conn.close()
        return templates.TemplateResponse(
            request, "admin_settings.html",
            {"cfg": cfg, "saved": bool(saved), "reset": bool(reset), "active": "settings"})

    @router.post("/settings")
    def settings_save(
        request: Request,
        points_per_line: str = Form(default=""),
        speed_mult: str = Form(default=""),
    ):
        if not is_admin(request):
            return RedirectResponse("/admin/login", status_code=302)
        conn = get_conn(settings.db_path)
        try:
            set_settings(conn, {
                "points_per_line": points_per_line,
                "speed_mult": speed_mult,
            })
        finally:
            conn.close()
        return RedirectResponse("/admin/settings?saved=1", status_code=303)

    @router.get("/export.csv")
    def export_csv(request: Request):
        if not is_admin(request):
            return RedirectResponse("/admin/login", status_code=302)
        conn = get_conn(settings.db_path)
        try:
            rows = fetch_all_events(conn)
        finally:
            conn.close()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "ts", "session_id", "variant", "event_type", "meta"])
        for r in rows:
            w.writerow([r["id"], r["ts"], r["session_id"], r["variant"], r["event_type"], r["meta"]])
        buf.seek(0)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=events.csv"})

    return router
