"""Server-side A/B assignment: random 50/50 on first visit, sticky via cookie.

The variant cookie is intentionally NOT httponly — the frontend reads it (via the
injected data-* attributes) to place the CTA. Source of truth is the server, so
the split is authoritative and cannot be skewed by the client.
"""
from __future__ import annotations

import random
import uuid

SID_COOKIE = "dp_sid"
VARIANT_COOKIE = "dp_variant"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year


def new_session(rng=random.random, uuidfn=lambda: uuid.uuid4().hex):
    """Return (sid, variant) with a fresh id and a fair 50/50 variant."""
    return uuidfn(), ("A" if rng() < 0.5 else "B")


def resolve(request):
    """Return (sid, variant, is_new). Reuses sticky cookies when present and valid."""
    sid = request.cookies.get(SID_COOKIE)
    variant = request.cookies.get(VARIANT_COOKIE)
    if sid and variant in ("A", "B"):
        return sid, variant, False
    sid, variant = new_session()
    return sid, variant, True
