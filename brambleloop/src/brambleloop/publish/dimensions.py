"""Every number a buyer sees, traced to the one object that knows it.

Requirement 60. Every displayed measurement must trace to one canonical measurement object;
contradictory or contextless dimensions must be detected -- the requirement's own example is
a finished-size card showing 90x122 cm alongside an unexplained 180 cm marker -- and labels
must identify width, length, circumference, component, blocked state and size variant where
relevant.

`cir.geometry` is already the canonical object and already refuses what it cannot measure.
What was missing is the audit on the way out: geometry being correct says nothing about what
reached the card, and every defect this requirement names happens *after* the measurement is
right.

Three things it checks, in ascending order of how hard they are to see.

**A number with no canonical source.** The easiest and the most dangerous: it came from
somewhere nobody can check, and it is indistinguishable from a correct one. A displayed
measurement names the canonical measurement it traces to, or it is refused.

**A number with no context.** The 180 cm marker is not *wrong* -- it may be perfectly true of
something -- it is unreadable, and unreadable is worse than wrong because nobody can even
disagree with it. An axis and a component are required; blocked state and size variant are
required only where the product has them, because demanding a variant label on a
single-size product trains everybody to write "n/a" and stop reading the field.

**Two numbers that disagree about the same thing.** Same axis, same component, same blocked
state, same variant, different values. This is the contradiction the requirement names, and
it is invisible to any check that validates measurements one at a time -- which is every
check that existed here before.

Blocked state is not a nicety. Crochet changes size when it is blocked, by a material amount,
and a finished-size claim that does not say which state it describes is ambiguous by more than
the tolerance anybody would accept.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The axes a measurement can be along. Closed: a number whose axis nobody named is the
# unexplained marker the requirement is written about.
WIDTH = "width"
LENGTH = "length"
CIRCUMFERENCE = "circumference"
DEPTH = "depth"
DIAMETER = "diameter"

AXES: dict[str, str] = {
    WIDTH: "across, at the widest point unless the label says otherwise",
    LENGTH: "along, from one named end to the other",
    CIRCUMFERENCE: "around a closed form",
    DEPTH: "through, for anything with a third dimension worth stating",
    DIAMETER: "across a circle, which is not the same as its circumference",
}

BLOCKED = "blocked"
UNBLOCKED = "unblocked"
BLOCK_STATES: tuple[str, ...] = (BLOCKED, UNBLOCKED)

# How far a displayed value may sit from its canonical source before it is a different
# number rather than a rounding of the same one. Tighter than the size tolerance the truth
# gate allows for gauge variation, because this is about transcription, not about yarn.
TRACE_TOLERANCE_CM = 0.5


class DimensionRefused(ValueError):
    """A number with no source, no context, or a twin that disagrees with it."""


@dataclass(frozen=True)
class Canonical:
    """One measurement from the geometry object, which is where numbers are allowed to start."""

    key: str
    axis: str
    component: str
    value_cm: float
    blocked: str = UNBLOCKED
    size_variant: str = ""

    def __post_init__(self) -> None:
        if self.axis not in AXES:
            raise DimensionRefused(f"{self.key}: {self.axis!r} is not an axis: {sorted(AXES)}")
        if self.blocked not in BLOCK_STATES:
            raise DimensionRefused(
                f"{self.key}: {self.blocked!r} is not a blocked state: {list(BLOCK_STATES)}. "
                f"Crochet changes size when it is blocked, by more than any tolerance worth "
                f"having, so a measurement that does not say which state it describes is "
                f"ambiguous rather than approximate")
        if self.value_cm <= 0:
            raise DimensionRefused(f"{self.key}: {self.value_cm} cm is not a measurement")
        if not self.component.strip():
            raise DimensionRefused(f"{self.key}: name the component this measures")

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return (self.axis, self.component, self.blocked, self.size_variant)


@dataclass(frozen=True)
class Displayed:
    """One number that reaches a buyer, and the canonical measurement it claims to be."""

    where: str                 # the frame, card or line it appears on
    value_cm: float
    traces_to: str             # a Canonical.key
    axis: str = ""
    component: str = ""
    blocked: str = ""
    size_variant: str = ""

    def __post_init__(self) -> None:
        if not self.traces_to.strip():
            raise DimensionRefused(
                f"{self.where}: a displayed measurement names the canonical measurement it "
                f"traces to. A number with no source came from somewhere nobody can check, "
                f"and it is indistinguishable from a correct one")
        if self.value_cm <= 0:
            raise DimensionRefused(f"{self.where}: {self.value_cm} cm is not a measurement")


def audit(displayed: list[Displayed], canonical: list[Canonical], *,
          has_variants: bool = False) -> dict:
    """Every displayed number against the one object that knows it."""
    by_key = {c.key: c for c in canonical}
    duplicated = sorted({c.identity for c in canonical
                         if sum(1 for o in canonical if o.identity == c.identity) > 1})
    problems: list[dict] = []
    if duplicated:
        problems.append({
            "kind": "canonical_contradiction", "identities": [list(d) for d in duplicated],
            "why": ("the canonical object holds two different values for the same axis, "
                    "component, blocked state and variant. Everything downstream of this is "
                    "arbitrary")})

    for d in displayed:
        source = by_key.get(d.traces_to)
        if source is None:
            problems.append({
                "kind": "untraceable", "where": d.where, "value_cm": d.value_cm,
                "why": (f"traces to {d.traces_to!r}, which is not a canonical measurement. "
                        f"This is the unexplained marker: not necessarily wrong, and "
                        f"impossible to disagree with")})
            continue

        if abs(d.value_cm - source.value_cm) > TRACE_TOLERANCE_CM:
            problems.append({
                "kind": "does_not_match_source", "where": d.where,
                "displayed": d.value_cm, "canonical": source.value_cm,
                "why": (f"{d.value_cm} cm displayed against {source.value_cm} cm canonical, "
                        f"beyond the {TRACE_TOLERANCE_CM} cm transcription tolerance. Gauge "
                        f"variation is the truth gate's business; this is a different number")})

        missing = []
        if not (d.axis or source.axis):
            missing.append("axis")
        if not (d.component or source.component):
            missing.append("component")
        if has_variants and not (d.size_variant or source.size_variant):
            missing.append("size_variant")
        if missing:
            problems.append({
                "kind": "contextless", "where": d.where, "value_cm": d.value_cm,
                "missing": missing,
                "why": (f"{d.value_cm} cm with no {', '.join(missing)}. Unreadable is worse "
                        f"than wrong: nobody can even disagree with it")})

        stated = d.blocked or source.blocked
        if stated not in BLOCK_STATES:
            problems.append({
                "kind": "ambiguous_blocked_state", "where": d.where,
                "why": ("neither the display nor its source says whether this is blocked. "
                        "The difference is larger than any tolerance worth stating")})
        elif d.blocked and d.blocked != source.blocked:
            problems.append({
                "kind": "blocked_state_disagrees", "where": d.where,
                "displayed": d.blocked, "canonical": source.blocked,
                "why": "the card and the geometry describe different states of the fabric"})

    # The contradiction the requirement names, and the one no per-measurement check finds.
    seen: dict[tuple, list[Displayed]] = {}
    for d in displayed:
        source = by_key.get(d.traces_to)
        if source is None:
            continue
        key = (d.axis or source.axis, d.component or source.component,
               d.blocked or source.blocked, d.size_variant or source.size_variant)
        seen.setdefault(key, []).append(d)
    for key, rows in sorted(seen.items(), key=lambda kv: str(kv[0])):
        values = {round(r.value_cm, 2) for r in rows}
        if len(values) > 1:
            problems.append({
                "kind": "contradiction", "identity": list(key),
                "values": sorted(values), "where": [r.where for r in rows],
                "why": (f"{sorted(values)} cm displayed for the same {key[0]} of the same "
                        f"{key[1]}. Checking measurements one at a time cannot find this, "
                        f"and one at a time is how they are usually checked")})

    return {
        "displayed": len(displayed), "canonical": len(canonical),
        "problems": problems, "ok": not problems,
        "traced": sum(1 for d in displayed if d.traces_to in by_key),
        "note": ("every number a buyer sees traces to the geometry object, which is where "
                 "measurements are allowed to start. Geometry being correct says nothing "
                 "about what reached the card"),
    }


def labels_for(canonical: Canonical, *, has_variants: bool = False) -> str:
    """The label this measurement must carry, so nobody writes it differently twice."""
    parts = [f"{canonical.component} {canonical.axis}"]
    if has_variants and canonical.size_variant:
        parts.append(f"size {canonical.size_variant}")
    parts.append(canonical.blocked)
    return ", ".join(parts)


def state() -> dict:
    """What the auditor checks, and the one it exists for."""
    return {
        "requirement": 60,
        "axes": dict(AXES),
        "block_states": list(BLOCK_STATES),
        "trace_tolerance_cm": TRACE_TOLERANCE_CM,
        "canonical_source": "cir.geometry, which already refuses what it cannot measure",
        "refuses": [
            "a displayed number with no canonical source",
            "a number with no axis or component, which is unreadable rather than wrong",
            "a displayed value beyond the transcription tolerance from its source",
            "a measurement whose blocked state nobody stated",
            "two displayed numbers disagreeing about the same axis of the same component",
        ],
        "note": ("the contradiction check is the one that matters: two numbers disagreeing "
                 "about the same thing is invisible to any check that validates measurements "
                 "one at a time, and one at a time is how they are usually checked"),
    }
