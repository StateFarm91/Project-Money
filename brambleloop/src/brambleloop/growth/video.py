"""Video modules with one canonical source, and the clip that outlives its pattern.

Requirement 248. Flagships and technique-heavy products generate reusable modules -- a
product reveal, a technique explanation, progress checkpoints, troubleshooting and
finished-result clips -- repurposed across platforms while keeping a canonical tutorial, with
assisted conversion and support reduction tracked.

The instruction that carries real weight is *keeping a canonical tutorial*, and the reason is
not tidiness. Five platform-specific videos with no canonical source diverge, and they
diverge silently: a pattern is corrected, the written instructions are reissued, and the
troubleshooting clip goes on telling three thousand people to do the thing that was wrong. A
clip that outlives its pattern is worse than no clip, because it is trusted and it is
specific.

That is the same problem `ops.artefacts` already solves for a PDF, so a video module is
recorded there like any other derived artefact, against the fingerprints of the design and
the canonical tutorial it was cut from. When the design moves, every clip cut from it is
stale by the same mechanism that makes the chart stale, and the sentinel that finds one finds
the others.

**Repurposing has to mean appropriately.** A twelve-minute technique explanation cut to
fifteen seconds is not a short; it is a trailer for nothing, and it converts nobody while
costing the same to make. Each module names the platforms whose shape it genuinely fits, and
a placement outside that list is refused with the reason rather than produced.

**The troubleshooting modules come from the same place the search clusters do.** The
questions worth answering on video are the ones makers demonstrably asked, counted from
observed reviews rather than imagined, so `growth.clusters` supplies them and a troubleshooting
clip for a problem nobody has reported is refused.

Nothing here produces a video. There is no video capability, no channel and no audience, so
a module is a plan: what it covers, what it was cut from, where it may go, and what it is
allowed to claim. Assisted conversion and support reduction both need people, and are
reported as unmeasurable rather than as zeroes.
"""
from __future__ import annotations

from dataclasses import dataclass

from .clusters import QUESTIONS

# The five the requirement names, with the shape each one actually has and where that shape
# fits. A platform list is a claim about length and attention, not about taste.
MODULES: dict[str, dict] = {
    "reveal": {
        "what": "the finished object, shown once, without instruction",
        "native_seconds": (15, 45),
        "platforms": ("shorts", "pinterest", "social"),
        "why": "it is an image that moves, and it is the one module a short is actually for",
    },
    "technique": {
        "what": "one technique taught properly, at the pace somebody can follow",
        "native_seconds": (240, 900),
        "platforms": ("youtube",),
        "why": ("a twelve-minute explanation cut to fifteen seconds is a trailer for "
                "nothing: it converts nobody and costs the same to make"),
    },
    "progress": {
        "what": "a checkpoint: what it should look like by row forty",
        "native_seconds": (30, 120),
        "platforms": ("shorts", "social"),
        "why": "it answers 'is mine going wrong', which is the question that stops people",
    },
    "troubleshooting": {
        "what": "one reported problem, and what to do about it",
        "native_seconds": (60, 300),
        "platforms": ("youtube", "social"),
        "why": ("the problems are the ones makers reported, counted rather than imagined, "
                "and this is the module that reduces support if any module does"),
    },
    "finished_result": {
        "what": "somebody else's finished object, with their permission",
        "native_seconds": (10, 30),
        "platforms": ("shorts", "pinterest", "social"),
        "why": "it is proof rather than instruction, and proof is short",
    },
}

PLATFORMS: tuple[str, ...] = ("youtube", "shorts", "pinterest", "social")

# The module every other one is cut from. Without it the set diverges silently.
CANONICAL = "technique"

# What the requirement asks to be measured, and what each needs.
MEASURES: dict[str, str] = {
    "assisted_conversion": "a visit from a video that ends in an order",
    "support_reduction": "support cases before and after the clip existed, on the same pattern",
}


class VideoRefused(ValueError):
    """A module nobody named, a placement its shape does not fit, or a clip with no source."""


@dataclass(frozen=True)
class Module:
    """One planned video module: what it covers and what it was cut from."""

    product_slug: str
    kind: str
    platform: str
    canonical_ref: str = ""        # the canonical tutorial this was cut from
    covers: str = ""               # for troubleshooting: which reported problem

    def __post_init__(self) -> None:
        if self.kind not in MODULES:
            raise VideoRefused(f"{self.kind!r} is not a module: {sorted(MODULES)}")
        if self.platform not in PLATFORMS:
            raise VideoRefused(f"{self.platform!r} is not a platform: {list(PLATFORMS)}")


def check(module: Module) -> dict:
    """Whether this module may be planned, and what is wrong with it when it may not."""
    spec = MODULES[module.kind]
    reasons: list[str] = []

    if module.platform not in spec["platforms"]:
        reasons.append(
            f"a {module.kind} module does not fit {module.platform}: {spec['why']}. It "
            f"belongs on {list(spec['platforms'])}")

    if module.kind != CANONICAL and not module.canonical_ref.strip():
        reasons.append(
            f"no canonical tutorial named. Five platform videos with no canonical source "
            f"diverge silently: the pattern is corrected, the written instructions are "
            f"reissued, and this clip goes on telling people to do the thing that was wrong")

    if module.kind == "troubleshooting":
        if not module.covers:
            reasons.append("a troubleshooting module has to name the problem it covers")
        elif module.covers not in QUESTIONS:
            reasons.append(
                f"{module.covers!r} is not a problem makers have reported: "
                f"{sorted(QUESTIONS)}. A troubleshooting clip for a problem nobody has had "
                f"is a clip about a problem that does not exist")

    return {
        "product_slug": module.product_slug, "kind": module.kind,
        "platform": module.platform, "ok": not reasons, "reasons": reasons,
        "native_seconds": list(spec["native_seconds"]),
        "covers": module.covers,
    }


def plan(product_slug: str, *, canonical_ref: str, reported: dict[str, int]) -> dict:
    """The module set for one product, with troubleshooting seeded from what was reported."""
    from .clusters import RECURRING_AT

    unknown = sorted(set(reported) - set(QUESTIONS))
    if unknown:
        raise VideoRefused(f"{unknown} are not reported problems")

    modules = []
    for kind, spec in MODULES.items():
        if kind == "troubleshooting":
            continue
        for platform in spec["platforms"]:
            modules.append(check(Module(product_slug, kind, platform,
                                        canonical_ref="" if kind == CANONICAL
                                        else canonical_ref)))
    worth_answering = [k for k, n in sorted(reported.items(), key=lambda kv: -kv[1])
                       if n >= RECURRING_AT]
    for problem in worth_answering:
        for platform in MODULES["troubleshooting"]["platforms"]:
            modules.append(check(Module(product_slug, "troubleshooting", platform,
                                        canonical_ref=canonical_ref, covers=problem)))

    return {
        "product_slug": product_slug,
        "canonical": canonical_ref,
        "modules": modules,
        "planned": sum(1 for m in modules if m["ok"]),
        "troubleshooting_for": worth_answering,
        "note": ("nothing reported often enough to answer on video, which is a finding about "
                 "the observation rather than about the product"
                 if not worth_answering else ""),
    }


def record(db, module: Module, *, design_fingerprint: str, canonical_fingerprint: str):
    """Record a produced module as a derived artefact, so it goes stale when its source does.

    Deliberately the same table and the same sentinel as the PDF and the chart. A clip that
    outlives its pattern is the same defect as a stale PDF, and it should be found by the
    same sweep rather than by somebody remembering that videos exist.
    """
    from ..ops import artefacts

    return artefacts.record(
        db, artefact_class="marketing_asset",
        artefact_key=f"video:{module.product_slug}:{module.kind}:{module.platform}",
        product_slug=module.product_slug,
        inputs={f"cir:{module.product_slug}": design_fingerprint,
                f"asset:{module.canonical_ref or 'canonical'}": canonical_fingerprint})


def measurement() -> dict:
    """What the requirement asks to be measured, and why neither can be yet."""
    return {
        "measures": dict(MEASURES),
        "measurable": False,
        "why": ("both need people. Assisted conversion needs a visit that ends in an order, "
                "and support reduction needs support cases on the same pattern before and "
                "after the clip existed -- there are no orders and no cases"),
        "needs": ["a published video with views", "an order attributable to a view",
                  "support cases on a pattern that has a clip"],
    }


def state() -> dict:
    """The modules, where each one fits, and what cannot be made."""
    return {
        "modules": {k: {"what": v["what"], "native_seconds": list(v["native_seconds"]),
                        "platforms": list(v["platforms"]), "why": v["why"]}
                    for k, v in MODULES.items()},
        "canonical": CANONICAL,
        "platforms": list(PLATFORMS),
        "troubleshooting_seeded_from": ("growth.clusters.QUESTIONS, which are the problems "
                                        "makers demonstrably reported"),
        "recorded_as": ("ops.artefacts, so a clip goes stale when the design it was cut from "
                        "moves -- found by the same sweep that finds a stale PDF"),
        "measurement": measurement(),
        "cannot_do_yet": ("there is no video capability, no channel and no audience, so a "
                          "module here is a plan: what it covers, what it was cut from, "
                          "where it may go and what it may claim"),
        "note": ("A clip that outlives its pattern is worse than no clip, because it is "
                 "trusted and it is specific: the pattern is corrected, the instructions are "
                 "reissued, and the troubleshooting video goes on telling people to do the "
                 "thing that was wrong (#248)."),
    }
