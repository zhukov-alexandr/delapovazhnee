# Concert Posters and Ticketscloud Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two legacy concert cards with five desktop posters, one mobile clickable tour poster, and Ticketscloud widgets while keeping every new PNG at or below 300,000 bytes.

**Architecture:** Keep the landing page self-contained in `templates/home.html`, following its existing inline CSS and i18n pattern. Render separate desktop and mobile concert presentations selected by the existing 760px breakpoint; both presentations use native `<button>` elements recognized by the single Ticketscloud script include. Optimize the six source PNGs in place with FFmpeg palette quantization because the site does not need their print-resolution dimensions.

**Tech Stack:** FastAPI static landing page, semantic HTML, inline responsive CSS, vanilla JavaScript/Ticketscloud widget, pytest, FFmpeg.

## Global Constraints

- Desktop shows Ufa, Ekaterinburg, Novosibirsk, Moscow, and Saint Petersburg in one horizontal row without a carousel or wrapping.
- Mobile shows only `все афиши.png`, with one accessible clickable overlay for each city row.
- Every desktop and mobile trigger has `data-tc-utm_source="site"`, the supplied common token, and its city's exact event ID.
- Include `https://ticketscloud.com/static/scripts/widget/tcwidget.js` exactly once.
- Preserve the six supplied filenames and PNG format; every resulting file is at most 300,000 bytes.
- Preserve the existing visual language and RU/EN/ZH language switcher.

---

### Task 1: Contract tests for poster assets and Ticketscloud markup

**Files:**
- Modify: `tests/test_routing.py`
- Test: `tests/test_routing.py`

**Interfaces:**
- Consumes: `/` from `main.create_app()` and the six files under `static/home/`.
- Produces: regression tests that define the required event IDs, trigger count, UTM values, responsive markup hooks, widget script include, asset paths, and byte limit.

- [ ] **Step 1: Write failing landing-page contract tests**

Append tests equivalent to:

```python
from pathlib import Path
import re


POSTER_NAMES = (
    "уфа а4.png", "екб а4.png", "нск а4.png",
    "мск а4.png", "спб а4.png", "все афиши.png",
)
EVENT_IDS = (
    "6a46a070983da59ac77d8ccd",
    "6a4b6ed19f4bf9931aca2868",
    "6a7085d06d1bdc42b48fdf81",
    "6a186cb9dd25944b28dbb181",
    "6a19b3b6f4606596ec821030",
)


def test_home_has_desktop_and_mobile_ticketcloud_triggers(client):
    html = client.get("/").text
    triggers = re.findall(r"<button\\b[^>]*data-tc-event=\"([^\"]+)\"[^>]*>", html)
    assert len(triggers) == 10
    assert sorted(triggers) == sorted(EVENT_IDS * 2)
    assert html.count('data-tc-utm_source="site"') == 10
    assert html.count('data-tc-token="') == 10
    assert html.count("https://ticketscloud.com/static/scripts/widget/tcwidget.js") == 1
    assert 'class="poster-grid poster-grid--desktop"' in html
    assert 'class="tour-poster-mobile"' in html


def test_home_references_all_new_posters(client):
    html = client.get("/").text
    for name in POSTER_NAMES:
        assert f"/static/home/{name}" in html


def test_new_poster_assets_are_at_most_300kb():
    home_assets = Path(__file__).parents[1] / "static" / "home"
    for name in POSTER_NAMES:
        assert (home_assets / name).stat().st_size <= 300_000, name
```

- [ ] **Step 2: Run tests and verify the expected failures**

Run: `pytest tests/test_routing.py -v`

Expected: the markup test fails because the current page has links and two legacy posters; the asset-size test fails because the six source PNGs are approximately 18–20 MB.

- [ ] **Step 3: Commit the failing contract tests**

```bash
git add tests/test_routing.py
git commit -m "test: define concert poster widget contract"
```

---

### Task 2: Five-card desktop layout and mobile image map

**Files:**
- Modify: `templates/home.html:174-191`
- Modify: `templates/home.html:230`
- Modify: `templates/home.html:339-363`
- Modify: `templates/home.html:410-473`
- Test: `tests/test_routing.py`

**Interfaces:**
- Consumes: the six poster paths and the `EVENT_IDS` contract from Task 1.
- Produces: `.poster-grid--desktop`, `.tour-poster-mobile`, `.tour-poster-mobile__trigger`, and ten Ticketscloud-compatible buttons.

- [ ] **Step 1: Replace the desktop grid markup**

Replace the two legacy cards with five `.poster` articles in this order: Ufa, Ekaterinburg, Novosibirsk, Moscow, Saint Petersburg. Each article uses its matching `/static/home/<name>.png`, translated alt/city/date/venue keys, and a button of this form:

```html
<button type="button"
        class="poster__tix tc-background-tomato"
        data-tc-utm_source="site"
        data-tc-event="CITY_EVENT_ID"
        data-tc-token="COMMON_TOKEN"
        data-i18n="tickets">Билеты</button>
```

Use the supplied token verbatim and map the five event IDs from the global constraints to the matching city.

- [ ] **Step 2: Add the mobile common poster with five overlay buttons**

Add a `.tour-poster-mobile` wrapper containing `все афиши.png` and five absolutely positioned buttons in the visual order Ufa, Ekaterinburg, Novosibirsk, Moscow, Saint Petersburg. Each button has `type="button"`, the Ticketscloud attributes from Step 1, a city-specific accessible label through `data-i18n-attr="aria-label:..."`, and visually hidden text naming the city.

- [ ] **Step 3: Implement responsive layout CSS**

Set the desktop grid to `grid-template-columns: repeat(5, minmax(0, 1fr))`, reduce card gaps/padding/type at desktop widths, and keep every card in one row. Hide `.tour-poster-mobile` by default. At `max-width: 760px`, hide `.poster-grid--desktop`, show the common poster wrapper, preserve its aspect ratio, and position the five overlay buttons over the city rows visible near the upper quarter of the image. Add hover/focus feedback that outlines the complete row without obscuring poster text.

- [ ] **Step 4: Update all three translation dictionaries**

Add alt text, date/city, venue, and mobile trigger accessible-label keys for all five cities in RU, EN, and ZH. Keep the visible ticket label on desktop connected to the existing `tickets` key.

- [ ] **Step 5: Include the Ticketscloud script once**

Add the following script near the closing `</body>`, after the page's inline behavior script:

```html
<script src="https://ticketscloud.com/static/scripts/widget/tcwidget.js"></script>
```

- [ ] **Step 6: Run the markup contract tests**

Run: `pytest tests/test_routing.py::test_home_has_desktop_and_mobile_ticketcloud_triggers tests/test_routing.py::test_home_references_all_new_posters -v`

Expected: PASS.

- [ ] **Step 7: Commit the responsive widget markup**

```bash
git add templates/home.html
git commit -m "feat: add responsive tour posters and ticket widgets"
```

---

### Task 3: Optimize six PNG assets below 300 KB

**Files:**
- Modify: `static/home/уфа а4.png`
- Modify: `static/home/екб а4.png`
- Modify: `static/home/нск а4.png`
- Modify: `static/home/мск а4.png`
- Modify: `static/home/спб а4.png`
- Modify: `static/home/все афиши.png`
- Delete: `static/home/poster-msk.jpg`
- Delete: `static/home/poster-spb.jpg`
- Test: `tests/test_routing.py`

**Interfaces:**
- Consumes: original high-resolution PNGs supplied by the user.
- Produces: same named PNG assets, city posters at 560px width with up to 96 indexed colors and the common poster at 680px width with up to 64 indexed colors.

- [ ] **Step 1: Optimize the five city posters in place**

For each city file, write FFmpeg output to a unique temporary PNG, confirm the output exists, then move it over the source:

```bash
ffmpeg -v error -i "INPUT.png" -vf "scale=560:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=full[p];[b][p]paletteuse=dither=sierra2_4a" -frames:v 1 "OUTPUT.tmp.png"
mv "OUTPUT.tmp.png" "INPUT.png"
```

- [ ] **Step 2: Optimize the mobile common poster in place**

```bash
ffmpeg -v error -i "static/home/все афиши.png" -vf "scale=680:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64:stats_mode=full[p];[b][p]paletteuse=dither=sierra2_4a" -frames:v 1 "/tmp/все-афиши.optimized.png"
mv "/tmp/все-афиши.optimized.png" "static/home/все афиши.png"
```

- [ ] **Step 3: Run the byte-limit test**

Run: `pytest tests/test_routing.py::test_new_poster_assets_are_at_most_300kb -v`

Expected: PASS with every file at or below 300,000 bytes. If one file exceeds the limit, reduce only that file by 20px width and rerun the same palette settings until it passes.

- [ ] **Step 4: Render and inspect both poster presentations**

Run the application locally, inspect `/` at 1440×900 and 390×844, and confirm poster text remains readable, all five desktop cards stay on one row, the common poster replaces them on mobile, and each overlay aligns with the intended city row.

- [ ] **Step 5: Commit optimized assets and legacy removals**

```bash
git add static/home tests/test_routing.py
git commit -m "perf: optimize tour poster assets"
```

---

### Task 4: Full regression verification

**Files:**
- Verify: `templates/home.html`
- Verify: `tests/test_routing.py`
- Verify: `static/home/*.png`

**Interfaces:**
- Consumes: completed responsive markup and optimized assets.
- Produces: verification evidence for the handoff.

- [ ] **Step 1: Run focused tests**

Run: `pytest tests/test_routing.py -v`

Expected: all routing and landing-page tests PASS.

- [ ] **Step 2: Run the complete Python test suite**

Run: `pytest -q`

Expected: zero failures.

- [ ] **Step 3: Validate the final diff**

Run: `git diff --check HEAD~3..HEAD` and `git status --short`.

Expected: no whitespace errors; status contains no unexpected files and preserves any pre-existing user changes outside this feature.

- [ ] **Step 4: Reconcile every requirement**

Confirm five desktop posters in one row, mobile common poster with five city triggers, ten UTM-marked triggers, five correct event IDs duplicated once per layout, one widget script, six PNGs no larger than 300,000 bytes, and no remaining references to either deleted legacy JPG.
