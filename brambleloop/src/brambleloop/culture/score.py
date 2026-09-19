"""Scoring a cultural moment, and refusing to score one that has not been observed.

Requirement 136. The score exists to stop two opposite failures at once: chasing every meme,
and being so slow that every signal arrives after saturation. Eleven components, and the
interesting design decisions are about which ones are allowed to be averaged.

**Two components are gates, not weights.** Rights feasibility and the make-time window cannot
be compensated for by anything else. A signal scoring five out of five on every commercial
dimension and zero on rights is not a four; it is a lawsuit with good margins. A signal whose
window closes before a customer could finish the object is not a strong opportunity with a
scheduling problem — the window *is* the opportunity. Averaging either of them in is how a
strong-looking total gets built on top of a fatal component, which is the same
minimum-not-average rule the confidence ladder and the creative jury already use.

**An unobserved component is absent, never zero and never a default.** A score computed over
the three components somebody happened to have data for reports the same number as a score
computed over eleven, and the difference between them is the entire question. So the result
carries `evidence_weight` — the fraction of components with a real observation behind them —
and a score under half observed says so in the same breath as the number.

The weights are a starting point, explicitly. #147 requires post-launch outcomes to update
them, and a weight that was never revised after the first ten launches is a guess that has
been promoted to a constant by the passage of time.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The eleven components #136 names. `gate` marks the two that cannot be traded away.
COMPONENTS: tuple[tuple[str, float, bool, str], ...] = (
    ("search_momentum",        0.16, False, "how fast interest is rising, not how high it is"),
    ("recurrence",             0.14, False, "whether this comes back every year or happened once"),
    ("nostalgia_durability",   0.10, False, "whether the feeling outlives the moment"),
    ("seasonal_fit",           0.10, False, "whether it lands on a date people already buy for"),
    ("crochet_translatability", 0.12, False, "whether yarn is a good material for this idea"),
    ("giftability",            0.10, False, "whether somebody buys it for somebody else"),
    ("visual_recognisability", 0.08, False, "whether it reads in a thumbnail at 200 pixels"),
    ("product_family_potential", 0.10, False, "whether it supports a collection or one item"),
    ("competition_density",    0.10, False, "inverted: crowded scores low"),
    ("make_time_window",       0.00, True,  "whether a customer could still finish it in time"),
    ("rights_feasibility",     0.00, True,  "whether this can be sold without somebody's permission"),
)

WEIGHTS: dict[str, float] = {k: w for k, w, _, _ in COMPONENTS}
GATES: tuple[str, ...] = tuple(k for k, _, g, _ in COMPONENTS if g)
MEANING: dict[str, str] = {k: m for k, _, _, m in COMPONENTS}

# Below this share of components observed, the number is an impression with a decimal point.
MIN_EVIDENCE_WEIGHT = 0.5

# A signal scoring above this with enough evidence behind it is worth a rapid-response cell.
ACT_NOW = 0.65


class ScoreRefused(Exception):
    """A component that does not exist, or a value off the scale."""


@dataclass
class Opportunity:
    signal_key: str
    observed: dict = field(default_factory=dict)
    absent: list = field(default_factory=list)
    gate_failures: list = field(default_factory=list)
    score: float = 0.0
    evidence_weight: float = 0.0

    @property
    def actionable(self) -> bool:
        return (not self.gate_failures
                and self.evidence_weight >= MIN_EVIDENCE_WEIGHT
                and self.score >= ACT_NOW)

    def to_dict(self) -> dict:
        return {
            "signal": self.signal_key,
            "score": round(self.score, 3),
            "observed": self.observed,
            "absent": list(self.absent),
            "gate_failures": list(self.gate_failures),
            "evidence_weight": round(self.evidence_weight, 3),
            "trustworthy": self.evidence_weight >= MIN_EVIDENCE_WEIGHT,
            "actionable": self.actionable,
            "meaning": MEANING,
            "note": self._note(),
        }

    def _note(self) -> str:
        if self.gate_failures:
            return (f"{', '.join(self.gate_failures)} is a gate rather than a weight: a "
                    f"signal cannot be strong enough elsewhere to compensate for it. Five "
                    f"out of five on every commercial dimension and zero on rights is not a "
                    f"four.")
        if self.evidence_weight < MIN_EVIDENCE_WEIGHT:
            return (f"only {len(self.observed)} of {len(COMPONENTS)} components have an "
                    f"observation behind them, so this number is an impression with a "
                    f"decimal point. The absent components are named rather than defaulted, "
                    f"because a default is a guess that survives review.")
        if self.actionable:
            return ("strong enough, and observed enough, to justify a rapid-response cell "
                    "(#141) -- which accelerates the work without lowering any gate")
        return "scored and observed, and not strong enough to displace committed work"


def score(signal_key: str, observations: dict) -> Opportunity:
    """Score one cultural moment from what has actually been observed about it.

    Values are 0.0-1.0. A component nobody measured is simply left out: passing 0.0 to mean
    "unknown" is the single most common way an honest scoring system starts lying, because
    zero and unknown produce different decisions and the same arithmetic.
    """
    unknown = [k for k in observations if k not in WEIGHTS]
    if unknown:
        raise ScoreRefused(
            f"{sorted(unknown)} are not opportunity components: {sorted(WEIGHTS)}")

    observed: dict = {}
    for key, value in observations.items():
        if value is None:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ScoreRefused(f"{key}: {value!r} is not a 0.0-1.0 value")
        if not 0.0 <= float(value) <= 1.0:
            raise ScoreRefused(f"{key}: {value!r} is outside 0.0-1.0")
        observed[key] = float(value)

    absent = [k for k in WEIGHTS if k not in observed]

    # The gates. An unobserved gate fails: "we did not check whether we are allowed to sell
    # this" is not a better position than "we are not allowed to sell this".
    gate_failures = []
    for gate in GATES:
        if gate not in observed:
            gate_failures.append(f"{gate} (never observed)")
        elif observed[gate] <= 0.0:
            gate_failures.append(gate)

    weighted = {k: v for k, v in observed.items() if WEIGHTS[k] > 0}
    total_weight = sum(WEIGHTS[k] for k in weighted)
    raw = (sum(v * WEIGHTS[k] for k, v in weighted.items()) / total_weight
           if total_weight else 0.0)

    # The gates multiply rather than add, so a weak gate drags the whole score instead of
    # being outvoted by nine strong commercial components.
    for gate in GATES:
        raw *= observed.get(gate, 0.0)

    evidence_weight = len(observed) / len(COMPONENTS)
    return Opportunity(signal_key=signal_key, observed=observed, absent=absent,
                       gate_failures=gate_failures, score=round(raw, 3),
                       evidence_weight=evidence_weight)


def rank(scored: list[Opportunity]) -> dict:
    """Order by score, with anything that failed a gate excluded rather than ranked last.

    Ranking a gate failure last puts it on the same list as everything else, and a list is a
    thing people work down when they run out of items above it.
    """
    usable = [o for o in scored if not o.gate_failures]
    blocked = [o for o in scored if o.gate_failures]
    return {
        "ranked": [o.to_dict() for o in sorted(usable, key=lambda o: -o.score)],
        "gated_out": [o.to_dict() for o in blocked],
        "note": ("Gate failures are excluded from the ranking rather than placed at the "
                 "bottom of it: a ranked list is a thing people work down when they run out "
                 "of items above."),
    }
