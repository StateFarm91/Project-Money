"""Listing image SEQUENCE policy per product class (owner D-FB-16 item 4).

Frame one sells the finished dream -- "I want to make that": an aspirational finished-product
or lifestyle hero. Every later frame is evidence that answers the buyer's next question, in a
fixed order: clarity, dimensions, yarn, charts, construction, skill, colours,
verification/trust, download contents.

Diagrams and engineering renders are **demoted, never deleted**: a stitch chart, a
construction schematic or a twin render of the CIR is validation evidence and keeps its place
in the evidence frames. Product Truth is unchanged by sequencing -- this module only decides
*order*; whether an asset may appear at all is decided by the hard gates
(`visual.rnd.gates` / `publish.eligibility`), and an asset that failed one is excluded from
every position, hero or evidence.

Rules (all deterministic, all checked by `check`):

1. Position 1 is the hero and its kind is in `ASPIRATIONAL_KINDS`. A kind in `NEVER_HERO_KINDS`
   (charts, schematics, engineering renders, size charts, contents, ...) can never be the hero,
   whatever its desirability score -- not even when it is the only accepted asset.
2. When no gate-passing aspirational asset exists the plan says `NO_ASPIRATIONAL_HERO`; it does
   not promote evidence to fill the slot.
3. Every gate-passing truth-evidence asset supplied is placed (one per slot first, extras after
   while the frame cap allows). Dropping evidence to make room is reported, never silent.
4. A generated (AI) concept may be the hero only when the caller says it is export-eligible
   (`export_allowed`), i.e. `publish.eligibility.may_export` passed it; classifying is not
   exporting (F-852).
5. Among eligible hero assets the class's preferred kinds come first, then the R&D objective
   (`visual.rnd.objective`) -- desirability only ever ranks assets that already passed gates.
"""
from __future__ import annotations

POLICY_VERSION = "listing-sequence/1"

# Etsy listings accept up to ten photos in the long-standing listing form (video separate);
# kept conservative here. If the marketplace cap is verified higher, raising it only adds
# evidence frames -- frame one is unaffected.
MAX_FRAMES = 10

HERO = "hero_aspiration"
# The evidence slots, in the order a buyer asks the questions (D-FB-16 item 4).
EVIDENCE_SLOTS: tuple[str, ...] = ("clarity", "dimensions", "yarn", "charts", "construction",
                                   "skill", "colours", "verification", "contents")
SLOTS: tuple[str, ...] = (HERO,) + EVIDENCE_SLOTS

SLOT_MEANS: dict[str, str] = {
    HERO: "the finished dream at thumbnail scale: 'I want to make that'",
    "clarity": "what the finished piece and its stitches really look like up close",
    "dimensions": "how big it is / which sizes exist, against something a person knows",
    "yarn": "what yarn, hook and notions to buy",
    "charts": "what the chart / written pattern looks like to work from",
    "construction": "how it is built: pieces, joins, construction diagram",
    "skill": "whether this buyer can make it (skill level, techniques used)",
    "colours": "colourways and how the design reads in other colours",
    "verification": "why it can be trusted: every count checked, tested, honest renders",
    "contents": "what arrives in the download",
}

# The `publish.eligibility` job each slot does, where one exists. Slots without one are new
# jobs (WIRING REQUEST to publish.eligibility: CONSTRUCTION, COLOURWAYS, TRUST).
ELIGIBILITY_JOB: dict[str, str | None] = {
    HERO: "DESIRE", "clarity": "DETAIL", "dimensions": "SCALE", "yarn": "MATERIALS",
    "charts": "PATTERN_PREVIEW", "construction": None, "skill": "DIFFICULTY",
    "colours": None, "verification": None, "contents": "CONTENTS",
}

ASPIRATIONAL_KINDS: frozenset[str] = frozenset({
    "lifestyle_scene", "on_model", "finished_product", "styled_flatlay", "seasonal_scene"})

# Asset kind -> evidence slot.
EVIDENCE_KIND_SLOT: dict[str, str] = {
    "detail_closeup": "clarity", "stitch_closeup": "clarity",
    "dimensions": "dimensions", "scale": "dimensions", "size_chart": "dimensions",
    "yarn_materials": "yarn", "materials": "yarn",
    "stitch_chart": "charts", "chart": "charts", "pattern_page": "charts",
    "construction_diagram": "construction", "schematic": "construction",
    "engineering_render": "construction", "diagram": "construction",
    "skill_level": "skill", "colourways": "colours", "verification": "verification",
    "trust": "verification", "download_contents": "contents", "pdf_preview": "contents",
}
NEVER_HERO_KINDS: frozenset[str] = frozenset(EVIDENCE_KIND_SLOT)

GENERATED_MEDIA = frozenset({"AI_LIFESTYLE_CONCEPT"})

# Per product class: which aspirational kinds make the strongest hero, in order, and whether
# Laura is the preferred face (D-FB-16 item 6: Laura is the centre of the brand but is not
# forced into every listing; non-wearables are product-first when that is stronger).
CLASS_POLICY: dict[str, dict] = {
    "fitted_garments": {"hero": ("on_model", "lifestyle_scene", "finished_product"),
                        "laura": "preferred", "dimensions_as": "size_chart"},
    "loose_garments": {"hero": ("on_model", "lifestyle_scene", "finished_product"),
                       "laura": "preferred", "dimensions_as": "size_chart"},
    "accessories": {"hero": ("on_model", "lifestyle_scene", "styled_flatlay",
                             "finished_product"), "laura": "optional",
                    "dimensions_as": "size_chart"},
    "blankets_home_textiles": {"hero": ("lifestyle_scene", "styled_flatlay",
                                        "finished_product"), "laura": "optional",
                               "dimensions_as": "scale"},
    "baskets_storage": {"hero": ("lifestyle_scene", "finished_product", "styled_flatlay"),
                        "laura": "not_default", "dimensions_as": "scale"},
    "coasters_tabletop": {"hero": ("lifestyle_scene", "styled_flatlay", "finished_product"),
                          "laura": "not_default", "dimensions_as": "scale"},
    "seasonal": {"hero": ("seasonal_scene", "lifestyle_scene", "styled_flatlay",
                          "finished_product"), "laura": "optional", "dimensions_as": "scale"},
    "laura_on_model": {"hero": ("on_model", "lifestyle_scene"), "laura": "required",
                       "dimensions_as": "size_chart"},
}
DEFAULT_POLICY = {"hero": ("lifestyle_scene", "finished_product", "styled_flatlay"),
                  "laura": "optional", "dimensions_as": "scale"}

# How the deterministic disclosed renderer's views map onto the sequence (its "hero" view is a
# finished-product render bound to the certified CIR, disclosed as a render).
DISCLOSED_VIEW_KIND = {"hero": "finished_product", "scale": "dimensions",
                       "detail": "detail_closeup"}

OK, NO_HERO = "OK", "NO_ASPIRATIONAL_HERO"


def policy(product_class: str) -> dict:
    p = CLASS_POLICY.get(product_class, DEFAULT_POLICY)
    return {"product_class": product_class, "hero_preference": list(p["hero"]),
            "laura": p["laura"], "evidence_order": list(EVIDENCE_SLOTS),
            "max_frames": MAX_FRAMES, "version": POLICY_VERSION}


def describe() -> dict:
    return {"version": POLICY_VERSION, "max_frames": MAX_FRAMES, "slots": list(SLOTS),
            "slot_means": SLOT_MEANS, "eligibility_job": ELIGIBILITY_JOB,
            "aspirational_kinds": sorted(ASPIRATIONAL_KINDS),
            "never_hero_kinds": sorted(NEVER_HERO_KINDS),
            "classes": {c: policy(c) for c in CLASS_POLICY},
            "rule": "frame 1 sells the finished dream; diagrams/engineering renders are "
                    "evidence frames, never the hero; gate-failed assets appear nowhere"}


def _slot_of(kind: str) -> str | None:
    if kind in ASPIRATIONAL_KINDS:
        return HERO
    return EVIDENCE_KIND_SLOT.get(kind)


def _objective_value(asset: dict) -> float:
    obj = asset.get("objective") or {}
    v = obj.get("value") if isinstance(obj, dict) else None
    return float(v) if v is not None else -1.0


def hero_eligible(asset: dict) -> tuple[bool, str]:
    kind = asset.get("kind", "")
    if kind in NEVER_HERO_KINDS or kind not in ASPIRATIONAL_KINDS:
        return False, f"kind {kind!r} is evidence, not an aspirational hero"
    if asset.get("accepted") is not True:
        return False, "did not pass every hard gate"
    if str(asset.get("medium", "")).upper() in GENERATED_MEDIA and \
            asset.get("export_allowed") is not True:
        return False, "generated concept not export-eligible (publish.eligibility.may_export)"
    return True, ""


def plan(product_class: str, assets: list[dict]) -> dict:
    """The listing frame order for one product. `assets`: dicts with `id`, `kind`, `medium`,
    `accepted` (every hard gate passed), optional `objective` ({"value": ...}) and
    `export_allowed`. Returns frames in order plus everything excluded or demoted, with why."""
    pol = CLASS_POLICY.get(product_class, DEFAULT_POLICY)
    excluded, unknown_kind = [], []
    accepted = []
    for a in assets:
        if a.get("accepted") is not True:
            excluded.append({"id": a.get("id"), "kind": a.get("kind"),
                             "why": "failed or did not run a hard gate: appears nowhere",
                             "failures": list(a.get("failures") or [])})
        elif _slot_of(a.get("kind", "")) is None:
            unknown_kind.append({"id": a.get("id"), "kind": a.get("kind"),
                                 "why": "kind has no slot in the sequence policy"})
        else:
            accepted.append(a)

    pref = list(pol["hero"])
    heroes = []
    for a in accepted:
        ok, _ = hero_eligible(a)
        if ok:
            rank = pref.index(a["kind"]) if a["kind"] in pref else len(pref)
            heroes.append((rank, -_objective_value(a), str(a.get("id")), a))
    heroes.sort(key=lambda t: t[:3])
    hero = heroes[0][3] if heroes else None
    alternates = [h[3] for h in heroes[1:]]

    frames = []
    if hero is not None:
        frames.append(_frame(1, HERO, hero, "hero"))
    by_slot: dict[str, list[dict]] = {s: [] for s in EVIDENCE_SLOTS}
    for a in accepted:
        slot = _slot_of(a["kind"])
        if slot != HERO:
            by_slot[slot].append(a)
    # Spare aspirational assets are useful clarity evidence, after the dedicated ones.
    by_slot["clarity"].extend(alternates)
    ordered = [(s, by_slot[s][0]) for s in EVIDENCE_SLOTS if by_slot[s]]
    extras = [(s, a) for s in EVIDENCE_SLOTS for a in by_slot[s][1:]]
    dropped = []
    for slot, a in ordered + extras:
        if len(frames) >= MAX_FRAMES:
            dropped.append({"id": a.get("id"), "kind": a.get("kind"),
                            "why": f"frame cap {MAX_FRAMES} reached"})
            continue
        frames.append(_frame(len(frames) + 1, slot, a, "evidence"))
    # Demotions: never-hero assets that the input order would have put first.
    demoted = []
    if assets and assets[0].get("kind") in NEVER_HERO_KINDS:
        demoted.append({"id": assets[0].get("id"), "kind": assets[0].get("kind"),
                        "why": "diagram/engineering evidence demoted from hero to an evidence "
                               "frame; Product Truth unchanged"})
    present = {f["slot"] for f in frames}
    missing = [s for s in SLOTS if s not in present]
    truth_ids = {a.get("id") for a in accepted if _slot_of(a["kind"]) != HERO}
    placed = {f["asset_id"] for f in frames}
    return {"product_class": product_class, "policy": policy(product_class),
            "status": OK if hero is not None else NO_HERO,
            "hero": None if hero is None else {"id": hero.get("id"), "kind": hero["kind"]},
            "frames": frames, "missing_slots": missing, "excluded": excluded,
            "unclassified": unknown_kind, "dropped": dropped, "demoted": demoted,
            "truth_evidence_kept": truth_ids <= placed,
            "why": ("frame 1 is the aspirational hero; evidence follows in buyer-question order"
                    if hero is not None else
                    "no gate-passing aspirational hero exists: the hero slot stays empty "
                    "rather than promoting a diagram (queue a hero challenger)")}


def _frame(position: int, slot: str, asset: dict, role: str) -> dict:
    return {"position": position, "slot": slot, "role": role, "asset_id": asset.get("id"),
            "kind": asset.get("kind"), "medium": asset.get("medium"),
            "eligibility_job": ELIGIBILITY_JOB.get(slot)}


def check(frames: list[dict], *, supplied_evidence_ids=()) -> list[str]:
    """Violations of the policy in an existing frame order (empty list = compliant)."""
    out = []
    if not frames:
        return ["no frames"]
    first = frames[0]
    if first.get("kind") not in ASPIRATIONAL_KINDS:
        out.append(f"frame 1 is {first.get('kind')!r}, not an aspirational hero")
    for f in frames[1:]:
        if f.get("slot") == HERO:
            out.append(f"position {f.get('position')} claims the hero slot")
    placed = {f.get("asset_id") for f in frames}
    lost = sorted(str(i) for i in set(supplied_evidence_ids) - placed)
    if lost and len(frames) < MAX_FRAMES:
        out.append(f"truth evidence dropped without a frame cap: {lost}")
    order = [EVIDENCE_SLOTS.index(f["slot"]) for f in frames[1:]
             if f.get("slot") in EVIDENCE_SLOTS and f.get("role") == "evidence"]
    firsts = list(dict.fromkeys(order))
    if firsts != sorted(firsts):
        out.append("evidence frames out of buyer-question order")
    return out


def from_disclosed_gallery(frames: list[dict], judged: list[dict]) -> list[dict]:
    """Adapt a deterministic disclosed gallery (`gates.produce` + `gates.judge_frame`) into
    sequence assets."""
    out = []
    for f, j in zip(frames, judged):
        out.append({"id": f.get("sha256"), "kind": DISCLOSED_VIEW_KIND.get(f["view"],
                                                                         "diagram"),
                    "medium": "DIGITAL_TWIN_RENDER", "accepted": bool(j.get("accepted")),
                    "failures": list(j.get("failures") or []), "view": f["view"]})
    return out
