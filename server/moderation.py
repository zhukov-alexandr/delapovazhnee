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
    "o": "о", "p": "р", "t": "т", "x": "х", "y": "у", "n": "п",
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
    # Ambiguous short tokens (сво/зов) only block as a whole name — as substrings
    # they'd hit свобода, зовёт, рубля, etc.
    if any(v in _BANNED_EXACT for v in variants):
        return False
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


# Whole-name only (ambiguous as substrings). Checked against both variants.
# Latin forms included since z/v aren't in the homoglyph fold.
_BANNED_EXACT = {"сво", "зов", "зига", "svo", "zov", "ziga"}

# --- Blocklist: roots/stems matched as substrings of the normalised name (ё is
# already folded to е, so only е-forms are needed). Stems catch derivatives —
# e.g. "залуп" catches залупа/залупка, "пизд" catches пизда/пиздец/распиздяй.
# Extend freely; keep stems specific enough to avoid common words (see the tests
# for the words that must stay allowed). ---
_BANNED = [
    # --- мат: хуй / пизда / ебать / блядь + производные ---
    "хуй", "хуе", "хуи", "хуя", "хуев", "хуил", "хуйн", "хуяр", "хуяк", "хуяц",
    "хует", "хуесос", "хуепл", "хуегл",
    "пизд", "пезд",
    "бляд", "блят", "бляц", "бляж", "бляб", "блях",
    "ебат", "ебал", "ебан", "ебуч", "ебло", "ебар", "ебак", "ебищ", "ебош",
    "ебот", "ебир", "ебис", "ебну", "ебка", "еблан", "оеб", "выеб", "въеб",
    "наеб", "заеб", "доеб", "поеб", "приеб", "проеб", "разъеб", "разеб",
    "съеб", "уеб", "отъеб", "подъеб", "испизд",
    "залуп",
    # --- прочий мат / обсценка ---
    "мудак", "мудил", "мудоз", "мудач", "мудло", "гандон", "гондон",
    "пидор", "пидар", "пидр", "пидер", "педик", "педрил", "педофил",
    "дроч", "минет", "конча", "сперм", "елда", "говно", "говн", "дерьм",
    "срак", "хер", "жоп", "мандавошк", "мандюк", "мандоеб", "долбоеб",
    "шлюх", "сучка", "сучар", "проститут",
    # --- тело / порно ---
    "сиськ", "сисек", "письк", "писюн", "писюль", "писич", "пенис", "вагин",
    "влагал", "анус", "порн", "секс", "дилдо",
    # --- война / политика / оскорбления по нац. признаку ---
    "война", "войну", "войне", "войны", "путин", "путлер", "зеленск", "бандер",
    "азов", "вагнер", "денаци", "нацик", "нацист", "спецопер", "бахмут",
    "донбас", "мариупол", "кацап", "катсап", "хохол", "хохлы", "хохлушк",
    "хохлят", "москал", "ватник", "колорад", "рашка", "рашист", "рашизм",
    "укроп", "лугандон", "даунбас", "пыня", "свидом", "зигхайль", "хайльгитлер",
    "гитлер", "жидовск", "жидоеб", "ниггер", "чурк", "хачи",
    # --- latin / translit (checked on the un-folded variant) ---
    "hui", "huy", "huj", "huil", "huyl", "pizd", "ebat", "ebal", "eban",
    "ebuch", "eblo", "zalup", "blyad", "blyat", "suka", "mudak", "mudil",
    "mudoz", "pidor", "pidar", "gandon", "gondon", "droch", "minet", "govno",
    "govn", "sperm", "penis", "vagina", "porn", "sex", "siski", "pisk",
    "pisyun", "dolboeb", "mudoeb", "zhopa",
    "voyna", "voina", "ukrain", "putin", "putler", "zelensk", "azov", "wagner",
    "bandera", "denaci", "kacap", "katsap", "hohol", "khokhol", "hohly",
    "moskal", "vatnik", "rashka", "rashist", "kolorad", "hitler", "nigger",
    "nigga",
]
