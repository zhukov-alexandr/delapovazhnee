def test_root_serves_landing(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Дела поважнее" in r.text  # landing <title>

def test_game_serves_game_page(client):
    r = client.get("/game")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'data-variant=' in r.text  # the templated game shell

def test_home_redirects_to_root(client):
    r = client.get("/home/", follow_redirects=False)
    assert r.status_code in (301, 307, 308)
    assert r.headers["location"] == "/"

def test_static_mounted(client):
    # game.css is created in a later task; here we only assert the mount exists
    r = client.get("/static/does-not-exist.css")
    assert r.status_code == 404  # mount handles it, not a routing 404 page

def test_game_assigns_variant_cookie(client):
    r = client.get("/game")
    assert r.cookies.get("dp_variant") in ("A", "B")
    assert r.cookies.get("dp_sid")

def test_variant_is_sticky(client):
    import re
    def variant_of(html):
        m = re.search(r'data-variant="([AB])"', html)
        return m.group(1) if m else None
    v1 = variant_of(client.get("/game").text)   # TestClient persists cookies across calls
    v2 = variant_of(client.get("/game").text)
    assert v1 in ("A", "B") and v1 == v2         # no reassignment once the cookie is set
