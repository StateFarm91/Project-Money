"""The versioned whole Visual pipeline per product class, its tunable surface and its guard.

A *pipeline version* is the complete parameter set one product class's images are made with --
renderer layout, post-processing, encoding, and (for the generated/photoreal path) provider and
model, lighting, camera, composition, crop/thumbnail strategy, control method and Laura
reproduction method. Every image the department judges is stamped with the version that made
it, so "why does this image look like this" is answerable from rows.

**The tunable surface is declared, and nothing else is tunable.** `TUNABLES` lists every
parameter a challenger may vary, its hard bounds, the stage of the pipeline it belongs to, the
product classes it applies to and whether trying it is free (`deterministic_local`) or costs
money (`paid_provider`). The guard (`check_change`) refuses, before anything runs:

1. a parameter on any protected invariant of `improve.invariants` (Product Truth, customer
   safety, authorization, spend, evidence floors, every protected gate) -- the same guard the
   Learn policy loops use;
2. a parameter naming a Visual gate or the canonical identity (`VISUAL_PROTECTED`): a challenger
   may change how an image is *made*, never how it is *judged*. Laura identity stays a hard,
   independent gate; "a similar woman" fails it whatever pipeline produced her;
3. an undeclared parameter (unknown is protected, never free), one that does not apply to the
   class, and a value outside its bounds or declared choices.

Gates are not parameters. `GATES` is a code constant, read by `gates.py`; no pipeline version
carries a gate list, so no promotion can drop one.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ...improve import invariants
from . import models as M

# ---------------------------------------------------------------------------- product classes

# Order matters: the first class whose words match a product's title/slug wins, so the narrow
# classes (seasonal, loose garments) are tried before the broad ones.
PRODUCT_CLASSES: dict[str, dict] = {
    "seasonal": {"title": "Seasonal creative",
                 "words": ("christmas", "halloween", "easter", "ornament", "holiday",
                           "valentine", "advent", "pumpkin", "snowflake")},
    "loose_garments": {"title": "Loose garments",
                       "words": ("poncho", "shawl", "wrap", "kimono", "oversized", "cape")},
    "fitted_garments": {"title": "Fitted garments",
                        "words": ("sweater", "cardigan", "pullover", "vest", "dress", "top",
                                  "bodice", "jumper")},
    "accessories": {"title": "Accessories",
                    "words": ("hat", "beanie", "scarf", "cowl", "bag", "tote", "mitt",
                              "mittens", "headband", "gloves")},
    "coasters_tabletop": {"title": "Coasters / tabletop",
                          "words": ("coaster", "coasters", "placemat", "trivet", "doily")},
    "baskets_storage": {"title": "Baskets / storage",
                        "words": ("basket", "bin", "storage", "caddy", "bowl")},
    "blankets_home_textiles": {"title": "Blankets / home textiles",
                               "words": ("blanket", "throw", "afghan", "cushion", "pillow",
                                         "rug")},
    # Not a product category: imagery with Laura wearing/using a product. Model-bearing, so
    # the Laura identity and anatomy gates apply.
    "laura_on_model": {"title": "Laura-on-model imagery", "words": ()},
}
MODEL_BEARING_CLASSES = frozenset({"laura_on_model"})
UNCLASSIFIED = "unclassified"


def classify(cir_or_text) -> str:
    """The product class of a CIR (by slug and title words), or `unclassified`."""
    if isinstance(cir_or_text, str):
        text = cir_or_text
    else:
        text = f"{getattr(cir_or_text, 'slug', '')} {getattr(cir_or_text, 'title', '')}"
    words = set(re.findall(r"[a-z]+", text.lower()))
    for key, spec in PRODUCT_CLASSES.items():
        if words & set(spec["words"]):
            return key
    return UNCLASSIFIED


# ---------------------------------------------------------------------------- tunables

DETERMINISTIC = "deterministic_local"
PAID = "paid_provider"

ALL_PRODUCT = tuple(k for k in PRODUCT_CLASSES if k not in MODEL_BEARING_CLASSES)
DISCLOSED_CLASSES = ("baskets_storage", "coasters_tabletop", "blankets_home_textiles")
GENERATED_CLASSES = tuple(PRODUCT_CLASSES)


def _image_providers() -> tuple[str, ...]:
    try:
        from ...gateway import images
        return tuple(p.key for p in images.PROVIDERS)
    except Exception:  # noqa: BLE001 - a missing gateway is a smaller choice set, not a crash
        return ("registry_incumbent",)


@dataclass(frozen=True)
class Tunable:
    name: str
    stage: str
    execution: str
    classes: tuple[str, ...]
    default: object
    lo: float | None = None
    hi: float | None = None
    integer: bool = False
    choices: tuple = ()
    trials: tuple = ()          # the values a challenger tries, in order
    why: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "stage": self.stage, "execution": self.execution,
                "classes": list(self.classes), "default": self.default, "lo": self.lo,
                "hi": self.hi, "integer": self.integer, "choices": list(self.choices),
                "trials": list(self.trials), "why": self.why}


TUNABLES: dict[str, Tunable] = {t.name: t for t in (
    # -- free, executed locally on the deterministic disclosed renderer ----------------------
    Tunable("hero_gap_ratio", "renderer_layout", DETERMINISTIC, ("coasters_tabletop",),
            0.18, lo=0.0, hi=0.5, trials=(0.06, 0.0, 0.12, 0.24),
            why="spacing of a multi-piece hero; tighter pieces are larger in the thumbnail, "
                "touching pieces merge and fail the verifier's piece count"),
    Tunable("post_grain_sigma", "post_processing", DETERMINISTIC, DISCLOSED_CLASSES,
            0.0, lo=0.0, hi=6.0, trials=(1.5,),
            why="film grain after rendering; structure-preserving in `presentation`, but the "
                "disclosed-render contract refuses off-palette pixels"),
    Tunable("encode_png_level", "encode", DETERMINISTIC, DISCLOSED_CLASSES,
            9, lo=0, hi=9, integer=True, trials=(6,),
            why="lossless PNG compression level: bytes and encode time, never pixels"),
    # -- paid: planned and queued, executed only under owner spend authority ------------------
    Tunable("provider_model", "provider_model", PAID, GENERATED_CLASSES,
            "registry_incumbent", choices=("registry_incumbent",) + _image_providers(),
            why="which image model presents the protected product / Laura"),
    Tunable("lighting_preset", "lighting", PAID, GENERATED_CLASSES, "north_window_soft",
            choices=("north_window_soft", "overcast_daylight", "warm_lamp_evening",
                     "studio_softbox")),
    Tunable("camera_elevation_deg", "camera", PAID, GENERATED_CLASSES, 30.0, lo=0.0, hi=75.0,
            trials=(15.0, 45.0)),
    Tunable("composition_preset", "composition", PAID, GENERATED_CLASSES, "centered_hero",
            choices=("centered_hero", "rule_of_thirds", "flatlay_overhead",
                     "in_use_lifestyle")),
    Tunable("thumbnail_crop", "crop_thumbnail", PAID, GENERATED_CLASSES, "center_square",
            choices=("center_square", "product_bbox_square")),
    Tunable("control_method", "control", PAID, GENERATED_CLASSES, "protected_composite",
            choices=("protected_composite", "depth_from_twin", "edge_from_twin")),
    Tunable("laura_reproduction", "laura_reproduction", PAID,
            ("laura_on_model", "fitted_garments", "loose_garments", "accessories"),
            "frozen_v15_reference_pack",
            choices=("frozen_v15_reference_pack", "frozen_v15_pack_plus_stress_set"),
            why="how the SAME canonical Laura (laura-v15-a42aeac7) is reproduced; every "
                "choice conditions on her frozen references -- none selects another woman"),
)}

# Names a challenger may never vary even if somebody declared them: gates, the identity, the
# judges and their thresholds. Matched on the canonical key, as substrings.
VISUAL_PROTECTED: tuple[str, ...] = (
    "identity", "laura_id", "face", "canonical", "likeness", "struct", "anatomy", "photoreal",
    "realism", "verif", "contract", "qualif", "judge", "accept", "threshold", "min_", "max_",
    "floor", "gate", "skip", "bypass", "disable", "disclos", "benchmark", "yield_target",
    "thumb_px", "mobile_px",
)

# The gate order of the R&D loop (owner directive §9). Code, not data: no version carries it.
GATES: tuple[str, ...] = ("product_truth", "structure", "laura_identity", "anatomy",
                          "photorealism", "composition", "mobile_thumbnail", "disclosure",
                          "gallery_contract", "blind_benchmark")
# Advisory gates are recorded and reported but cannot accept or reject on their own (the
# benchmark needs observed galleries and a vision judge, both gated today).
ADVISORY_GATES = frozenset({"blind_benchmark"})


def _assert_tunables_safe() -> None:
    for name in TUNABLES:
        hit = invariants.protected_invariant(name)
        if hit is not None:
            raise AssertionError(f"tunable {name} lands on protected invariant {hit.key}")
        key = invariants.canonical_key(name)
        if any(w in key for w in VISUAL_PROTECTED):
            raise AssertionError(f"tunable {name} names a Visual gate or identity")


_assert_tunables_safe()


def applicable(product_class: str, *, execution: str | None = None) -> list[Tunable]:
    return [t for t in TUNABLES.values() if product_class in t.classes
            and (execution is None or t.execution == execution)]


def defaults(product_class: str) -> dict:
    return {t.name: t.default for t in applicable(product_class)}


# ---------------------------------------------------------------------------- the guard

@dataclass
class Refusal:
    param: str
    reason: str
    invariant: str

    def to_dict(self) -> dict:
        return {"param": self.param, "invariant": self.invariant, "reason": self.reason}


def check_change(product_class: str, changes: dict) -> list[Refusal]:
    """Every reason this change may not be tried. Empty means it may."""
    out: list[Refusal] = []
    if product_class not in PRODUCT_CLASSES:
        return [Refusal("", f"{product_class!r} is not a product class", "unknown_class")]
    if not isinstance(changes, dict) or not changes:
        return [Refusal("", "a challenger names what it changes", "malformed_value")]
    canon, twins = invariants.canonical_payload(changes)
    for ck in twins:
        out.append(Refusal(ck, "spelled by more than one key in one change", "malformed_value"))
    for raw, value in changes.items():
        key = invariants.canonical_key(raw)
        hit = invariants.protected_invariant(raw)
        if hit is not None:
            out.append(Refusal(raw, f"{raw!r} is on the protected invariant {hit.key!r} "
                                    f"({hit.protects})", hit.key))
            continue
        if any(w in key for w in VISUAL_PROTECTED):
            out.append(Refusal(raw, f"{raw!r} names a Visual gate, judge or the canonical "
                                    f"identity. A challenger changes how an image is made, "
                                    f"never how it is judged", "visual_gate"))
            continue
        t = TUNABLES.get(key)
        if t is None:
            out.append(Refusal(raw, f"{raw!r} is not a declared Visual tunable; undeclared is "
                                    f"treated as protected, never as free",
                               "undeclared_surface"))
            continue
        if product_class not in t.classes:
            out.append(Refusal(raw, f"{raw!r} does not apply to {product_class}",
                               "not_applicable"))
            continue
        if t.choices:
            if value not in t.choices:
                out.append(Refusal(raw, f"{value!r} is not one of {list(t.choices)}",
                                   "hard_bounds"))
            continue
        verdict = invariants.check(key, value, tunable={"param": key, "lo": t.lo, "hi": t.hi,
                                                        "integer": t.integer})
        if not verdict.ok:
            out.append(Refusal(raw, verdict.reason, verdict.invariant))
    return out


# ---------------------------------------------------------------------------- versions

INCUMBENT, CANDIDATE, RETIRED, REJECTED, ROLLED_BACK = (
    "incumbent", "candidate", "retired", "rejected", "rolled_back")


def digest_of(params: dict) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()


def label(product_class: str, generation: int, digest: str) -> str:
    return f"{product_class}/g{generation}-{digest[:8]}"


def _row(r) -> dict:
    return {"id": r.id, "product_class": r.product_class, "generation": r.generation,
            "label": r.label, "params": dict(r.params or {}), "digest": r.digest,
            "parent_id": r.parent_id, "state": r.state, "why": r.why,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "promoted_at": r.promoted_at.isoformat() if r.promoted_at else None,
            "retired_at": r.retired_at.isoformat() if r.retired_at else None,
            "promoted_on": r.promoted_on}


def ensure_incumbent(db, product_class: str) -> dict:
    """The class's running version; generation 1 from the declared defaults if none exists."""
    from sqlalchemy import select

    M.ensure_tables(db)
    with M.session(db) as s:
        row = s.scalar(select(M.VisualPipelineVersion).where(
            M.VisualPipelineVersion.product_class == product_class,
            M.VisualPipelineVersion.state == INCUMBENT).order_by(
                M.VisualPipelineVersion.id.desc()))
        if row is None:
            params = defaults(product_class)
            d = digest_of(params)
            row = M.VisualPipelineVersion(
                product_class=product_class, generation=1, label=label(product_class, 1, d),
                params=params, digest=d, parent_id=None, state=INCUMBENT,
                why="generation 1: the declared defaults (the launch-day pipeline)",
                promoted_at=datetime.now(timezone.utc))
            s.add(row)
            s.flush()
        return _row(row)


def get(db, version_id: int) -> dict | None:
    with M.session(db) as s:
        r = s.get(M.VisualPipelineVersion, version_id)
        return _row(r) if r is not None else None


def versions(db, product_class: str | None = None) -> list[dict]:
    from sqlalchemy import select

    with M.session(db) as s:
        q = select(M.VisualPipelineVersion).order_by(M.VisualPipelineVersion.id)
        if product_class:
            q = q.where(M.VisualPipelineVersion.product_class == product_class)
        return [_row(r) for r in s.scalars(q)]


def new_candidate(db, product_class: str, parent: dict, changes: dict, why: str) -> dict:
    params = {**parent["params"], **{invariants.canonical_key(k): v for k, v in changes.items()}}
    d = digest_of(params)
    with M.session(db) as s:
        row = M.VisualPipelineVersion(
            product_class=product_class, generation=parent["generation"] + 1,
            label=label(product_class, parent["generation"] + 1, d), params=params, digest=d,
            parent_id=parent["id"], state=CANDIDATE, why=why)
        s.add(row)
        s.flush()
        return _row(row)


def set_state(db, version_id: int, state: str) -> None:
    with M.session(db) as s:
        s.get(M.VisualPipelineVersion, version_id).state = state


def promote(db, candidate_id: int, *, promoted_on: dict) -> dict:
    """The candidate becomes the class's incumbent; the old incumbent is retired."""
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    with M.session(db) as s:
        row = s.get(M.VisualPipelineVersion, candidate_id)
        for other in s.scalars(select(M.VisualPipelineVersion).where(
                M.VisualPipelineVersion.product_class == row.product_class,
                M.VisualPipelineVersion.state == INCUMBENT)):
            other.state = RETIRED
            other.retired_at = now
        row.state = INCUMBENT
        row.promoted_at = now
        row.promoted_on = dict(promoted_on)
        s.flush()
        return _row(row)


def rollback(db, product_class: str, *, why: str, to_id: int | None = None) -> dict:
    """Restore the version the incumbent replaced (or `to_id`), recording why."""
    from sqlalchemy import select

    if not (why or "").strip():
        raise ValueError("a rollback names why it happened")
    now = datetime.now(timezone.utc)
    with M.session(db) as s:
        cur = s.scalar(select(M.VisualPipelineVersion).where(
            M.VisualPipelineVersion.product_class == product_class,
            M.VisualPipelineVersion.state == INCUMBENT))
        if cur is None:
            return {"rolled_back": False, "why": "no incumbent"}
        target_id = to_id or cur.parent_id
        target = s.get(M.VisualPipelineVersion, target_id) if target_id else None
        if target is None or target.product_class != product_class:
            return {"rolled_back": False, "why": "nothing to roll back to: a first version "
                                                 "has no predecessor"}
        cur.state = ROLLED_BACK
        cur.retired_at = now
        cur.why = (cur.why + f" | rolled back {now.isoformat()}: {why.strip()}")[:4000]
        target.state = INCUMBENT
        target.retired_at = None
        s.flush()
        return {"rolled_back": True, "from": _row(cur), "to": _row(target),
                "why": why.strip()}
