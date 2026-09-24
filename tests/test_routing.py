from pathlib import Path
import re


POSTER_NAMES = (
    "уфа а4.png",
    "екб а4.png",
    "нск а4.png",
    "мск а4.png",
    "спб а4.png",
    "mobile_afisha.jpg",
)

# The «Пламя» cover: 852px lossy WebP (same spec as the game's 19_2 cover) so the
# ~420px desktop slot still gets a retina image, inside the posters' 300 KB budget.
SINGLE_COVER = "plamya.webp"
PRESAVE_URL = "https://dnkmusic.ru/_plamya_"

EVENT_IDS = (
    "6a46a070983da59ac77d8ccd",
    "6a4b6ed19f4bf9931aca2868",
    "6a7085d06d1bdc42b48fdf81",
    "6a186cb9dd25944b28dbb181",
    "6a19b3b6f4606596ec821030",
)


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
    def variant_of(html):
        m = re.search(r'data-variant="([AB])"', html)
        return m.group(1) if m else None
    v1 = variant_of(client.get("/game").text)   # TestClient persists cookies across calls
    v2 = variant_of(client.get("/game").text)
    assert v1 in ("A", "B") and v1 == v2         # no reassignment once the cookie is set


def test_home_has_desktop_and_mobile_ticketcloud_triggers(client):
    html = client.get("/").text
    triggers = re.findall(r'<button\b[^>]*data-tc-event="([^"]+)"[^>]*>', html)

    assert len(triggers) == 10
    assert sorted(triggers) == sorted(EVENT_IDS * 2)
    assert html.count('data-tc-utm_source="site"') == 10
    assert html.count('data-tc-token="') == 10
    assert html.count("https://ticketscloud.com/static/scripts/widget/tcwidget.js") == 1
    assert 'class="poster-grid poster-grid--desktop"' in html
    assert 'class="tour-poster-mobile"' in html


def test_home_forwards_utm_tags_to_ticketscloud(client):
    html = client.get("/").text

    # The passthrough must execute BEFORE tcwidget.js: the widget script is
    # synchronous, so a DOMContentLoaded handler would set the attributes too late.
    widget_tag = '<script src="https://ticketscloud.com/static/scripts/widget/tcwidget.js">'
    assert html.index('var STORE = "dp_utm"') < html.index(widget_tag)
    assert 'btn.setAttribute("data-tc-" + k, utm[k])' in html
    # utm_source is pinned to "site" on the buttons, so it stays out of the
    # forwarded set (the separate outbound-link propagation still carries it).
    assert 'var KEYS = ["utm_medium", "utm_campaign", "utm_content", "utm_term"];' in html
    assert html.count('data-tc-utm_source="site"') == 10


def test_single_section_offers_one_listen_cta(client):
    html = client.get("/").text
    section = html.split('<section id="single"', 1)[1].split("</section>", 1)[0]
    ctas = re.findall(r'<a class="btn[^"]*"[^>]*href="([^"]+)"', section)

    # «Пламя» is out: the same smartlink now lists the streaming services, so
    # the one button says «listen», not «pre-save».
    assert ctas == [PRESAVE_URL]
    assert "Слушать песню" in section
    assert "data-listen-open" in section  # opens the smartlink in-page, not a new tab
    assert "/game" not in section


def test_no_presave_wording_left_on_the_page(client):
    html = client.get("/").text
    # the pre-save lead stays only inside an HTML comment, for the next single
    visible = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    markup = visible.split("<script>", 1)[0]
    assert "пресейв" not in markup.lower()
    assert "Сделай пресейв" not in html


def test_presave_opens_embedded_not_offsite(client):
    html = client.get("/").text

    # The modal iframe is what the CTA actually shows; https matters because an
    # http:// frame would be blocked as mixed content on the live site.
    assert f'var URL = "{PRESAVE_URL}";' in html
    assert 'id="listen-frame"' in html
    assert "dnkmusic.ru/august_31" not in html  # the previous single is fully gone
    assert "dnkmusic.ru/devyatnadtsat" not in html


def test_home_references_new_single_cover(client):
    html = client.get("/").text
    assert f"/static/home/{SINGLE_COVER}" in html
    assert "/static/home/31_avgusta.jpg" not in html
    assert "31 августа" not in html


def test_single_cover_is_at_most_300kb():
    cover = Path(__file__).parents[1] / "static" / "home" / SINGLE_COVER
    assert cover.stat().st_size <= 300_000


def test_home_references_all_new_posters(client):
    html = client.get("/").text

    for name in POSTER_NAMES:
        assert f"/static/home/{name}" in html


def test_desktop_ticket_buttons_use_primary_button_design(client):
    html = client.get("/").text

    assert html.count(
        'class="poster__tix btn btn--fill tc-background-tomato"'
    ) == 5


def test_new_poster_assets_are_at_most_300kb():
    home_assets = Path(__file__).parents[1] / "static" / "home"

    for name in POSTER_NAMES:
        assert (home_assets / name).stat().st_size <= 300_000, name
