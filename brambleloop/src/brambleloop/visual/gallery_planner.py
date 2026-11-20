"""The gallery planner: seven or more distinct frames per listing (ENG-WARDROBE-SCENES).

For one listing it picks, deterministically:

* one frame per campaign role (`scene_library.FRAME_ROLES`): hero, flat-lay, lifestyle,
  alternative angle, close-up, scale or in-use, and an extra frame;
* a different scene for every generated frame, preferring a different place and a different
  camera angle each time, so the gallery shows several environments;
* ONE outfit for every frame Laura is in (the listing's claim, `outfit_library`);
* the same product block in every frame (`prompt_assembly.ProductRef`).

Each role carries exactly one gallery job (#65's one-job rule and
`shot_plans.campaign_standard`): hero DESIRE, flat-lay COLOUR_CONTEXT, lifestyle LIFESTYLE,
alternative angle ANGLE, close-up DETAIL, scale SCALE. The extra frame is CONSTRUCTION for a
shaped or worn family (generated, it shows the base, joins or seams) and otherwise the
deterministic download-information frame (CONTENTS, from the certified PDF, never generated).
A shaped or worn family also gets the CONTENTS frame, as an eighth.

**Where Laura appears** follows how the product meets her (`outfit_library.interaction`):
worn products are worn in the hero, lifestyle, back view and fit frames; held products are
used by her in the lifestyle and scale frames; home goods have her in the lifestyle frame.
Flat-lays and close-ups never show her.

**No filler** (`check_gallery`). A plan is refused when it has fewer than seven frames, a
repeated role or job, a repeated scene, the same place seen from the same angle twice, fewer
than `MIN_PLACES` places, more than one outfit (or a Laura frame with none), a product block
that differs between frames, or two frames whose scene text is nearly the same
(`MAX_SCENE_OVERLAP`, REPETITIVE_FILLER).

Deterministic. No model call, no network, CA$0.
"""
from __future__ import annotations

import hashlib
import re

from . import outfit_library as OL
from . import prompt_assembly as PA
from . import scene_library as SL
from ..publish import eligibility as el

PLANNER_VERSION = "gallery-planner/1"
MIN_FRAMES = 7
MIN_PLACES = 3
MAX_SCENE_OVERLAP = 0.70

JOB_OF_FRAME: dict[str, str] = {
    "hero": el.DESIRE, "flat_lay": el.COLOUR_CONTEXT, "lifestyle": el.LIFESTYLE,
    "alt_angle": el.ANGLE, "close_up": el.DETAIL, "scale_in_use": el.SCALE,
}
_SHAPED = frozenset({"basket", "amigurumi", "pillow", "ornament", "hat", "bag", "garment"})

# frame role -> interaction modes in which Laura is in the frame
LAURA_IN: dict[str, frozenset[str]] = {
    "hero": frozenset({OL.WORN}),
    "lifestyle": frozenset({OL.WORN, OL.HELD, OL.NEAR}),
    "alt_angle": frozenset({OL.WORN}),
    "scale_in_use": frozenset({OL.WORN, OL.HELD}),
}


class GalleryRefused(ValueError):
    pass


def extra_job(family: str) -> str:
    return el.CONSTRUCTION if family in _SHAPED else el.CONTENTS


def laura_in(frame_role: str, family: str) -> bool:
    return OL.interaction(family) in LAURA_IN.get(frame_role, frozenset())



def _rank(listing: str, role: str, scenes: list[SL.Scene]) -> list[SL.Scene]:
    return sorted(scenes, key=lambda s: hashlib.sha256(
        f"{PLANNER_VERSION}|{listing}|{role}|{s.scene_id}".encode()).hexdigest())


def _pool(listing: str, role: str, family: str, season: str, laura: bool) -> list[SL.Scene]:
    pool = SL.scenes_for(family, role, season=season)
    if laura:
        pool = [s for s in pool if s.laura]
    return _rank(listing, role, pool)


def _assign(listing: str, family: str, season: str, roles: list[str]) -> dict[str, SL.Scene]:
    """A distinct scene for every generated role: no scene twice, no place seen from the same
    angle twice, and as many places as the library allows. Deterministic depth-first search
    over each role's ranked pool, scarcest role first; the first assignment reaching the most
    distinct places (capped at the role count) wins."""
    pools = {r: _pool(listing, r, family, season, laura_in(r, family)) for r in roles}
    empty = [r for r in roles if not pools[r]]
    if empty:
        raise GalleryRefused(f"no {empty} scene for {family} (season {season or 'any'}); the "
                             f"gallery is held, never padded with a repeat")
    order = sorted(roles, key=lambda r: (len(pools[r]), roles.index(r)))
    best: dict = {}
    target = len(roles)

    def places(chosen: dict) -> int:
        return len({s.place for s in chosen.values()})

    def dfs(i: int, chosen: dict, steps: list) -> bool:
        steps[0] += 1
        if steps[0] > 20000:
            return True
        if i == len(order):
            if places(chosen) > places(best) or not best:
                best.clear()
                best.update(chosen)
            return places(best) >= min(target, MIN_PLACES + 2)
        role = order[i]
        used_ids = {s.scene_id for s in chosen.values()}
        pairs = {(s.place, s.angle) for s in chosen.values()}
        seen = {s.place for s in chosen.values()}
        cands = [s for s in pools[role] if s.scene_id not in used_ids
                 and (s.place, s.angle) not in pairs]
        cands.sort(key=lambda s: s.place in seen)
        for sc in cands:
            chosen[role] = sc
            if dfs(i + 1, chosen, steps):
                return True
            del chosen[role]
        return False

    dfs(0, {}, [0])
    if len(best) != len(roles):
        raise GalleryRefused(f"no distinct set of {roles} scenes for {family} (season "
                             f"{season or 'any'}); the gallery is held, never padded with a "
                             f"repeat")
    return dict(best)


def plan_gallery(listing: str, *, product: PA.ProductRef, outfit: OL.Outfit | None,
                 season: str = "", learned: dict | None = None) -> dict:
    """The frames for one listing. `outfit` is the listing's claimed outfit; it is required
    whenever any frame has Laura. `learned` maps frame role -> ENG-LEARN prompt_for result."""
    family = product.family
    roles = list(JOB_OF_FRAME) + ["extra"]
    generated = [r for r in roles if not (r == "extra" and extra_job(family) == el.CONTENTS)]
    scenes = _assign(listing, family, season, generated)
    frames = []
    for role in roles:
        job = JOB_OF_FRAME.get(role) or extra_job(family)
        if role not in scenes:
            frames.append(_contents_frame(len(frames) + 1, role, product))
            continue
        laura = laura_in(role, family)
        sc = scenes[role]
        fr = PA.assemble(scene=sc, product=product, frame_role=role, laura=laura,
                         outfit=outfit if laura else None,
                         learned=(learned or {}).get(role))
        frames.append({"position": len(frames) + 1, "frame_role": role, "job": job,
                       "generate": True, "place": sc.place, "angle": sc.angle,
                       "lighting": sc.lighting, **fr})
    if extra_job(family) != el.CONTENTS:
        frames.append(_contents_frame(len(frames) + 1, "download_info", product))
    plan = {"planner_version": PLANNER_VERSION, "listing": listing, "family": family,
            "season": season or "any", "outfit_id": outfit.outfit_id if outfit else None,
            "product": product.view(), "frames": frames,
            "roles": [{"role": f["frame_role"], "job": f["job"]} for f in frames]}
    plan["check"] = check_gallery(plan)
    return plan


def _contents_frame(pos: int, role: str, product: PA.ProductRef) -> dict:
    return {"position": pos, "frame_role": role, "job": el.CONTENTS, "generate": False,
            "source": "disclosed_render", "medium": "PATTERN_PREVIEW",
            "brief": ("download information: the deterministic preview of the certified US "
                      "and UK pattern PDFs (never generated)"),
            "product_digest": product.digest(), "laura": False, "outfit_id": None,
            "scene_id": None}


_WORD = re.compile(r"[a-z]+")


def _overlap(a: str, b: str) -> float:
    wa, wb = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    return len(wa & wb) / len(wa | wb) if wa | wb else 1.0


def check_gallery(plan: dict) -> dict:
    """Every reason this gallery plan is refused. ok is True only with none."""
    from .shot_plans import campaign_standard

    frames = list(plan.get("frames") or [])
    gen = [f for f in frames if f.get("generate")]
    problems: list[dict] = []
    std = campaign_standard({"roles": [{"job": f.get("job")} for f in frames]})
    problems += std["problems"]
    roles = [f.get("frame_role") for f in frames]
    dup_roles = sorted({r for r in roles if roles.count(r) > 1})
    if dup_roles:
        problems.append({"kind": "duplicate_role", "roles": dup_roles})
    scenes = [f.get("scene_id") for f in gen]
    dup_sc = sorted({s for s in scenes if scenes.count(s) > 1})
    if dup_sc:
        problems.append({"kind": "duplicate_scene", "scenes": dup_sc})
    pairs = [(f.get("place"), f.get("angle")) for f in gen]
    dup_pairs = sorted({p for p in pairs if pairs.count(p) > 1})
    if dup_pairs:
        problems.append({"kind": "same_place_same_angle", "pairs": [list(p) for p in dup_pairs]})
    places = {f.get("place") for f in gen}
    if len(places) < MIN_PLACES:
        problems.append({"kind": "too_few_places", "places": sorted(map(str, places)),
                         "minimum": MIN_PLACES})
    laura_outfits = {f.get("outfit_id") for f in frames if f.get("laura")}
    if None in laura_outfits:
        problems.append({"kind": "laura_without_outfit"})
    if len(laura_outfits - {None}) > 1:
        problems.append({"kind": "more_than_one_outfit",
                         "outfits": sorted(laura_outfits - {None})})
    if plan.get("outfit_id") and laura_outfits - {None, plan["outfit_id"]}:
        problems.append({"kind": "outfit_not_the_listing_claim"})
    digests = {f.get("product_digest") for f in frames}
    if len(digests) != 1 or None in digests:
        problems.append({"kind": "product_not_invariant", "digests": len(digests)})
    for f in gen:
        if f.get("product_digest") and plan.get("product", {}).get("digest") and \
                f["product_digest"] != plan["product"]["digest"]:
            problems.append({"kind": "product_not_invariant", "frame": f.get("position")})
            break
    for i, a in enumerate(gen):
        for b in gen[i + 1:]:
            ov = _overlap(a.get("variable_text") or a["sections"]["scene"],
                          b.get("variable_text") or b["sections"]["scene"])
            if ov >= MAX_SCENE_OVERLAP:
                problems.append({"kind": "repetitive_filler", "frames": [a["position"],
                                                                          b["position"]],
                                 "overlap": round(ov, 3), "maximum": MAX_SCENE_OVERLAP})
    return {"ok": not problems, "frames": len(frames), "generated": len(gen),
            "places": sorted(map(str, places)), "problems": problems}


def plan_for_listing(db, listing: str, *, family: str | None = None, cir=None,
                     season: str = "") -> dict:
    """Claim the listing's one outfit (if any frame has Laura) and plan its gallery.

    `cir` defaults to the listing's certified primary CIR (`launch_imagery._listing_parts`)."""
    if cir is None or family is None:
        from .launch_imagery import _listing_parts

        _cand, cirs, category = _listing_parts(listing)
        cir = cir or cirs[0]
        family = family or category
    product = PA.product_ref(cir, family=family)
    needs_laura = any(laura_in(r, family) for r in JOB_OF_FRAME)
    outfit = None
    claim = None
    if needs_laura:
        claim = OL.claim_for_listing(db, listing, family=family, product_colours=cir.colors,
                                     season=season)
        if claim["status"] != "PASS":
            raise GalleryRefused(f"no outfit for {listing!r}: {claim['why']}")
        outfit = OL.BY_ID.get(claim["outfit_id"])
        if outfit is None:
            raise GalleryRefused(f"{listing!r} holds {claim['outfit_id']}, which is not a "
                                 f"library outfit; it is kept, and planned by its owner")
    plan = plan_gallery(listing, product=product, outfit=outfit, season=season)
    return {**plan, "claim": claim}
