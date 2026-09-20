"""The weekly deep cycle, and the review that is only allowed to add.

Requirement 194. A deeper weekly audit across product creativity, pattern correctness,
competitor intelligence, conversion, ads, support, infrastructure and cost; and then the part
that makes it *deep* rather than long — re-evaluate the department architecture itself: add
specialists where gaps exist, merge redundant ones, revise metrics, and update the roadmap.

`improve.velocity` already refuses the version of this that only adds work, for cadences,
experiments, polish, queries and infrastructure: a review producing no STOP list is asked to
say why, because "nothing to stop" is exactly what a bureaucracy reports. That argument does
not stop at cadences. An architecture review permitted to add specialists and never to merge
or retire one grows the org chart every week, forever, and each addition is individually
defensible — which is what makes the total indefensible and invisible. So an architecture
change is one of four moves, three of which subtract, and a week that only adds is asked the
same question `velocity.stop_list` asks.

**Revising a metric is the dangerous move and gets its own rules.** A department that changes
its own success measure after a bad quarter has not improved; it has moved the goalposts, and
from inside it feels like better measurement, because the old metric genuinely was imperfect —
every metric is. Three things hold here. A department may never propose a revision to its own
metric, which is `improve.roles`' separation of proposing and judging applied to the
scoreboard. The old metric's history is preserved rather than migrated, because a revision
that rewrites the past removes the only evidence that the change was self-serving. And the
justification may not be that the old number was unflattering — the argument has to be about
what the metric fails to measure, not about what it measured.

**The eight domains are audited, not visited.** Each carries the same three-outcome rule the
nightly sweep uses, for the same reason: a weekly audit that reports eight domains reviewed
and a clean bill of health reads identically whether it looked or not. A domain with no
reading is `not_audited`, and the cycle will not call itself complete while one remains.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import cells, roles

# The eight the requirement names, each mapped to where its reading comes from.
DOMAINS: dict[str, str] = {
    "product_creativity": "the tournament scorecard and field spread",
    "pattern_correctness": "certification first-pass rate and reverse-compiler agreement",
    "competitor_intelligence": "benchmark observation freshness and coverage",
    "conversion": "listing tests, funnel stages and the friction audit",
    "ads": "paid-media spend against attributed contribution",
    "support": "cases per order, response time and refund causes",
    "infrastructure": "dead letters, health signals and deploy outcomes",
    "cost": "the ledger, by category, against what it returned",
}

AUDITED = "audited"
NOT_AUDITED = "not_audited"

# The four architecture moves. Three of them subtract, and that is the point: a list with
# only `add` on it is how an org chart grows forever, one defensible step at a time.
ADD = "add_specialist"
MERGE = "merge_redundant"
RETIRE = "retire_weak"
REVISE_METRIC = "revise_metric"

MOVES: dict[str, str] = {
    ADD: "a capability nothing currently owns, with the work that proves the gap",
    MERGE: "two roles doing the same job, folded into one",
    RETIRE: "a role that has not earned its standing cost",
    REVISE_METRIC: "a department's success measure replaced, under the rules below",
}

SUBTRACTIVE: tuple[str, ...] = (MERGE, RETIRE)

# A justification for a metric revision may not be that the old number was unflattering.
# These are the ways that gets said out loud, and each one is an argument about the reading
# rather than about the measure.
GOALPOST_PHRASES: tuple[str, ...] = (
    "does not reflect", "unfair", "too harsh", "makes us look", "penalises us",
    "not representative of our", "would look better", "hard to move", "always low",
    "discouraging",
)


class WeeklyRefused(ValueError):
    """A domain visited rather than audited, or a department regrading itself."""


# ---- the eight domains ----------------------------------------------------

@dataclass(frozen=True)
class DomainReading:
    """One domain's audit. `read` is what makes it an audit rather than a visit."""

    domain: str
    read: int
    findings: int = 0
    note: str = ""

    def __post_init__(self) -> None:
        if self.domain not in DOMAINS:
            raise WeeklyRefused(f"{self.domain!r} is not a weekly domain: {sorted(DOMAINS)}")
        if self.read < 0 or self.findings < 0:
            raise WeeklyRefused(f"{self.domain}: negative counts are not measurements")
        if self.findings > 0 and self.read == 0:
            raise WeeklyRefused(
                f"{self.domain}: {self.findings} findings from nothing read. A finding comes "
                f"from a row somebody looked at")

    @property
    def outcome(self) -> str:
        return AUDITED if self.read > 0 else NOT_AUDITED

    def to_dict(self) -> dict:
        return {"domain": self.domain, "source": DOMAINS[self.domain],
                "outcome": self.outcome, "read": self.read, "findings": self.findings,
                "note": self.note}


# ---- the architecture move ------------------------------------------------

@dataclass(frozen=True)
class ArchitectureChange:
    """One proposed change to the shape of the organisation, with who proposed it."""

    move: str
    subject: str
    proposed_by: str
    because: str
    replaces_metric: str = ""
    new_metric: str = ""

    def __post_init__(self) -> None:
        if self.move not in MOVES:
            raise WeeklyRefused(f"{self.move!r} is not an architecture move: {sorted(MOVES)}")
        if len(self.because.split()) < 6:
            raise WeeklyRefused(
                f"{self.subject}: changing the shape of the organisation needs a reason "
                f"somebody can argue with")
        if self.move == ADD and self.subject in cells.BY_KEY:
            raise WeeklyRefused(
                f"{self.subject} already exists as a department. Adding a specialist for a "
                f"capability something already owns is how two roles end up doing one job, "
                f"which is the thing {MERGE} exists to undo")
        if self.move in (MERGE, RETIRE, REVISE_METRIC) and self.subject not in cells.BY_KEY:
            raise WeeklyRefused(
                f"{self.subject} is not a department: {sorted(cells.BY_KEY)}")
        if self.move == REVISE_METRIC:
            self._check_metric_revision()

    def _check_metric_revision(self) -> None:
        if not self.new_metric.strip():
            raise WeeklyRefused(f"{self.subject}: a metric revision names the new metric")
        current = cells.BY_KEY[self.subject].metric
        if self.replaces_metric != current:
            raise WeeklyRefused(
                f"{self.subject}: this claims to replace {self.replaces_metric!r} and the "
                f"department currently answers for {current!r}. A revision that does not "
                f"name the metric it replaces cannot be checked against it afterwards")
        if self.new_metric == current:
            raise WeeklyRefused(f"{self.subject}: the new metric is the old one")
        if self.proposed_by == self.subject:
            raise WeeklyRefused(
                f"{self.subject} proposed the revision of its own success measure. A "
                f"department that changes its own metric after a bad quarter has not "
                f"improved; it has moved the goalposts, and from inside that feels like "
                f"better measurement because the old metric genuinely was imperfect -- every "
                f"metric is")
        lowered = self.because.lower()
        hit = next((p for p in GOALPOST_PHRASES if p in lowered), None)
        if hit:
            raise WeeklyRefused(
                f"{self.subject}: {hit!r} is an argument about the reading, not about the "
                f"measure. A revision has to say what the metric fails to measure, never "
                f"that the number it produced was unwelcome")

    def to_dict(self) -> dict:
        out = {"move": self.move, "means": MOVES[self.move], "subject": self.subject,
               "proposed_by": self.proposed_by, "because": self.because,
               "subtracts": self.move in SUBTRACTIVE}
        if self.move == REVISE_METRIC:
            out["replaces_metric"] = self.replaces_metric
            out["new_metric"] = self.new_metric
            out["history"] = ("preserved under the old metric. A revision that rewrites the "
                              "past removes the only evidence that it was self-serving")
        return out


def check_proposer(change: ArchitectureChange) -> dict:
    """Whether the proposer is allowed to make this move at all."""
    try:
        role = roles.role(change.proposed_by)
    except roles.RoleRefused:
        # A department proposing about another department is ordinary; only the meta-agent
        # roles have declared powers, so a non-role proposer is checked for self-dealing only.
        if change.proposed_by == change.subject and change.move in (MERGE, RETIRE):
            return {"ok": True, "proposed_by": change.proposed_by,
                    "why": ("a department proposing its own merge or retirement is the one "
                            "self-interested move that costs the proposer, so it is allowed")}
        return {"ok": True, "proposed_by": change.proposed_by,
                "why": "not a meta-agent role; no declared powers to check"}
    if roles.PROPOSE not in role.powers and roles.ANNOTATE not in role.powers:
        return {"ok": False, "proposed_by": change.proposed_by,
                "why": f"{role.key} may not propose: {list(role.powers)}"}
    return {"ok": True, "proposed_by": role.key, "why": f"{role.key} may propose"}


# ---- the cycle ------------------------------------------------------------

def cycle(readings: list[DomainReading], changes: list[ArchitectureChange], *,
          at: datetime | None = None, nothing_to_subtract_because: str = "") -> dict:
    """One week's deep audit, and the question a week that only added has to answer."""
    at = at or datetime.now(timezone.utc)
    by_domain = {r.domain: r for r in readings}

    duplicated = sorted({r.domain for r in readings
                         if sum(1 for o in readings if o.domain == r.domain) > 1})
    if duplicated:
        raise WeeklyRefused(f"{duplicated} audited twice in one cycle")

    domains = {}
    for name in DOMAINS:
        reading = by_domain.get(name)
        domains[name] = (reading.to_dict() if reading else
                         {"domain": name, "source": DOMAINS[name], "outcome": NOT_AUDITED,
                          "read": 0, "findings": 0,
                          "note": "no reading was reported for this domain"})
    not_audited = sorted(n for n, d in domains.items() if d["outcome"] == NOT_AUDITED)

    # Every change passes the proposer check here rather than only where a caller remembers
    # to call it. A rule enforced at one call site is enforced at the call sites somebody
    # thought of.
    refused = []
    for change in changes:
        verdict = check_proposer(change)
        if not verdict["ok"]:
            refused.append({"subject": change.subject, "move": change.move,
                            "proposed_by": change.proposed_by, "why": verdict["why"]})
    if refused:
        raise WeeklyRefused(
            "architecture changes from proposers who may not propose: "
            + "; ".join(f"{r['proposed_by']} -> {r['move']} {r['subject']} ({r['why']})"
                        for r in refused))

    added = [c for c in changes if c.move == ADD]
    subtracted = [c for c in changes if c.move in SUBTRACTIVE]
    revised = [c for c in changes if c.move == REVISE_METRIC]

    architecture_note = ""
    if added and not subtracted:
        if not nothing_to_subtract_because.strip():
            architecture_note = (
                f"{len(added)} specialist(s) added and nothing merged or retired, with no "
                f"reason given. An architecture review that only adds grows the org chart "
                f"every week, one individually defensible step at a time, and that is what "
                f"makes the total indefensible. This is not blocked -- a genuinely growing "
                f"company exists -- but it is not silent either")
        else:
            architecture_note = (
                f"added without subtracting, because: {nothing_to_subtract_because.strip()}")

    complete = not not_audited
    return {
        "at": at.isoformat(),
        "complete": complete,
        "domains": domains,
        "not_audited": not_audited,
        "total_read": sum(r.read for r in readings),
        "total_findings": sum(r.findings for r in readings),
        "architecture": {
            "changes": [c.to_dict() for c in changes],
            "added": len(added), "subtracted": len(subtracted), "metrics_revised": len(revised),
            "only_added": bool(added) and not subtracted,
            "note": architecture_note,
        },
        "why": ("every domain was audited" if complete else
                f"{len(not_audited)} of {len(DOMAINS)} domains have no reading: "
                f"{', '.join(not_audited)}. A weekly audit reporting a clean bill of health "
                f"across domains it did not read is the same output as one that did"),
    }


def roadmap(cycle_result: dict, *, carried: list[dict] | None = None) -> dict:
    """The improvement roadmap this week's cycle leaves behind.

    Carried items are listed with their age, because an item that has been on the roadmap for
    nine weeks is a decision nobody is making rather than work nobody has reached.
    """
    carried = list(carried or [])
    aged = sorted(carried, key=lambda item: -int(item.get("weeks_carried", 0)))
    stuck = [item for item in aged if int(item.get("weeks_carried", 0)) >= 4]
    findings = cycle_result.get("total_findings", 0)
    return {
        "from_cycle": cycle_result.get("at"),
        "new_findings": findings,
        "carried": aged,
        "stuck": stuck,
        "why": ("an item carried four weeks or more is a decision nobody is making rather "
                "than work nobody has reached, and the two need opposite responses"),
        "complete_cycle": cycle_result.get("complete", False),
    }


def state() -> dict:
    """The eight domains, the four moves, and the three that subtract."""
    return {
        "requirement": 194,
        "domains": dict(DOMAINS),
        "moves": dict(MOVES),
        "subtractive_moves": list(SUBTRACTIVE),
        "builds_on": {
            "improve.velocity": "the STOP list, which refuses the add-only review for cadences",
            "improve.freshness": "which departments are stale or churning",
            "improve.roles": "who may propose, and who may not grade themselves",
            "swarm.orchestrate": "the merge and retire rules for agents (#192)",
        },
        "refuses": [
            "a domain reported with findings but nothing read",
            "a complete cycle while any domain has no reading",
            "a department proposing the revision of its own success measure",
            "a metric revision justified by the old number being unflattering",
            "a metric revision that does not name the metric it replaces",
            "adding a specialist for a capability a department already owns",
        ],
        "note": ("an architecture review permitted to add and never to subtract grows the "
                 "org chart forever, one individually defensible step at a time. Three of "
                 "the four moves subtract, and a week that only added is asked why -- the "
                 "same question improve.velocity asks of a review that stops nothing"),
    }
