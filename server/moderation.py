"""Leaderboard name moderation.

Two rules, enforced authoritatively on the server (the input field mirrors the
first for UX, but this is the source of truth):

1. Allowed characters only: unicode letters, digits, underscore, hyphen. No
   spaces, punctuation, or emoji — this also removes the easiest filter-evasion
   (spacing letters out, e.g. "х у й").
2. No profanity / obscene / war-related terms. Checked against a blocklist of
   roots after light normalisation (lowercasing, ё→е, stripping separators and
   repeated letters, and folding latin/leet homoglyphs to Cyrillic) so simple
   dodges — "х_у_й", "хуууй", "xyй", "6лядь" — are still caught.

The blocklists are plain lists at the bottom: extend them freely.
"""
from __future__ import annotations

import re

MAX_NAME_LEN = 24

# Rule 1: allowed characters. \w is unicode (matches Cyrillic) and includes "_";
# we add "-". Anything else (space, punctuation, emoji, …) makes the name invalid.
_ALLOWED_RE = re.compile(r"[\w-]+", re.UNICODE)


def has_allowed_chars(name: str) -> bool:
    return bool(name) and _ALLOWED_RE.fullmatch(name) is not None


# Rule 2 normalisation.
# Fold latin homoglyphs + leetspeak to their Cyrillic lookalikes so mixed-script
# and digit-substituted spellings collapse onto the Cyrillic roots below.
_FOLD = str.maketrans({
    "a": "а", "b": "в", "c": "с", "e": "е", "h": "н", "k": "к", "m": "м",
    "o": "о", "p": "р", "t": "т", "x": "х", "y": "у", "n": "п", "u": "и",
    "3": "е", "0": "о", "4": "ч", "6": "б", "1": "и", "5": "с", "8": "в",
    "@": "а", "$": "с",
})


def _base(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[\W_]+", "", s, flags=re.UNICODE)  # drop separators incl. _ and -
    s = re.sub(r"(.)\1{2,}", r"\1", s)              # collapse 3+ repeats
    return s


def _variants(name: str) -> tuple[str, str]:
    b = _base(name)
    return b, b.translate(_FOLD)


def is_clean(name: str) -> bool:
    variants = _variants(name)
    return not any(bad in v for v in variants for bad in _BANNED)


def check_name(name: str) -> tuple[bool, str]:
    """Return (ok, reason). reason is a short RU message for the client.

    Empty is OK (the caller substitutes «Аноним»)."""
    name = (name or "").strip()
    if not name:
        return True, ""
    if len(name) > MAX_NAME_LEN:
        return False, f"Имя не длиннее {MAX_NAME_LEN} символов"
    if not has_allowed_chars(name):
        return False, "Только буквы, цифры, _ и -"
    if not is_clean(name):
        return False, "Недопустимое имя"
    return True, ""


# --- Blocklist (roots; matched as substrings of the normalised name). Extend. ---
_BANNED = [
    # --- мат ---
    "хуй", "хуе", "хуи", "хуя", "хуё", "хует", "хуев", "пизд", "пезд", "ебан",
    "ебат", "ебал", "ебуч", "ебло", "ебан", "выеб", "наеб", "уеб", "заеб",
    "бляд", "блят", "бляц", "залуп", "гандон", "пидор", "пидар", "пидр",
    "педик", "манда", "мудак", "мудил", "мудо", "долбоеб", "говно", "говн",
    "срак", "дерьм", "елда", "конча", "кончи", "дроч", "минет", "хер",
    # --- обсценка / тело ---
    "сиськ", "сисек", "письк", "писюн", "писич", "пенис", "вагин", "влагал",
    "анус", "порн", "секс", "залупа",
    # --- война / украина ---
    "война", "войну", "войне", "войны", "украин", "путин", "зеленск", "бандер",
    "азов", "вагнер", "денаци", "спецопер", "бахмут", "донбас", "мариупол",
    # --- latin spellings (checked before folding) ---
    "hui", "huy", "huj", "pizd", "ebat", "ebal", "eban", "blyad", "blyat",
    "suka", "mudak", "pidor", "zalupa", "gandon", "siski", "pisk", "penis",
    "vagina", "sex", "porn", "voyna", "voina", "ukrain", "putin", "zelensk",
    "azov", "wagner", "bandera",
]
