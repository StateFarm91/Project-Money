"""The canonical model system, built for an identity nobody has chosen yet.

Requirements 200, 201, 202, 203, 204. The owner will select one fictional model who becomes
Brambleloop's recurring face, and after that selection her identity is frozen: the company may
improve photography, posing, wardrobe and merchandising, and may not redesign her without
explicit approval.

Nothing has been selected. That is the fact this module is organised around, because the
tempting shortcut is to let the first generated face become canonical by being first — nobody
decides, the reference pack fills up with whatever was produced, and by the time anybody
notices, a hundred listings carry a woman nobody chose.

So there are two distinct states and no path between them that does not go through the owner:

- **candidates** — as many as generation produces, none of them canonical, none usable in a
  published asset.
- **canonical** — exactly one, frozen at selection, with a versioned reference pack.

`canonical()` returns `None` today and every function that would use it says so rather than
falling back to a candidate. The anti-drift evaluator reports `unavailable` for the same
reason: drift is measured against a reference pack, and there is no reference pack to measure
against. A drift check that passed because it had nothing to compare with would be worse than
no drift check, because it would be believed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# What a reference pack has to pin (#200). Each is something that drifts between generations
# and that a buyer notices across a gallery without being able to say why.
IDENTITY_FIELDS: tuple[str, ...] = (
    "facial_geometry", "hair", "eyes", "age_band", "complexion", "representative_angles",
    "representative_expressions",
)

CANDIDATE = "candidate"
CANONICAL = "canonical"
RETIRED = "retired"

# Drift dimensions (#201). A beautiful image of the wrong woman fails.
DRIFT_DIMENSIONS: tuple[str, ...] = ("face", "hair", "eyes", "age", "stylisation")

# Products where a clean product-only hero outsells a modelled one (#204). Product truth and
# category fit outrank compulsory model presence, so this is a list of exceptions rather than
# a preference.
PRODUCT_FIRST_FORMS: frozenset[str] = frozenset({
    "blanket", "throw", "coaster", "placemat", "runner", "basket", "pillow", "wall_hanging",
    "ornament", "garland", "wreath", "toy",
})


class IdentityUnavailable(RuntimeError):
    """Something needs the canonical model and no model has been selected."""


class IdentityRefused(ValueError):
    """An attempt to change an identity that only the owner may change."""


@dataclass(frozen=True)
class ReferencePack:
    """The frozen description of the canonical model, versioned (#200)."""

    version: int
    fields: dict
    approved_by_owner_at: str

    def missing(self) -> list[str]:
        return [f for f in IDENTITY_FIELDS if not self.fields.get(f)]

    def complete(self) -> bool:
        return not self.missing()


@dataclass
class Candidate:
    """One generated face. Not canonical, and not usable in anything published."""

    key: str
    fields: dict = field(default_factory=dict)
    state: str = CANDIDATE
    note: str = ""

    def to_dict(self) -> dict:
        return {"key": self.key, "state": self.state,
                "described": sorted(k for k in self.fields if self.fields[k]),
                "note": self.note}


def canonical(packs: list[ReferencePack] | None = None) -> ReferencePack | None:
    """The selected model, or None.

    Returns None today. Every caller is expected to handle that rather than fall back to a
    candidate, because a candidate promoted by being first is an identity nobody chose.
    """
    approved = [p for p in (packs or []) if p.approved_by_owner_at]
    return max(approved, key=lambda p: p.version) if approved else None


def select(candidate: Candidate, *, owner_approved: bool,
           existing: ReferencePack | None = None) -> ReferencePack:
    """Freeze a candidate as canonical. Only the owner can do this, and only once.

    Replacing an existing canonical identity is a redesign, which #200 reserves to the owner
    explicitly — so it is refused here even when `owner_approved` is true, because "approved"
    on a selection call is not the same as approving a redesign.
    """
    if not owner_approved:
        raise IdentityRefused(
            f"{candidate.key} cannot become canonical without the owner's selection. A "
            f"candidate that becomes canonical by being first is an identity nobody chose, "
            f"and it is discovered a hundred listings later")
    if existing is not None:
        raise IdentityRefused(
            "a canonical identity already exists. Replacing her is a redesign, which needs "
            "explicit owner approval as a separate decision rather than as a side effect of "
            "a selection call (#200)")
    missing = [f for f in IDENTITY_FIELDS if not candidate.fields.get(f)]
    if missing:
        raise IdentityRefused(
            f"the reference pack would be incomplete: {missing}. An unpinned field is a field "
            f"that drifts, and drift is what the pack exists to prevent")
    return ReferencePack(version=1, fields=dict(candidate.fields),
                         approved_by_owner_at=datetime.now(timezone.utc).isoformat())


def drift_check(observed: dict, pack: ReferencePack | None,
                *, tolerance: float = 0.15) -> dict:
    """Compare an asset's rendered identity against the canonical reference (#201).

    With no pack the verdict is `unavailable`, never `pass`. A drift check that passed because
    it had nothing to compare against would be worse than no check at all, because it would
    be believed — and the assets it waved through would carry a face that changed slowly
    across a gallery in the way buyers notice without being able to name.
    """
    if pack is None:
        return {
            "verdict": "unavailable",
            "reason": ("no canonical model has been selected, so there is no reference pack "
                       "to measure drift against. This is not a pass"),
            "blocks_release": True,
            "dimensions": {},
        }

    scored: dict[str, float] = {}
    for dimension in DRIFT_DIMENSIONS:
        want = pack.fields.get({"face": "facial_geometry", "age": "age_band",
                                "stylisation": "representative_expressions"}.get(
                                    dimension, dimension))
        got = observed.get(dimension)
        if want is None or got is None:
            scored[dimension] = 1.0      # unmeasured counts as maximum drift
            continue
        scored[dimension] = 0.0 if str(want) == str(got) else 1.0

    worst = max(scored.values()) if scored else 1.0
    failed = [d for d, v in scored.items() if v > tolerance]
    return {
        "verdict": "pass" if not failed else "fail",
        "dimensions": scored,
        "failed": failed,
        "blocks_release": bool(failed),
        "reason": ("" if not failed else
                   f"identity drifted on {failed}: a beautiful image of the wrong woman "
                   f"fails (#201)"),
        "worst": worst,
    }


def shot_plan(*, product_form: str, has_model: bool = True) -> dict:
    """The gallery a product deserves (#203, #204, #80).

    Two rules shape it. Model presence is not compulsory: for a blanket, a clean product-only
    hero outsells a modelled one, and product truth outranks brand recognition. And the plan
    is a list of *jobs* rather than a target count — #80 asks for minimum quality, not minimum
    count, so every frame here has a commercial job it must do or be dropped.
    """
    product_first = product_form in PRODUCT_FIRST_FORMS
    frames = [
        {"role": "hero", "job": "create desire and comprehension in one frame at grid size",
         "model": not product_first and has_model},
        {"role": "detail", "job": "prove the texture and stitch definition are real",
         "model": False},
        {"role": "scale", "job": "answer 'how big is it' without a stated dimension",
         "model": not product_first and has_model},
        {"role": "construction", "job": "show how it goes together where that is the risk",
         "model": False},
        {"role": "evidence", "job": "substantiate size, materials, files and chart quality",
         "model": False},
    ]
    if not product_first and has_model:
        frames.insert(1, {"role": "fit", "job": "show the garment on a body, truthfully",
                          "model": True})
    return {
        "product_form": product_form,
        "product_first": product_first,
        "frames": frames,
        "model_frames": sum(1 for f in frames if f["model"]),
        "note": ("A clean product-only hero is commercially stronger for this form, so the "
                 "model is not forced into it: product truth and category fit outrank "
                 "compulsory model presence (#204)."
                 if product_first else
                 "A modelled hero earns its place on this form, and every frame still has a "
                 "job it must do (#80)."),
    }


def status(packs: list[ReferencePack] | None = None,
           candidates: list[Candidate] | None = None) -> dict:
    pack = canonical(packs)
    return {
        "canonical_selected": pack is not None,
        "version": pack.version if pack else None,
        "candidates": [c.to_dict() for c in (candidates or [])],
        "identity_fields_required": list(IDENTITY_FIELDS),
        "drift_check": "operative" if pack else "unavailable — no reference pack",
        "note": ("Nothing has been selected, and nothing will select itself. A candidate that "
                 "became canonical by being first is an identity nobody chose, discovered a "
                 "hundred listings later."
                 if pack is None else
                 "The canonical identity is frozen; improving photography, posing and "
                 "wardrobe is allowed, redesigning her is the owner's decision."),
    }
