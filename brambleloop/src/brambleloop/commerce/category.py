"""The deepest truthful Etsy category, and the attributes that category takes (F-005..F-009).

Every listing this company drafted carried one constant, taxonomy 66, whatever it was: a
blanket, a basket and a Christmas ornament were all filed at the same shallow node, and the
node itself had never been read back from Etsy. Section 8 asks for the opposite on both
counts -- the *most specific valid* category for each product, chosen from Etsy's real tree --
and for every attribute that category takes to be set truthfully or declared not applicable.

What this module decides, per product, from the stored snapshot
(`integrations.etsy_taxonomy`) and the product's own facts:

- **The node (F-005).** Inside the crochet-pattern subtree, descend while a child names this
  product's object (or, failing that, its object family). The node where descent stops is the
  deepest one the product truthfully belongs to; a node with a child that also names the
  product is refused as unnecessarily broad (`refuse_broad`). No snapshot, or no crochet
  pattern node in it, is **UNKNOWN** -- never a silent default to 66, because a remembered
  integer is exactly the thing that was never verified.
- **The inheritance (F-006).** The chosen node's ancestor names, so coverage scoring counts a
  phrase the category path already supplies as covered, and tags need not repeat it (F-014).
- **The properties (F-007, F-008).** Each property of the chosen node is SET from a pattern
  fact, NOT_APPLICABLE with a written reason, MISSING (relevant, no truthful value), or
  UNDECIDED (a property no rule here covers). Completeness is "nothing MISSING or UNDECIDED".
  The payload is shaped for Etsy's `updateListingProperty` (property_id, value_ids, values,
  scale_id); transmitting it is the publish path's job, not this module's.
- **The filter surface (F-009).** Which of the node's filters the listing enters (SET) and
  which it loses, and why.

Deterministic, no model, no network.
"""
from __future__ import annotations

import colorsys
import re
from dataclasses import dataclass, field

CHOSEN = "CHOSEN"
UNKNOWN = "UNKNOWN"

SET = "SET"
NOT_APPLICABLE = "NOT_APPLICABLE"
MISSING = "MISSING"
UNDECIDED = "UNDECIDED"

# What each catalogue category *is*, in words a taxonomy node would use. `object` names the
# thing; `family` names the shelf it sits on. Descent prefers an object match at every level,
# accepts a family match only when no child names the object, and stops when neither matches.
CATEGORY_NODE_TERMS: dict[str, dict[str, tuple[str, ...]]] = {
    "mosaic_blanket": {"object": ("blanket", "afghan", "throw"), "family": ("home",)},
    "blanket": {"object": ("blanket", "afghan", "throw"), "family": ("home",)},
    "graphghan": {"object": ("blanket", "afghan", "graphghan"), "family": ("home",)},
    "baby": {"object": ("baby", "blanket"), "family": ("children", "kids")},
    "nursery": {"object": ("nursery", "mobile", "baby"), "family": ("children", "home")},
    "amigurumi": {"object": ("amigurumi", "toy", "doll", "stuffed"), "family": ("children",)},
    "hat": {"object": ("hat", "beanie"), "family": ("accessor", "clothing", "apparel")},
    "scarf": {"object": ("scarf", "scarves", "cowl"), "family": ("accessor", "clothing")},
    "shawl": {"object": ("shawl", "wrap"), "family": ("accessor", "clothing")},
    "garment": {"object": ("sweater", "cardigan", "top", "garment"),
                "family": ("clothing", "apparel")},
    "bag": {"object": ("bag", "tote", "purse"), "family": ("accessor",)},
    "basket": {"object": ("basket", "storage"), "family": ("home",)},
    "coaster": {"object": ("coaster",), "family": ("kitchen", "home")},
    "placemat": {"object": ("placemat", "table"), "family": ("kitchen", "home")},
    "runner": {"object": ("runner", "table"), "family": ("kitchen", "home")},
    "pillow": {"object": ("pillow", "cushion"), "family": ("home",)},
    "wall_decor": {"object": ("wall", "hanging"), "family": ("home", "decor")},
    "ornament": {"object": ("ornament",), "family": ("holiday", "seasonal", "christmas")},
    "stocking": {"object": ("stocking",), "family": ("holiday", "seasonal", "christmas")},
    "seasonal_decor": {"object": ("holiday", "seasonal"), "family": ("decor", "home")},
    "flower": {"object": ("flower", "applique"), "family": ()},
    "pet": {"object": ("pet", "dog", "cat"), "family": ()},
    "wedding": {"object": ("wedding",), "family": ()},
}

_WORD = re.compile(r"[a-z0-9]+")


def _words(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def _names(node: dict, terms: tuple[str, ...]) -> bool:
    return any(w.startswith(t) for w in _words(node.get("name", "")) for t in terms)


def _terms(category: str) -> dict[str, tuple[str, ...]]:
    return CATEGORY_NODE_TERMS.get(category, {
        "object": tuple(_words(category.replace("_", " "))), "family": ()})


@dataclass
class CategoryChoice:
    status: str
    taxonomy_id: int | None = None
    path_ids: list[int] = field(default_factory=list)
    path_names: list[str] = field(default_factory=list)
    snapshot_id: int | None = None
    why: str = ""
    considered: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"status": self.status, "taxonomy_id": self.taxonomy_id,
                "path_ids": list(self.path_ids), "path_names": list(self.path_names),
                "snapshot_id": self.snapshot_id, "why": self.why,
                "considered": list(self.considered)}


def _index(snapshot: dict) -> dict[int, dict]:
    return {int(n["id"]): n for n in snapshot.get("nodes") or []}


def crochet_pattern_root(snapshot: dict) -> dict | None:
    """The shallowest node whose path names both a pattern and crochet."""
    best = None
    for n in snapshot.get("nodes") or []:
        names = [p.lower() for p in n.get("path_names") or []]
        if any("pattern" in p for p in names) and any("crochet" in p for p in names):
            if best is None or len(n["path_ids"]) < len(best["path_ids"]):
                best = n
    return best


def choose(snapshot: dict | None, category: str) -> CategoryChoice:
    """The deepest node in the crochet-pattern subtree that truthfully names this product."""
    if not snapshot:
        return CategoryChoice(UNKNOWN, why=(
            "no Etsy taxonomy snapshot is stored: the tree has never been read, so no "
            "category can be chosen and none is assumed (taxonomy 66 was never verified)"))
    index = _index(snapshot)
    root = crochet_pattern_root(snapshot)
    if root is None:
        return CategoryChoice(UNKNOWN, snapshot_id=snapshot.get("id"), why=(
            "the stored taxonomy has no node whose path names both a pattern and crochet"))
    terms = _terms(category)
    node, considered = root, []
    while True:
        children = [index[c] for c in node.get("child_ids") or [] if c in index]
        by_object = [c for c in children if _names(c, terms["object"])]
        by_family = [c for c in children if _names(c, terms["family"])] if terms["family"] \
            else []
        considered.append({"at": node["id"], "children": [c["name"] for c in children],
                           "object_matches": [c["name"] for c in by_object],
                           "family_matches": [c["name"] for c in by_family]})
        pick = (by_object or by_family)
        if not pick:
            break
        # Two siblings both naming the product is a tie the tree cannot settle; the lower id
        # makes the choice deterministic and `considered` records that it was a tie.
        node = sorted(pick, key=lambda c: int(c["id"]))[0]
    return CategoryChoice(
        CHOSEN, taxonomy_id=int(node["id"]), path_ids=list(node["path_ids"]),
        path_names=list(node["path_names"]), snapshot_id=snapshot.get("id"),
        why=(f"deepest crochet-pattern node naming a {category.replace('_', ' ')}: "
             f"{' > '.join(node['path_names'])}"), considered=considered)


def refuse_broad(snapshot: dict | None, taxonomy_id: int | None, category: str) -> str | None:
    """Why a proposed node is not the deepest truthful one, or None when it is.

    The check a caller holding an id from anywhere else -- a constant, an old payload, a
    person -- must pass: the node must exist in the stored tree, sit inside the crochet
    pattern subtree, and have no child that also names the product.
    """
    if taxonomy_id is None:
        return "no taxonomy id"
    chosen = choose(snapshot, category)
    if chosen.status != CHOSEN:
        return f"category UNKNOWN: {chosen.why}"
    if int(taxonomy_id) == chosen.taxonomy_id:
        return None
    index = _index(snapshot or {})
    node = index.get(int(taxonomy_id))
    if node is None:
        return f"taxonomy {taxonomy_id} is not in the stored Etsy tree"
    if int(taxonomy_id) in chosen.path_ids:
        return (f"taxonomy {taxonomy_id} ({node['name']}) is a parent of the deeper valid "
                f"node {chosen.taxonomy_id} ({' > '.join(chosen.path_names)})")
    return (f"taxonomy {taxonomy_id} ({' > '.join(node.get('path_names') or [])}) is not the "
            f"crochet-pattern node for this product ({' > '.join(chosen.path_names)})")


def path_phrases(choice: CategoryChoice) -> list[str]:
    """The phrases the category path supplies on its own (F-006, F-014)."""
    return [n.lower() for n in choice.path_names if n]


# ---- properties ---------------------------------------------------------------------------

# Etsy's colour vocabulary is small; the pattern's yarn names are not. Named first, then by
# hue from the hex the CIR carries, and never guessed past that.
COLOUR_NAMES: dict[str, str] = {
    "cream": "Beige", "oatmeal": "Beige", "ecru": "Beige", "natural": "Beige",
    "ivory": "White", "white": "White", "snow": "White",
    "forest": "Green", "pine": "Green", "sage": "Green", "olive": "Green", "green": "Green",
    "gold": "Gold", "mustard": "Yellow", "yellow": "Yellow",
    "wine": "Red", "burgundy": "Red", "red": "Red", "cranberry": "Red",
    "ink": "Blue", "navy": "Blue", "blue": "Blue", "denim": "Blue",
    "rust": "Orange", "orange": "Orange", "pumpkin": "Orange",
    "blush": "Pink", "pink": "Pink", "rose": "Pink",
    "grey": "Gray", "gray": "Gray", "charcoal": "Gray", "black": "Black",
    "brown": "Brown", "chocolate": "Brown", "purple": "Purple", "plum": "Purple",
}


def colour_family(name: str, hex_value: str | None = None) -> str | None:
    """Etsy's colour name for one yarn colour, or None when it cannot be said truthfully."""
    key = (name or "").strip().lower()
    if key in COLOUR_NAMES:
        return COLOUR_NAMES[key]
    if not hex_value or not re.fullmatch(r"#?[0-9A-Fa-f]{6}", hex_value):
        return None
    h = hex_value.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    if sat < 0.15:
        return "White" if light > 0.85 else "Black" if light < 0.15 else "Gray"
    deg = hue * 360
    for upper, family in ((15, "Red"), (45, "Orange"), (70, "Yellow"), (170, "Green"),
                          (260, "Blue"), (320, "Purple"), (345, "Pink"), (361, "Red")):
        if deg < upper:
            return family
    return None


HOLIDAYS: dict[str, str] = {
    "christmas": "Christmas", "halloween": "Halloween", "easter": "Easter",
    "thanksgiving": "Thanksgiving", "valentine": "Valentine's Day",
    "mother": "Mother's Day", "father": "Father's Day", "hanukkah": "Hanukkah",
    "new year": "New Year's",
}

SKILL: dict[str, str] = {"beginner": "Beginner", "confident beginner": "Beginner",
                         "intermediate": "Intermediate", "advanced": "Advanced"}

# Properties a crochet PDF must never claim, with the reason written down (F-008).
NOT_APPLICABLE_REASONS: dict[str, str] = {
    "recipient": ("a pattern is bought by a maker for whoever they choose; claiming a "
                  "recipient is an irrelevant attribute"),
    "material": "a PDF has no material; the yarn is the maker's choice",
    "primary material": "a PDF has no material; the yarn is the maker's choice",
    "fiber": "a PDF has no fibre; the yarn is the maker's choice",
    "fibre": "a PDF has no fibre; the yarn is the maker's choice",
    "subject": "a subject is a stylistic judgement with no deterministic source",
    "theme": "a theme is a stylistic judgement with no deterministic source",
    "style": "a style is a stylistic judgement with no deterministic source",
    "sustainability": "a PDF makes no sustainability claim this company can evidence",
    "personalization": "the pattern is not personalised per order",
    "room": "the room a finished object goes in is the maker's decision",
}


@dataclass
class Facts:
    """What the compiled pattern knows, and nothing it does not."""

    category: str
    difficulty: str
    colors: list[tuple[str, str | None]]
    season: str | None = None
    width_cm: float | None = None
    height_cm: float | None = None


def _norm(name: str) -> str:
    return " ".join(_words(name))


def _value(prop: dict, wanted: str) -> dict | None:
    for v in prop.get("possible_values") or []:
        if _norm(str(v.get("name", ""))) == _norm(wanted):
            return v
    return None


def _decide(prop: dict, facts: Facts) -> dict:
    """One property of the chosen node: SET / NOT_APPLICABLE / MISSING / UNDECIDED."""
    name = _norm(prop.get("name") or prop.get("display_name") or "")
    base = {"property_id": prop.get("property_id"), "name": prop.get("name"),
            "is_required": bool(prop.get("is_required"))}

    def set_to(wanted: str | None, source: str) -> dict:
        if not wanted:
            return {**base, "status": MISSING, "source": source,
                    "why": f"no truthful value for {prop.get('name')} in the pattern data"}
        choices = prop.get("possible_values") or []
        if choices:
            hit = _value(prop, wanted)
            if hit is None:
                return {**base, "status": MISSING, "source": source, "wanted": wanted,
                        "why": f"{wanted!r} is not one of Etsy's values for "
                               f"{prop.get('name')}; not guessed"}
            return {**base, "status": SET, "source": source, "value_ids": [hit.get("value_id")],
                    "values": [hit.get("name")], "scale_id": None}
        return {**base, "status": SET, "source": source, "value_ids": [],
                "values": [wanted], "scale_id": None}

    def na(why: str) -> dict:
        return {**base, "status": NOT_APPLICABLE, "why": why}

    if name in ("primary color", "primary colour"):
        c = facts.colors[0] if facts.colors else None
        return set_to(colour_family(*c) if c else None, "cir.colors[0]")
    if name in ("secondary color", "secondary colour"):
        if len(facts.colors) < 2:
            return na("the pattern is worked in one colour")
        return set_to(colour_family(*facts.colors[1]), "cir.colors[1]")
    if name == "occasion" and facts.category == "wedding":
        return set_to("Wedding", "catalogue category")
    if name in ("holiday", "occasion"):
        season = (facts.season or "").split(" (")[0].lower()
        if not season:
            return na("not a seasonal product; a holiday or occasion would be an "
                      "irrelevant attribute (F-008)")
        hit = next((v for k, v in HOLIDAYS.items() if k in season), None)
        if name == "occasion" and hit in ("Christmas", "Halloween", "Easter",
                                          "Thanksgiving", "Hanukkah"):
            return na(f"{hit} is a holiday, not an occasion; set on the holiday property")
        if hit is None:
            return na(f"season {facts.season!r} has no Etsy {name} value this module can "
                      f"defend")
        if (prop.get("possible_values") or []) and _value(prop, hit) is None:
            return na(f"Etsy offers no {hit!r} {name} value, so the property does not apply")
        return set_to(hit, "catalogue season")
    if name in ("craft type", "craft"):
        return set_to("Crochet", "the product is a crochet pattern")
    if name in ("skill level", "difficulty", "craft skill level"):
        return set_to(SKILL.get(facts.difficulty), "publish.difficulty (printed on the PDF)")
    if name in ("digital file type", "digital file types", "file type", "file format"):
        return set_to("PDF", "the delivered files are PDFs")
    if name in ("width", "length", "height"):
        value = facts.width_cm if name == "width" else facts.height_cm
        if value is None:
            return {**base, "status": MISSING, "why": "the twin states no finished size"}
        scale = next((s for s in prop.get("scales") or []
                      if "centimet" in str(s.get("display_name", "")).lower()), None)
        if scale is None:
            return {**base, "status": MISSING,
                    "why": f"{prop.get('name')} has no centimetre scale; not converted"}
        return {**base, "status": SET, "source": "twin finished size", "value_ids": [],
                "values": [f"{value:.0f}"], "scale_id": scale.get("scale_id")}
    if name in NOT_APPLICABLE_REASONS:
        return na(NOT_APPLICABLE_REASONS[name])
    return {**base, "status": UNDECIDED,
            "why": (f"no rule decides whether {prop.get('name')!r} applies to a crochet "
                    f"pattern; it cannot be called complete until one does")}


def properties_for(snapshot: dict | None, choice: CategoryChoice, facts: Facts) -> dict:
    """Every property of the chosen node, decided, plus the payload and the filter audit."""
    if choice.status != CHOSEN or not snapshot:
        return {"status": UNKNOWN, "decisions": [], "payload": [], "complete": False,
                "why": "no category, so no property schema to be complete against",
                "filters": {"entered": [], "lost": [], "measurable": False}}
    raw = (snapshot.get("properties") or {}).get(str(choice.taxonomy_id))
    if raw is None:
        return {"status": UNKNOWN, "decisions": [], "payload": [], "complete": False,
                "why": f"the snapshot holds no property schema for node {choice.taxonomy_id}",
                "filters": {"entered": [], "lost": [], "measurable": False}}
    decisions = [_decide(p, facts) for p in raw]
    gaps = [d for d in decisions if d["status"] in (MISSING, UNDECIDED)]
    payload = [{"property_id": d["property_id"], "value_ids": d["value_ids"],
                "values": d["values"], "scale_id": d["scale_id"], "name": d["name"]}
               for d in decisions if d["status"] == SET]
    return {"status": "DECIDED", "decisions": decisions, "payload": payload,
            "complete": not gaps,
            "gaps": [f"{d['status']}: {d['name']} -- {d['why']}" for d in gaps],
            "filters": filter_audit(decisions),
            "why": ("every property of the node is set or declared not applicable" if not gaps
                    else f"{len(gaps)} propert{'y' if len(gaps) == 1 else 'ies'} "
                         f"missing or undecided")}


def filter_audit(decisions: list[dict]) -> dict:
    """Which of the node's filters this listing enters and which it loses (F-009)."""
    entered = [{"filter": d["name"], "values": d.get("values")}
               for d in decisions if d["status"] == SET]
    lost = [{"filter": d["name"], "status": d["status"], "why": d.get("why", "")}
            for d in decisions if d["status"] != SET]
    return {"measurable": True, "entered": entered, "lost": lost,
            "lost_to_missing_data": [x["filter"] for x in lost
                                     if x["status"] in (MISSING, UNDECIDED)]}


def attribute_values(decisions: list[dict]) -> list[str]:
    """Phrases the structured fields supply on their own (F-006/F-014 dedup input)."""
    return [str(v).lower() for d in decisions if d["status"] == SET
            for v in d.get("values") or []]


def for_product(db, *, category: str, facts: Facts) -> dict:
    """The live entry point: read the newest snapshot and decide everything above."""
    from ..integrations import etsy_taxonomy

    snapshot = etsy_taxonomy.latest(db)
    choice = choose(snapshot, category)
    props = properties_for(snapshot, choice, facts)
    return {"choice": choice, "properties": props,
            "snapshot": ({"id": snapshot["id"], "fetched_at": snapshot["fetched_at"],
                          "sha256": snapshot["sha256"]} if snapshot else None)}


def publish_inputs(db, *, slug: str, version: str) -> dict:
    """What the publish path sends to Etsy for this listing: node and property payload.

    The interface cluster B's `store.publish` reads. `taxonomy_id` is None when the category
    is UNKNOWN, and the publish path must then refuse rather than send a default node;
    `properties` is shaped for `updateListingProperty` (property_id, value_ids, values,
    scale_id). `certified` is the stored search certificate's verdict -- PASS only once the
    hero was judged on a certified listing set and while that evidence and the copy are
    still current (`search.stored_pass_problems`), STALE otherwise; the publish-time
    verdict, with the hero and the fingerprint check, is `release_gates.search_gate`.
    """
    from sqlalchemy import select

    from ..core.models import ListingSearchProfile

    with db.session() as s:
        row = s.scalar(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == slug,
            ListingSearchProfile.version == version))
        if row is None:
            return {"status": UNKNOWN, "taxonomy_id": None, "properties": [],
                    "certified": None, "why": "listing.seo has recorded no search profile"}
        out = {"status": row.category_status, "taxonomy_id": row.taxonomy_id,
               "path": list(row.taxonomy_path or []), "properties": list(row.properties or []),
               "certified": row.verdict,
               "why": "" if row.category_status == CHOSEN else "category UNKNOWN"}
    # A stored PASS counts only while it still describes this listing: the hero judged on the
    # listing-set certificate still valid for this release, and the copy unchanged since.
    if out["certified"] == "PASS":
        from .search import stored_pass_problems

        stale = stored_pass_problems(db, slug=slug, version=version)
        if stale:
            out["certified"] = "STALE"
            out["certified_problems"] = stale
    return out
