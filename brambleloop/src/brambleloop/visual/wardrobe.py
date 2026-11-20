"""Laura's wardrobe: complete outfits, how alike two outfits are, and the reference outfit.

This is the owner's wardrobe-diversity fix (2026-10-19). FLUX kept carrying the beige trousers
and the ivory top over from the canonical body references. Three rules follow from that:

* **The reference outfit is never an outfit.** The clothes in the canonical torso and
  full-length references (`REFERENCE_OUTFIT`) fix Laura's anatomy, not her wardrobe. The
  selector treats that outfit as already used. The prompt replaces it explicitly
  (`creative.flux_prompt` identity v2 plus `REFERENCE_CLOTHING_NEGATIVES`).
* **Distinct means distinct as a whole.** `similarity` compares two complete outfits slot by
  slot on garment category, colour and distinctive features. The weights put the trousers
  and the footwear above the top, so changing only the shirt while keeping the same
  distinctive trousers and shoes scores at or above `MAX_SIMILARITY` and is rejected
  (WARDROBE_REPETITION).
* **No colour or category is banned outright.** Two listings may both use jeans, or both use
  black, as long as the complete outfits differ.

Everything here is deterministic text analysis of declared outfits. Whether an *image* shows
the declared outfit is a vision judgement (`outfit_consistency`), and it stays UNKNOWN until
the vision judge is funded.
"""
from __future__ import annotations

import re

SLOTS = ("top_or_dress", "lower", "shoes", "outerwear", "accessories")
# The lower garment and the footwear carry most of an outfit's identity in a seated lifestyle
# frame. A top-only change is (0.30 + 0.20 + 0.15 + 0.10) = 0.75 similar when the rest is
# identical, which is above the bar.
WEIGHTS = {"top_or_dress": 0.25, "lower": 0.30, "shoes": 0.20, "outerwear": 0.15,
           "accessories": 0.10}
MAX_SIMILARITY = 0.60

REFERENCE_OUTFIT = {"top_or_dress": "ivory/cream top", "lower": "beige trousers",
                    "shoes": "tan sandals", "outerwear": "none", "accessories": "none"}
REFERENCE_CLOTHING_NEGATIVES = (
    "the beige trousers from the reference images", "the ivory or cream top from the "
    "reference images", "the tan sandals from the reference images", "any garment copied "
    "from the canonical reference images")

_CATEGORIES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "top_or_dress": (("dress", ("dress", "pinafore")), ("cardigan", ("cardigan",)),
                     ("turtleneck", ("turtleneck", "roll-neck")),
                     ("jumper", ("jumper", "sweater", "pullover", "knit crew")),
                     ("shirt", ("shirt", "chambray", "flannel")), ("blouse", ("blouse",)),
                     ("tee", ("tee", "t-shirt")), ("top", ("top", "camisole", "henley"))),
    "lower": (("jeans", ("jeans", "denim trousers")), ("skirt", ("skirt",)),
              ("tailored_trousers", ("tailored", "wool trousers", "slacks", "pleated trousers")),
              ("casual_trousers", ("trousers", "chinos", "corduroy", "cargo", "pants")),
              ("leggings", ("leggings",))),
    "shoes": (("boots", ("boot",)), ("loafers", ("loafer",)), ("sneakers", ("sneaker", "trainer")),
              ("sandals", ("sandal",)), ("flats", ("ballet", "flats", "mary jane")),
              ("slippers", ("slipper", "house socks")), ("clogs", ("clog",))),
    "outerwear": (("coat", ("coat",)), ("jacket", ("jacket",)), ("blazer", ("blazer",)),
                  ("vest", ("vest", "gilet")), ("shawl", ("shawl", "wrap", "poncho"))),
    "accessories": (("earrings", ("hoop", "stud", "earring")),
                    ("necklace", ("necklace", "chain", "pendant")), ("watch", ("watch",)),
                    ("hair", ("barrette", "headband")), ("ring", ("ring",)),
                    ("belt", ("belt",)), ("bag", ("bag", "tote"))),
}
_COLOUR_FAMILY = {
    "ivory": "light", "cream": "light", "white": "light", "oatmeal": "light", "stone": "light",
    "beige": "light", "ecru": "light", "tan": "warm_brown", "camel": "warm_brown",
    "brown": "warm_brown", "rust": "warm_brown", "cognac": "warm_brown", "black": "dark",
    "charcoal": "dark", "navy": "dark", "indigo": "denim", "denim": "denim", "blue": "blue",
    "chambray": "blue", "grey": "grey", "gray": "grey", "heather": "grey", "sage": "green",
    "olive": "green", "green": "green", "forest": "green", "red": "red", "burgundy": "red",
    "wine": "red", "rose": "pink", "pink": "pink", "blush": "pink", "mustard": "yellow",
    "yellow": "yellow", "gold": "metal", "silver": "metal", "lilac": "purple", "plum": "purple",
}
_FEATURES = ("wide-leg", "straight-leg", "skinny", "cropped", "midi", "maxi", "mini",
             "pleated", "cable-knit", "ribbed", "fitted", "oversized", "ankle", "knee-high",
             "leather", "wool", "linen", "corduroy", "chunky", "quilted", "light-wash",
             "dark-wash", "long-sleeve", "short-sleeve", "a-line", "wrap", "tailored", "suede")
_NONE = {"", "none", "no", "n/a"}


def _words(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9/ -]", " ", str(text or "").lower()) + " "


def parse_garment(slot: str, text: str) -> dict:
    t = _words(text)
    if t.strip() in _NONE:
        return {"text": "", "category": "none", "colours": [], "features": []}
    cat = next((c for c, keys in _CATEGORIES[slot] if any(k in t for k in keys)), "other")
    colours = sorted({c for c in _COLOUR_FAMILY if re.search(rf"[ /-]{c}[ /-]", t)})
    feats = sorted({f for f in _FEATURES if f in t})
    return {"text": str(text).strip(), "category": cat, "colours": colours, "features": feats}


def split_outfit_text(text: str) -> dict:
    """A free-text outfit ("brown top, cream trousers, tan boots, gold necklace") as slots.
    Each comma part goes to the first slot whose garment category it names; unmatched parts
    join the accessories. Used for owner-manual history, never to invent a garment."""
    out = {s: [] for s in SLOTS}
    for part in [p.strip() for p in re.split(r",| and ", str(text or "")) if p.strip()]:
        slot = next((s for s in ("lower", "shoes", "outerwear", "top_or_dress", "accessories")
                     if parse_garment(s, part)["category"] not in ("other", "none")),
                    "accessories")
        out[slot].append(part)
    return {s: ", ".join(v) if v else ("none" if s in ("outerwear", "accessories") else "")
            for s, v in out.items()}


def parse_outfit(garments: dict | None) -> dict:
    g = garments or {}
    return {s: parse_garment(s, g.get(s) or "") for s in SLOTS}


def _colour_score(a: list, b: list) -> float:
    if not a and not b:
        return 1.0
    if set(a) & set(b):
        return 1.0
    if {_COLOUR_FAMILY[c] for c in a} & {_COLOUR_FAMILY[c] for c in b}:
        return 0.6
    return 0.0


def slot_similarity(a: dict, b: dict) -> float:
    if a["category"] == "none" and b["category"] == "none":
        return 1.0
    if (a["category"] == "none") != (b["category"] == "none"):
        return 0.0
    cat = 1.0 if a["category"] == b["category"] else 0.0
    fa, fb = set(a["features"]), set(b["features"])
    feat = 1.0 if not fa and not fb else len(fa & fb) / len(fa | fb)
    return round(0.5 * cat + 0.3 * _colour_score(a["colours"], b["colours"]) + 0.2 * feat, 4)


def similarity(a: dict | None, b: dict | None) -> dict:
    """Weighted complete-outfit similarity in [0, 1], with the per-slot breakdown."""
    pa, pb = parse_outfit(a), parse_outfit(b)
    per = {s: slot_similarity(pa[s], pb[s]) for s in SLOTS}
    return {"score": round(sum(WEIGHTS[s] * per[s] for s in SLOTS), 4), "slots": per}


def too_similar(candidate: dict, others: list[tuple[str, dict]]) -> dict | None:
    """The first prior outfit `candidate` is not distinct from (`score >= MAX_SIMILARITY`)."""
    for name, other in others:
        sim = similarity(candidate, other)
        if sim["score"] >= MAX_SIMILARITY:
            return {"against": name, **sim}
    return None


# ---- the catalogue the selector draws from -------------------------------------------------
# (text, seasons, formality). Seasons: "any", "winter", "summer". Every garment fits the brand
# aesthetic (natural fibres, quiet colour); variety covers jeans, skirts, dresses, tailored
# and casual trousers, and the full range of footwear and outerwear.
TOPS = (("black fitted long-sleeve top", "any", "casual"),
        ("sage-green cable-knit cardigan over a white tee", "any", "casual"),
        ("oatmeal chunky jumper", "winter", "casual"),
        ("chambray button-down shirt", "any", "smart"),
        ("rust ribbed turtleneck", "winter", "smart"),
        ("navy striped breton tee", "summer", "casual"),
        ("heather-grey fisherman jumper", "winter", "casual"),
        ("burgundy wrap blouse", "any", "smart"),
        ("charcoal knit midi dress", "winter", "smart"),
        ("olive linen shirt dress", "summer", "casual"),
        ("dusty-rose knit cardigan over a camisole", "any", "casual"),
        ("mustard crew-neck jumper", "winter", "casual"))
LOWERS = (("dark indigo straight-leg jeans", "any", "casual"),
          ("light-wash wide-leg jeans", "summer", "casual"),
          ("black pleated midi skirt", "any", "smart"),
          ("camel corduroy a-line skirt", "winter", "casual"),
          ("charcoal tailored wool trousers", "winter", "smart"),
          ("navy tailored cropped trousers", "any", "smart"),
          ("olive cargo trousers", "any", "casual"),
          ("rust corduroy wide-leg trousers", "winter", "casual"),
          ("denim midi skirt", "any", "casual"))
SHOES = (("brown leather ankle boots", "winter", "any"),
         ("black leather loafers", "any", "smart"),
         ("white canvas sneakers", "summer", "casual"),
         ("grey wool slippers", "winter", "casual"),
         ("burgundy suede ballet flats", "any", "smart"),
         ("black knee-high boots", "winter", "smart"),
         ("navy sneakers", "any", "casual"),
         ("olive suede clogs", "any", "casual"))
OUTERWEAR = (("none", "any", "any"), ("camel wool coat", "winter", "smart"),
             ("quilted olive vest", "winter", "casual"), ("denim jacket", "summer", "casual"),
             ("oatmeal shawl wrap", "any", "casual"), ("navy wool blazer", "any", "smart"))
ACCESSORIES = (("small gold hoops", "any", "any"), ("silver stud earrings", "any", "any"),
               ("leather-strap watch", "any", "any"), ("thin gold chain necklace", "any", "any"),
               ("tortoiseshell barrette", "any", "any"), ("silver ring", "any", "any"))
CATALOGUE = {"top_or_dress": TOPS, "lower": LOWERS, "shoes": SHOES, "outerwear": OUTERWEAR,
             "accessories": ACCESSORIES}
