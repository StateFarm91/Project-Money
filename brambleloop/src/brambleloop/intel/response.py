"""When the benchmark proves demand, what this company is obliged to do about it.

Requirements 306, 307, 308, 309. The mission's whole commercial argument is that watching a
successful shop tells you where the demand is, and the argument only pays if something
*happens* when it does. So #306 is written as an obligation — the relevant pod MUST consider
entering a proven arena — and the interesting part is what "consider" is allowed to mean.

The line this module has to hold is the one the spec draws itself, and it is finer than the
ones already drawn elsewhere. A competitor's photographs, written instructions and distinctive
design are protected. But "cropped V-neck button cardigan" and "striped colour-blocking" are
not somebody's property; they are what the product category *is*, visible to anyone who looks
at a finished object, and refusing to make a cardigan because a competitor makes one would be
the intelligence mission concluding that the useful answer is never to act on it.

So a third boundary, in the same mechanical shape as the teardown library's and the culture
rights router's, but drawn in a different place: **generic characteristics of the finished
object may be preserved; anything that identifies the source may not.** A striped cropped
cardigan is an arena. Their stripe sequence is theirs.

Three other rules.

**Entering is a decision with a recorded reason, including when the answer is no (#306).**
"MUST consider" is satisfied by a considered refusal and not by silence, which is the only
version that is checkable — and silence is what a queue produces when nothing forces a row.

**Every proven concept is asked the seasonal question (#307).** Not "is this seasonal" but
"how does this speak to the *next* season", through palette, trim, motif, gift context and
bundle. The mandatory lenses are named so an agent cannot answer for the easy one and stop.

**The pipeline is a named sequence with a gate at each step (#309).** Written out because the
failure of a long pipeline is never the whole thing collapsing; it is one stage quietly
becoming optional, and a stage nobody named cannot be noticed missing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .pods import BY_KEY, POD_KEYS, route

# Broad arenas #306 names, plus the rest of the category. An arena is a market, not a design:
# it is what a buyer types and what a category is made of.
ARENAS: dict[str, str] = {
    "cardigan": "an open-front garment, buttoned or not",
    "sweater": "a closed pullover garment",
    "stocking": "a Christmas stocking",
    "blanket": "a large flat warmth object",
    "ornament": "a hanging decoration",
    "bag": "a carried container",
    "hat": "a head covering",
    "coaster": "a small flat surface protector",
    "decor": "an object whose job is to be seen",
    "amigurumi": "a sculptural soft figure",
    "scarf": "a long neck garment",
    "pillow": "a covered cushion",
}

# Characteristics of a *finished object* that anybody can see and that no one owns. These may
# be preserved when entering an arena, which is what #306 explicitly permits.
GENERIC_CHARACTERISTICS: dict[str, str] = {
    "silhouette": "cropped, longline, oversized, fitted -- the outline of the category",
    "neckline": "V-neck, crew, boat, collared",
    "closure": "buttons, open front, zip, tie",
    "colour_blocking": "striped, colour-blocked, ombre, solid -- the arrangement, not the hues",
    "texture_class": "cabled, bobbled, ribbed, textured, smooth",
    "sleeve_form": "long, short, balloon, raglan, drop-shoulder",
    "size_range": "the span of sizes offered",
    "yarn_weight_class": "DK, worsted, chunky -- a standard, not a brand",
}

# Language that means the source is being reproduced rather than the arena entered. Same
# shape as the teardown content boundary, and drawn tighter because this is the module whose
# whole job is to act on what a competitor did.
_IDENTIFIES_THE_SOURCE = (
    "their stripe sequence", "their exact", "their colourway", "their palette",
    "same colours as", "copy their", "match their design", "their photograph",
    "their styling", "recreate their", "as close as possible to",
)

# #307's mandatory lenses. Named individually because an agent asked to "seasonalise" answers
# for the palette and stops, and palette alone is the recolour this whole build is trying to
# stop producing.
SEASONAL_LENSES: dict[str, str] = {
    "colour_palette": "the season's colours, chosen rather than defaulted",
    "styling": "how it is presented for the occasion",
    "trim": "edging, closures and finishing that read as the season",
    "motif_vocabulary": "what it depicts, if anything",
    "gift_context": "who gives this to whom at this time of year",
    "supporting_accessories": "what it is worn or used with",
    "bundles": "what it is sold beside",
    "merchandising": "how the listing frames the occasion",
}

# #309's pipeline. Each stage names the gate that must pass before the next one starts, so a
# stage cannot quietly become optional -- which is how a long pipeline actually fails.
PIPELINE: tuple[tuple[str, str], ...] = (
    ("observation", "a dated benchmark observation exists"),
    ("pod_routing", "the listing is assigned to a specialist pod"),
    ("market_decomposition", "form, function and merchandising are recorded as mechanisms"),
    ("demand_and_season_fit", "the arena is scored and placed on the rolling calendar"),
    ("seasonal_tournament", "concepts compete on all eight seasonal lenses"),
    ("make_time_estimate", "a customer's make time is estimated for the lane"),
    ("launch_dates", "preferred and latest effective launch dates are computed"),
    ("cir_engineering", "an original CIR is authored; nothing is transcribed"),
    ("certification", "the full gate chain grants a release certificate"),
    ("premium_assets", "Brambleloop-owned assets pass Asset Truth and Creative Parity"),
    ("benchmark_challenge", "the pre-launch challenge passes or is deliberately traded"),
    ("seo_content", "the listing answers reachable queries"),
    ("launch", "published -- owner-gated, and refused in shadow mode"),
    ("measurement", "performance is attributed and fed back"),
)

PIPELINE_STAGES: tuple[str, ...] = tuple(name for name, _ in PIPELINE)


class ResponseRefused(Exception):
    """An arena entered by reproducing the source, or a consideration that is silence."""


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())


def check_generic(description: str) -> None:
    """Refuse a description that identifies the source rather than the arena (#306).

    The permitted side is wide on purpose: a cropped striped cardigan is what the category
    is, and refusing it would make the intelligence mission conclude that the useful answer
    is never to act on what it found. The forbidden side is anything that only makes sense
    as a reference to one shop's product.
    """
    low = " ".join(_normalise(description).split())
    for phrase in _IDENTIFIES_THE_SOURCE:
        if " ".join(_normalise(phrase).split()) in low:
            raise ResponseRefused(
                f"{phrase!r} identifies the source rather than the arena. Generic "
                f"characteristics of a finished object -- silhouette, neckline, closure, "
                f"colour-blocking, texture class -- are what the category is made of and may "
                f"be preserved. What may not is anything that only makes sense as a "
                f"reference to their product (#306)")


@dataclass
class ArenaDecision:
    """A pod's recorded answer to a proven arena. Including 'no', which is the point."""

    arena: str
    pod: str
    enter: bool
    reason: str
    preserved: tuple[str, ...] = ()
    differentiator: str = ""

    def to_dict(self) -> dict:
        return {"arena": self.arena, "pod": self.pod, "enter": self.enter,
                "reason": self.reason,
                "preserved_characteristics": [
                    {"key": k, "meaning": GENERIC_CHARACTERISTICS[k]} for k in self.preserved],
                "differentiator": self.differentiator}


def consider_arena(arena: str, *, enter: bool, reason: str,
                   preserved: tuple[str, ...] = (), differentiator: str = "",
                   pod: str = "") -> ArenaDecision:
    """The obligation in #306, as a row rather than an intention.

    A considered refusal satisfies "MUST consider" and silence does not, which is the only
    version anybody can check — and silence is exactly what a queue produces when nothing
    forces a row to exist.
    """
    if arena not in ARENAS:
        raise ResponseRefused(
            f"{arena!r} is not a recorded arena: {sorted(ARENAS)}. An arena is a market a "
            f"buyer shops in, not a design")
    pod = pod or route(arena, arena)
    if pod not in POD_KEYS:
        raise ResponseRefused(f"{pod!r} is not a pod: {sorted(POD_KEYS)}")
    if len(reason.split()) < 8:
        raise ResponseRefused(
            f"{arena}: a decision needs a reason somebody can disagree with later. "
            f"'MUST consider' is satisfied by a considered refusal and not by a short one")
    check_generic(reason)
    check_generic(differentiator)

    unknown = [c for c in preserved if c not in GENERIC_CHARACTERISTICS]
    if unknown:
        raise ResponseRefused(
            f"{sorted(unknown)} are not generic characteristics of a finished object: "
            f"{sorted(GENERIC_CHARACTERISTICS)}. The closed list is what keeps 'preserved "
            f"characteristics' from becoming a place to put their design")

    if enter and not differentiator:
        raise ResponseRefused(
            f"{arena}: entering an arena the benchmark already serves needs something this "
            f"company does better or differently. Entering on parity is the floor #163 "
            f"refuses, arriving through the competitive door")

    return ArenaDecision(arena=arena, pod=pod, enter=enter, reason=reason.strip(),
                         preserved=tuple(preserved), differentiator=differentiator.strip())


def seasonalise(concept: str, arena: str, lenses: dict) -> dict:
    """Ask the seasonal question of a proven concept, on every lens (#307).

    An agent told to "seasonalise" answers for the palette and stops, and a palette answer
    alone is the recolour this whole build exists to stop producing. So the lenses are
    enumerated and an unanswered one is reported rather than assumed irrelevant.
    """
    if arena not in ARENAS:
        raise ResponseRefused(f"{arena!r} is not a recorded arena")
    unknown = [k for k in lenses if k not in SEASONAL_LENSES]
    if unknown:
        raise ResponseRefused(
            f"{sorted(unknown)} are not seasonal lenses: {sorted(SEASONAL_LENSES)}")

    answered, absent = {}, []
    for key, meaning in SEASONAL_LENSES.items():
        value = str(lenses.get(key) or "").strip()
        if not value:
            absent.append(key)
            continue
        check_generic(value)
        answered[key] = value

    only_palette = set(answered) <= {"colour_palette"}
    return {
        "concept": concept,
        "arena": arena,
        "answered": answered,
        "unanswered": absent,
        "complete": not absent,
        "palette_only": only_palette and bool(answered),
        "note": ("Only the palette was answered, which is a recolour with a season's name on "
                 "it -- the exact output this build measured as its creativity defect (#307)."
                 if only_palette and answered else
                 f"{len(answered)} of {len(SEASONAL_LENSES)} lenses answered"),
    }


@dataclass
class PipelineRun:
    """One MJs signal moving through #309's sequence."""

    signal: str
    completed: list = field(default_factory=list)

    @property
    def next_stage(self) -> str | None:
        for name in PIPELINE_STAGES:
            if name not in self.completed:
                return name
        return None

    def advance(self, stage: str, *, gate_passed: bool, evidence: str = "") -> dict:
        if stage not in PIPELINE_STAGES:
            raise ResponseRefused(
                f"{stage!r} is not a pipeline stage: {list(PIPELINE_STAGES)}")
        expected = self.next_stage
        if stage != expected:
            raise ResponseRefused(
                f"{stage!r} cannot run before {expected!r}. The failure of a long pipeline is "
                f"never the whole thing collapsing; it is one stage quietly becoming "
                f"optional, and a stage that can be skipped is optional (#309)")
        if not gate_passed:
            return {"stage": stage, "advanced": False,
                    "gate": dict(PIPELINE)[stage],
                    "why": (f"the {stage!r} gate did not pass: {dict(PIPELINE)[stage]}. The "
                            f"run stops here rather than continuing with the stage marked "
                            f"amber")}
        self.completed.append(stage)
        return {"stage": stage, "advanced": True, "evidence": evidence,
                "next": self.next_stage}

    def to_dict(self) -> dict:
        return {"signal": self.signal, "completed": list(self.completed),
                "next_stage": self.next_stage,
                "stages": [{"stage": n, "gate": g, "done": n in self.completed}
                           for n, g in PIPELINE],
                "complete": self.next_stage is None}


def describe() -> dict:
    return {
        "arenas": ARENAS,
        "generic_characteristics": GENERIC_CHARACTERISTICS,
        "seasonal_lenses": SEASONAL_LENSES,
        "pipeline": [{"stage": n, "gate": g} for n, g in PIPELINE],
        "pods": sorted(BY_KEY),
        "boundary": ("Generic characteristics of a finished object may be preserved -- a "
                     "cropped striped cardigan is what the category is, and refusing it "
                     "would make the intelligence mission conclude that the useful answer "
                     "is never to act on what it found. Anything that only makes sense as a "
                     "reference to their product may not (#306)."),
    }
