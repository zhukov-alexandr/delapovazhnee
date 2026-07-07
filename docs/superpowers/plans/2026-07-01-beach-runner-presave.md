# Beach Runner + Presave A/B — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a beach-sunset pixel runner served at the site root plus a FastAPI backend that collects A/B presave analytics, without touching the existing landing.

**Architecture:** One FastAPI app (`main.py` factory + `server/` package) serves the game page at `/`, mounts the untouched landing at `/home/`, serves game assets at `/static/`, exposes an events API, a logging presave redirect, a server-side QR endpoint, and a cookie-protected admin dashboard. Storage is a single SQLite `events` table queried with SQL aggregations. The game is vanilla canvas-2D JS split into pure logic modules (physics, obstacles, ab) plus a thin renderer/loop/input shell.

**Tech Stack:** Python 3.12 + FastAPI + Uvicorn, stdlib `sqlite3` (no ORM), Jinja2, `qrcode[pil]`, Starlette `SessionMiddleware`; vanilla ES-module JS + canvas 2D; pytest + httpx for backend tests; in-browser self-test harness for game logic (no Node runtime available).

## Global Constraints

- **Python interpreter:** create the venv with `python3.12` (system `python3` is 3.8 and will not work). All `python`/`pytest` commands below assume the activated `.venv`.
- **Node is installed as a local test runner.** Pure game logic is verified headless via `node tests/js/selftest.node.mjs` (RED→GREEN, exits non-zero on failure). The in-page self-test harness (`/?selftest=1`) remains for visual/manual verification. Backend via `pytest`. (`static/js/package.json` sets `{"type":"module"}` so Node imports the ES modules.)
- **Three distinct visual identities** — see `docs/superpowers/specs/2026-07-01-visual-directions.md` (authoritative). Do NOT unify them:
  - **Game** (`/`): summer sunset pixel (PS1/Sega) — the sunset token system.
  - **Landing** (`/home`): "handwritten lyrics on torn paper" — style of the previous single's cover (midnight-blue, torn-paper mountains, handwriting). NOT the sunset style. Redesigned in its own UI task; needs the cover image file in `static/home/`.
  - **Admin** (`/admin`): plain & functional, no frills (system font, light bg, simple tables). This OVERRIDES the brief's "admin in retro aesthetic" — do NOT retro-skin the admin.
- **Landing relocated** (done): old site lives at `templates/home.html` + `static/home/`, served at `/home` and `/home/` via `FileResponse`.
- **All secrets via env / `.env`:** `PRESAVE_URL`, `ADMIN_USER`, `ADMIN_PASS`, `SECRET_KEY`, optional `PUBLIC_BASE_URL`, optional `DB_PATH`. Never hard-code them.
- **Runtime deps only in `requirements.txt`:** `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`, `itsdangerous`, `qrcode[pil]`, `python-dotenv`. Test deps in `requirements-dev.txt`: `pytest`, `httpx`.
- **Event types (exact):** `visit`, `game_start`, `game_over`, `cta_view`, `cta_click`. **Variants (exact):** `A`, `B`. **CTA sources (exact):** `button`, `qr`.
- **UI language is Russian**; the pixel font MUST support Cyrillic (Press Start 2P does not — use e.g. Pixelify Sans).
- **Frequent commits:** one commit per task minimum, at the task's final step.
- **Do not commit** the `db/` sqlite files, `.venv/`, `.env`, or `.DS_Store` (add to `.gitignore`).
- **Schema init once at startup:** the sqlite schema is created a single time in `create_app` (open conn → `init_db` → close). Per-request connection helpers (`_conn()` in `server/api.py`, and the admin routes) MUST just `get_conn(...)` and MUST NOT call `init_db` per request.

---

## File Structure

```
main.py                        # entrypoint: create_app(), __main__ uvicorn runner
server/__init__.py
server/config.py               # Settings dataclass + load_settings() from env
server/ab.py                   # server-side 50/50 variant assignment + sticky cookie resolve
server/db.py                   # get_conn(path), init_db(conn), insert_event(...), query helpers
server/metrics.py              # compute_dashboard(conn), two_proportion_z(...)
server/qr.py                   # build_presave_url(...), make_qr_png(...)
server/api.py                  # APIRouter: POST /api/event, GET /go/presave, GET /qr
server/admin.py                # APIRouter: /admin login/dashboard/export/logout + auth dep
templates/game.html            # game page (canvas + overlays)
templates/admin_login.html
templates/admin.html           # dashboard
static/css/game.css
static/css/admin.css
static/js/config.js            # shared game constants
static/js/physics.js           # pure: runner vertical state (jump/double/gravity)
static/js/obstacles.js         # pure: spawn scheduling, movement, AABB collision, scoring
static/js/ab.js                # pure session/variant resolution + event sender + CTA helpers
static/js/sprites.js           # procedural placeholder art + PNG swap point
static/js/audio.js             # bg music loop + mute + WebAudio SFX
static/js/game.js              # loop + renderer + input + responsive canvas (glue)
static/js/selftest.js          # in-browser assertion harness for pure modules
requirements.txt
requirements-dev.txt
.env.example
.gitignore
README.md
tests/conftest.py
tests/test_routing.py
tests/test_ab_assign.py
tests/test_db.py
tests/test_api_event.py
tests/test_presave_redirect.py
tests/test_qr.py
tests/test_metrics.py
tests/test_admin.py
```

Interface contracts (locked here so tasks can be built out of order):

- `Settings(db_path:str, presave_url:str, admin_user:str, admin_pass:str, secret_key:str, public_base_url:str|None)`
- `get_conn(db_path:str) -> sqlite3.Connection` (row_factory = `sqlite3.Row`, WAL)
- `init_db(conn) -> None`
- `insert_event(conn, session_id:str, variant:str, event_type:str, meta:dict) -> int` (returns row id; timestamps server-side UTC ISO8601)
- `compute_dashboard(conn) -> dict` (shape defined in Task 6)
- `prob_b_beats_a(clicks_a:int, views_a:int, clicks_b:int, views_b:int) -> float` → Bayesian P(CVR_B > CVR_A), 0..1
- `fisher_exact_two_sided(a:int, b:int, c:int, d:int) -> float` → exact two-sided p-value for the 2×2 click/no-click table
- `build_presave_url(base_url:str, variant:str, sid:str, src:str) -> str`
- `make_qr_png(data:str) -> bytes` (PNG)
- `create_app(settings:Settings) -> FastAPI`
- `new_session(rng=random.random, uuidfn=...) -> (sid:str, variant:str)` — 50/50 A/B (server-side)
- `resolve(request) -> (sid:str, variant:str, is_new:bool)` — reads sticky cookies or assigns
- JS `readSession(root) -> {sid, variant}` — reads server-injected `data-variant`/`data-sid`
- JS physics `createRunner(cfg)`, `jump(runner)`, `stepRunner(runner, dt, cfg)`
- JS obstacles `createSpawner(cfg)`, `stepObstacles(state, dt, cfg)`, `collides(runnerBox, obstacleBox)`

---

## Task 1: Project scaffold, config, app factory & routing

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `.env.example`, `.gitignore`
- Create: `main.py`, `server/__init__.py`, `server/config.py`, `server/ab.py`
- Create: `tests/conftest.py`, `tests/test_routing.py`, `tests/test_ab_assign.py`
- Create: `static/.gitkeep`, `templates/game.html` (temporary placeholder body)

**Interfaces:**
- Consumes: nothing.
- Produces: `create_app(settings) -> FastAPI`; `load_settings() -> Settings`; `Settings` dataclass; `server.ab.new_session(...)`, `server.ab.resolve(request)`; routing where `/` assigns a sticky 50/50 A/B variant via cookie and returns the game page, `/home/` serves `html/` landing, `/static/*` serves `static/`.

- [ ] **Step 1: Create dependency and ignore files**

`requirements.txt`:
```
fastapi
uvicorn[standard]
jinja2
python-multipart
itsdangerous
qrcode[pil]
python-dotenv
```
`requirements-dev.txt`:
```
-r requirements.txt
pytest
httpx
```
`.env.example`:
```
PRESAVE_URL=https://example.com/presave
ADMIN_USER=admin
ADMIN_PASS=change-me
SECRET_KEY=please-generate-a-long-random-string
# Optional: absolute base used to build QR target URLs (else derived from request)
PUBLIC_BASE_URL=
# Optional: sqlite path (default db/stats.db)
DB_PATH=
```
`.gitignore` (append; keep existing entries):
```
.venv/
__pycache__/
*.pyc
db/
.env
.DS_Store
.idea/
```

- [ ] **Step 2: Create the environment**

Run:
```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
```
Expected: installs without error; `python -c "import fastapi, qrcode, jinja2; print('ok')"` prints `ok`.

- [ ] **Step 3: Write config module**

`server/config.py`:
```python
"""Application settings loaded from environment variables (.env supported)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    db_path: str
    presave_url: str
    admin_user: str
    admin_pass: str
    secret_key: str
    public_base_url: str | None = None


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
    )
```

- [ ] **Step 4: Write the failing routing test**

`tests/conftest.py`:
```python
import pathlib
import pytest
from fastapi.testclient import TestClient

from server.config import Settings
from main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        db_path=str(tmp_path / "test.db"),
        presave_url="https://presave.example/target",
        admin_user="admin",
        admin_pass="secret",
        secret_key="test-secret-key",
        public_base_url="http://testserver",
    )


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))
```
`tests/test_routing.py`:
```python
def test_root_serves_game_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]

def test_home_serves_landing(client):
    r = client.get("/home/")
    assert r.status_code == 200
    assert "Дела поважнее" in r.text  # landing <title>

def test_static_mounted(client):
    # game.css is created in a later task; here we only assert the mount exists
    r = client.get("/static/does-not-exist.css")
    assert r.status_code == 404  # mount handles it, not a routing 404 page

def test_root_assigns_variant_cookie(client):
    r = client.get("/")
    assert r.cookies.get("dp_variant") in ("A", "B")
    assert r.cookies.get("dp_sid")

def test_variant_is_sticky(client):
    import re
    def variant_of(html):
        m = re.search(r'data-variant="([AB])"', html)
        return m.group(1) if m else None
    v1 = variant_of(client.get("/").text)   # TestClient persists cookies across calls
    v2 = variant_of(client.get("/").text)
    assert v1 in ("A", "B") and v1 == v2     # no reassignment once the cookie is set
```
`tests/test_ab_assign.py`:
```python
import random
from server.ab import new_session

def test_new_session_is_random_5050():
    random.seed(42)
    n = 4000
    a = sum(1 for _ in range(n) if new_session()[1] == "A")
    assert 0.45 < a / n < 0.55            # ~50/50 split
    assert new_session()[1] in ("A", "B")

def test_new_session_uuid_injectable_and_unique():
    assert new_session(uuidfn=lambda: "fixed")[0] == "fixed"
    assert new_session()[0] != new_session()[0]
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `pytest tests/test_routing.py -v`
Expected: FAIL (`cannot import name 'create_app'`).

- [ ] **Step 6: Create the placeholder game template**

The server injects the assigned variant/sid as `data-*` attributes so the frontend can read them (Task 11/14). Placeholder body is replaced in Task 14.

`templates/game.html`:
```html
<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Дела поважнее — игра</title></head>
<body data-variant="{{ variant }}" data-sid="{{ sid }}">
  <canvas id="game"></canvas><!-- replaced in later tasks -->
</body></html>
```

- [ ] **Step 7: Write the A/B assignment module and the app factory & routing**

`server/ab.py`:
```python
"""Server-side A/B assignment: random 50/50 on first visit, sticky via cookie.

The variant cookie is intentionally NOT httponly — the frontend reads it (via the
injected data-* attributes) to place the CTA and build the QR. Source of truth is
the server, so the split is authoritative and cannot be skewed by the client.
"""
from __future__ import annotations

import random
import uuid

SID_COOKIE = "dp_sid"
VARIANT_COOKIE = "dp_variant"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year


def new_session(rng=random.random, uuidfn=lambda: uuid.uuid4().hex):
    """Return (sid, variant) with a fresh id and a fair 50/50 variant."""
    return uuidfn(), ("A" if rng() < 0.5 else "B")


def resolve(request):
    """Return (sid, variant, is_new). Reuses sticky cookies when present and valid."""
    sid = request.cookies.get(SID_COOKIE)
    variant = request.cookies.get(VARIANT_COOKIE)
    if sid and variant in ("A", "B"):
        return sid, variant, False
    sid, variant = new_session()
    return sid, variant, True
```

`main.py`:
```python
"""FastAPI entrypoint: assembles routes, static mounts, and the admin dashboard."""
from __future__ import annotations

import pathlib
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from server.ab import resolve, SID_COOKIE, VARIANT_COOKIE, COOKIE_MAX_AGE
from server.config import Settings, load_settings

BASE_DIR = pathlib.Path(__file__).resolve().parent


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="delapovazhnee-game")
    app.state.settings = settings
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    app.state.templates = templates

    # Game at the root: assign (or reuse) the sticky A/B variant, then render.
    @app.get("/", response_class=HTMLResponse)
    def game_page(request: Request):
        sid, variant, is_new = resolve(request)
        resp = templates.TemplateResponse(
            "game.html", {"request": request, "variant": variant, "sid": sid})
        if is_new:
            resp.set_cookie(SID_COOKIE, sid, max_age=COOKIE_MAX_AGE, samesite="lax")
            resp.set_cookie(VARIANT_COOKIE, variant, max_age=COOKIE_MAX_AGE, samesite="lax")
        return resp

    # Game assets.
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    # Existing landing, served untouched under /home/ (relative asset paths resolve there).
    app.mount("/home", StaticFiles(directory=str(BASE_DIR / "html"), html=True), name="home")

    # Routers added in later tasks:
    #   from server.api import build_api_router
    #   from server.admin import build_admin_router
    #   app.include_router(build_api_router(settings))
    #   app.include_router(build_admin_router(settings))
    return app


app = create_app(load_settings())


if __name__ == "__main__":
    # Loads .env if python-dotenv is present; otherwise rely on the shell env.
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_routing.py -v`
Expected: 3 passed.

- [ ] **Step 9: Commit**

```bash
git add requirements.txt requirements-dev.txt .env.example .gitignore main.py server tests templates static
git commit -m "feat: scaffold FastAPI app, config, server-side A/B assignment, routing"
```

---

## Task 2: SQLite storage module

**Files:**
- Create: `server/db.py`
- Create: `tests/test_db.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `get_conn(db_path)`, `init_db(conn)`, `insert_event(conn, session_id, variant, event_type, meta) -> int`, `fetch_all_events(conn) -> list[sqlite3.Row]`.

- [ ] **Step 1: Write the failing test**

`tests/test_db.py`:
```python
import json
from server.db import get_conn, init_db, insert_event, fetch_all_events


def make_conn():
    conn = get_conn(":memory:")
    init_db(conn)
    return conn

def test_insert_and_fetch_roundtrip():
    conn = make_conn()
    rid = insert_event(conn, "sid-1", "A", "game_over", {"score": 7})
    assert rid == 1
    rows = fetch_all_events(conn)
    assert len(rows) == 1
    row = rows[0]
    assert row["session_id"] == "sid-1"
    assert row["variant"] == "A"
    assert row["event_type"] == "game_over"
    assert json.loads(row["meta"]) == {"score": 7}
    assert row["ts"].endswith("Z") or "T" in row["ts"]  # ISO8601 UTC

def test_meta_defaults_to_empty_object():
    conn = make_conn()
    insert_event(conn, "sid-2", "B", "visit", {})
    row = fetch_all_events(conn)[0]
    assert json.loads(row["meta"]) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL (`No module named 'server.db'`).

- [ ] **Step 3: Implement the DB module**

`server/db.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add server/db.py tests/test_db.py
git commit -m "feat: sqlite events storage (init, insert, fetch)"
```

---

## Task 3: POST /api/event endpoint

**Files:**
- Create: `server/api.py`
- Modify: `main.py` (include the API router)
- Create: `tests/test_api_event.py`

**Interfaces:**
- Consumes: `server.db` helpers, `server.config.Settings`.
- Produces: `build_api_router(settings) -> APIRouter` with `POST /api/event`; a per-request `conn` opened from `settings.db_path`. Body schema `EventIn{session_id, variant, event_type, meta}`.

- [ ] **Step 1: Write the failing test**

`tests/test_api_event.py`:
```python
from server.db import get_conn, fetch_all_events

def test_post_event_persists(client, settings):
    r = client.post("/api/event", json={
        "session_id": "sid-9", "variant": "A",
        "event_type": "game_over", "meta": {"score": 5}})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    conn = get_conn(settings.db_path)
    rows = fetch_all_events(conn)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "game_over"

def test_post_event_rejects_bad_variant(client):
    r = client.post("/api/event", json={
        "session_id": "s", "variant": "Z",
        "event_type": "visit", "meta": {}})
    assert r.status_code == 422

def test_post_event_rejects_unknown_type(client):
    r = client.post("/api/event", json={
        "session_id": "s", "variant": "A",
        "event_type": "hacking", "meta": {}})
    assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_event.py -v`
Expected: FAIL (404 — route not registered).

- [ ] **Step 3: Implement the API router**

`server/api.py`:
```python
"""Public API: event ingestion (presave redirect and QR are added in later tasks)."""
from __future__ import annotations

from typing import Literal
from fastapi import APIRouter
from pydantic import BaseModel, Field

from server.config import Settings
from server.db import get_conn, init_db, insert_event

Variant = Literal["A", "B"]
EventType = Literal["visit", "game_start", "game_over", "cta_view", "cta_click"]


class EventIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    variant: Variant
    event_type: EventType
    meta: dict = {}


def build_api_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    def _conn():
        conn = get_conn(settings.db_path)
        init_db(conn)
        return conn

    @router.post("/api/event")
    def post_event(ev: EventIn):  # sync -> runs in threadpool, safe with sqlite
        conn = _conn()
        try:
            insert_event(conn, ev.session_id, ev.variant, ev.event_type, ev.meta)
        finally:
            conn.close()
        return {"ok": True}

    return router
```

- [ ] **Step 4: Wire the router into the app**

In `main.py`, inside `create_app`, replace the "Routers added in later tasks" comment block with:
```python
    from server.api import build_api_router
    app.include_router(build_api_router(settings))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_api_event.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add server/api.py main.py tests/test_api_event.py
git commit -m "feat: POST /api/event with validated event types and variants"
```

---

## Task 4: /go/presave redirect with click logging

**Files:**
- Modify: `server/api.py` (add route)
- Create: `tests/test_presave_redirect.py`

**Interfaces:**
- Consumes: `settings.presave_url`, `insert_event`.
- Produces: `GET /go/presave?v={A|B}&src={button|qr}&sid=...` → logs `cta_click` (meta `{"src": src}`) then 302 to `settings.presave_url`.

- [ ] **Step 1: Write the failing test**

`tests/test_presave_redirect.py`:
```python
import json
from server.db import get_conn, fetch_all_events

def test_presave_logs_click_and_redirects(client, settings):
    r = client.get("/go/presave", params={"v": "B", "src": "qr", "sid": "sid-7"},
                   follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == settings.presave_url
    rows = fetch_all_events(get_conn(settings.db_path))
    assert len(rows) == 1
    assert rows[0]["event_type"] == "cta_click"
    assert rows[0]["variant"] == "B"
    assert rows[0]["session_id"] == "sid-7"
    assert json.loads(rows[0]["meta"]) == {"src": "qr"}

def test_presave_missing_sid_uses_empty(client, settings):
    r = client.get("/go/presave", params={"v": "A", "src": "button"},
                   follow_redirects=False)
    assert r.status_code == 302
    rows = fetch_all_events(get_conn(settings.db_path))
    assert rows[0]["session_id"] == ""

def test_presave_bad_variant_400(client):
    r = client.get("/go/presave", params={"v": "Q", "src": "button"},
                   follow_redirects=False)
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_presave_redirect.py -v`
Expected: FAIL (404).

- [ ] **Step 3: Implement the redirect route**

Add to `server/api.py` imports:
```python
from fastapi import Query, HTTPException
from fastapi.responses import RedirectResponse
```
Add inside `build_api_router`, before `return router`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_presave_redirect.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add server/api.py tests/test_presave_redirect.py
git commit -m "feat: /go/presave logs cta_click and 302-redirects to PRESAVE_URL"
```

---

## Task 5: Server-side QR endpoint

**Files:**
- Create: `server/qr.py`
- Modify: `server/api.py` (add `/qr` route)
- Create: `tests/test_qr.py`

**Interfaces:**
- Consumes: `settings.public_base_url` (fallback: request base url).
- Produces: `build_presave_url(base_url, variant, sid, src)`, `make_qr_png(data) -> bytes`; `GET /qr?v=&sid=` → `image/png` encoding the `/go/presave?...&src=qr` URL.

- [ ] **Step 1: Write the failing test**

`tests/test_qr.py`:
```python
from server.qr import build_presave_url, make_qr_png

def test_build_presave_url_shape():
    url = build_presave_url("http://testserver", "A", "sid-1", "qr")
    assert url == "http://testserver/go/presave?v=A&src=qr&sid=sid-1"

def test_make_qr_png_returns_png_bytes():
    data = make_qr_png("http://x/y")
    assert data[:8] == b"\x89PNG\r\n\x1a\n"

def test_qr_endpoint_returns_png(client):
    r = client.get("/qr", params={"v": "A", "sid": "sid-1"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

def test_qr_endpoint_bad_variant_400(client):
    r = client.get("/qr", params={"v": "Z", "sid": "s"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_qr.py -v`
Expected: FAIL (`No module named 'server.qr'`).

- [ ] **Step 3: Implement the QR module**

`server/qr.py`:
```python
"""Build the presave target URL and render it as a QR PNG (scannable cross-device)."""
from __future__ import annotations

import io
from urllib.parse import urlencode, quote

import qrcode


def build_presave_url(base_url: str, variant: str, sid: str, src: str = "qr") -> str:
    base = base_url.rstrip("/")
    # Keep parameter order stable for predictable QR contents.
    return f"{base}/go/presave?v={quote(variant)}&src={quote(src)}&sid={quote(sid)}"


def make_qr_png(data: str) -> bytes:
    img = qrcode.make(data)  # returns a PIL image
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
```

- [ ] **Step 4: Add the /qr route**

In `server/api.py`, add import:
```python
from fastapi import Request
from fastapi.responses import Response
from server.qr import build_presave_url, make_qr_png
```
Add inside `build_api_router`, before `return router`:
```python
    @router.get("/qr")
    def qr(request: Request, v: str = Query(...), sid: str = Query("")):
        if v not in ("A", "B"):
            raise HTTPException(status_code=400, detail="bad variant")
        base = settings.public_base_url or str(request.base_url)
        target = build_presave_url(base, v, sid, "qr")
        png = make_qr_png(target)
        return Response(png, media_type="image/png",
                        headers={"Cache-Control": "no-store"})
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_qr.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add server/qr.py server/api.py tests/test_qr.py
git commit -m "feat: server-side QR endpoint encoding the presave redirect URL"
```

---

## Task 6: Metrics aggregation + Bayesian/Fisher comparison

**Files:**
- Create: `server/metrics.py`
- Create: `tests/test_metrics.py`

**Interfaces:**
- Consumes: `server.db` (conn with events).
- Produces: `prob_b_beats_a(clicks_a, views_a, clicks_b, views_b) -> float`, `fisher_exact_two_sided(a, b, c, d) -> float`; `compute_dashboard(conn) -> dict` with this exact shape:
```python
{
  "variants": {
    "A": {"sessions": int, "cta_view_total": int, "cta_view_sessions": int,
          "cta_click_total": int, "cta_click_button": int, "cta_click_qr": int,
          "cta_click_sessions": int, "cvr": float,  # 0..1
          "games_started": int, "games_finished": int, "avg_score": float},
    "B": {...same keys...},
  },
  "daily": [ {"date": "YYYY-MM-DD", "A": int, "B": int} ],  # visits/day per variant
  "leader": "A" | "B" | None,          # by CVR
  "prob_b_beats_a": float | None,      # Bayesian P(CVR_B > CVR_A), 0..1; None until both variants have CTA views
  "fisher_p": float | None,            # exact two-sided p-value; None until both variants have CTA views
  "enough_data": bool,                 # both variants have >=1 cta_view session
}
```
Rationale: on a low-traffic campaign the normal-approximation z-test is unreliable. The Bayesian
`prob_b_beats_a` is exact at any sample size and reads plainly ("B лучше с вероятностью 78%");
Fisher's exact p-value is the rigorous frequentist companion. Both are stdlib-only and deterministic.

- [ ] **Step 1: Write the failing test**

`tests/test_metrics.py`:
```python
from server.db import get_conn, init_db, insert_event
from server.metrics import compute_dashboard, prob_b_beats_a, fisher_exact_two_sided

def seed(conn):
    # Variant A: 2 sessions view CTA, 1 clicks (button)
    insert_event(conn, "a1", "A", "cta_view", {})
    insert_event(conn, "a2", "A", "cta_view", {})
    insert_event(conn, "a1", "A", "cta_click", {"src": "button"})
    insert_event(conn, "a1", "A", "visit", {})
    insert_event(conn, "a2", "A", "visit", {})
    insert_event(conn, "a1", "A", "game_start", {})
    insert_event(conn, "a1", "A", "game_over", {"score": 4})
    # Variant B: 2 sessions view CTA, 2 click (one qr, one button)
    insert_event(conn, "b1", "B", "cta_view", {})
    insert_event(conn, "b2", "B", "cta_view", {})
    insert_event(conn, "b1", "B", "cta_click", {"src": "qr"})
    insert_event(conn, "b2", "B", "cta_click", {"src": "button"})
    insert_event(conn, "b1", "B", "visit", {})
    insert_event(conn, "b2", "B", "visit", {})

def test_dashboard_counts():
    conn = get_conn(":memory:"); init_db(conn); seed(conn)
    d = compute_dashboard(conn)
    a, b = d["variants"]["A"], d["variants"]["B"]
    assert a["cta_view_sessions"] == 2
    assert a["cta_click_sessions"] == 1
    assert a["cta_click_button"] == 1 and a["cta_click_qr"] == 0
    assert abs(a["cvr"] - 0.5) < 1e-9
    assert a["games_finished"] == 1 and abs(a["avg_score"] - 4.0) < 1e-9
    assert b["cta_click_qr"] == 1 and b["cta_click_button"] == 1
    assert abs(b["cvr"] - 1.0) < 1e-9
    assert d["leader"] == "B"
    assert d["enough_data"] is True
    assert d["prob_b_beats_a"] is not None and d["prob_b_beats_a"] > 0.5  # B better
    assert d["fisher_p"] is not None and 0.0 <= d["fisher_p"] <= 1.0

def test_dashboard_none_when_insufficient():
    conn = get_conn(":memory:"); init_db(conn)
    insert_event(conn, "a1", "A", "cta_view", {})  # only A has views
    d = compute_dashboard(conn)
    assert d["enough_data"] is False
    assert d["prob_b_beats_a"] is None and d["fisher_p"] is None

def test_prob_b_beats_a_symmetry_and_extremes():
    assert abs(prob_b_beats_a(1, 2, 1, 2) - 0.5) < 1e-9   # identical rates -> 50%
    assert prob_b_beats_a(0, 10, 10, 10) > 0.99           # B clearly better
    assert prob_b_beats_a(10, 10, 0, 10) < 0.01           # A clearly better

def test_fisher_exact_known_values():
    assert abs(fisher_exact_two_sided(2, 2, 2, 2) - 1.0) < 1e-9  # no difference -> p=1
    assert fisher_exact_two_sided(10, 0, 0, 10) < 0.001          # perfect separation
    assert 0.0 <= fisher_exact_two_sided(1, 1, 2, 0) <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_metrics.py -v`
Expected: FAIL (`No module named 'server.metrics'`).

- [ ] **Step 3: Implement metrics**

`server/metrics.py`:
```python
"""SQL aggregations for the A/B dashboard plus small-sample-safe comparisons.

Instead of a normal-approximation z-test (unreliable on low traffic) we report a
Bayesian probability that B beats A (Beta-Binomial, exact closed form) and an exact
Fisher two-sided p-value. Both are stdlib-only and deterministic.
"""
from __future__ import annotations

from math import comb, lgamma, exp, log


def _log_beta(x: float, y: float) -> float:
    return lgamma(x) + lgamma(y) - lgamma(x + y)


def prob_b_beats_a(clicks_a: int, views_a: int, clicks_b: int, views_b: int) -> float:
    """P(CVR_B > CVR_A) under uniform Beta(1,1) priors (Evan Miller closed form).

    Posteriors: A ~ Beta(1+clicks_a, 1+non_a), B ~ Beta(1+clicks_b, 1+non_b).
    """
    non_a = max(0, views_a - clicks_a)
    non_b = max(0, views_b - clicks_b)
    aA, bA = 1 + clicks_a, 1 + non_a
    aB, bB = 1 + clicks_b, 1 + non_b
    log_norm = _log_beta(aA, bA)
    total = 0.0
    for i in range(aB):  # aB is an integer >= 1
        term = _log_beta(aA + i, bA + bB) - log(bB + i) - _log_beta(1 + i, bB) - log_norm
        total += exp(term)
    return min(1.0, max(0.0, total))


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Exact two-sided p-value for the 2x2 table [[a,b],[c,d]] (clicks/no-clicks by variant).

    Sums hypergeometric probabilities of all fixed-margin tables no more likely than
    the observed one — the same definition R/scipy use.
    """
    r1, r2, c1, n = a + b, c + d, a + c, a + b + c + d
    if r1 == 0 or r2 == 0 or c1 == 0 or (b + d) == 0:
        return 1.0
    denom = comb(n, c1)

    def hyp(x: int) -> float:
        return comb(r1, x) * comb(r2, c1 - x) / denom

    p_obs = hyp(a)
    lo, hi = max(0, c1 - r2), min(r1, c1)
    total = sum(px for x in range(lo, hi + 1)
                if (px := hyp(x)) <= p_obs * (1 + 1e-7))
    return min(1.0, total)


def _variant_stats(conn, v: str) -> dict:
    row = conn.execute(
        """
        SELECT
          COUNT(DISTINCT session_id) AS sessions,
          SUM(event_type='cta_view')                                   AS cta_view_total,
          COUNT(DISTINCT CASE WHEN event_type='cta_view'  THEN session_id END) AS cta_view_sessions,
          SUM(event_type='cta_click')                                  AS cta_click_total,
          SUM(event_type='cta_click' AND json_extract(meta,'$.src')='button') AS cta_click_button,
          SUM(event_type='cta_click' AND json_extract(meta,'$.src')='qr')     AS cta_click_qr,
          COUNT(DISTINCT CASE WHEN event_type='cta_click' THEN session_id END) AS cta_click_sessions,
          SUM(event_type='game_start')                                 AS games_started,
          SUM(event_type='game_over')                                  AS games_finished,
          AVG(CASE WHEN event_type='game_over' THEN json_extract(meta,'$.score') END) AS avg_score
        FROM events WHERE variant=?
        """, (v,)).fetchone()
    d = {k: (row[k] or 0) for k in row.keys()}
    views = d["cta_view_sessions"]
    d["cvr"] = (d["cta_click_sessions"] / views) if views else 0.0
    d["avg_score"] = float(d["avg_score"] or 0.0)
    return d


def _daily(conn) -> list:
    rows = conn.execute(
        """
        SELECT substr(ts,1,10) AS date,
               SUM(variant='A' AND event_type='visit') AS a,
               SUM(variant='B' AND event_type='visit') AS b
        FROM events GROUP BY date ORDER BY date
        """).fetchall()
    return [{"date": r["date"], "A": r["a"] or 0, "B": r["b"] or 0} for r in rows]


def compute_dashboard(conn) -> dict:
    a = _variant_stats(conn, "A")
    b = _variant_stats(conn, "B")
    enough = a["cta_view_sessions"] > 0 and b["cta_view_sessions"] > 0
    prob_b = fisher_p = None
    if enough:
        prob_b = prob_b_beats_a(a["cta_click_sessions"], a["cta_view_sessions"],
                                b["cta_click_sessions"], b["cta_view_sessions"])
        na = max(0, a["cta_view_sessions"] - a["cta_click_sessions"])
        nb = max(0, b["cta_view_sessions"] - b["cta_click_sessions"])
        fisher_p = fisher_exact_two_sided(a["cta_click_sessions"], na,
                                          b["cta_click_sessions"], nb)
    leader = None
    if a["cvr"] != b["cvr"]:
        leader = "A" if a["cvr"] > b["cvr"] else "B"
    return {
        "variants": {"A": a, "B": b},
        "daily": _daily(conn),
        "leader": leader,
        "prob_b_beats_a": prob_b,   # None until both variants have CTA views
        "fisher_p": fisher_p,
        "enough_data": enough,
    }
```
Note: `json_extract` requires SQLite ≥ 3.9 (system is 3.35 — fine).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_metrics.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add server/metrics.py tests/test_metrics.py
git commit -m "feat: A/B dashboard aggregations + two-proportion z-test"
```

---

## Task 7: Admin authentication

**Files:**
- Create: `server/admin.py`
- Create: `templates/admin_login.html`
- Modify: `main.py` (include admin router)
- Create: `tests/test_admin.py`

**Interfaces:**
- Consumes: `settings.admin_user/admin_pass`, session middleware (already added in Task 1).
- Produces: `build_admin_router(settings) -> APIRouter`; `require_admin(request)` dependency that redirects to `/admin/login` when not authed; `GET/POST /admin/login`, `GET /admin/logout`.

- [ ] **Step 1: Write the failing test (auth only)**

`tests/test_admin.py`:
```python
def test_admin_requires_login(client):
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/admin/login" in r.headers["location"]

def test_login_success_grants_access(client):
    r = client.post("/admin/login", data={"username": "admin", "password": "secret"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    r2 = client.get("/admin")
    assert r2.status_code == 200
    assert "Dashboard" in r2.text or "Дашборд" in r2.text

def test_login_failure_rejected(client):
    r = client.post("/admin/login", data={"username": "admin", "password": "wrong"},
                    follow_redirects=False)
    assert r.status_code in (200, 401)
    r2 = client.get("/admin", follow_redirects=False)
    assert r2.status_code in (302, 307)

def test_logout_clears_session(client):
    client.post("/admin/login", data={"username": "admin", "password": "secret"})
    client.get("/admin/logout")
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code in (302, 307)
```
Note: `/admin` (dashboard body) is completed in Task 8; this task only needs it to return 200 when authed. Provide a minimal authed dashboard stub here, replaced in Task 8.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_admin.py -v`
Expected: FAIL (404).

- [ ] **Step 3: Create the login template**

`templates/admin_login.html`:
```html
<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Вход — админка</title>
<link rel="stylesheet" href="/static/css/admin.css"></head>
<body class="login">
  <form method="post" action="/admin/login" class="login-card">
    <h1>Админка</h1>
    {% if error %}<p class="err">Неверный логин или пароль</p>{% endif %}
    <input name="username" placeholder="Логин" autocomplete="username">
    <input name="password" type="password" placeholder="Пароль" autocomplete="current-password">
    <button type="submit">Войти</button>
  </form>
</body></html>
```

- [ ] **Step 4: Implement the admin router (auth + stub dashboard)**

`server/admin.py`:
```python
"""Admin auth and dashboard (dashboard body filled in Task 8)."""
from __future__ import annotations

import secrets
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from server.config import Settings


def build_admin_router(settings: Settings, templates: Jinja2Templates) -> APIRouter:
    router = APIRouter(prefix="/admin")

    def is_admin(request: Request) -> bool:
        return bool(request.session.get("admin"))

    @router.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return templates.TemplateResponse("admin_login.html", {"request": request, "error": False})

    @router.post("/login")
    def login(request: Request, username: str = Form(...), password: str = Form(...)):
        ok = (secrets.compare_digest(username, settings.admin_user)
              and secrets.compare_digest(password, settings.admin_pass))
        if not ok:
            return templates.TemplateResponse(
                "admin_login.html", {"request": request, "error": True}, status_code=200)
        request.session["admin"] = True
        return RedirectResponse("/admin", status_code=303)

    @router.get("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/admin/login", status_code=303)

    @router.get("", response_class=HTMLResponse)
    def dashboard(request: Request):
        if not is_admin(request):
            return RedirectResponse("/admin/login", status_code=302)
        # Stub replaced in Task 8.
        return HTMLResponse("<h1>Dashboard</h1>")

    return router
```

- [ ] **Step 5: Wire the admin router**

In `main.py` `create_app`, after including the API router, add:
```python
    from server.admin import build_admin_router
    app.include_router(build_admin_router(settings, templates))
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_admin.py -v`
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add server/admin.py templates/admin_login.html main.py tests/test_admin.py
git commit -m "feat: admin login/logout with signed-cookie session gate"
```

---

## Task 8: Admin dashboard + CSV export

**Files:**
- Modify: `server/admin.py` (real dashboard + `/admin/export.csv`)
- Create: `templates/admin.html`
- Create: `static/css/admin.css` (minimal; restyled in Task 15)
- Modify: `tests/test_admin.py` (add dashboard + CSV assertions)

**Interfaces:**
- Consumes: `compute_dashboard(conn)`, `fetch_all_events(conn)`, `get_conn`.
- Produces: authed `GET /admin` renders metrics; authed `GET /admin/export.csv` streams events CSV; both redirect to login when unauthed.

- [ ] **Step 1: Add failing tests**

Append to `tests/test_admin.py`:
```python
from server.db import get_conn, init_db, insert_event

def _login(client):
    client.post("/admin/login", data={"username": "admin", "password": "secret"})

def test_dashboard_shows_variant_columns(client, settings):
    conn = get_conn(settings.db_path); init_db(conn)
    insert_event(conn, "a1", "A", "cta_view", {})
    insert_event(conn, "a1", "A", "cta_click", {"src": "button"})
    _login(client)
    r = client.get("/admin")
    assert r.status_code == 200
    assert "Вариант A" in r.text and "Вариант B" in r.text
    assert "CVR" in r.text

def test_export_csv_requires_auth(client):
    r = client.get("/admin/export.csv", follow_redirects=False)
    assert r.status_code in (302, 307)

def test_export_csv_returns_rows(client, settings):
    conn = get_conn(settings.db_path); init_db(conn)
    insert_event(conn, "a1", "A", "visit", {})
    _login(client)
    r = client.get("/admin/export.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert r.text.splitlines()[0] == "id,ts,session_id,variant,event_type,meta"
    assert "a1" in r.text
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_admin.py -v`
Expected: new tests FAIL (stub dashboard, no CSV route).

- [ ] **Step 3: Implement the dashboard template**

`templates/admin.html`:
```html
<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Дашборд — A/B пресейв</title>
<link rel="stylesheet" href="/static/css/admin.css"></head>
<body class="admin">
  <header><h1>Дашборд A/B пресейва</h1>
    <a href="/admin/export.csv" class="btn">Экспорт CSV</a>
    <a href="/admin/logout" class="btn">Выйти</a>
  </header>

  {% set A = d.variants.A %}{% set B = d.variants.B %}
  <table class="metrics">
    <thead><tr><th>Метрика</th><th>Вариант A (старт)</th><th>Вариант B (Game Over)</th></tr></thead>
    <tbody>
      <tr><td>Уникальные сессии</td><td>{{ A.sessions }}</td><td>{{ B.sessions }}</td></tr>
      <tr><td>CTA показы (уник. сессий)</td><td>{{ A.cta_view_sessions }}</td><td>{{ B.cta_view_sessions }}</td></tr>
      <tr><td>CTA клики (уник. сессий)</td><td>{{ A.cta_click_sessions }}</td><td>{{ B.cta_click_sessions }}</td></tr>
      <tr><td>— кнопка / QR</td><td>{{ A.cta_click_button }} / {{ A.cta_click_qr }}</td><td>{{ B.cta_click_button }} / {{ B.cta_click_qr }}</td></tr>
      <tr class="hi"><td>CVR</td><td>{{ '%.1f'|format(A.cvr*100) }}%</td><td>{{ '%.1f'|format(B.cvr*100) }}%</td></tr>
      <tr><td>Игр начато / завершено</td><td>{{ A.games_started }} / {{ A.games_finished }}</td><td>{{ B.games_started }} / {{ B.games_finished }}</td></tr>
      <tr><td>Средний счёт</td><td>{{ '%.1f'|format(A.avg_score) }}</td><td>{{ '%.1f'|format(B.avg_score) }}</td></tr>
    </tbody>
  </table>

  <p class="leader">
    {% if d.leader %}Лидирует <b>Вариант {{ d.leader }}</b>{% else %}Пока паритет{% endif %}
    {% if d.prob_b_beats_a is not none %}
      — вероятность, что B лучше A: <b>{{ '%.0f'|format(d.prob_b_beats_a * 100) }}%</b>;
      точный тест Фишера: p={{ '%.3f'|format(d.fisher_p) }}
      <span class="caveat">(при малом трафике выводы делайте осторожно)</span>
    {% else %}
      — данных пока недостаточно для сравнения
    {% endif %}
  </p>

  <h2>Заходы по дням</h2>
  <div class="bars">
    {% set maxv = (d.daily | map(attribute='A') | list + d.daily | map(attribute='B') | list + [1]) | max %}
    {% for row in d.daily %}
      <div class="day">
        <div class="bar a" style="height: {{ (row.A / maxv * 100)|round }}%" title="A: {{ row.A }}"></div>
        <div class="bar b" style="height: {{ (row.B / maxv * 100)|round }}%" title="B: {{ row.B }}"></div>
        <span class="lbl">{{ row.date[5:] }}</span>
      </div>
    {% endfor %}
  </div>
</body></html>
```

- [ ] **Step 4: Replace dashboard route + add CSV export**

In `server/admin.py`, add imports:
```python
import csv, io
from fastapi.responses import StreamingResponse
from server.db import get_conn, fetch_all_events
from server.metrics import compute_dashboard
```
Note: schema is created once at startup (see Global Constraints), so admin routes just `get_conn(...)` — no per-request `init_db`.
Replace the stub `dashboard` route body with:
```python
    @router.get("", response_class=HTMLResponse)
    def dashboard(request: Request):
        if not is_admin(request):
            return RedirectResponse("/admin/login", status_code=302)
        conn = get_conn(settings.db_path)
        try:
            data = compute_dashboard(conn)
        finally:
            conn.close()
        return templates.TemplateResponse("admin.html", {"request": request, "d": data})

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
```

- [ ] **Step 5: Minimal admin CSS**

`static/css/admin.css` (functional only; visual pass in Task 15):
```css
body.admin { font-family: monospace; margin: 24px; }
table.metrics { border-collapse: collapse; width: 100%; max-width: 720px; }
table.metrics th, table.metrics td { border: 1px solid #999; padding: 6px 10px; text-align: left; }
table.metrics tr.hi { font-weight: bold; }
.bars { display: flex; gap: 8px; align-items: flex-end; height: 160px; }
.bars .day { display: flex; gap: 2px; align-items: flex-end; height: 100%; }
.bars .bar { width: 10px; background: #c60; }
.bars .bar.b { background: #06c; }
.login-card { max-width: 280px; margin: 10vh auto; display: flex; flex-direction: column; gap: 10px; }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_admin.py -v`
Expected: all admin tests pass.

- [ ] **Step 7: Full backend suite green**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add server/admin.py templates/admin.html static/css/admin.css tests/test_admin.py
git commit -m "feat: admin dashboard (A/B metrics, daily bars) + CSV export"
```

---

## Task 9: Game config + physics module (pure) + self-test harness

**Files:**
- Create: `static/js/config.js`
- Create: `static/js/physics.js`
- Create: `static/js/selftest.js`
- Create: `static/js/package.json` (`{"type":"module","private":true}` — lets Node import the ES modules)
- Create: `tests/js/selftest.node.mjs` (headless runner for `run()`)

**Interfaces:**
- Consumes: nothing.
- Produces (ES modules):
  - `config.js` exports `GAME` constants (`WORLD_H`, `GROUND_Y`, `GRAVITY`, `JUMP_V`, `DOUBLE_JUMP_V`, `RUN_SPEED`, `SPEED_RAMP`, `MAX_SPEED`, `RUNNER_W`, `RUNNER_H`, `RUNNER_X`).
  - `physics.js` exports `createRunner()`, `jump(runner)`, `stepRunner(runner, dt)`.
  - `selftest.js` exports `run(assert)` and a browser bootstrap that runs when `location.search` includes `selftest=1`.
- Runner model: `{ y, vy, onGround, jumps }`. `jump` adds first jump from ground (`JUMP_V`) or a second, higher jump in the air (`DOUBLE_JUMP_V`) up to 2 total; `stepRunner` integrates gravity, clamps to ground, resets `jumps` on landing.

- [ ] **Step 1: Write the self-test assertions first**

`static/js/selftest.js`:
```js
// In-browser assertion harness (no Node runtime is available in this project).
// Open the game with ?selftest=1 to run. Results print to console + on-page banner.
import { GAME } from "./config.js";
import { createRunner, jump, stepRunner } from "./physics.js";

export function run(assert) {
  // Single jump leaves the ground.
  const r = createRunner();
  assert(r.onGround === true, "runner starts on ground");
  jump(r);
  stepRunner(r, 1 / 60);
  assert(r.onGround === false, "single jump leaves ground");
  assert(r.jumps === 1, "one jump consumed");

  // Double jump goes higher than single jump apex.
  const single = createRunner(); jump(single);
  let apexSingle = single.y;
  for (let i = 0; i < 200; i++) { stepRunner(single, 1 / 60); apexSingle = Math.min(apexSingle, single.y); }

  const dbl = createRunner(); jump(dbl);
  stepRunner(dbl, 1 / 60);
  jump(dbl); // second jump mid-air
  let apexDbl = dbl.y;
  for (let i = 0; i < 200; i++) { stepRunner(dbl, 1 / 60); apexDbl = Math.min(apexDbl, dbl.y); }
  assert(apexDbl < apexSingle, "double jump reaches higher apex");

  // No triple jump.
  const t = createRunner(); jump(t); jump(t); jump(t);
  assert(t.jumps <= 2, "cannot jump more than twice");

  // Returns to ground eventually.
  const g = createRunner(); jump(g);
  for (let i = 0; i < 600; i++) stepRunner(g, 1 / 60);
  assert(g.onGround === true && Math.abs(g.y - GAME.GROUND_Y) < 0.5, "lands back on ground");
}

// Browser bootstrap.
export function bootstrap() {
  const results = [];
  const assert = (cond, msg) => results.push({ ok: !!cond, msg });
  try { run(assert); } catch (e) { results.push({ ok: false, msg: "threw: " + e.message }); }
  const failed = results.filter((r) => !r.ok);
  results.forEach((r) => console[r.ok ? "log" : "error"]((r.ok ? "PASS " : "FAIL ") + r.msg));
  const banner = document.createElement("div");
  banner.style.cssText =
    "position:fixed;top:0;left:0;right:0;z-index:9999;padding:8px;font:14px monospace;" +
    "color:#fff;background:" + (failed.length ? "#a00" : "#070");
  banner.textContent = failed.length ? `SELFTEST: ${failed.length} FAILED` : "SELFTEST: ALL PASS";
  document.body.appendChild(banner);
}

if (typeof location !== "undefined" && location.search.includes("selftest=1")) {
  window.addEventListener("DOMContentLoaded", bootstrap);
}
```

- [ ] **Step 2: Create config with constants (so imports resolve)**

`static/js/config.js`:
```js
// Shared game constants. Units: logical world pixels; y grows downward.
export const GAME = {
  WORLD_H: 360,          // fixed logical height; width comes from viewport
  GROUND_Y: 300,         // runner baseline (top of feet band)
  GRAVITY: 2600,         // px/s^2
  JUMP_V: -760,          // px/s initial velocity, single jump
  DOUBLE_JUMP_V: -900,   // px/s for the second (air) jump — STRONGER than JUMP_V so the
                         // air jump (which resets vy) reaches a clearly higher apex
  RUN_SPEED: 260,        // starting world scroll speed px/s
  SPEED_RAMP: 3.5,       // px/s added per second survived
  MAX_SPEED: 560,        // speed cap
  RUNNER_W: 34,
  RUNNER_H: 48,
  RUNNER_X: 90,          // fixed horizontal position of the runner
};
```

- [ ] **Step 3: Create the headless node runner + package.json, run it to verify it fails**

`static/js/package.json`:
```json
{ "type": "module", "private": true }
```
`tests/js/selftest.node.mjs`:
```js
// Headless runner: executes the pure self-test assertions under Node (no browser).
import { run } from "../../static/js/selftest.js";

let failed = 0;
run((cond, msg) => {
  if (cond) console.log("PASS " + msg);
  else { failed++; console.error("FAIL " + msg); }
});
if (failed) { console.error(`SELFTEST: ${failed} FAILED`); process.exit(1); }
console.log("SELFTEST: ALL PASS");
```
Run: `node tests/js/selftest.node.mjs`
Expected: FAIL (physics not implemented → module import error / assertions fail, non-zero exit).

- [ ] **Step 4: Implement physics**

`static/js/physics.js`:
```js
// Pure vertical physics for the runner. No DOM, no canvas — unit-testable.
import { GAME } from "./config.js";

export function createRunner() {
  return { y: GAME.GROUND_Y, vy: 0, onGround: true, jumps: 0 };
}

// Trigger a jump: first from ground, second (higher) allowed mid-air, max 2.
export function jump(runner) {
  if (runner.jumps === 0) {
    runner.vy = GAME.JUMP_V;
    runner.onGround = false;
    runner.jumps = 1;
  } else if (runner.jumps === 1) {
    runner.vy = GAME.DOUBLE_JUMP_V;
    runner.jumps = 2;
  }
}

// Integrate one frame of gravity; clamp to ground and reset jump count on landing.
export function stepRunner(runner, dt) {
  runner.vy += GAME.GRAVITY * dt;
  runner.y += runner.vy * dt;
  if (runner.y >= GAME.GROUND_Y) {
    runner.y = GAME.GROUND_Y;
    runner.vy = 0;
    runner.onGround = true;
    runner.jumps = 0;
  }
}
```
Note: the air jump RESETS `vy` to `DOUBLE_JUMP_V`. Because `DOUBLE_JUMP_V` (-900) is a larger magnitude than `JUMP_V` (-760), the second jump reaches a clearly higher apex than a single jump (the self-test asserts this). Do NOT weaken `DOUBLE_JUMP_V` below `JUMP_V` or the assertion fails. Final jump *feel* is tuned later during manual play (Tasks 13/15); this constant only needs to satisfy the invariant here.

- [ ] **Step 5: Re-run the runner to verify it passes**

Run: `node tests/js/selftest.node.mjs`
Expected: `SELFTEST: ALL PASS` (exit 0).

- [ ] **Step 6: Commit**

```bash
git add static/js/config.js static/js/physics.js static/js/selftest.js static/js/package.json tests/js/selftest.node.mjs
git commit -m "feat: game config + pure runner physics (headless node self-test)"
```

---

## Task 10: Obstacles module (spawn, movement, collision, scoring)

**Files:**
- Create: `static/js/obstacles.js`
- Modify: `static/js/selftest.js` (add obstacle assertions)

**Interfaces:**
- Consumes: `config.js`.
- Produces: `createGameState()`, `stepObstacles(state, dt)`, `collides(a, b)`, `runnerBox(runner)`.
  - Obstacle: `{ x, w, h, type: 'single'|'umbrella', passed: bool }`. `umbrella` is taller (needs double jump).
  - `state`: `{ obstacles:[], speed, timeToNext, elapsed, score }`.
  - `stepObstacles` moves obstacles left by `speed*dt`, spawns on `timeToNext<=0` with a balanced randomized gap, ramps `speed` toward `MAX_SPEED`, increments `score` when an obstacle passes `RUNNER_X`, and drops off-screen obstacles.
  - `collides(a,b)` is AABB overlap; `runnerBox(runner)` returns the runner's world AABB.

- [ ] **Step 1: Add failing self-test assertions**

Add to `static/js/selftest.js` — extend imports and the `run` body:
```js
import { createGameState, stepObstacles, collides, runnerBox } from "./obstacles.js";
```
Append inside `run(assert)`:
```js
  // AABB overlap detection.
  assert(collides({x:0,y:0,w:10,h:10}, {x:5,y:5,w:10,h:10}) === true, "AABB overlap true");
  assert(collides({x:0,y:0,w:10,h:10}, {x:20,y:0,w:10,h:10}) === false, "AABB apart false");

  // Obstacles spawn over time and scroll left.
  const gs = createGameState();
  for (let i = 0; i < 300; i++) stepObstacles(gs, 1 / 60);
  assert(gs.obstacles.length > 0, "obstacles spawn over time");
  assert(gs.speed >= GAME.RUN_SPEED, "speed does not drop below start");
  assert(gs.speed <= GAME.MAX_SPEED, "speed capped");

  // Score increments as obstacles pass the runner.
  const gs2 = createGameState();
  let ticks = 0;
  while (gs2.score === 0 && ticks < 3000) { stepObstacles(gs2, 1 / 60); ticks++; }
  assert(gs2.score >= 1, "score increments when an obstacle passes");
```

- [ ] **Step 2: Run the runner to verify it fails**

Run: `node tests/js/selftest.node.mjs`
Expected: FAIL (obstacles module missing → import error / assertions fail, non-zero exit).

- [ ] **Step 3: Implement obstacles**

`static/js/obstacles.js`:
```js
// Pure obstacle system: spawning, scrolling, collision, scoring. No rendering.
import { GAME } from "./config.js";

const SINGLE = { w: 44, h: 26 };   // sunbather on a mat — clear with single jump
const UMBRELLA = { w: 52, h: 78 };  // sunbather with umbrella — needs double jump

export function createGameState() {
  return { obstacles: [], speed: GAME.RUN_SPEED, timeToNext: 1.2, elapsed: 0, score: 0 };
}

// Balanced randomized gap (seconds) that tightens slightly as speed grows.
function nextGap(speed) {
  const base = Math.max(0.9, 1.8 - (speed - GAME.RUN_SPEED) / 500);
  return base + Math.random() * 0.9;
}

function spawn(state, worldW) {
  const umbrella = Math.random() < 0.35;
  const dim = umbrella ? UMBRELLA : SINGLE;
  state.obstacles.push({
    x: worldW + 20, w: dim.w, h: dim.h,
    type: umbrella ? "umbrella" : "single", passed: false,
  });
}

// worldW defaults large so the pure self-test (no canvas) still spawns/moves sanely.
export function stepObstacles(state, dt, worldW = 640) {
  state.elapsed += dt;
  state.speed = Math.min(GAME.MAX_SPEED, state.speed + GAME.SPEED_RAMP * dt);

  state.timeToNext -= dt;
  if (state.timeToNext <= 0) {
    spawn(state, worldW);
    state.timeToNext = nextGap(state.speed);
  }

  for (const o of state.obstacles) {
    o.x -= state.speed * dt;
    if (!o.passed && o.x + o.w < GAME.RUNNER_X) {
      o.passed = true;
      state.score += 1;
    }
  }
  state.obstacles = state.obstacles.filter((o) => o.x + o.w > -40);
}

export function runnerBox(runner) {
  return { x: GAME.RUNNER_X, y: runner.y - GAME.RUNNER_H, w: GAME.RUNNER_W, h: GAME.RUNNER_H };
}

export function collides(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}
```

- [ ] **Step 4: Re-run the runner to verify it passes**

Run: `node tests/js/selftest.node.mjs`
Expected: `SELFTEST: ALL PASS` (exit 0).

- [ ] **Step 5: Commit**

```bash
git add static/js/obstacles.js static/js/selftest.js
git commit -m "feat: pure obstacle system (spawn, scroll, collision, scoring)"
```

---

## Task 11: A/B session module (pure) + event sender

**Files:**
- Create: `static/js/ab.js`
- Modify: `static/js/selftest.js` (add ab assertions)

**Interfaces:**
- Consumes: nothing (DOM/`fetch` injected).
- Produces:
  - `readSession(root) -> {sid, variant}` — reads the server-assigned `data-variant`/`data-sid` from a root element (`document.documentElement`). The server owns the 50/50 split (Task 1); the frontend never randomizes. Falls back to variant `"A"` and a generated sid only if the attributes are missing/invalid (defensive).
  - `markVisited(store) -> bool` — returns `true` only the first time (guards one `visit` per session); `store` is `localStorage`-shaped.
  - `createEmitter(session, post = fetch) -> emit(type, meta)` — POSTs `{session_id, variant, event_type, meta}` to `/api/event`.
  - `goPresaveUrl(variant, sid, src) -> "/go/presave?..."`.

- [ ] **Step 1: Add failing ab assertions**

Add import in `static/js/selftest.js`:
```js
import { readSession, markVisited, goPresaveUrl } from "./ab.js";
```
Append inside `run(assert)`:
```js
  // readSession reads the server-injected data-* attributes.
  const rootB = { dataset: { variant: "B", sid: "sid-xyz" } };
  const rs = readSession(rootB);
  assert(rs.variant === "B" && rs.sid === "sid-xyz", "readSession reads server variant/sid");

  // Defensive fallback when attributes are missing/invalid.
  const rootBad = { dataset: {} };
  const fb = readSession(rootBad);
  assert(fb.variant === "A" && typeof fb.sid === "string" && fb.sid.length > 0,
         "readSession falls back to A + generated sid");

  // Fake localStorage for the visit guard.
  const mkStore = () => { const m = {}; return {
    getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); } }; };
  const sv = mkStore();
  assert(markVisited(sv) === true, "first visit true");
  assert(markVisited(sv) === false, "second visit false");

  // presave URL shape.
  assert(goPresaveUrl("A", "sid-1", "button") === "/go/presave?v=A&src=button&sid=sid-1",
         "presave url shape");
```

- [ ] **Step 2: Run to verify failure**

Run: `node tests/js/selftest.node.mjs` → FAIL (ab.js missing, non-zero exit).

- [ ] **Step 3: Implement ab.js**

`static/js/ab.js`:
```js
// A/B analytics on the frontend. The server assigns the variant (Task 1) and injects
// it as data-* attributes; here we only read it. Pure functions take root/store/fetch
// by injection so they can be exercised by the self-test harness.

const KEY_VISITED = "dp_visited";

// Read the server-assigned variant/sid from data-* attributes on the root element.
// Falls back to "A" + a generated sid only if the server did not inject them.
export function readSession(root) {
  const ds = (root && root.dataset) || {};
  const variant = ds.variant === "A" || ds.variant === "B" ? ds.variant : "A";
  const sid = ds.sid && ds.sid.length ? ds.sid : defaultUuid();
  return { sid, variant };
}

// True exactly once per session (guards a single `visit` event).
export function markVisited(store) {
  if (store.getItem(KEY_VISITED)) return false;
  store.setItem(KEY_VISITED, "1");
  return true;
}

export function goPresaveUrl(variant, sid, src) {
  return `/go/presave?v=${encodeURIComponent(variant)}&src=${encodeURIComponent(src)}&sid=${encodeURIComponent(sid)}`;
}

// Returns emit(type, meta) that POSTs an event; failures are swallowed (analytics best-effort).
export function createEmitter(session, post = fetch) {
  return function emit(type, meta = {}) {
    try {
      post("/api/event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: session.sid, variant: session.variant,
          event_type: type, meta,
        }),
        keepalive: true,
      });
    } catch (_) { /* ignore */ }
  };
}

function defaultUuid() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}
```

- [ ] **Step 4: Re-run to verify pass**

Run: `node tests/js/selftest.node.mjs` → `SELFTEST: ALL PASS` (exit 0).

- [ ] **Step 5: Commit**

```bash
git add static/js/ab.js static/js/selftest.js
git commit -m "feat: A/B frontend reads server-assigned variant + event emitter (self-tested)"
```

---

## Task 12: Sprites module + parallax renderer (procedural placeholder art)

**Files:**
- Create: `static/js/sprites.js`
- Create: `tests/js/sprites.smoke.mjs` (headless smoke test with a mock 2D context)

**Interfaces:**
- Consumes: `config.js`.
- Produces:
  - `drawBackground(ctx, cam, worldW)` — sunset sky gradient (orange→pink→purple), large sun fixed above the sea line, parallax sea band and sand (parallax factor from `cam.x`).
  - `drawRunner(ctx, runner, t)` — procedural pixel runner with a slight run bob driven by `t`.
  - `drawObstacle(ctx, o)` — `single` (sunbather on mat) vs `umbrella` (taller with parasol).
  - `PALETTE` — named colors reused across the game and admin for one visual identity.
  - **Swap point:** each `draw*` first checks `sprites.images[name]`; if a loaded `HTMLImageElement` exists it blits that instead of drawing primitives. `loadSprites(manifest)` populates `sprites.images`. This is where real PNGs replace placeholder art with zero logic changes.

This task is verified two ways: a **headless Node smoke test** (mock canvas context — no crash + the PNG swap-point logic) here, and a **true visual check by the controller after Task 14** (when the full game renders). Subagents cannot see a browser, so do NOT rely on a manual browser check in this task.

- [ ] **Step 1: Implement sprites.js with the swap point**

Create `static/js/sprites.js` exporting `PALETTE`, `images = {}`, `loadSprites(manifest)`, and the `draw*` functions. Each `draw*` begins with:
```js
if (images[name]) { ctx.drawImage(images[name], dx, dy, dw, dh); return; }
```
then falls back to `fillRect`-based pixel art using `PALETTE`. Use integer coordinates and disable smoothing (`ctx.imageSmoothingEnabled = false`) for crisp pixels. Background draws in layer order: sky gradient → sun → sea band → sand.

- [ ] **Step 2: Headless smoke test with a mock 2D context**

`tests/js/sprites.smoke.mjs` builds a mock context recording method calls and asserts the draw functions run without throwing and actually paint:
```js
import { PALETTE, images, drawBackground, drawRunner, drawObstacle } from "../../static/js/sprites.js";
import { createRunner } from "../../static/js/physics.js";

function mockCtx() {
  const calls = [];
  const rec = (n) => (...a) => calls.push([n, ...a]);
  return { calls,
    fillRect: rec("fillRect"), drawImage: rec("drawImage"),
    fillStyle: "", strokeStyle: "", lineWidth: 1, imageSmoothingEnabled: true,
    beginPath: rec("beginPath"), moveTo: rec("moveTo"), lineTo: rec("lineTo"),
    stroke: rec("stroke"), fill: rec("fill"), save: rec("save"), restore: rec("restore"),
    arc: rec("arc"), rect: rec("rect"), translate: rec("translate"),
    createLinearGradient: () => ({ addColorStop() {} }) };
}
let failed = 0;
const ok = (c, m) => { if (c) console.log("PASS " + m); else { failed++; console.error("FAIL " + m); } };

const cam = { x: 0 };
let ctx = mockCtx();
drawBackground(ctx, cam, 640); ok(ctx.calls.length > 0, "background paints");
ctx = mockCtx(); drawRunner(ctx, createRunner(), 0); ok(ctx.calls.length > 0, "runner paints");
ctx = mockCtx(); drawObstacle(ctx, { x: 200, y: 274, w: 44, h: 26, type: "single", passed: false });
ok(ctx.calls.some(c => c[0] === "fillRect"), "single obstacle uses primitives");
ctx = mockCtx(); drawObstacle(ctx, { x: 200, y: 222, w: 52, h: 78, type: "umbrella", passed: false });
ok(ctx.calls.length > 0, "umbrella obstacle paints");

// PNG swap point: when a loaded image exists for a sprite, drawImage is used.
images.runner = { __img: true };
ctx = mockCtx(); drawRunner(ctx, createRunner(), 0);
ok(ctx.calls.some(c => c[0] === "drawImage"), "swap point blits loaded PNG instead of primitives");
delete images.runner;

ok(typeof PALETTE === "object" && Object.keys(PALETTE).length > 0, "PALETTE exported");
if (failed) { console.error(`SPRITES SMOKE: ${failed} FAILED`); process.exit(1); }
console.log("SPRITES SMOKE: ALL PASS");
```
Run: `node tests/js/sprites.smoke.mjs` → `SPRITES SMOKE: ALL PASS` (exit 0). (`drawRunner`/`drawObstacle` must accept a `name` for their sprite and check `images[name]` first — pick stable names like `runner`, `single`, `umbrella`.)

- [ ] **Step 3: Commit**

```bash
git add static/js/sprites.js tests/js/sprites.smoke.mjs
git commit -m "feat: procedural sunset parallax + runner/obstacle art with PNG swap point"
```

---

## Task 13: Game loop, input, responsive canvas (glue)

**Files:**
- Create: `static/js/gamestate.js` (PURE game progression — node-testable)
- Create: `tests/js/gamestate.smoke.mjs` (node test for progression)
- Create: `static/js/game.js` (DOM glue: canvas, loop, input, resize)

**Interfaces:**
- Consumes: `config.js`, `physics.js`, `obstacles.js`, `sprites.js`.
- Produces (pure, `gamestate.js`):
  - `createGame() -> { runner, obs, state:'menu'|'running'|'over', score:0 }` (runner from `createRunner()`, obs from `createGameState()`).
  - `startGame(g)` sets `state='running'` and resets runner/obs/score. `stepGame(g, dt, worldW) -> { over:boolean, scoreDelta:number }` — no-op unless `state==='running'`; advances `stepRunner`/`stepObstacles`, mirrors `g.score = g.obs.score` (returns the delta), and on any `collides(runnerBox(g.runner), o)` sets `state='over'` and returns `over:true`. NO DOM.
- Produces (glue, `game.js`): `Game` controller with `start()`, `reset()`, states `menu|running|over`; hooks `onStart`, `onGameOver(score)`, `onScore(score)` for the shell (Task 14). DOM/RAF happen only INSIDE methods (nothing at module top level) so the file imports without side effects.
- Responsive canvas: fixed logical height `WORLD_H`; CSS size fills viewport; backing store scaled by `devicePixelRatio`; recompute on `resize`/`orientationchange`. Input: `Space`/click/`touchstart` → `jump`; `touchstart` calls `preventDefault`; canvas uses `touch-action: manipulation`. Loop uses `requestAnimationFrame` with clamped delta-time.

Progression (`stepGame`) is node-tested here; the DOM glue (loop/canvas/input/resize) is verified visually by the controller after Task 14.

- [ ] **Step 1: Pure `gamestate.js` + node smoke test**

`static/js/gamestate.js` (no DOM):
```js
import { createRunner, stepRunner } from "./physics.js";
import { createGameState, stepObstacles, collides, runnerBox } from "./obstacles.js";

export function createGame() {
  return { runner: createRunner(), obs: createGameState(), state: "menu", score: 0 };
}
export function startGame(g) {
  g.runner = createRunner(); g.obs = createGameState(); g.score = 0; g.state = "running";
}
// Advance one frame. Returns {over, scoreDelta}. No-op unless running.
export function stepGame(g, dt, worldW) {
  if (g.state !== "running") return { over: false, scoreDelta: 0 };
  stepRunner(g.runner, dt);
  const before = g.obs.score;
  stepObstacles(g.obs, dt, worldW);
  const scoreDelta = g.obs.score - before;
  g.score = g.obs.score;
  const box = runnerBox(g.runner);
  for (const o of g.obs.obstacles) {
    if (collides(box, o)) { g.state = "over"; return { over: true, scoreDelta }; }
  }
  return { over: false, scoreDelta };
}
```
`tests/js/gamestate.smoke.mjs`:
```js
import { GAME } from "../../static/js/config.js";
import { createGame, startGame, stepGame } from "../../static/js/gamestate.js";

let failed = 0;
const ok = (c, m) => { if (c) console.log("PASS " + m); else { failed++; console.error("FAIL " + m); } };

// Not running -> no-op.
const g0 = createGame();
const r0 = stepGame(g0, 1 / 60, 640);
ok(r0.over === false && g0.state === "menu", "stepGame is a no-op before start");

// Collision -> over.
const g1 = createGame(); startGame(g1);
g1.obs.obstacles.push({ x: GAME.RUNNER_X, y: GAME.GROUND_Y - 26, w: 44, h: 26, type: "single", passed: false });
const r1 = stepGame(g1, 1 / 60, 640);
ok(r1.over === true && g1.state === "over", "collision ends the run");

// Score increments when an obstacle passes the runner. Place it LEFT of the runner's
// x-lane (right edge < RUNNER_X) so it scores this tick WITHOUT colliding — a standing
// runner's box overlaps any obstacle in its own lane, so we must avoid the lane here.
const g2 = createGame(); startGame(g2);
g2.obs.obstacles.push({ x: 40, y: GAME.GROUND_Y - 26, w: 44, h: 26, type: "single", passed: false });
const r2 = stepGame(g2, 1 / 60, 640);
ok(r2.scoreDelta >= 1 && g2.score >= 1 && r2.over === false, "score increments when an obstacle passes");

if (failed) { console.error(`GAMESTATE SMOKE: ${failed} FAILED`); process.exit(1); }
console.log("GAMESTATE SMOKE: ALL PASS");
```
Run: `node tests/js/gamestate.smoke.mjs` → make it pass (`GAMESTATE SMOKE: ALL PASS`, exit 0).

- [ ] **Step 1b: Implement the `game.js` loop (glue) around `stepGame`**

`game.js` builds the `Game` controller. The RAF loop (inside `start()`, not top level):
```js
let last = performance.now();
const frame = (now) => {
  let dt = Math.min((now - last) / 1000, 1 / 30); // clamp to avoid tunneling on tab-switch
  last = now;
  const { over, scoreDelta } = stepGame(game, dt, worldW);
  if (scoreDelta) onScore(game.score);
  if (over) onGameOver(game.score);
  render();
  raf = requestAnimationFrame(frame);
};
```
`render()` clears and calls `sprites.drawBackground(ctx, cam, worldW)`, `drawRunner`, `drawObstacle` for each `game.obs.obstacles`.

- [ ] **Step 2: Implement responsive sizing**

```js
function resize() {
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  const cssH = canvas.clientHeight, cssW = canvas.clientWidth;
  const scale = cssH / GAME.WORLD_H;            // logical->css
  worldW = cssW / scale;                          // visible world width
  canvas.width = Math.round(cssW * dpr);
  canvas.height = Math.round(cssH * dpr);
  ctx.setTransform(dpr * scale, 0, 0, dpr * scale, 0, 0);
  ctx.imageSmoothingEnabled = false;
}
window.addEventListener("resize", resize);
window.addEventListener("orientationchange", resize);
```

- [ ] **Step 3: Implement input**

Bind `keydown` (`Space`/`ArrowUp` → `handleJump`, prevent page scroll), `mousedown`, and `touchstart` (with `e.preventDefault()`); `handleJump` calls `jump(runner)` only while `state==="running"`, and is also used by the shell to start/restart.

- [ ] **Step 4: Manual play check + balance tuning**

Start server, open `/`. Expected: runner runs, single tap jumps, double tap jumps higher, umbrella obstacles require a double jump, collision ends the run, score rises per cleared obstacle. Confirm on a narrow (mobile-emulated) viewport too.

Collision uses `collides(runnerBox(runner), o)` — obstacles already carry a ground-anchored `y` (from Task 10 fix), so this works directly. **Balance tuning:** the umbrella must be tall enough that a SINGLE jump cannot clear it but a DOUBLE jump can — that distinction is the whole point. Single-jump apex puts the runner's feet at ~`GROUND_Y - 111`; double-jump apex at ~`GROUND_Y - 160`. So set the umbrella height so its top sits between those (roughly `h` in ~120–150 px, top between single and double apex). Tune `single`/`umbrella` heights + spawn gaps here until it feels right; keep the node self-test green after any obstacle-shape change.

- [ ] **Step 5: Commit**

```bash
git add static/js/gamestate.js tests/js/gamestate.smoke.mjs static/js/game.js
git commit -m "feat: pure game progression (node-tested) + loop, DPR/responsive canvas, input"
```

---

## Task 14: Game HTML shell — overlays, A/B CTA, audio wiring

**Files:**
- Rewrite: `templates/game.html`
- Create: `static/css/game.css`
- Create: `static/js/audio.js`

**Interfaces:**
- Consumes: `game.js` hooks, `ab.js` (`resolveSession`, `markVisited`, `createEmitter`, `goPresaveUrl`), `audio.js`.
- Produces the full page: `<canvas>` + overlays (start / HUD / game-over) + CTA block (QR `<img src="/qr?v=&sid=">` + «Пресейв» button) + mute button; and the boot script that resolves the session, emits events, and places the CTA by variant.

- [ ] **Step 1: Implement audio.js**

`static/js/audio.js` exports `createAudio()` → `{ startMusic(), toggleMute()->bool, sfxJump(), sfxGameOver() }`. Music is an `Audio("/static/assets/music.mp3")` with `loop=true`, `volume=0.5`, started on first user gesture (autoplay policy). SFX use a `WebAudio` `OscillatorNode` (short square-wave blips) — no audio files. Guard missing music file (catch play rejection).

- [ ] **Step 2: Write game.html shell**

Rewrite `templates/game.html`:
```html
<!doctype html>
<html lang="ru" data-variant="{{ variant }}" data-sid="{{ sid }}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
  <title>Дела поважнее — беги по пляжу</title>
  <link rel="stylesheet" href="/static/css/game.css">
</head>
<body>
  <div id="stage">
    <canvas id="game"></canvas>

    <div id="hud" class="hud hidden"><span id="score">0</span></div>
    <button id="mute" class="mute" aria-label="Звук">🔊</button>
    <a id="home" class="home" href="/home/">На главную</a>

    <!-- CTA block (moved into #start for variant A, into #over for variant B by boot.js) -->
    <template id="cta-tpl">
      <div class="cta">
        <img class="qr" alt="QR пресейв" />
        <a class="presave btn" target="_blank" rel="noopener">Сделать пресейв</a>
      </div>
    </template>

    <div id="start" class="overlay">
      <h1>ДЕЛА ПОВАЖНЕЕ</h1>
      <p>Прыгай через отдыхающих. Пробел или тап.</p>
      <button id="play" class="btn big">Играть</button>
      <div id="start-cta"></div>
    </div>

    <div id="over" class="overlay hidden">
      <h1>Игра окончена</h1>
      <p>Счёт: <span id="final-score">0</span></p>
      <button id="retry" class="btn big">Ещё раз</button>
      <div id="over-cta"></div>
    </div>
  </div>

  <script type="module" src="/static/js/selftest.js"></script>
  <script type="module" src="/static/js/boot.js"></script>
</body>
</html>
```

- [ ] **Step 3: Create boot.js (wires session, events, CTA, audio, overlays)**

Create `static/js/boot.js` that:
1. `session = readSession(document.documentElement)` (variant/sid assigned by the server); `emit = createEmitter(session)`.
2. If `markVisited(localStorage)` → `emit("visit", {})`.
3. Builds the CTA from `#cta-tpl`: `img.src = "/qr?v="+variant+"&sid="+sid`; `a.href = goPresaveUrl(variant, sid, "button")`; and mounts it into `#start-cta` when `variant==="A"` else into `#over-cta`.
4. Fires `emit("cta_view", {})` when that CTA becomes visible (variant A: on load; variant B: when the game-over overlay is shown).
5. Wires `Game` hooks: `onStart` → `emit("game_start")` + start music; `onScore(s)` → update `#score`; `onGameOver(s)` → `emit("game_over", {score:s})` + show `#over` (+ CTA for B).
6. `#play`/`#retry` start/restart the game and hide/show overlays; `#mute` toggles audio and swaps the icon.
Note: the CTA link intentionally points at `/go/presave` (server logs the click), NOT directly at the presave URL.

- [ ] **Step 4: Write game.css (functional layout; restyled in Task 15)**

Cover: `#stage` full-viewport with `env(safe-area-inset-*)` padding; `#game` fills stage, `image-rendering: pixelated`, `touch-action: manipulation`; overlays centered with `.hidden{display:none}`; `.btn` min 44px touch targets; `.cta .qr` sized ~140px; responsive via `clamp()`.

- [ ] **Step 5: Manual end-to-end check for BOTH variants**

Force variant A: in devtools console `localStorage.clear()` then reload until `localStorage.dp_variant==='A'` (or temporarily hard-set it). Confirm CTA shows on the start screen, QR renders, clicking «Пресейв» hits `/go/presave` and redirects. Repeat forcing variant B and confirm CTA shows on Game Over. After clicks, open `/admin` and confirm `cta_view`/`cta_click` counts moved.

- [ ] **Step 6: Commit**

```bash
git add templates/game.html static/css/game.css static/js/audio.js static/js/boot.js
git commit -m "feat: game shell — overlays, A/B CTA placement, QR, music+mute wiring"
```

---

## Task 15: Visual design pass — GAME ONLY (sunset pixel) + adaptivity polish

Design system is already fixed in `docs/superpowers/specs/2026-07-01-visual-directions.md` (§1).
This task applies the **sunset pixel** system to the **game only**. Do NOT touch the admin
(it stays plain — Task 8 css is final) and do NOT touch the landing (separate task, different identity).

**Files:**
- Modify: `static/css/game.css`, `templates/game.html`, `static/js/sprites.js` (palette/art tuning)

**Interfaces:** no API changes — visual only.

- [ ] **Step 1: Load the fonts + tokens (from the visual-directions doc §1)**

Add Google Fonts `<link>` for the Cyrillic pixel trio — `Handjet` (display), `Pixelify Sans` (body/UI), `VT323` (data/HUD) — in `templates/game.html`. Define the palette CSS variables in `static/css/game.css`:
`--night #241539, --grape #6D2E8B, --flare #FF5D73, --sun #FFD35C, --sand #F2C078, --foam #FFF4E2, --arcade #2FE6D6, --ink #2A1533`.

- [ ] **Step 2: Apply the sunset system across the GAME screens**

Style start / HUD / Game Over per §1: dithered-sun signature, translucent dusk scrims, `--arcade` cyan for CTA/buttons/focus, VT323 score on a mini sun-disc. Update `sprites.js` `PALETTE` to the same hexes so canvas art and DOM UI share one palette. Keep pixel crispness (`image-rendering: pixelated`, integer scaling). Admin and landing are OUT OF SCOPE here.

- [ ] **Step 3: Adaptivity polish (game)**

Verify and fix on the game screens: portrait + landscape on a phone viewport; `resize`/`orientationchange` reflow; touch targets ≥ 44px; QR + «Пресейв» legible on small screens; safe-area insets respected on notched devices. (Admin responsiveness is Task 8's plain-CSS concern, not this retro pass.)

- [ ] **Step 4: Manual check on desktop + mobile viewport**

Confirm one coherent **sunset** look across the game screens (start / HUD / Game Over) and correct behavior in both orientations. Confirm `pytest -v` still green (visual changes must not touch backend behavior).

- [ ] **Step 5: Commit**

```bash
git add static/css templates static/js/sprites.js
git commit -m "style: unified sunset pixel identity across game + admin; adaptivity polish"
```

---

## Task 15B: Landing redesign — "torn-paper lyrics" (previous single's cover)

Redesign the landing (`templates/home.html` + `static/home/`) in the style of the previous
single's cover — see `docs/superpowers/specs/2026-07-01-visual-directions.md` §2. This is a
SEPARATE identity from the game (midnight-blue, torn-paper mountains, handwriting — NOT sunset).
Keep all existing content (release/streaming links, tour, socials) and integrations (Yandex.Metrika,
UTM script, all outbound links) intact — only reskin.

**Prerequisite:** the cover image file must be in `static/home/` (ask the user to add it, e.g.
`static/home/cover.jpg`). Do not start the visual build until it is present.

**Files:**
- Modify: `templates/home.html`, `static/home/styles.css`

**Interfaces:** no API changes — visual only; served at `/home` via the existing `FileResponse` route.

- [ ] **Step 1: Confirm the cover image is present** in `static/home/` (else stop and ask).
- [ ] **Step 2: Apply the palette + type** from §2: midnight-blue field (`--ld-sky-top #0B1524`,
  `--ld-sky #16273F`, `--ld-sky-glow #24405F`), paper (`--ld-paper #EDE7DA`, `--ld-paper-sh #B9C2CC`),
  ink (`--ld-ink #1B2430`); a restrained Cyrillic handwritten face (e.g. `Caveat`) for accents + a
  quiet Cyrillic sans for body.
- [ ] **Step 3: Torn-paper motif** — use the cover image as hero/background/texture; render section
  cards (Релиз / Тур / Соцсети) as paper layers on the dark-blue field; torn edges via the image or
  SVG/`clip-path`.
- [ ] **Step 4: Manual check** desktop + mobile; confirm all outbound links, tour tickets, streaming
  links, and the Yandex.Metrika/UTM scripts still work; `/home` and `/home/` both serve it.
- [ ] **Step 5: Commit**

```bash
git add templates/home.html static/home
git commit -m "style: redesign landing in previous single's cover aesthetic (torn-paper lyrics)"
```

---

## Task 16: README, run script, final verification

**Files:**
- Create: `README.md`
- Create: `run.sh` (optional convenience)

- [ ] **Step 1: Write README**

Document: create venv with `python3.12`, `pip install -r requirements-dev.txt`, copy `.env.example`→`.env` and fill secrets, generate `SECRET_KEY`, run `uvicorn main:app --host 0.0.0.0 --port 8000`, where the game (`/`), landing (`/home/`), and admin (`/admin`) live, how the A/B variants and metrics work, and how to drop real sprites/PNGs into `static/sprites/` + `static/assets/music.mp3`. State the JS self-test URL (`/?selftest=1`) and `pytest` for backend.

- [ ] **Step 2: Full verification pass**

Run:
```bash
. .venv/bin/activate
pytest -v
```
Expected: all backend tests pass.
Then open `http://localhost:8000/?selftest=1` (green banner), play a full round on desktop and on a mobile-emulated viewport, exercise BOTH A and B CTAs, and confirm `/admin` reflects the events and CSV export downloads.

- [ ] **Step 3: Commit**

```bash
git add README.md run.sh
git commit -m "docs: README with setup, run, A/B, and asset-swap instructions"
```

---

## Self-Review (completed by plan author)

**Spec coverage:**
- Routing/structure (one server, game at `/`, landing at `/home/`, `/static`, `/db`) → Tasks 1, 8.
- Gameplay (auto-run, single/double jump, single vs umbrella obstacles, spawn/speed ramp, collision→game over, score) → Tasks 9, 10, 13.
- Visual style (sunset parallax, sun over sea, pixel art, unified retro incl. admin, pixel font) → Tasks 12, 15.
- Music (loop, gesture-start, 0.5 vol, mute, retro SFX) → Task 14.
- A/B (server-side random 50/50 assignment, sticky via cookie + injected sid, A on start / B on game over, QR+button via `/go/presave`, cross-device QR attribution, events visit/game_start/game_over/cta_view/cta_click with ts/session/variant/meta) → Tasks 1, 3–5, 11, 14.
- Backend/metrics/admin (events table, per-variant metrics, CVR, button/qr split, games+avg score, daily chart, leader + Bayesian P(B>A) + Fisher exact p, login via env, CSV export) → Tasks 2, 6, 7, 8.
- Adaptivity (desktop space + mobile tap, DPR, orientations, touch targets, safe areas) → Tasks 13, 15.
- Secrets via env → Task 1 + Global Constraints.
- Don't break landing → Global Constraints + Task 1 mount.

**Placeholder scan:** rendering/visual tasks (12–15) are intentionally interface+acceptance specified rather than full code because exact art/colours are produced by the frontend-design pass; all deterministic logic (backend, physics, obstacles, ab) has complete code and concrete tests.

**Type consistency:** JS module signatures (`createRunner/jump/stepRunner`, `createGameState/stepObstacles/collides/runnerBox`, `readSession/markVisited/createEmitter/goPresaveUrl`) and Python signatures (`new_session/resolve`, `get_conn/init_db/insert_event/fetch_all_events`, `compute_dashboard/prob_b_beats_a/fisher_exact_two_sided`, `build_presave_url/make_qr_png`, `build_api_router/build_admin_router`, `create_app/load_settings`) match across all tasks and the interface-contracts block.

---

# ADDENDUM — Session 2 features (collectibles, best score, character select)

**Confirmed with user:** collectibles float in the AIR (caught by jumping, +1 each); best score
persists in `localStorage`; 4 characters are COSMETIC ONLY (same physics/hitbox, different sprite).
Placeholder art now + swap points; asset folders already created:
`static/sprites/characters/` (char1..char4.png) and `static/sprites/items/` (item1.png, item2.png, …).

## Task 17: Collectibles (pure) + gamestate scoring

**Files:** Create `static/js/collectibles.js`, `tests/js/collectibles.smoke.mjs`; Modify `static/js/config.js`, `static/js/gamestate.js`.

**Interfaces (pure, `collectibles.js`):** `createCollectibleState()`, `stepCollectibles(state, dt, worldW=640)` (spawns air items on a randomized gap, moves them left by GAME.RUN_SPEED-ish/scroll speed, drops off-screen), `catchCollectibles(runnerBox, state) -> count` (AABB overlap via `collides` imported from obstacles.js; marks/removes caught, returns how many caught this call). Item shape `{x, y, w, h, kind, caught}`.

- [ ] **Step 1: config additions.** Add to `GAME` in `config.js`: `ITEM_W: 24, ITEM_H: 24, ITEM_KINDS: 3, ITEM_MIN_GAP: 1.6, ITEM_MAX_GAP: 3.2, ITEM_Y_MIN: 140, ITEM_Y_MAX: 200` (item top-y range — inside the jump arc so items are catchable; single-jump apex feet ≈189, double ≈139).
- [ ] **Step 2: write `collectibles.smoke.mjs` (RED).**
```js
import { GAME } from "../../static/js/config.js";
import { createCollectibleState, stepCollectibles, catchCollectibles } from "../../static/js/collectibles.js";
import { runnerBox } from "../../static/js/obstacles.js";
import { createRunner } from "../../static/js/physics.js";
let failed = 0; const ok = (c,m)=>{ if(c)console.log("PASS "+m); else{failed++;console.error("FAIL "+m);} };
// spawns over time
const s = createCollectibleState();
for (let i=0;i<600;i++) stepCollectibles(s, 1/60, 640);
ok(s.items.length >= 0, "stepCollectibles runs without error");
ok(s.items.every(it => it.y >= GAME.ITEM_Y_MIN && it.y <= GAME.ITEM_Y_MAX), "items spawn in the air band");
// catch: airborne runner overlapping an item scores it, item removed
const s2 = createCollectibleState();
const r = createRunner(); r.y = 170; // airborne, box ~[122,170]
s2.items.push({ x: GAME.RUNNER_X, y: 150, w: GAME.ITEM_W, h: GAME.ITEM_H, kind: 0, caught: false });
const n = catchCollectibles(runnerBox(r), s2);
ok(n === 1 && s2.items.length === 0, "airborne runner catches the item (+1, removed)");
// grounded runner does NOT catch a high air item
const s3 = createCollectibleState();
const g = createRunner(); // grounded, box ~[252,300]
s3.items.push({ x: GAME.RUNNER_X, y: 150, w: GAME.ITEM_W, h: GAME.ITEM_H, kind: 0, caught: false });
ok(catchCollectibles(runnerBox(g), s3) === 0, "grounded runner misses a high air item");
if (failed){ console.error(`COLLECTIBLES SMOKE: ${failed} FAILED`); process.exit(1); }
console.log("COLLECTIBLES SMOKE: ALL PASS");
```
Run `node tests/js/collectibles.smoke.mjs` → FAIL (module missing).
- [ ] **Step 3: implement `collectibles.js`** so the smoke passes. Reuse `collides` from obstacles.js. Randomized spawn gap in `[ITEM_MIN_GAP, ITEM_MAX_GAP]`, item `x` starts at `worldW+20`, `y` random in `[ITEM_Y_MIN, ITEM_Y_MAX]`, `kind` random `0..ITEM_KINDS-1`. Move left each step (use a fixed scroll ~ `GAME.RUN_SPEED` or accept a speed param — keep it self-contained with `GAME.RUN_SPEED` for the pure test). Drop items with `x + w < -40`.
- [ ] **Step 4: integrate into `gamestate.js`.** `createGame()` adds `col: createCollectibleState()` and `caught: 0`. `startGame(g)` resets `col`/`caught`. In `stepGame`: after obstacles, call `stepCollectibles(g.col, dt, worldW)` then `const caught = catchCollectibles(runnerBox(g.runner), g.col); g.caught += caught;` and set `g.score = g.obs.score + g.caught`. `scoreDelta` returned must include `caught` (i.e. `obstacleDelta + caught`). Collectibles NEVER cause game-over.
- [ ] **Step 5:** update `tests/js/gamestate.smoke.mjs` — add an assertion that catching an item raises `g.score` without setting `over` (place an item overlapping an airborne runner, step, assert scoreDelta≥1 and !over). Run `node tests/js/gamestate.smoke.mjs` and `node tests/js/collectibles.smoke.mjs` → both PASS.
- [ ] **Step 6: commit** `git add static/js/collectibles.js static/js/config.js static/js/gamestate.js tests/js/collectibles.smoke.mjs tests/js/gamestate.smoke.mjs` → `feat: air collectibles (catch = +1), integrated into scoring`.

## Task 18: Prefs — best score (localStorage) + character selection (pure)

**Files:** Create `static/js/prefs.js`, `tests/js/prefs.smoke.mjs`.

**Interfaces (pure, store = localStorage-shaped):** `getBest(store) -> number`, `updateBest(store, score) -> number` (stores & returns max), `getChar(store) -> 0..3` (default 0), `setChar(store, i)` (clamps to 0..3).

- [ ] **Step 1: `prefs.smoke.mjs` (RED)** with a fake store: `updateBest` keeps the max across calls; `getBest` reads it; `getChar` defaults 0; `setChar(store,2)`+`getChar`→2; `setChar` clamps 9→3 and -1→0.
- [ ] **Step 2: implement `prefs.js`** (keys `dp_best`, `dp_char`); parse ints defensively. Run `node tests/js/prefs.smoke.mjs` → PASS.
- [ ] **Step 3: commit** `git add static/js/prefs.js tests/js/prefs.smoke.mjs` → `feat: prefs — persistent best score + character selection`.

## Task 19: Sprites — draw collectibles + 4 character variants (procedural + swap)

**Files:** Modify `static/js/sprites.js`, `tests/js/sprites.smoke.mjs`.

- [ ] **Step 1:** add `drawCollectible(ctx, item)` — procedural per `item.kind` (a few distinct shapes/colors from PALETTE, e.g. a spinning gem/star/shell), swap point `images["item_" + item.kind]` (drawImage + return if present). Extend `drawRunner(ctx, runner, t, charIndex = 0)` — 4 distinct procedural variants keyed by `charIndex` (different palette accents/silhouette), swap point `images["char_" + charIndex]`. Keep default `charIndex=0` so existing callers/tests don't break.
- [ ] **Step 2:** make `loadSprites(manifest)` graceful — set `img.onerror` so a MISSING PNG does NOT populate `images[name]` (procedural fallback stays); only loaded images swap in. (So dropping files into the folders "just works" on reload.)
- [ ] **Step 3:** extend `tests/js/sprites.smoke.mjs`: `drawCollectible(mockCtx, {x,y,w,h,kind:0,...})` paints; `drawRunner(mockCtx, createRunner(), 0, 2)` paints; swap point: set `images["char_2"]`→drawImage used; set `images["item_0"]`→drawImage used. Run `node tests/js/sprites.smoke.mjs` → PASS. Confirm `node tests/js/selftest.node.mjs` still PASS.
- [ ] **Step 4: commit** `git add static/js/sprites.js tests/js/sprites.smoke.mjs` → `feat: collectible art + 4 character variants (procedural, PNG swap points)`.

## Task 20: UI wiring — character picker, best score, catch render (visual; controller-verified)

**Files:** Modify `templates/game.html`, `static/css/game.css`, `static/js/boot.js`, `static/js/game.js`. Modify `readme.md` (asset folders).

- [ ] **Step 1: `game.js`** — the `Game` controller gets a `charIndex` (settable before `start()`); `render()` passes it to `sprites.drawRunner(ctx, runner, t, charIndex)` and draws every `game.col.items` via `sprites.drawCollectible`. (score already includes catches via `stepGame`; `onScore` already fires.)
- [ ] **Step 2: `boot.js`** — import `getBest/updateBest/getChar/setChar` from prefs.js. Character picker in `#start`: 4 selectable thumbnails; click → `setChar(localStorage,i)`, highlight, and set `game.charIndex`. On load read `getChar` and preselect. Best score: on `onGameOver(s)` → `updateBest(localStorage, s)`; show `getBest(localStorage)` on the start overlay and on Game Over ("Рекорд: N"). Optional: a short WebAudio catch blip when score jumps from a catch.
- [ ] **Step 3: `game.html` + `game.css`** — add a `#char-picker` (4 tiles) in `#start`, and best-score `<span>`s on start + game over. Style with the sunset tokens (tiles ≥44px touch targets, selected tile highlighted in `--arcade`). Keep the character tiles rendered with placeholder art (CSS/procedural or the sprite) so they're visible before PNGs exist.
- [ ] **Step 4: `readme.md`** — document `static/sprites/characters/` (char1..char4.png) and `static/sprites/items/` (item1.png…) drop-in, auto-swap on reload.
- [ ] **Step 5:** headless checks — `node --check static/js/boot.js`, `node tests/js/*` all green. Controller does the browser visual/gameplay verify.
- [ ] **Step 6: commit** `git add templates/game.html static/css/game.css static/js/boot.js static/js/game.js readme.md` → `feat: character picker + session best score + collectibles rendering`.

---

# ADDENDUM — Session 3 (admin redesign+tabs, game settings, lyric reveal, mobile, manual)

**Confirmed with user:** speed = multiplier **0.6×–1.2×** (default 1.0×); manual = **always on start screen**;
admin = **modern LIGHT dashboard** (this OVERRIDES the earlier "plain/minimal admin" — admin is now a
proper modern UI, still its own identity separate from the game's sunset). Song = 24 ordered lines
(chorus repeats as written). N (points per revealed line) is editable in admin, default 5.

## Task 21: Backend — game settings store + public config API

**Files:** Create `server/settings.py`, `tests/test_settings.py`; Modify `server/db.py` (add `settings` table to SCHEMA), `server/api.py` (add `GET /api/config`).

- `settings` table: `settings(key TEXT PRIMARY KEY, value TEXT)` — add to `SCHEMA` in db.py (created at startup).
- `server/settings.py`:
  - `DEFAULTS = {"points_per_line": 5, "speed_mult": 1.0}`
  - `get_settings(conn) -> dict` — read rows, merge over DEFAULTS, coerce types (int/float).
  - `set_settings(conn, updates: dict) -> dict` — validate+clamp (`points_per_line` int ≥1; `speed_mult` float clamped to [0.6, 1.2]), upsert, return the new full settings.
- `GET /api/config` (public, no auth) in api.py → `{"points_per_line": int, "speed_mult": float}` from `get_settings`.
- Tests: defaults when empty; set+get roundtrip; clamp (speed 5.0→1.2, 0.1→0.6; points 0→1); `/api/config` returns JSON with both keys.
- Commit on branch `game`, targeted add.

## Task 22: Admin — modern light redesign + tabs (A/B + Настройки игры)

**Files:** Rewrite `static/css/admin.css`, `templates/admin.html`, `templates/admin_login.html`; Create `templates/admin_settings.html`; Modify `server/admin.py` (shared layout/nav, `GET/POST /admin/settings`).

Design tokens (modern light): font = system UI sans (`-apple-system, "Segoe UI", Roboto, Inter, sans-serif`);
bg `#F6F7F9`, card `#FFFFFF`, border `#E6E8EC`, text `#111827`, muted `#6B7280`, accent `#6D28D9` (violet),
accent-2 `#0EA5E9` (for variant B bars); radius 12px, subtle shadow `0 1px 3px rgba(16,24,40,.08)`.
Clean cards, generous spacing, accessible focus states, responsive (cards stack, table scrolls on mobile).

- Top nav/tabs (server-rendered, active highlighted): **A/B** (`/admin`) · **Настройки игры** (`/admin/settings`) · Экспорт CSV · Выйти.
- `/admin` (A/B tab): the existing metrics (sessions, CTA views/clicks button/qr, CVR, games, avg score, daily bars, Bayes P(B>A)+Fisher) — restyled as modern cards + a clean bar chart. Same `compute_dashboard` data.
- `/admin/settings` (GET, auth): form — **N (очков на строчку)** number input; **скорость игры** range slider `0.6–1.2` step `0.05` with a live value label (default from settings). POST `/admin/settings` (auth) → `set_settings` → redirect back with a "сохранено" note.
- Login page restyled to match (centered card, modern).
- Tests (extend `tests/test_admin.py`): `/admin/settings` requires auth; POST saves (get_settings reflects it) + clamps; `/admin` still 200 and shows both tab links.
- Commit on branch `game`, targeted add.

## Task 23: Game — config fetch, speed, lyric-reveal mechanic

**Files:** Create `static/js/lyrics.js`, `tests/js/reveal.smoke.mjs`; Modify `static/js/audio.js` (sfxReveal), `static/js/gamestate.js` (speedMult + reveal helper), `static/js/obstacles.js` (`createGameState(speedMult=1)`), `static/js/game.js` (reveal→pause hook + resume), `static/js/boot.js` (fetch /api/config, wire reveal popup + counter pulse), `templates/game.html` + `static/css/game.css` (reveal popup + score pulse).

- `static/js/lyrics.js`: `export const LYRICS = [ ...24 lines in order... ]` (see the 24 lines below, verbatim, chorus repeated).
- Speed: `createGameState(speedMult = 1)` → `speed = GAME.RUN_SPEED * speedMult`, cap `GAME.MAX_SPEED * speedMult`. `startGame(g, speedMult)` passes it. boot sets speedMult from `/api/config`.
- Reveal helper (pure, in gamestate.js): `nextRevealIndex(score, n, revealed, total) -> number|null` — returns `revealed` if `n>0 && revealed<total && Math.floor(score/n) > revealed`, else null. Node-tested (`reveal.smoke.mjs`): at score n→index0, 2n→index1, stops at total, n=0→null.
- game.js: Game gains `pointsPerLine`, `speedMult`, `lyricsCount`, `revealed=0`. In the loop after stepGame (while running): if `nextRevealIndex(score, pointsPerLine, revealed, lyricsCount)` is not null → set `state='paused'`, call `onReveal(index)`, `revealed++`. Add `resume()` (sets `state='running'`, resets `last` timestamp to avoid a dt jump). Loop keeps rendering while paused (frozen scene).
- audio.js: `sfxReveal()` — 3 ascending square-wave notes (e.g. 523/659/784 Hz), short, retro.
- boot.js: on load `fetch('/api/config')` → set `game.pointsPerLine`, `game.speedMult`, `game.lyricsCount = LYRICS.length` (fallback defaults on error). `onReveal(i)`: pause is already set by game.js → play `sfxReveal()`, add a `pulse` class to `#score` (scale up→down via CSS), show `#reveal-popup` with text `Ура, вы открыли новую строчку из песни:` + `LYRICS[i]`. Popup "Дальше" button → hide popup, `game.resume()`.
- game.html/game.css: `#reveal-popup` overlay (sunset-styled, centered, big line, "Дальше" ≥44px); `#score.pulse` keyframe (scale 1.0→1.4→1.0 ~450ms).
- Commit on branch `game`, targeted add.

### Song lines (verbatim, order for lyrics.js — chorus repeats)
```
я встретил тебя на курортном проспекте
такой неуклюжий а ты улыбнулась
мы будто родились на разных планетах
ты ярко сияешь я робко сутулюсь
пойдем же быстрей ты вдруг мне сказала
кто встретит закат, если нас там не будет?
я чувствовал только как вспыхнуло пламя
и будто мы самые близкие люди
девятнадцать часов середина июля
в закатное солнце на пляже смотрю я
мечтаем с тобой навсегда здесь остаться
и пусть снова нам будет по девятнадцать
мне хочется верить, что это не вымысел
всё так хорошо будто я это выдумал
лежали в объятиях по звездам гадали
что мы ни смотря ни на что вновь увидимся
и вот я стою на том самом месте
прошел всего год, а как будто бы вечность
мне раньше казалось, что так не бывает
но вижу тебя и ты улыбаешься
девятнадцать часов середина июля
в закатное солнце на пляже смотрю я
мечтаем с тобой навсегда здесь остаться
и пусть снова нам будет по девятнадцать
```

## Task 24: Game — mobile camera + pre-game manual

**Files:** Modify `static/js/game.js` (responsive camera), `templates/game.html` + `static/css/game.css` (manual block); possibly `static/js/config.js` (a MIN_VIEW_W constant).

- **Mobile "too big / runner in the middle / no reaction time":** keep the pure logic + RUNNER_X=90 UNCHANGED (don't touch obstacles/physics/tests). Fix the CAMERA in `game.js` resize(): ensure a MINIMUM visible world width so the runner (logical x=90) sits in the LEFT portion with lots of track ahead, and elements render smaller on small screens. Approach: `scale = min(cssH / GAME.WORLD_H, cssW / MIN_VIEW_W)` where `MIN_VIEW_W ≈ 720` (logical). Anchor the ground band to the bottom (translate so `GROUND_Y` maps near the bottom of the canvas). Result: on wide desktop it fills height as before; on narrow mobile it zooms OUT to show ≥720 logical px of width (runner ~12% from left, more track visible) and everything is smaller. Verify the ground/sun still frame correctly. This is game.js glue only.
- **Manual (always on start):** in `#start`, add a compact controls panel (above/around «Играть»): «Пробел / тап — прыжок», «Двойной тап — двойной прыжок (выше)», «Лови предметы в воздухе (+1)», «Перепрыгивай отдыхающих». Small pixel icons or emoji, sunset-styled, readable on mobile. Static (no JS logic).
- Verify by play on desktop + mobile viewport (controller). Commit on branch `game`, targeted add.

---

# ADDENDUM — Session 4: presave modal + real-presave experiment (Tasks 25–26)

**Confirmed with user:** replace the external presave redirect with an IN-GAME modal (our own
markup: cover + 5 service buttons visually replicating bandlink's white pills / «Пресейв» /
«Сохранено» spans). Detection of REAL presave via band.link's `redirectUrl` substitution —
automation only, no self-report. New admin tab «Пресейвы» inside the A/B section.

**Recon facts (verified):** dnkmusic.ru = BandLink. Popup URLs:
`https://band.link/save-presave?type={yandex|vkmusic|mts|zvuk|apple}&bandlink_hash=ywthC&upc=4610605713098&redirectUrl=<URL>`
— all 5 types return 200; redirectUrl accepts foreign URLs at render time (end-to-end unverifiable
without a real account; if ignored, presave_done just won't fire — accepted risk).
Their iframe embedding breaks (needs secure context + OAuth anti-framing) — NOT used.

## Task 25: Backend — presave events, return endpoint, «Пресейвы» admin tab

**Files:** Modify `server/api.py`, `server/metrics.py`, `server/admin.py`, `templates/_admin_nav.html`; Create `templates/admin_presave.html`, `tests/test_presave_flow.py`.

- `server/api.py`: extend `EventType` Literal with `"streaming_click"` and `"presave_done"` (POST /api/event accepts them). Add `GET /presave/return?service=X&sid=&v={A|B}`: validates v∈{A,B} (400 otherwise), coerces unknown service to "unknown", logs `presave_done` with meta `{"service": service}`, returns a minimal HTML page («Сохранено! Возвращайся в игру») whose inline script does `try{ window.opener && window.opener.postMessage({dp:"presave_done",service:"X"}, "*") }catch(e){}` then `window.close()` attempt; page shows the message regardless (close may be blocked).
- `server/metrics.py`: add `compute_presave_dashboard(conn) -> dict` — same shape idea as compute_dashboard but per variant: `sessions`, `cta_view_sessions`, `cta_click_sessions`, `streaming_click_sessions`, `presave_done_sessions`, `presave_done_total`, per-service breakdown from meta.service (dict), `cvr = presave_done_sessions / cta_view_sessions` (0 when no views); leader by cvr; reuse `prob_b_beats_a`+`fisher_exact_two_sided` on (presave_done_sessions, cta_view_sessions); `enough_data` as before.
- `server/admin.py` + templates: new authed route `GET /admin/presave` rendering `admin_presave.html` (modern light cards like admin.html, columns A/B: показы CTA, открытия модалки (cta_click), клики по стримингам, **пресейвы** (highlight), разбивка по сервисам, CVR, Bayes/Fisher line). `_admin_nav.html`: the A/B area now has two tabs — «A/B: клики» (`/admin`) and «A/B: пресейвы» (`/admin/presave`) — plus existing Настройки/CSV/Выйти; active-tab handling extended (`active` values: "ab", "presave", "settings").
- `tests/test_presave_flow.py`: POST /api/event accepts streaming_click/presave_done (422 for junk still); GET /presave/return logs presave_done with right variant/sid/service + 200 HTML containing «Сохранено» and postMessage script; bad v → 400; /admin/presave requires auth; authed 200 contains «Пресейвы» and both variant labels after seeding events; nav on /admin contains link to /admin/presave.

## Task 26: Frontend — in-game presave modal + popup flow + live «Сохранено»

**Files:** Modify `templates/game.html`, `static/css/game.css`, `static/js/boot.js`, `static/js/config.js`.

- `config.js`: add `PRESAVE = { HASH: "ywthC", UPC: "4610605713098", SERVICES: [ {id:"yandex", name:"Яндекс Музыка"}, {id:"vkmusic", name:"VK Музыка"}, {id:"zvuk", name:"Звук"}, {id:"mts", name:"МТС Музыка"}, {id:"apple", name:"Apple Music"} ] }` (export alongside GAME).
- `game.html`: add `#presave-modal` overlay (hidden): card with cover (`/static/sprites/cover.jpg`), title, list of 5 service rows — white pill rows (`.bl-row`): service name left, `<span class="el-link__action">Пресейв</span>` right; close (×) button. The CTA's «Сделать пресейв» button now OPENS this modal instead of navigating (keep the `<template id="cta-tpl">` cover+button; button loses href).
- `boot.js`: on CTA click → show modal + `emit("cta_click", {src:"button"})` (client-side now; /go/presave no longer used by UI — leave route alone). Per service click: `emit("streaming_click", {service})` + `window.open(bandLinkUrl(service))` where redirectUrl = `location.origin + "/presave/return?service="+id+"&sid="+sid+"&v="+variant`. Listen `window.addEventListener("message", ...)`: accept only data.dp==="presave_done" → mark that service's row as saved: replace span with `<span class="el-link__action el-link__action_disabled" title="Релиз автоматически добавится в раздел Коллекция">Сохранено</span>`, persist ids in localStorage `dp_presaved` (JSON array), restore on modal open. No self-report fallback (decision).
- `game.css`: modal card styling + `.bl-row` white pills mimicking bandlink look (white bg, dark text, rounded, service name + action span; `_disabled` state gray) — intentionally NOT sunset-styled (per user: «оставь как есть на этом сайте»).
- Headless verify: node --check boot.js; pytest suite green; controller screenshots the modal (variant A) and clicks a service to verify popup URL shape.
