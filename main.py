"""FastAPI entrypoint: assembles routes, static mounts, and the admin dashboard."""
from __future__ import annotations

import pathlib
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from server.ab import resolve, SID_COOKIE, VARIANT_COOKIE, COOKIE_MAX_AGE
from server.config import Settings, load_settings
from server.db import get_conn, init_db

BASE_DIR = pathlib.Path(__file__).resolve().parent


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="delapovazhnee-game")
    app.state.settings = settings

    # Initialize the sqlite schema once at startup (not per request).
    _init_conn = get_conn(settings.db_path)
    try:
        init_db(_init_conn)
    finally:
        _init_conn.close()
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    app.state.templates = templates

    # Landing at the root. Served as a plain file (NOT via Jinja) so the JS
    # template literals in it are untouched. (Assets under static/home/.)
    @app.get("/", response_class=HTMLResponse)
    def home_page():
        return FileResponse(BASE_DIR / "templates" / "home.html")

    # Old landing path → root, so existing /home links keep working.
    @app.get("/home", response_class=HTMLResponse)
    @app.get("/home/", response_class=HTMLResponse)
    def home_redirect():
        return RedirectResponse("/", status_code=301)

    # Game at /game: assign (or reuse) the sticky A/B variant, then render.
    @app.get("/game", response_class=HTMLResponse)
    @app.get("/game/", response_class=HTMLResponse)
    def game_page(request: Request):
        sid, variant, is_new = resolve(request)
        resp = templates.TemplateResponse(
            request, "game.html",
            {"variant": variant, "sid": sid, "build": settings.app_version})
        if is_new:
            resp.set_cookie(SID_COOKIE, sid, max_age=COOKIE_MAX_AGE, samesite="lax")
            resp.set_cookie(VARIANT_COOKIE, variant, max_age=COOKIE_MAX_AGE, samesite="lax")
        return resp

    # Make the browser revalidate the HTML pages and static assets on every load
    # (cheap 304 via ETag/Last-Modified) instead of heuristically caching them —
    # otherwise a landing/game/JS/CSS update isn't picked up without a hard refresh.
    @app.middleware("http")
    async def _no_cache(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/static/") or path in ("/", "/game", "/game/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    # Game assets (also serves the landing's assets under /static/home/).
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    # Routers added in later tasks:
    from server.api import build_api_router
    app.include_router(build_api_router(settings))
    from server.admin import build_admin_router
    app.include_router(build_admin_router(settings, templates))
    return app


app = create_app(load_settings())


if __name__ == "__main__":
    # Loads .env if python-dotenv is present; otherwise rely on the shell env.
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
