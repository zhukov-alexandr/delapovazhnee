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


from server.db import insert_score
from server.metrics import compute_scores_dashboard


def test_leaderboard_requires_login(client):
    r = client.get("/admin/leaderboard", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/admin/login" in r.headers["location"]


def test_leaderboard_renders_and_filters(client, settings):
    conn = get_conn(settings.db_path); init_db(conn)
    insert_score(conn, "Kirill_777", 142, 0, 95000)
    insert_score(conn, "SashaPlayer", 77, 2, 50000)
    conn.close()
    _login(client)
    r = client.get("/admin/leaderboard")
    assert r.status_code == 200
    assert "Лидерборд" in r.text
    assert "Kirill_777" in r.text and "SashaPlayer" in r.text
    # filter to Саша (character 2): only Sasha's row, not Kirill's
    r2 = client.get("/admin/leaderboard?character=2")
    assert "SashaPlayer" in r2.text and "Kirill_777" not in r2.text


def test_leaderboard_rejects_bad_character(client):
    # Query validation (0..3) fires before the handler — 422 regardless of auth.
    assert client.get("/admin/leaderboard?character=9").status_code == 422


def test_compute_scores_dashboard(settings):
    conn = get_conn(settings.db_path); init_db(conn)
    for name, sc, ch, tm in [("A", 100, 0, 60000), ("B", 50, 0, 30000), ("C", 80, 2, 40000)]:
        insert_score(conn, name, sc, ch, tm)
    d = compute_scores_dashboard(conn)
    assert d["total"] == 3
    assert d["score"]["max"] == 100
    assert d["score"]["mean"] == round((100 + 50 + 80) / 3, 1)
    per = {c["name"]: c for c in d["per_char"]}
    assert per["Кирилл"]["count"] == 2 and per["Саша"]["count"] == 1
    # filtered by character 0 (Кирилл): 2 rows, all Кирилл
    d0 = compute_scores_dashboard(conn, 0)
    assert d0["total"] == 2 and all(r["char_name"] == "Кирилл" for r in d0["rows"])
    conn.close()


from server.db import top_scores


def test_scores_delete_requires_login(client):
    r = client.post("/admin/scores/delete", data={"id": "1"}, follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/admin/login" in r.headers["location"]


def test_scores_delete_removes_one_row_and_keeps_filter(client, settings):
    conn = get_conn(settings.db_path); init_db(conn)
    insert_score(conn, "Keep", 100, 0, 1000)
    del_id = insert_score(conn, "DeleteMe", 50, 1, 2000)
    conn.close()
    _login(client)
    r = client.post("/admin/scores/delete",
                    data={"id": str(del_id), "character": "1"}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/admin/leaderboard?character=1"
    names = [row["name"] for row in top_scores(get_conn(settings.db_path), 10)]
    assert "DeleteMe" not in names and "Keep" in names
