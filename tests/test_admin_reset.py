from server.db import get_conn, insert_event, insert_score, top_scores, fetch_all_events


def _login(client):
    client.post("/admin/login", data={"username": "admin", "password": "secret"})


def _seed(settings):
    conn = get_conn(settings.db_path)
    insert_event(conn, "s1", "A", "cta_view", {})
    insert_event(conn, "s1", "A", "cta_click", {"src": "button"})
    insert_score(conn, "Кирилл", 42)
    conn.close()


def test_reset_endpoints_require_login(client):
    for path in ("/admin/events/reset", "/admin/scores/reset"):
        r = client.post(path, follow_redirects=False)
        assert r.status_code in (302, 307)
        assert "/admin/login" in r.headers["location"]


def test_events_reset_clears_events_only(client, settings):
    _seed(settings)
    _login(client)
    r = client.post("/admin/events/reset", data={"next": "/admin/presave"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "/admin/presave?reset=1" in r.headers["location"]
    conn = get_conn(settings.db_path)
    assert len(fetch_all_events(conn)) == 0        # events wiped
    assert len(top_scores(conn)) == 1              # scores untouched
    conn.close()


def test_events_reset_bad_next_falls_back_to_ab(client, settings):
    _seed(settings)
    _login(client)
    r = client.post("/admin/events/reset", data={"next": "http://evil.example"},
                    follow_redirects=False)
    assert r.headers["location"] == "/admin?reset=1"


def test_scores_reset_clears_scores_only(client, settings):
    _seed(settings)
    _login(client)
    r = client.post("/admin/scores/reset", follow_redirects=False)
    assert r.status_code == 303
    assert "/admin/settings?reset=1" in r.headers["location"]
    conn = get_conn(settings.db_path)
    assert len(top_scores(conn)) == 0              # scores wiped
    assert len(fetch_all_events(conn)) == 2        # events untouched
    conn.close()


def test_reset_buttons_render(client, settings):
    _login(client)
    assert "Начать тест заново" in client.get("/admin").text
    assert "Начать тест заново" in client.get("/admin/presave").text
    assert "Обнулить все рекорды" in client.get("/admin/settings").text


def test_ttest_shown_in_dashboards(client, settings):
    # give both variants CTA views + some clicks so the comparison is computed
    conn = get_conn(settings.db_path)
    for i in range(6):
        insert_event(conn, f"a{i}", "A", "cta_view", {})
        if i < 3:
            insert_event(conn, f"a{i}", "A", "cta_click", {"src": "button"})
        insert_event(conn, f"b{i}", "B", "cta_view", {})
        if i < 1:
            insert_event(conn, f"b{i}", "B", "cta_click", {"src": "button"})
    conn.close()
    _login(client)
    assert "t-тест" in client.get("/admin").text
    assert "t-тест" in client.get("/admin/presave").text
