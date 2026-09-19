"""What self-improvement may never do, enforced before a hypothesis is written down.

Requirement 102 draws the line: the system may improve code, prompts, scoring, workflows and
agent configuration within tested, reversible, spend-authorised bounds — and may never weaken
policy gates, fabricate evidence, bypass owner authority or disable safety checks.

That sentence describes the central hazard of a system that optimises its own metrics. Every
number this company reports is produced by a check, so the cheapest way to improve any of them
is to loosen the check that produces it. A release-certification rate rises beautifully when
the certifier stops refusing things. The improvement is real, the measurement is real, the
company is worse, and nothing in the loop would notice — because from inside, weakening a gate
and fixing a defect look identical: a change, followed by a better number.

So the boundary is a refusal at the point a hypothesis is *proposed*, before any work is done
on it. Not a review afterwards, because by then somebody has built the thing and the argument
becomes about the work rather than about the rule.

The protected surfaces are named rather than inferred. A blocklist of file paths would be
evaded by a refactor; these are the *capabilities* that may not be traded away, whatever file
they end up living in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# The gates whose strictness is not an optimisation variable. Each exists because something
# went wrong once, or would have.
PROTECTED_GATES: tuple[str, ...] = (
    "deterministic_validation",     # the compiler decides what a pattern says
    "reverse_compilation",          # the document and the design must agree
    "asset_truth",                  # an image must be what it claims
    "policy_gate",                  # platform policy and legal compliance
    "claim_gates",                  # no size or technique claim the twin cannot support
    "shadow_mode",                  # publication refusal while unpromoted
    "spend_ceilings",               # budget enforced in code
    "owner_authority",              # RED actions belong to the owner
    "evidence_grading",             # a substitute may never close a mandate
    "confidence_ladder",            # the CA$5K model counts rows
    "creative_jury",                # one rejection ends a concept
    "benchmark_quarantine",         # competitor files stay unreachable
)

# Phrases that describe loosening rather than improving. Matched against the hypothesis text,
# which is where the intent is actually stated.
_LOOSENING = (
    "lower the threshold", "raise the threshold to pass", "relax", "loosen", "soften",
    "disable", "skip the", "bypass", "turn off", "remove the check", "remove the gate",
    "stop refusing", "allow through", "widen the tolerance", "reduce strictness",
    "make the gate optional", "waive", "suppress the warning", "ignore the finding",
)

_FABRICATION = (
    "synthetic review", "fake review", "seed customers", "simulate orders",
    "backfill revenue", "sample data as evidence", "placeholder metric",
    "assume conversion", "estimate the sample", "fill in the missing",
)


class GovernanceRefused(PermissionError):
    """A hypothesis that improves a number by damaging the thing it measures."""


@dataclass(frozen=True)
class Boundary:
    ok: bool
    reason: str = ""
    rule: str = ""

    def raise_if_refused(self) -> None:
        if not self.ok:
            raise GovernanceRefused(f"{self.reason} [{self.rule}]")


def _mentions(text: str, needles: tuple[str, ...]) -> str | None:
    low = (text or "").lower()
    for needle in needles:
        if needle in low:
            return needle
    return None


# Verbs that weaken, and the objects they weaken, checked as a *pair within a sentence*
# rather than as a fixed phrase. Found by writing "lower the thumbnail threshold": the
# literal-phrase list caught "lower the threshold on the thumbnail check" and missed the
# same sentence with the words reordered. A weakening detector that a paraphrase defeats is
# a detector that fails exactly when somebody is rewriting a hypothesis to get it through,
# which is the only time it matters.
_WEAKEN_VERBS: tuple[str, ...] = (
    "lower", "reduce", "relax", "loosen", "soften", "weaken", "drop", "ease",
    "widen", "shrink", "skip", "bypass", "disable", "remove", "waive", "suppress",
)

_GATE_OBJECTS: tuple[str, ...] = (
    "threshold", "thresholds", "check", "checks", "gate", "gates", "validation",
    "tolerance", "strictness", "standard", "standards", "bar", "requirement",
    "requirements", "refusal", "refusals", "guard", "guards",
)

_SENTENCE_SPLIT = re.compile(r"[.;!?\n]+")


# How far after a weakening verb its object may sit and still be the thing being weakened.
# "lower the thumbnail threshold" is three tokens; "reduce defects reaching release" never
# reaches a gate object at all, which is the case that matters -- an early version of this
# paired any verb with any object in the sentence and refused "tightening the thumbnail check
# should reduce defects reaching release", a hypothesis that *strengthens* a gate.
_GOVERNS_WITHIN = 4


def _weakens(text: str) -> str | None:
    """A weakening verb governing a gate object, judged by proximity rather than by phrase.

    Proximity rather than a literal phrase because a paraphrase defeats a phrase list, and
    rewriting the sentence is exactly what somebody does when a hypothesis is refused.
    Proximity rather than same-sentence co-occurrence because the verb has to be acting on
    the gate: "reduce defects" and "the thumbnail check" can share a sentence in a proposal
    that makes the check stricter.
    """
    for sentence in _SENTENCE_SPLIT.split((text or "").lower()):
        tokens = re.findall(r"[a-z]+", sentence)
        for index, token in enumerate(tokens):
            if token not in _WEAKEN_VERBS:
                continue
            window = tokens[index + 1:index + 1 + _GOVERNS_WITHIN]
            obj = next((w for w in window if w in _GATE_OBJECTS), None)
            if obj:
                return f"{token} the {obj}"
    return None


def check(hypothesis: str, *, touches: tuple[str, ...] = (),
          reversible: bool = True, spend_cad: float = 0.0,
          spend_authorised_cad: float = 0.0) -> Boundary:
    """Decide whether this change is one the system is allowed to make to itself.

    Ordered so the most serious refusal is the one reported: weakening a gate is worse than
    being irreversible, and fabricating evidence is worse than both.
    """
    fabricating = _mentions(hypothesis, _FABRICATION)
    if fabricating:
        return Boundary(False,
                        f"the hypothesis proposes {fabricating!r}, which manufactures the "
                        f"evidence rather than the result. Every number this company reports "
                        f"is only worth what produced it",
                        "#102: may never fabricate evidence")

    protected = [name for name in touches if name in PROTECTED_GATES]
    loosening = _mentions(hypothesis, _LOOSENING) or _weakens(hypothesis)
    if protected and loosening:
        return Boundary(False,
                        f"this proposes to {loosening!r} on {protected}, which improves the "
                        f"metric by damaging the thing that produces it. From inside the "
                        f"loop, weakening a gate and fixing a defect look identical: a "
                        f"change, then a better number",
                        "#102: may never weaken a policy gate")
    if loosening and not protected:
        # Loosening something unprotected is ordinary tuning, and allowed — but the surfaces
        # it touches have to have been declared, or the check above is trivially avoided by
        # saying nothing.
        if not touches:
            return Boundary(False,
                            f"the hypothesis proposes to {loosening!r} without declaring what "
                            f"it touches. An undeclared surface cannot be checked against the "
                            f"protected list, which makes the list advisory",
                            "#102: the surfaces a change touches must be declared")

    if not reversible:
        return Boundary(False,
                        "an improvement with no way back is not an experiment, it is a "
                        "decision — and #93 requires every promotion to store its rollback "
                        "path before it is applied",
                        "#93: automatic rollback")

    if spend_cad > spend_authorised_cad:
        return Boundary(False,
                        f"CA${spend_cad:.2f} exceeds the CA${spend_authorised_cad:.2f} "
                        f"authorised for improvement work. Continuous learning is not "
                        f"permission to burn tokens (#99)",
                        "#99: improvement budget")

    return Boundary(True)


def check_owner_authority(action: str) -> Boundary:
    """Refuse a self-improvement that quietly grants the system an owner-only power."""
    owner_only = ("publish", "kyc", "identity verification", "banking", "payout",
                  "legal acceptance", "advertising budget", "phase to production",
                  "graduate the phase", "connect etsy")
    hit = _mentions(action, owner_only)
    if hit:
        return Boundary(False,
                        f"{hit!r} is the owner's to decide. A system that can widen its own "
                        f"authority has none",
                        "#102: may never bypass owner authority")
    return Boundary(True)


def protected_surface(name: str) -> bool:
    return name in PROTECTED_GATES


def describe() -> dict:
    """The boundary, stated where the owner can read it rather than inferred from code."""
    return {
        "may": ["code", "prompts", "scoring weights", "workflows", "agent configuration",
                "cadences", "routing", "thresholds on unprotected surfaces"],
        "may_never": [
            "weaken a protected gate",
            "fabricate evidence, reviews, customers or revenue",
            "bypass owner authority",
            "disable a safety check",
            "spend beyond the authorised improvement budget",
            "promote a change with no rollback path",
        ],
        "protected_gates": list(PROTECTED_GATES),
        "why": ("Every number this company reports is produced by a check, so the cheapest "
                "way to improve any of them is to loosen the check. The improvement would be "
                "real, the measurement would be real, and the company would be worse."),
    }


_WORD_BOUNDARY = re.compile(r"\b")  # kept for future stricter matching
