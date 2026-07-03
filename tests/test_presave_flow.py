import json

from server.db import get_conn, init_db, insert_event, fetch_all_events


def _login(client):
    client.post("/admin/login", data={"username": "admin", "password": "secret"})


# --- POST /api/event: new event types ---

def test_post_event_accepts_streaming_click(client):
    r = client.post("/api/event", json={
        "session_id": "s1", "variant": "A",
        "event_type": "streaming_click", "meta": {"service": "yandex"}})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_post_event_accepts_presave_done(client):
    r = client.post("/api/event", json={
        "session_id": "s1", "variant": "B",
        "event_type": "presave_done", "meta": {"service": "vkmusic"}})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_post_event_still_rejects_unknown_type(client):
    r = client.post("/api/event", json={
        "session_id": "s1", "variant": "A",
        "event_type": "bogus", "meta": {}})
    assert r.status_code == 422


# --- GET /presave/return/{service}/{sid}/{variant} ---
# band.link appends a "…Presaved=<upc>" marker on success; a bare return is a cancel.

def test_presave_return_logs_event_and_returns_html(client, settings):
    r = client.get("/presave/return/yandex/sid-1/B?yandexPresaved=4610605713098")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Сохранено" in r.text
    assert "postMessage" in r.text
    rows = fetch_all_events(get_conn(settings.db_path))
    assert len(rows) == 1
    assert rows[0]["event_type"] == "presave_done"
    assert rows[0]["variant"] == "B"
    assert rows[0]["session_id"] == "sid-1"
    assert json.loads(rows[0]["meta"]) == {"service": "yandex"}


def test_presave_return_coerces_unknown_service(client, settings):
    r = client.get("/presave/return/deezer/sid-2/A?deezerPresaved=4610605713098")
    assert r.status_code == 200
    rows = fetch_all_events(get_conn(settings.db_path))
    assert json.loads(rows[0]["meta"]) == {"service": "unknown"}


def test_presave_return_without_marker_is_not_counted(client, settings):
    # A bare return (user opened the flow but did not save) logs nothing and
    # does not postMessage the row into the «Сохранено» state.
    r = client.get("/presave/return/yandex/sid-3/A")
    assert r.status_code == 200
    assert "postMessage" not in r.text
    assert fetch_all_events(get_conn(settings.db_path)) == []


def test_presave_return_bad_variant_400(client):
    r = client.get("/presave/return/yandex/s/Q?yandexPresaved=1")
    assert r.status_code == 400


# --- GET /admin/presave ---

def test_admin_presave_requires_login(client):
    r = client.get("/admin/presave", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/admin/login" in r.headers["location"]


def test_admin_presave_dashboard_authed(client, settings):
    conn = get_conn(settings.db_path)
    init_db(conn)
    insert_event(conn, "a1", "A", "cta_view", {})
    insert_event(conn, "a1", "A", "cta_click", {})
    insert_event(conn, "a1", "A", "streaming_click", {"service": "yandex"})
    insert_event(conn, "a1", "A", "presave_done", {"service": "yandex"})
    insert_event(conn, "b1", "B", "cta_view", {})
    insert_event(conn, "b1", "B", "presave_done", {"service": "vkmusic"})
    _login(client)
    r = client.get("/admin/presave")
    assert r.status_code == 200
    assert "Пресейвы" in r.text
    assert "Вариант A" in r.text and "Вариант B" in r.text


def test_admin_nav_links_to_presave_tab(client):
    _login(client)
    r = client.get("/admin")
    assert r.status_code == 200
    assert 'href="/admin/presave"' in r.text
