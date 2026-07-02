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


from server.settings import get_settings


def test_admin_settings_requires_login(client):
    r = client.get("/admin/settings", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/admin/login" in r.headers["location"]

def test_admin_settings_form_shows_current_values(client, settings):
    conn = get_conn(settings.db_path); init_db(conn)
    _login(client)
    r = client.get("/admin/settings")
    assert r.status_code == 200
    assert "Настройки игры" in r.text
    assert 'name="points_per_line"' in r.text
    assert 'name="speed_mult"' in r.text

def test_admin_settings_post_saves(client, settings):
    conn = get_conn(settings.db_path); init_db(conn)
    _login(client)
    r = client.post("/admin/settings",
                    data={"points_per_line": "7", "speed_mult": "0.9"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    cfg = get_settings(conn)
    assert cfg["points_per_line"] == 7
    assert cfg["speed_mult"] == 0.9

def test_admin_settings_post_clamps_speed(client, settings):
    conn = get_conn(settings.db_path); init_db(conn)
    _login(client)
    r = client.post("/admin/settings",
                    data={"points_per_line": "5", "speed_mult": "5"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    cfg = get_settings(conn)
    assert cfg["speed_mult"] == 1.2

def test_admin_dashboard_shows_both_tabs(client):
    _login(client)
    r = client.get("/admin")
    assert r.status_code == 200
    assert "Настройки игры" in r.text
    assert 'href="/admin"' in r.text
    assert 'href="/admin/settings"' in r.text
