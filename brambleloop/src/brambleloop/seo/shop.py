"""Shop-level SEO: recommendations for lane C's store copy, and a checker for whatever C ships.

Lane G does not own store copy (lane C does: `store_foundation.copy_v2`). This module only
(1) states what shop-level search needs, as a recommendation C may take or leave, and
(2) checks a piece of shop copy against the shop-level constraints and search rules, so the
integrator/certifier can run it over C's final text. It never edits C's files.

What shop-level text can and cannot do for search is kept honest:

- Listing search on Etsy matches *listings*. Whether the shop title / announcement / About are
  read by Etsy's listing search is not documented anywhere this environment could read
  (UNVERIFIED either way). What is reasonable to claim: the shop title is the shop page's
  heading (VERIFIED: updateShop `title` -- "A brief heading string for the shop's main page")
  and is what external search engines and shoppers who land on the shop read first. So the
  recommendation is: name the category in buyer words once, readably, and never as a
  keyword list. That serves people first; any search effect is a bonus, not a promise.
- Sections are navigation. Their names should be the words a buyer would click.
"""
from __future__ import annotations

import re
from collections import Counter

from . import constraints as C

CATEGORY_WORDS = ("crochet", "pattern")      # the category in the words a buyer types
TECH_WORDS = re.compile(r"\b(ai|a\.i\.|compiler|compiled|machine[- ]checked|algorithm|"
                        r"agent|agents|llm|model provider|cir|deterministic|software)\b", re.I)

RECOMMENDATION = {
    "for": "lane C (store_foundation.copy_v2) -- recommendation only; C owns final copy",
    "shop_title": {
        "goal": "say what the shop sells in buyer words, once, warmly",
        "options": [
            "Modern crochet patterns for home and nursery",
            "Crochet patterns for a calm, cosy home",
            "Thoughtful crochet patterns for home and baby",
        ],
        "rules": ["contains 'crochet' and 'pattern(s)'", "no repeated word",
                  "no technology words (AI, compiler, agent...)",
                  f"<= {C.get('shop_title_max_chars').value} characters "
                  f"({C.get('shop_title_max_chars').status}; confirm in Shop Manager)"],
    },
    "announcement": {
        "goal": "first sentence names what a buyer can make and what they get",
        "example": ("Crochet patterns for baskets, blankets and coasters you will love "
                    "making, with clear written instructions and charts in US and UK terms."),
        "rules": ["first sentence carries the category words",
                  "no keyword list; one or two sentences",
                  "no discount claims unless a real sale exists"],
    },
    "about": {
        "goal": "story first (Laura, taste, why these patterns); the careful-checking "
                "process later as a proof point in customer-value words",
        "rules": ["names the category in buyer words at least once",
                  "no fabricated human biography or physical acts",
                  "proportionate disclosure where Etsy requires it (lanes C/I own wording)"],
    },
    "sections": {
        "goal": "show only populated sections at launch; names are buyer words",
        "launch0": [
            {"name": "Baby & Nursery", "products": ["cloudline-baby-blanket",
                                                    "nursery-nesting-baskets"]},
            {"name": "Home & Table", "products": ["hexagon-coaster-set"]},
        ],
        "alternative": "with only three listings, no sections at all is also acceptable; "
                       "add sections when a second product per section exists",
        "rules": [f"<= {C.get('section_name_max_chars').value} characters per name "
                  f"({C.get('section_name_max_chars').status})",
                  f"<= {C.get('sections_max_count').value} sections "
                  f"({C.get('sections_max_count').status})"],
        "note": ("the existing brand.storefront.SECTIONS map baskets to Home; the "
                 "nursery qualifier on the basket product makes Baby & Nursery the truer "
                 "shelf -- C/B decide"),
    },
    "listing_titles": "see seo.strategy.TITLES (buyer-first, object + 'crochet pattern' "
                      "first)",
}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _stem(w: str) -> str:
    from .facts import stem

    return stem(w)


def check_shop_copy(copy: dict) -> list[dict]:
    """Findings over a dict with any of: shop_title, announcement, about, sections (names).

    severity: fail (a VERIFIED rule or a truth rule) | warn (an UNVERIFIED limit or a
    search-quality rule). Never a pass on an unverified limit: it is reported as such.
    """
    out: list[dict] = []

    def f(code, sev, detail):
        out.append({"code": code, "severity": sev, "detail": detail})

    title = copy.get("shop_title") or ""
    if title:
        lim = C.get("shop_title_max_chars")
        if len(title) > lim.value:
            f("SHOP_TITLE_TOO_LONG", "warn" if lim.status != C.VERIFIED else "fail",
              f"{len(title)} > {lim.value} ({lim.status}: {lim.url})")
        stems = {_stem(w) for w in _words(title)}
        missing = [w for w in CATEGORY_WORDS if w not in stems]
        if missing:
            f("SHOP_TITLE_CATEGORY_SILENT", "warn", f"shop title never says {missing}")
        rep = sorted(w for w, n in Counter(_stem(x) for x in _words(title)).items()
                     if n > 1 and len(w) > 3)
        if rep:
            f("SHOP_TITLE_REPEATS", "warn", f"repeats {rep}")
    for field in ("shop_title", "announcement"):
        text = copy.get(field) or ""
        hit = TECH_WORDS.search(text)
        if hit:
            f("TECH_FOREGROUNDED", "warn", f"{field} foregrounds {hit.group(0)!r}; lead with "
                                           f"the crochet, keep process words deeper down")
    ann = copy.get("announcement") or ""
    if ann:
        first = re.split(r"(?<=[.!?])\s", ann.strip(), maxsplit=1)[0]
        if not {"crochet", "pattern"} & {_stem(w) for w in _words(first)}:
            f("ANNOUNCEMENT_CATEGORY_LATE", "warn",
              "the first sentence does not name crochet or patterns")
        words = _words(ann)
        if words and len(set(words)) / len(words) < 0.5:
            f("ANNOUNCEMENT_KEYWORD_LIST", "warn", "reads like a keyword list")
    about = copy.get("about") or ""
    if about and not {"crochet"} <= {_stem(w) for w in _words(about)}:
        f("ABOUT_CATEGORY_SILENT", "warn", "About never says crochet")
    sections = list(copy.get("sections") or [])
    if sections:
        cnt = C.get("sections_max_count")
        if len(sections) > cnt.value:
            f("SECTIONS_TOO_MANY", "warn", f"{len(sections)} > {cnt.value} ({cnt.status})")
        nm = C.get("section_name_max_chars")
        for s in sections:
            if len(s) > nm.value:
                f("SECTION_NAME_TOO_LONG", "warn", f"{s!r}: {len(s)} > {nm.value} "
                                                   f"({nm.status})")
    for field in ("shop_title", "announcement", "about"):
        from ..commerce import seo as seo_mod

        hit = seo_mod._UNSUPPORTABLE.search(copy.get(field) or "")
        if hit:
            f("UNSUPPORTABLE_CLAIM", "fail", f"{field}: {hit.group(0)!r}")
    return out


def lane_c_copy() -> dict | None:
    """C's exported copy, if `store_foundation.copy_v2` exists in this tree; else None.

    Tolerant of absence and of shape: reads attributes/dict keys it recognises only.
    """
    try:
        from ..store_foundation import copy_v2  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - not built / not integrated yet
        return None
    get = getattr(copy_v2, "copy", None) or getattr(copy_v2, "surfaces", None)
    try:
        data = get() if callable(get) else (get or {})
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None

    def pick(*keys):
        for k in keys:
            v = data.get(k)
            if isinstance(v, dict):
                v = v.get("text") or v.get("value")
            if v:
                return v
        return None

    secs = data.get("sections") or []
    names = [s.get("name") if isinstance(s, dict) else str(s) for s in secs]
    return {"shop_title": pick("shop_title", "tagline", "title"),
            "announcement": pick("announcement"), "about": pick("about", "about_story"),
            "sections": [n for n in names if n]}


def review() -> dict:
    """Recommendation + (when C's copy exists) the findings over it."""
    copy = lane_c_copy()
    own = check_shop_copy({"shop_title": RECOMMENDATION["shop_title"]["options"][0],
                           "announcement": RECOMMENDATION["announcement"]["example"],
                           "sections": [s["name"] for s in
                                        RECOMMENDATION["sections"]["launch0"]]})
    return {"recommendation": RECOMMENDATION, "recommendation_findings": own,
            "lane_c_copy": ("absent: store_foundation.copy_v2 not in this tree"
                            if copy is None else copy),
            "lane_c_findings": None if copy is None else check_shop_copy(copy)}
