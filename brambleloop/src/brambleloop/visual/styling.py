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
* **Distinctness** (owner wardrobe fix): a complete outfit too similar to any outfit another
  listing holds (`wardrobe.similarity` >= `MAX_SIMILARITY`) is skipped automatically, and so
  is anything too similar to the canonical references' own clothing
  (`wardrobe.REFERENCE_OUTFIT`). That clothing is treated as already used and is never
  defaulted to. No single colour or garment category is banned. A setting already used by
  another listing is avoided while an unused one fits.
* **Variety:** jeans, skirts, dresses, tailored and casual trousers, and a full range of
  footwear and outerwear (`wardrobe.CATALOGUE`). The choice is filtered by season and ranked
  by the product's formality.
* **Natural direction** (§5): every concept names a believable everyday action, a real room
  and natural light, never a studio pose. The pose list excludes generic catalogue poses.
"""
from __future__ import annotations

import hashlib

STYLING_VERSION = "styling/2"
BRAND_AESTHETIC = "warm, quiet Scandinavian-cottage: natural light, natural fibres, unhurried"

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


def _rank(key: str, items) -> list:
    """A deterministic order over items, seeded by the listing key."""
    return sorted(items, key=lambda x: hashlib.sha256(f"{key}|{x}".encode()).hexdigest())


def _clashes(garment: str, product_colours: set[str]) -> bool:
    from .wardrobe import parse_garment

    return bool(set(parse_garment("top_or_dress", garment)["colours"]) & product_colours)


_FORMALITY = {"placemat": "smart", "coaster": "smart", "ornament": "smart"}


def _pool(slot: str, key: str, season: str, formality: str) -> list[str]:
    from .wardrobe import CATALOGUE

    items = [(t, se, fo) for t, se, fo in CATALOGUE[slot]
             if se == "any" or not season or se == season]
    # Formality is a preference, never a ban: matching items first, the rest after.
    ranked = sorted(items, key=lambda i: (i[2] not in ("any", formality),
                                          hashlib.sha256(f"{key}|{slot}|{i[0]}".encode())
                                          .hexdigest()))
    return [t for t, _se, _fo in ranked]


def select(listing: str, *, category: str, product_colours=(), season: str = "",
           target_customer: str = "", materials=(), use: str = "",
           used_outfits=(), used_settings=()) -> dict:
    """The complete outfit and photoshoot concept for one listing. Deterministic.

    `used_outfits` is [(name, garments)] for every outfit another listing holds. The
    reference outfit (`wardrobe.REFERENCE_OUTFIT`) is always added: it is never chosen, and
    nothing too similar to it is chosen either."""
    from .outfits import signature
    from .wardrobe import REFERENCE_OUTFIT, too_similar

    pc = {str(c).lower() for c in product_colours}
    from .wardrobe import _COLOUR_FAMILY

    pc |= {c for word in list(pc) for c in _COLOUR_FAMILY if c in word}
    used = [("canonical reference outfit", REFERENCE_OUTFIT)] + list(used_outfits)
    used_set = set(used_settings)
    formality = _FORMALITY.get(category, "casual")
    pools = {slot: _pool(slot, listing, season, formality) for slot in
             ("top_or_dress", "lower", "shoes", "outerwear", "accessories")}
    chosen, rejected = None, 0
    for top in pools["top_or_dress"]:
        if _clashes(top, pc):
            continue
        is_dress = "dress" in top or "pinafore" in top
        for lower in ([""] if is_dress else pools["lower"]):
            if lower and _clashes(lower, pc):
                continue
            for shoes in pools["shoes"]:
                garments = {"top_or_dress": top, "lower": lower, "shoes": shoes,
                            "outerwear": pools["outerwear"][0],
                            "accessories": pools["accessories"][0]}
                if too_similar(garments, used) is not None:
                    rejected += 1
                    continue
                chosen = garments
                break
            if chosen:
                break
        if chosen:
            break
    if chosen is None:
        return {"outfit": None, "why": "every complete outfit in the wardrobe is too similar to "
                                       "one already used, or clashes with the product"}
    from .wardrobe import parse_outfit

    colours = sorted({c for g in parse_outfit(chosen).values() for c in g["colours"]})
    settings = SETTINGS.get(category, ("living room by a window",))
    fresh = [x for x in _rank(listing + "|set", settings) if x not in used_set]
    setting = (fresh or _rank(listing + "|set", settings))[0]
    oid = "auto-" + hashlib.sha256(f"{listing}|{signature(chosen)}".encode()).hexdigest()[:10]
    return {
        "styling_version": STYLING_VERSION,
        "outfit": {"outfit_id": oid, "garments": chosen, "colours": colours,
                   "description": "; ".join(v for v in chosen.values() if v and v != "none")},
        "concept": {"setting": setting, "setting_reused": not fresh,
                    "action": ACTIONS.get(category, "using the finished piece"),
                    "light": "natural window light", "season": season or "any",
                    "target_customer": target_customer or "a maker who loves a calm home",
                    "aesthetic": BRAND_AESTHETIC, "formality": formality,
                    "materials": list(materials), "use": use,
                    "avoid": ["studio backdrop", "generic catalogue pose", "staring at camera "
                              "while holding the product up", "over-staged props",
                              "hands hidden or merged with the yarn",
                              "the canonical references' clothing"]},
        "inputs": {"category": category, "product_colours": sorted(pc), "season": season,
                   "outfits_considered_too_similar": rejected},
    }


def select_for_listing(db, listing: str, *, exclude=()) -> dict:
    """`select` with the facts read from the listing's certified CIR and the registry."""
    from . import outfits
    from .launch_imagery import _listing_parts

    _cand, cirs, category = _listing_parts(listing)
    cir = cirs[0]
    colours = [getattr(c, "name", str(c)) for c in (cir.colors or {})] if not isinstance(
        cir.colors, dict) else list(cir.colors)
    season = "winter" if any(w in listing for w in ("winter", "nordic", "star")) else ""
    reg = [o for o in outfits.registry(db) if o.get("listing") and o["listing"] != listing
           and o["outfit_id"] not in set(exclude)]
    used = [(f"{o['outfit_id']} ({o['listing']})", o.get("garments") or {}) for o in reg]
    used += [(f"{oid} (excluded)", (outfits.get(db, oid) or {}).get("garments") or {})
             for oid in exclude]
    used_set = {o.get("setting") for o in reg if o.get("setting")}
    return select(listing, category=category, product_colours=colours, season=season,
                  materials=[m.name for m in getattr(cir, "materials", [])],
                  used_outfits=used, used_settings=used_set)
