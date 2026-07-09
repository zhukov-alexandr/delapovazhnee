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


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta (Numerical Recipes betacf)."""
    MAXIT, EPS, FPMIN = 300, 1e-14, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < EPS:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b) — stdlib-only, deterministic."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = exp(a * log(x) + b * log(1.0 - x) - _log_beta(a, b))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def welch_t_test(n_a: int, x_a: int, n_b: int, x_b: int):
    """Welch's two-sample t-test on the per-session conversion (0/1) samples.

    Each session is a Bernoulli trial (converted or not); the test compares the
    two conversion means. Returns {"t", "df", "p"} (p two-sided) or None when it
    can't be computed (a group has <2 sessions, or neither group has any variance).
    """
    if n_a < 2 or n_b < 2:
        return None
    pa, pb = x_a / n_a, x_b / n_b
    va = pa * (1.0 - pa) * n_a / (n_a - 1)   # sample variance of a Bernoulli sample
    vb = pb * (1.0 - pb) * n_b / (n_b - 1)
    se2 = va / n_a + vb / n_b
    if se2 <= 0.0:
        return None
    t = (pa - pb) / (se2 ** 0.5)
    da = (va / n_a) ** 2 / (n_a - 1)
    db = (vb / n_b) ** 2 / (n_b - 1)
    df = se2 * se2 / (da + db) if (da + db) > 0 else float(n_a + n_b - 2)
    p = _betai(df / 2.0, 0.5, df / (df + t * t))   # two-sided p for Student's t
    return {"t": t, "df": df, "p": min(1.0, max(0.0, p))}


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
          SUM(event_type='cta_click'    AND json_extract(meta,'$.src')='life_lost') AS cta_click_ingame,
          SUM(event_type='presave_done' AND json_extract(meta,'$.src')='life_lost') AS presave_ingame,
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


def _presave_variant_stats(conn, v: str) -> dict:
    row = conn.execute(
        """
        SELECT
          COUNT(DISTINCT session_id) AS sessions,
          COUNT(DISTINCT CASE WHEN event_type='cta_view'  THEN session_id END) AS cta_view_sessions,
          COUNT(DISTINCT CASE WHEN event_type='cta_click' THEN session_id END) AS cta_click_sessions,
          COUNT(DISTINCT CASE WHEN event_type='streaming_click' THEN session_id END) AS streaming_click_sessions,
          COUNT(DISTINCT CASE WHEN event_type='presave_done' THEN session_id END) AS presave_done_sessions,
          SUM(event_type='presave_done')                               AS presave_done_total,
          SUM(event_type='cta_click'    AND json_extract(meta,'$.src')='life_lost') AS cta_click_ingame,
          SUM(event_type='presave_done' AND json_extract(meta,'$.src')='life_lost') AS presave_ingame
        FROM events WHERE variant=?
        """, (v,)).fetchone()
    d = {k: (row[k] or 0) for k in row.keys()}
    service_rows = conn.execute(
        """
        SELECT json_extract(meta,'$.service') AS service, COUNT(*) AS n
        FROM events WHERE variant=? AND event_type='presave_done'
        GROUP BY service
        """, (v,)).fetchall()
    d["services"] = {r["service"]: r["n"] for r in service_rows if r["service"]}
    views = d["cta_view_sessions"]
    d["cvr"] = (d["presave_done_sessions"] / views) if views else 0.0
    return d


def compute_presave_dashboard(conn) -> dict:
    a = _presave_variant_stats(conn, "A")
    b = _presave_variant_stats(conn, "B")
    enough = a["cta_view_sessions"] > 0 and b["cta_view_sessions"] > 0
    prob_b = fisher_p = None
    if enough:
        prob_b = prob_b_beats_a(a["presave_done_sessions"], a["cta_view_sessions"],
                                b["presave_done_sessions"], b["cta_view_sessions"])
        na = max(0, a["cta_view_sessions"] - a["presave_done_sessions"])
        nb = max(0, b["cta_view_sessions"] - b["presave_done_sessions"])
        fisher_p = fisher_exact_two_sided(a["presave_done_sessions"], na,
                                          b["presave_done_sessions"], nb)
    t_test = None
    if enough:
        t_test = welch_t_test(a["cta_view_sessions"], a["presave_done_sessions"],
                              b["cta_view_sessions"], b["presave_done_sessions"])
    leader = None
    if a["cvr"] != b["cvr"]:
        leader = "A" if a["cvr"] > b["cvr"] else "B"
    return {
        "variants": {"A": a, "B": b},
        "leader": leader,
        "prob_b_beats_a": prob_b,   # None until both variants have CTA views
        "fisher_p": fisher_p,
        "t_test": t_test,
        "enough_data": enough,
    }


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
    t_test = None
    if enough:
        t_test = welch_t_test(a["cta_view_sessions"], a["cta_click_sessions"],
                              b["cta_view_sessions"], b["cta_click_sessions"])
    leader = None
    if a["cvr"] != b["cvr"]:
        leader = "A" if a["cvr"] > b["cvr"] else "B"
    return {
        "variants": {"A": a, "B": b},
        "daily": _daily(conn),
        "leader": leader,
        "prob_b_beats_a": prob_b,   # None until both variants have CTA views
        "fisher_p": fisher_p,
        "t_test": t_test,
        "enough_data": enough,
    }


# --- Leaderboard analytics (scores table) ---------------------------------
# Character index -> display name (matches the game's picker order).
CHAR_NAMES = ["Кирилл", "Никита", "Саша", "Костя"]


def _median(xs: list) -> float:
    if not xs:
        return 0
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _fmt_time(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def _histogram(values: list, bins: int, label_fmt) -> list:
    """Equal-width histogram → list of {label, count, pct} (pct is bar height
    relative to the tallest bin, so bars are readable regardless of counts)."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [{"label": label_fmt(lo, hi), "count": len(values), "pct": 100}]
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = int((v - lo) / width)
        if idx >= bins:
            idx = bins - 1
        counts[idx] += 1
    peak = max(counts) or 1
    out = []
    for i, c in enumerate(counts):
        blo, bhi = lo + i * width, lo + (i + 1) * width
        out.append({"label": label_fmt(blo, bhi), "count": c, "pct": round(c / peak * 100)})
    return out


def _char_name(ci: int):
    return CHAR_NAMES[ci] if 0 <= ci < len(CHAR_NAMES) else "—"


def compute_scores_dashboard(conn, character: int | None = None) -> dict:
    """Full leaderboard (optionally filtered by character 0-3) + summary stats,
    score/time distributions, and a per-character comparison for the admin page."""
    if character is None:
        rows = conn.execute(
            "SELECT id, name, score, character, time_ms, ts FROM scores "
            "ORDER BY score DESC, id ASC LIMIT 2000"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name, score, character, time_ms, ts FROM scores WHERE character=? "
            "ORDER BY score DESC, id ASC LIMIT 2000",
            (character,),
        ).fetchall()

    lb = [{
        "id": r["id"],
        "rank": i + 1,
        "name": r["name"],
        "score": r["score"],
        "char_name": _char_name(r["character"]),
        "time_str": _fmt_time((r["time_ms"] or 0) / 1000) if r["time_ms"] else "—",
        "date": (r["ts"] or "")[:10],
    } for i, r in enumerate(rows)]

    scores = [r["score"] for r in rows]
    # Play time excludes legacy 0-time rows (saved before time tracking) so the
    # time stats aren't skewed by a pile of zeros.
    times = [(r["time_ms"] or 0) / 1000 for r in rows if r["time_ms"]]

    score_stats = {
        "min": min(scores) if scores else 0,
        "max": max(scores) if scores else 0,
        "mean": round(sum(scores) / len(scores), 1) if scores else 0,
        "median": round(_median(scores), 1),
        "hist": _histogram(scores, 10, lambda lo, hi: f"{round(lo)}–{round(hi)}"),
    }
    time_stats = {
        "mean": _fmt_time(sum(times) / len(times)) if times else "—",
        "median": _fmt_time(_median(times)) if times else "—",
        "max": _fmt_time(max(times)) if times else "—",
        "with_time": len(times),
        "hist": _histogram(times, 10, lambda lo, hi: f"{_fmt_time(lo)}–{_fmt_time(hi)}"),
    }

    # Per-character comparison — always over the WHOLE table (ignores the filter)
    # so you can compare heroes side by side.
    per = conn.execute(
        "SELECT character AS c, COUNT(*) AS n, AVG(score) AS avg_s, MAX(score) AS best, "
        "AVG(CASE WHEN time_ms>0 THEN time_ms END) AS avg_t FROM scores GROUP BY character"
    ).fetchall()
    per_map = {r["c"]: r for r in per}
    per_char = []
    for idx, nm in enumerate(CHAR_NAMES):
        r = per_map.get(idx)
        per_char.append({
            "idx": idx,
            "name": nm,
            "count": r["n"] if r else 0,
            "avg_score": round(r["avg_s"], 1) if r and r["avg_s"] is not None else 0,
            "best": r["best"] if r else 0,
            "avg_time": _fmt_time((r["avg_t"] or 0) / 1000) if r and r["avg_t"] else "—",
        })
    legacy = per_map.get(-1)

    return {
        "character": character,
        "char_name": _char_name(character) if character is not None else None,
        "total": len(rows),
        "rows": lb,
        "score": score_stats,
        "time": time_stats,
        "per_char": per_char,
        "legacy_count": legacy["n"] if legacy else 0,
    }
