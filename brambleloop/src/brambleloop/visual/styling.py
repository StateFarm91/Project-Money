"""Automatic styling and scene direction (D-W4-LAURA-FLUX3 §5).

The owner does not choose. Creative chooses a complete outfit and a photoshoot concept from
these inputs:

* product type, colours, materials, use and season;
* target customer;
* brand aesthetic;
* the outfits and settings other listings already use.

The selector is deterministic: the same inputs and the same used set always give the same
choice, so a re-run of a workflow stage never picks a second outfit. No model is called and
nothing is generated here.

* **Complete outfit** (§4): a top or dress, a lower garment (none with a dress), shoes,
  outerwear and accessories. The outfit's colours are chosen so they do not compete with the
  product's colours.
* **Uniqueness** (§4): a complete outfit whose signature (`outfits.signature`) is already
  used by another listing is skipped. A setting already used by another listing is avoided
  while an unused one fits.
* **Natural direction** (§5): every concept names a believable everyday action, a real room
  and natural light, never a studio pose. The pose list excludes generic catalogue poses.
"""
from __future__ import annotations

import hashlib

STYLING_VERSION = "styling/1"
BRAND_AESTHETIC = "warm, quiet Scandinavian-cottage: natural light, natural fibres, unhurried"

TOPS = ("cream cable-knit cardigan over a white tee", "sage-green cardigan over a cream tee",
        "oatmeal crew-neck jumper", "soft blue chambray shirt", "rust ribbed turtleneck",
        "ivory linen blouse", "heather-grey fisherman jumper", "dusty-rose knit cardigan")
DRESSES = ("charcoal knit midi dress", "olive corduroy pinafore over a cream tee")
LOWERS = ("dark straight-leg jeans", "camel wide-leg trousers", "light-wash jeans",
          "charcoal wool trousers", "brown corduroy trousers")
SHOES = ("tan leather loafers", "grey wool slippers", "white canvas sneakers",
         "brown ankle boots", "cream knit house socks")
OUTERWEAR = ("none", "camel wool coat", "quilted olive vest", "none", "oatmeal shawl wrap")
ACCESSORIES = ("small gold hoops", "thin gold chain", "tortoiseshell hair clip",
               "silver stud earrings", "leather-strap watch")
# Garment colour words, used to keep the outfit from competing with the product's colours.
_COLOUR_WORDS = ("cream", "sage", "oatmeal", "blue", "rust", "ivory", "grey", "rose", "charcoal",
                 "olive", "camel", "brown", "white", "tan", "gold", "silver")

SETTINGS: dict[str, tuple[str, ...]] = {
    "baby": ("sunlit nursery with a wooden cot", "living-room sofa by a window",
             "rocking chair beside a nursery shelf"),
    "blanket": ("living-room sofa by a window", "reading nook with a wool rug",
                "bedroom with a linen-covered bed"),
    "basket": ("hallway console by the front door", "bathroom shelf with folded towels",
               "nursery shelf with soft toys"),
    "coaster": ("kitchen table at breakfast", "coffee table beside a sofa"),
    "placemat": ("dining table set for two", "kitchen table at breakfast"),
    "ornament": ("Christmas tree in a living room", "windowsill with winter light"),
}
ACTIONS: dict[str, str] = {
    "baby": "folding the blanket over her arm", "blanket": "drawing the throw over her lap",
    "basket": "putting things into the basket", "coaster": "setting a mug down beside a coaster",
    "placemat": "laying a plate onto a placemat", "ornament": "hanging an ornament",
}
SEASONAL = {"winter": ("camel wool coat", "oatmeal shawl wrap")}


def _rank(key: str, items) -> list:
    """A deterministic order over items, seeded by the listing key."""
    return sorted(items, key=lambda x: hashlib.sha256(f"{key}|{x}".encode()).hexdigest())


def _clashes(garment: str, product_colours: set[str]) -> bool:
    words = {w for w in _COLOUR_WORDS if w in garment.lower()}
    return bool(words & product_colours)


def select(listing: str, *, category: str, product_colours=(), season: str = "",
           target_customer: str = "", materials=(), use: str = "",
           used_signatures=(), used_settings=()) -> dict:
    """The complete outfit and photoshoot concept for one listing. Deterministic."""
    from .outfits import signature

    pc = {str(c).lower() for c in product_colours}
    pc |= {w for c in pc for w in _COLOUR_WORDS if w in c}
    used_sig, used_set = set(used_signatures), set(used_settings)
    outer_pool = SEASONAL.get(season, OUTERWEAR)
    chosen = None
    for top in _rank(listing + "|top", TOPS + DRESSES):
        if _clashes(top, pc):
            continue
        is_dress = top in DRESSES
        for lower in ([""] if is_dress else _rank(listing + "|lower", LOWERS)):
            for shoes in _rank(listing + "|shoes", SHOES):
                garments = {"top_or_dress": top, "lower": lower, "shoes": shoes,
                            "outerwear": _rank(listing + "|outer", outer_pool)[0],
                            "accessories": _rank(listing + "|acc", ACCESSORIES)[0]}
                colours = sorted({w for g in garments.values()
                                  for w in _COLOUR_WORDS if w in g})
                if signature(garments) not in used_sig:
                    chosen = (garments, colours)
                    break
            if chosen:
                break
        if chosen:
            break
    if chosen is None:
        return {"outfit": None, "why": "every complete outfit in the wardrobe is used or clashes; "
                                       "the wardrobe needs new garments"}
    garments, colours = chosen
    settings = SETTINGS.get(category, ("living room by a window",))
    fresh = [s for s in _rank(listing + "|set", settings) if s not in used_set]
    setting = (fresh or _rank(listing + "|set", settings))[0]
    oid = "auto-" + hashlib.sha256(f"{listing}|{signature(garments)}".encode()).hexdigest()[:10]
    return {
        "styling_version": STYLING_VERSION,
        "outfit": {"outfit_id": oid, "garments": garments, "colours": colours,
                   "description": "; ".join(v for v in garments.values() if v and v != "none")},
        "concept": {"setting": setting, "setting_reused": not fresh,
                    "action": ACTIONS.get(category, "using the finished piece"),
                    "light": "natural window light", "season": season or "any",
                    "target_customer": target_customer or "a maker who loves a calm home",
                    "aesthetic": BRAND_AESTHETIC, "materials": list(materials), "use": use,
                    "avoid": ["studio backdrop", "generic catalogue pose", "staring at camera "
                              "while holding the product up", "over-staged props",
                              "hands hidden or merged with the yarn"]},
        "inputs": {"category": category, "product_colours": sorted(pc), "season": season},
    }


def select_for_listing(db, listing: str) -> dict:
    """`select` with the facts read from the listing's certified CIR and the registry."""
    from . import outfits
    from .launch_imagery import _listing_parts

    _cand, cirs, category = _listing_parts(listing)
    cir = cirs[0]
    colours = [getattr(c, "name", str(c)) for c in (cir.colors or {})] if not isinstance(
        cir.colors, dict) else list(cir.colors)
    season = "winter" if any(w in listing for w in ("winter", "nordic", "star")) else ""
    reg = [o for o in outfits.registry(db) if o.get("listing") and o["listing"] != listing]
    used_sig = {outfits.signature(o.get("garments") or {}) for o in reg}
    used_set = {o.get("setting") for o in reg if o.get("setting")}
    return select(listing, category=category, product_colours=colours, season=season,
                  materials=[m.name for m in getattr(cir, "materials", [])],
                  used_signatures=used_sig, used_settings=used_set)
