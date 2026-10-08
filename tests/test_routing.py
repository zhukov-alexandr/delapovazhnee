from pathlib import Path
import re


HOME_ASSETS = Path(__file__).parents[1] / "static" / "home"

# The landing shows the «Сочинение» tour poster: the whole vertical sheet on
# phones, cut above the torn faces on desktop (the hero already has the band).
TOUR_POSTERS = ("tour-m.webp", "tour-d.webp")

# The tickets page: one poster per row. Kazakhstan shares one for two dates.
GIG_POSTERS = (
    "tour-myata.webp",
    "tour-ufa.webp",
    "tour-ekb.webp",
    "tour-nsk.webp",
    "tour-kz.webp",
    "tour-msk.webp",
    "tour-spb.webp",
)

# The «Сочинение» album cover: 852px lossy WebP (same spec as the game's 19_2
# cover) so the ~495px desktop slot still gets a retina image, inside the
# posters' 300 KB budget.
RELEASE_COVER = "sochinenie.webp"
LISTEN_URL = "https://dnkmusic.ru/sochinenie_"

# TicketsCloud events: Ufa, Ekaterinburg, Novosibirsk, Moscow, Saint Petersburg.
EVENT_IDS = (
    "6a46a070983da59ac77d8ccd",
    "6a4b6ed19f4bf9931aca2868",
    "6a7085d06d1bdc42b48fdf81",
    "6a186cb9dd25944b28dbb181",
    "6a19b3b6f4606596ec821030",
)

TICKETON = {
    "Алматы": "https://ticketon.kz/concerts/event/tckt2-dela-povazhnee-shabash-almaty",
    "Астана": "https://ticketon.kz/concerts/event/tckt2-dela-povazhnee-shabash-astana",
}


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


def test_tickets_page_is_served(client):
    for path in ("/tickets", "/tickets/"):
        r = client.get(path)
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert r.headers["cache-control"] == "no-cache"
    assert "<title>Билеты – Дела поважнее</title>" in client.get("/tickets").text


def test_tickets_page_has_one_ticketscloud_trigger_per_russian_city(client):
    html = client.get("/tickets").text
    triggers = re.findall(r'<button\b[^>]*data-tc-event="([^"]+)"[^>]*>', html)

    assert sorted(triggers) == sorted(EVENT_IDS)
    assert html.count('data-tc-utm_source="site"') == 5
    assert html.count('data-tc-token="') == 5
    assert html.count("https://ticketscloud.com/static/scripts/widget/tcwidget.js") == 1
    # same button as every other on the page, whatever the widget tries to restyle
    assert html.count('class="gig__tix btn btn--fill tc-background-tomato"') == 5


def test_tickets_page_forwards_utm_tags_to_ticketscloud(client):
    html = client.get("/tickets").text

    # The passthrough must execute BEFORE tcwidget.js: the widget script is
    # synchronous, so a DOMContentLoaded handler would set the attributes too late.
    widget_tag = '<script src="https://ticketscloud.com/static/scripts/widget/tcwidget.js">'
    assert html.index('var STORE = "dp_utm"') < html.index(widget_tag)
    assert 'btn.setAttribute("data-tc-" + k, utm[k])' in html
    # utm_source is pinned to "site" on the buttons, so it stays out of the
    # forwarded set (the separate outbound-link propagation still carries it).
    assert 'var KEYS = ["utm_medium", "utm_campaign", "utm_content", "utm_term"];' in html


def test_landing_hands_campaign_tags_over_to_the_tickets_page():
    # The buy buttons moved off the landing, so it must pass its tags on: in the
    # /tickets link (handled with every other link) and in sessionStorage under
    # the key the tickets page reads.
    js = (HOME_ASSETS / "site.js").read_text(encoding="utf-8")
    assert 'sessionStorage.setItem("dp_utm"' in js
    assert '["utm_medium", "utm_campaign", "utm_content", "utm_term"]' in js


def test_tickets_page_lists_the_whole_tour_in_date_order(client):
    html = client.get("/tickets").text
    cities = re.findall(r'<h2 class="gig__city display"[^>]*>([^<]+)</h2>', html)

    assert cities == [
        "Бунырево", "Уфа", "Екатеринбург", "Новосибирск",
        "Алматы", "Астана", "Москва", "Санкт-Петербург",
    ]
    for name in GIG_POSTERS:
        assert f"/static/home/{name}" in html


def test_kazakhstan_concerts_sell_through_ticketon(client):
    html = client.get("/tickets").text
    lines = html.split('<div class="gig__line">')[1:]

    for city, url in TICKETON.items():
        line = next(l for l in lines if f">{city}</h2>" in l)
        assert f'href="{url}"' in line
        assert "data-tc-event" not in line


def test_dikaya_myata_is_free_entry_with_a_link_to_the_festival(client):
    html = client.get("/tickets").text
    line = next(l for l in html.split('<div class="gig__line">')[1:] if ">Бунырево</h2>" in l)

    assert "Вход свободный" in line
    assert 'href="https://wmcamp.ru/#concert"' in line
    assert "data-tc-event" not in line      # nothing to buy
    assert ">Билеты<" not in line


def test_only_bunyrevo_is_marked_as_not_the_album_presentation(client):
    # The page is headed «Презентация альбома «Сочинение»», and Bunyrevo is the
    # one concert that isn't: it gets a note saying what is played instead.
    html = client.get("/tickets").text
    lines = html.split('<div class="gig__line">')[1:]
    noted = [l for l in lines if "gig__program" in l]

    assert len(noted) == 1
    assert ">Бунырево</h2>" in noted[0]
    assert "Не презентация: играем любимые песни" in noted[0]


def test_landing_sends_ticket_buyers_to_the_tickets_page(client):
    html = client.get("/").text
    section = html.split('<section id="concerts"', 1)[1].split("</section>", 1)[0]

    assert '<a class="btn btn--fill" href="/tickets"' in section
    for name in TOUR_POSTERS:
        assert f"/static/home/{name}" in section
    # phones get the vertical sheet, everything wider the cropped one
    assert '<source media="(max-width: 760px)" srcset="/static/home/tour-m.webp"' in section
    # the buy buttons and their widget live on /tickets only
    assert "data-tc-event" not in html
    assert "tcwidget.js" not in html


def test_release_section_offers_one_listen_cta(client):
    html = client.get("/").text
    section = html.split('<section id="release"', 1)[1].split("</section>", 1)[0]
    ctas = re.findall(r'<a class="btn[^"]*"[^>]*href="([^"]+)"', section)

    # «Сочинение» is out: one button, and it opens the album's smartlink.
    assert ctas == [LISTEN_URL]
    assert "Слушать альбом" in section
    assert "data-listen-open" in section  # opens the smartlink in-page, not a new tab
    assert "/game" not in section
    assert 'id="single"' in section       # old anchor: /#single links still land here


def test_no_presave_wording_left_on_the_page(client):
    html = client.get("/").text
    # the pre-save lead stays only inside an HTML comment, for the next release
    visible = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    markup = visible.split("<script>", 1)[0]
    assert "пресейв" not in markup.lower()
    assert "Сделай пресейв" not in html


def test_album_opens_embedded_not_offsite(client):
    html = client.get("/").text

    # The modal iframe is what the CTA actually shows; https matters because an
    # http:// frame would be blocked as mixed content on the live site.
    assert f'var URL = "{LISTEN_URL}";' in html
    assert 'id="listen-frame"' in html
    for old in ("dnkmusic.ru/_plamya_", "dnkmusic.ru/august_31", "dnkmusic.ru/devyatnadtsat"):
        assert old not in html  # the previous releases are fully gone


def test_home_references_the_album_cover(client):
    html = client.get("/").text
    assert f"/static/home/{RELEASE_COVER}" in html
    assert "/static/home/plamya.webp" not in html
    assert "«Пламя»" not in html


def test_web_images_stay_inside_the_300kb_budget():
    for name in (RELEASE_COVER, "mark.webp", "sochinenie-ground.webp", *TOUR_POSTERS, *GIG_POSTERS):
        assert (HOME_ASSETS / name).stat().st_size <= 300_000, name


def test_both_pages_share_one_stylesheet_and_script(client):
    for path in ("/", "/tickets"):
        html = client.get(path).text
        assert '<link rel="stylesheet" href="/static/home/site.css">' in html
        assert '<script src="/static/home/site.js"></script>' in html
        # the dictionary must be defined before the engine that reads it
        assert html.index("window.DP_I18N = {") < html.index('<script src="/static/home/site.js">')
