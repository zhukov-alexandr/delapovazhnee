# Concert Layout Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the old concert-section composition on large screens while keeping five posters in one row and making every desktop ticket trigger look and behave like the site's primary “Слушать песню” button.

**Architecture:** Keep the implementation in the landing page's existing inline CSS and markup. Turn the concert wrapper into a full-height flex stage so the eyebrow stays at the top and the poster grid centers in the remaining space while retaining the site's standard `.wrap` width. Stack each narrow five-column card footer with equal-height details and a right-aligned action; reuse `.btn.btn--fill` and compact only its padding at intermediate widths.

**Tech Stack:** Semantic HTML, responsive CSS Grid/Flexbox, existing `Montserrat` and `Golos Text` typography, Ticketscloud widget attributes, pytest.

## Global Constraints

- Keep Ufa, Ekaterinburg, Novosibirsk, Moscow, and Saint Petersburg in one horizontal desktop row.
- Keep the section eyebrow at the top and center the poster row vertically in the remaining section height.
- The concert row uses the same `.wrap` width and horizontal edges as the other site sections.
- Card information sits above a right-aligned ticket button; equal detail heights align all five actions.
- On intermediate desktop widths, compact button padding prevents overflow.
- Desktop ticket triggers use `poster__tix btn btn--fill tc-background-tomato` and retain all existing event IDs, token values, and `data-tc-utm_source="site"` attributes.
- The visible Russian label remains sentence case: `Билеты`.
- Do not change the mobile common poster or its five transparent Ticketscloud hotspots.

---

### Task 1: Primary-button contract and responsive concert stage

**Files:**
- Modify: `tests/test_routing.py`
- Modify: `templates/home.html:173-239`
- Modify: `templates/home.html:351-409`
- Test: `tests/test_routing.py`

**Interfaces:**
- Consumes: existing `.btn`, `.btn--fill`, `.screen`, `.wrap`, `.poster-grid--desktop`, and Ticketscloud attributes.
- Produces: five desktop buttons using the shared primary-button interface, a vertically centered standard-width desktop grid, aligned stacked card footers, and compact intermediate-width actions.

- [ ] **Step 1: Add the failing primary-button contract test**

```python
def test_desktop_ticket_buttons_use_primary_button_design(client):
    html = client.get("/").text

    assert html.count(
        'class="poster__tix btn btn--fill tc-background-tomato"'
    ) == 5
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_routing.py::test_desktop_ticket_buttons_use_primary_button_design -v`

Expected: FAIL because none of the five desktop triggers yet contains `btn btn--fill`.

- [ ] **Step 3: Make the concert wrapper a centered stage**

Add a concert-specific wrapper that can consume the remaining `.screen` height without changing the global `.wrap` used by other sections:

```css
.concerts .wrap {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.poster-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  align-items: stretch;
  gap: clamp(8px, 1.3vw, 18px);
  width: 100%;
  margin-block: auto;
  padding-block: clamp(12px, 2.5vh, 28px);
}
```

- [ ] **Step 4: Align the five narrow card footers**

Keep the standard site width and stack each footer so five cards remain readable:

```css
.poster__meta {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: stretch;
  gap: 12px;
  padding: 12px 6px 14px;
}
.poster__details { min-width: 0; min-height: 82px; }
```

Keep the five cards visually substantial on large screens with `10px` paper padding and responsive date/address typography capped at the old design's `16px`/`13px` sizes.

- [ ] **Step 5: Reuse the primary button classes and protect their visual contract**

Change each of the five desktop buttons to:

```html
class="poster__tix btn btn--fill tc-background-tomato"
```

Use `.poster__tix` only to center the control inside the card footer, preserve `text-transform: none`, and restate the primary-button values with sufficient specificity to beat Ticketscloud's later stylesheet: Montserrat 800, responsive 13–15px type, crimson paper colors, 2px border/radius, and `15px 26px` padding.

- [ ] **Step 6: Add the intermediate desktop fallback**

Between `761px` and `1399px`, reduce only the card-local button dimensions so five cards remain in one row:

```css
@media (min-width: 761px) and (max-width: 1399px) {
  .poster__details { min-height: 76px; }
  .poster__tix {
    align-self: flex-end;
    font-size: 12px !important;
    padding: 10px 14px !important;
  }
}
```

- [ ] **Step 7: Run the focused contract tests and verify GREEN**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_routing.py -v`

Expected: all routing tests PASS, including ten Ticketscloud triggers and five shared primary-button classes.

- [ ] **Step 8: Commit the correction**

```bash
git add templates/home.html tests/test_routing.py
git commit -m "fix: center responsive concert card layout"
```

---

### Task 2: Regression and responsive review

**Files:**
- Verify: `templates/home.html`
- Verify: `tests/test_routing.py`

**Interfaces:**
- Consumes: the responsive stage and shared button classes from Task 1.
- Produces: verification evidence that desktop composition changed without breaking Ticketscloud or mobile hotspots.

- [ ] **Step 1: Verify the wide-screen composition**

At a viewport at least `1400px` wide, confirm the eyebrow remains at the top, the five-card row is vertically centered in the remaining section, its edges match the other sections, cards share equal footer height, and every button is aligned to the right immediately below its card details.

- [ ] **Step 2: Verify the intermediate desktop composition**

At widths from `761px` through `1399px`, confirm all five posters remain in one row, no button overflows, and each compact button remains aligned to the lower right of its own stacked footer.

- [ ] **Step 3: Verify mobile remains unchanged**

At `760px` and below, confirm `.poster-grid--desktop` remains hidden and `.tour-poster-mobile` still shows the common poster with five city hotspots.

- [ ] **Step 4: Run the full suite**

Run: `PYTHONPATH=. .venv/bin/pytest -q`

Expected: zero failures.

- [ ] **Step 5: Validate the final diff and widget contract**

Run: `git diff --check` and `git status --short`.

Confirm exactly five desktop elements contain `poster__tix btn btn--fill tc-background-tomato`, all ten triggers still contain `data-tc-utm_source="site"`, and no mobile hotspot class or position changed.
