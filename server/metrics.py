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
          SUM(event_type='presave_done')                               AS presave_done_total
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
    leader = None
    if a["cvr"] != b["cvr"]:
        leader = "A" if a["cvr"] > b["cvr"] else "B"
    return {
        "variants": {"A": a, "B": b},
        "leader": leader,
        "prob_b_beats_a": prob_b,   # None until both variants have CTA views
        "fisher_p": fisher_p,
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
    leader = None
    if a["cvr"] != b["cvr"]:
        leader = "A" if a["cvr"] > b["cvr"] else "B"
    return {
        "variants": {"A": a, "B": b},
        "daily": _daily(conn),
        "leader": leader,
        "prob_b_beats_a": prob_b,   # None until both variants have CTA views
        "fisher_p": fisher_p,
        "enough_data": enough,
    }
