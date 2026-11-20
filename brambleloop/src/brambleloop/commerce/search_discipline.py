"""Search-language discipline: no typo SEO (F-017) and regional phrases (F-016).

**No typo SEO (F-017).** A deliberate misspelling ("crochte", "patern") is an old SEO trick
Etsy does not reward and a shop's copy should never carry. Our templates are fixed English, so
none are written today; the risk is observed-phrase ingestion (`intent.listing_language`)
bringing one in from somebody else's title. `typos(text)` flags a word that is *not* in the
vocabulary but sits one edit from a vocabulary word of five or more letters -- the shape of a
misspelling rather than of a different word. Plurals and the vocabulary's own regional
spellings are never typos. A word nowhere near the vocabulary (a product's own name) is not
judged: this is a guard against misspellings, not a dictionary of permitted English.

**Regional phrases (F-016).** Two kinds of regional difference, treated differently:

* `SPELLING_VARIANTS` -- the same word spelled two ways (colour/color, cosy/cozy, grey/gray).
  Treated as one word: a second slot for the other spelling is redundant (`redundant_tag`).
  This is the conservative reading of "avoid redundant spelling variants it already
  handles": it costs at most a variant the index does not fold, never a slot spent twice.
* `LEXICAL_VARIANTS` -- different words for one thing (jumper/sweater, toque/beanie,
  nappy/diaper). Etsy cannot fold these, so a listing may
  spend **one** tag slot on a non-normalised regional phrase, and only one
  (`MAX_REGIONAL_SLOTS`), so regional reach never crowds out the product's own phrases.
"""
from __future__ import annotations

import re

SPELLING_VARIANTS: dict[str, str] = {
    "colour": "color", "colours": "colors", "colourful": "colorful", "colourwork": "colorwork",
    "cosy": "cozy", "cosies": "cozies", "grey": "gray", "favourite": "favorite",
    "jewellery": "jewelry", "centre": "center", "mould": "mold", "organise": "organize",
    "personalised": "personalized", "customised": "customized",
}
LEXICAL_VARIANTS: dict[str, str] = {
    "jumper": "sweater", "toque": "beanie", "nappy": "diaper", "dummy": "pacifier",
    "bobble hat": "pom pom hat", "tea towel": "dish towel", "cardi": "cardigan",
}
MAX_REGIONAL_SLOTS = 1

_WORD = re.compile(r"[a-z]+")


def vocabulary() -> frozenset[str]:
    from ..cir import stitches
    from . import intent

    words: set[str] = set(intent.BUYER_QUALIFIERS) | set(intent.MARKETPLACE_FURNITURE)
    words |= set(intent._FACET_WORDS)                      # noqa: SLF001 - the shared table
    for table in (intent.CATEGORY_USE, intent.CATEGORY_OBJECT):
        for k, v in table.items():
            words |= set(_WORD.findall(k.replace("_", " "))) | set(_WORD.findall(v))
    for name in getattr(stitches, "STITCHES", {}) or {}:
        words |= set(_WORD.findall(str(name).lower()))
    for a, b in list(SPELLING_VARIANTS.items()) + list(LEXICAL_VARIANTS.items()):
        words |= set(_WORD.findall(a)) | set(_WORD.findall(b))
    words |= {"chart", "written", "terms", "instructions", "blanket", "granny", "square",
              "amigurumi", "graphghan", "placemat", "coaster", "table", "runner", "wall",
              "hanging", "garland", "stocking", "ornament", "pillow", "basket", "baby",
              "printable", "beginner", "intermediate", "advanced", "worsted", "weight",
              "yarn", "hook", "stitches", "gauge", "sizes", "inches", "tutorial", "summer",
              "christmas", "halloween", "valentine", "easter"}
    return frozenset(w for w in words if w)


def _one_edit(a: str, b: str) -> bool:
    """Damerau-Levenshtein distance exactly one (substitution, insertion, deletion, swap)."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        return (len(diff) == 2 and diff[1] == diff[0] + 1
                and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    s, t = (a, b) if len(a) < len(b) else (b, a)
    i = j = 0
    skipped = False
    while i < len(s) and j < len(t):
        if s[i] != t[j]:
            if skipped:
                return False
            skipped = True
            j += 1
            continue
        i += 1
        j += 1
    return True


def typos(text: str, *, vocab: frozenset[str] | None = None) -> list[tuple[str, str]]:
    """(word, the vocabulary word it misspells) for each likely misspelling in `text`."""
    vocab = vocab or vocabulary()
    out = []
    for w in dict.fromkeys(_WORD.findall((text or "").lower())):
        if len(w) < 4 or w in vocab or w.rstrip("s") in vocab or (w + "s") in vocab:
            continue
        near = next((v for v in sorted(vocab) if len(v) >= 5 and _one_edit(w, v)), None)
        if near and near.rstrip("s") != w.rstrip("s"):
            out.append((w, near))
    return out


def _spelling_key(phrase: str) -> str:
    return " ".join(SPELLING_VARIANTS.get(w, w) for w in phrase.lower().split())


def redundant_tag(phrase: str, chosen: list[str]) -> str | None:
    """The chosen tag this phrase only re-spells (colour/color), or None."""
    key = _spelling_key(phrase)
    for c in chosen:
        if c != phrase and _spelling_key(c) == key:
            return c
    return None


def regional_terms(phrase: str) -> list[str]:
    p = f" {phrase.lower()} "
    return [k for k in LEXICAL_VARIANTS if f" {k} " in p]


def regional_slots_used(chosen: list[str]) -> int:
    return sum(1 for c in chosen if regional_terms(c))
