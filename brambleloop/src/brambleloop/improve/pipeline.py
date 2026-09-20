"""An upgrade that prepares its own evidence, and the two things it may never prepare.

Requirement 190. Improvement agents may open bounded upgrade proposals, run tests,
simulations and shadow deployments, and prepare promotion evidence around the clock. Low-risk
pre-authorised changes may auto-promote inside defined governance; higher-risk changes queue a
concise owner approval carrying exact impact, cost and rollback.

The governance half already exists and is not rebuilt here. `improve.tiers` classifies a
change by the surfaces it touches -- never by what it is called -- and holds the cooldown,
the weekly ceiling and the evidence each tier requires; `improve.governance` bounds what any
self-improvement may go near; `improve.roles` says who may propose and who may judge. What
was missing is the object in between: a proposal that accumulates evidence over hours, knows
what it still lacks, and cannot quietly grade itself.

Four rules, and the first is the one everything else rests on.

**Evidence is a recorded run, never a field the proposal sets.** A proposal that runs its own
tests and reports them passed has reported its own opinion in the shape of a fact. Every piece
of evidence here carries the identifier of the run that produced it, and a piece with no
reference is refused at the point it is attached rather than doubted later.

**Evidence is about a version, and a proposal that changed has lost it.** A sandbox result
gathered on Tuesday describes Tuesday's proposal. If the content moves afterwards, the result
is evidence about something that no longer exists -- so each proposal carries a fingerprint,
evidence records the fingerprint it was gathered against, and a mismatch invalidates it rather
than ageing it out. This is the same rule as a forecast dated before its period and a derived
artefact checked against its inputs; it arrives here because the work is done over hours by
something that never sleeps, which is exactly the situation in which the version silently
moves under the evidence.

**Bounded means the scope is declared first and enforced after.** "Bounded upgrade proposal"
is the requirement's own phrase and nothing was enforcing it: a proposal declares the surfaces
it may touch when it opens, and evidence or promotion naming a surface outside that scope is
refused. Otherwise scope is whatever the proposal turned out to touch, which is not a bound.

**Auto-promotion is a property of the tier, never of the proposal's own confidence.** The
pre-authorised set is a constant here, it is the two cheapest tiers, and a proposal cannot
argue into it -- `may_auto_promote` does not read anything the proposal says about itself.
Everything else becomes an owner card, and the card is refused unless impact, cost and
rollback are all *exact*: surfaces named, a number in CAD, and a concrete target to return to.
"Minimal impact", "low cost" and "we can revert" are the three things an approval queue fills
with when nobody checks, and they are each individually unactionable.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import governance, tiers

# Tiers whose promotions may happen without a person, when everything else is satisfied.
# A constant, not a parameter: a pre-authorisation a caller can widen is not one.
PRE_AUTHORISED: tuple[str, ...] = ("scoring", "prompt")

OPEN = "open"
GATHERING = "gathering_evidence"
READY = "ready"
QUEUED_FOR_OWNER = "queued_for_owner"
PROMOTED = "promoted"
WITHDRAWN = "withdrawn"

STATES: tuple[str, ...] = (OPEN, GATHERING, READY, QUEUED_FOR_OWNER, PROMOTED, WITHDRAWN)


class PipelineRefused(ValueError):
    """A proposal grading itself, escaping its scope, or asking for an unactionable approval."""


def fingerprint(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Evidence:
    """One recorded result, tied to the run that produced it and the version it describes."""

    kind: str
    run_ref: str
    against_fingerprint: str
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    detail: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in tiers.EVIDENCE_KINDS:
            raise PipelineRefused(
                f"{self.kind!r} is not an evidence kind: {list(tiers.EVIDENCE_KINDS)}")
        if not self.run_ref.strip():
            raise PipelineRefused(
                f"{self.kind} with no run reference is the proposal's own opinion in the "
                f"shape of a fact. Evidence names the run that produced it, or it is not "
                f"evidence")
        if not self.against_fingerprint.strip():
            raise PipelineRefused(
                "evidence records the version it was gathered against, or it cannot be told "
                "apart from evidence about a proposal that has since changed")

    def to_dict(self) -> dict:
        return {"kind": self.kind, "run_ref": self.run_ref,
                "against_fingerprint": self.against_fingerprint,
                "at": self.at.isoformat(), "detail": dict(self.detail)}


@dataclass
class Proposal:
    """One bounded upgrade, its declared scope, and whatever it has proved so far."""

    key: str
    author_role: str
    hypothesis: str
    scope: tuple[str, ...]
    content: str
    rollback_to: str = ""
    spend_cad: float = 0.0
    evidence: list[Evidence] = field(default_factory=list)
    state: str = OPEN

    def __post_init__(self) -> None:
        from . import roles

        if not self.scope:
            raise PipelineRefused(
                f"{self.key}: a proposal with no declared scope is not bounded. Without it "
                f"the scope is whatever the change turned out to touch, decided afterwards")
        unknown = sorted(set(self.scope) - set(tiers.SURFACE_TIER))
        if unknown:
            raise PipelineRefused(
                f"{self.key}: {unknown} are not surfaces the tier classifier knows: "
                f"{sorted(tiers.SURFACE_TIER)}. An unclassifiable surface would take no tier "
                f"and therefore no cooldown, ceiling or evidence requirement")
        role = roles.role(self.author_role)
        if roles.PROPOSE not in role.powers:
            raise PipelineRefused(
                f"{self.author_role} may not open proposals: {list(role.powers)}")
        if len(self.hypothesis.split()) < 6:
            raise PipelineRefused(
                f"{self.key}: state what this change is expected to do, in a sentence. A "
                f"proposal nobody can disagree with cannot be shown to have failed")

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.content)

    @property
    def tier(self) -> tiers.Tier:
        return tiers.classify(self.scope)

    def current_evidence(self) -> list[Evidence]:
        """Only what was gathered against this exact version."""
        return [e for e in self.evidence if e.against_fingerprint == self.fingerprint]

    def invalidated_evidence(self) -> list[Evidence]:
        return [e for e in self.evidence if e.against_fingerprint != self.fingerprint]


def attach(proposal: Proposal, evidence: Evidence, *,
           touched: tuple[str, ...] = ()) -> dict:
    """Record a result against this proposal, refusing one from outside its bound."""
    outside = sorted(set(touched) - set(proposal.scope))
    if outside:
        raise PipelineRefused(
            f"{proposal.key}: this run touched {outside}, which is outside the declared "
            f"scope {list(proposal.scope)}. A bound that widens to fit what happened is a "
            f"description, not a bound")
    if evidence.against_fingerprint != proposal.fingerprint:
        raise PipelineRefused(
            f"{proposal.key}: evidence was gathered against {evidence.against_fingerprint} "
            f"and the proposal is now {proposal.fingerprint}. A result describes the version "
            f"it ran on, and this one no longer exists")
    proposal.evidence.append(evidence)
    proposal.state = GATHERING
    return status(proposal)


def revise(proposal: Proposal, content: str) -> dict:
    """Change what the proposal would do, losing the evidence that described the old one."""
    lost = [e.kind for e in proposal.current_evidence()]
    proposal.content = content
    proposal.state = OPEN if lost else proposal.state
    return {"key": proposal.key, "fingerprint": proposal.fingerprint,
            "evidence_invalidated": sorted(lost),
            "why": ("evidence describes the version it ran against, so revising the proposal "
                    "invalidates it rather than ageing it out. Nothing here re-runs by "
                    "itself; the runs have to happen again"
                    if lost else "no evidence had been gathered yet")}


def status(proposal: Proposal) -> dict:
    """What this proposal has, what it still needs, and which way it can leave."""
    tier = proposal.tier
    have = {e.kind for e in proposal.current_evidence()}
    missing = [need for need in tier.requires if need not in have]
    invalidated = [e.kind for e in proposal.invalidated_evidence()]

    return {
        "key": proposal.key, "state": proposal.state, "tier": tier.key,
        "tier_rank": tier.rank, "scope": list(proposal.scope),
        "fingerprint": proposal.fingerprint,
        "evidence_have": sorted(have), "evidence_missing": missing,
        "evidence_invalidated": sorted(set(invalidated)),
        "complete": not missing,
        "route": "auto" if tier.key in PRE_AUTHORISED else "owner",
        "why": (f"{tier.key} promotions require {list(tier.requires)}; still missing "
                f"{missing}" if missing else
                f"every piece of evidence a {tier.key} promotion requires is present and "
                f"was gathered against this version"),
    }


def may_auto_promote(db, proposal: Proposal, *, now: datetime | None = None) -> dict:
    """Whether this may promote without a person. Reads the tier, never the proposal's view.

    Nothing a proposal says about its own risk appears in this function. A change that could
    argue itself into the fast lane by describing itself carefully is the failure
    `improve.tiers` was built to prevent, and re-opening it here through a confidence field
    would undo that from the other side.
    """
    tier = proposal.tier
    if tier.key not in PRE_AUTHORISED:
        return {"may_auto_promote": False, "tier": tier.key, "route": "owner",
                "why": (f"{tier.key} is not pre-authorised {list(PRE_AUTHORISED)}. {tier.why}")}

    boundary = governance.check(proposal.hypothesis, touches=proposal.scope)
    if not boundary.ok:
        return {"may_auto_promote": False, "tier": tier.key, "route": "refused",
                "why": f"refused by the improvement boundary: {boundary.reason}"}

    have = tuple(e.kind for e in proposal.current_evidence())
    try:
        verdict = tiers.check_promotion(db, touches=proposal.scope, evidence=have, now=now)
    except tiers.TierRefused as e:
        return {"may_auto_promote": False, "tier": tier.key, "route": "held", "why": str(e)}
    return {"may_auto_promote": True, "tier": tier.key, "route": "auto",
            "tier_state": verdict,
            "why": (f"{tier.key} is pre-authorised, every required piece of evidence was "
                    f"gathered against this version, and the tier's cooldown and ceiling "
                    f"both allow it")}


# ---- the owner card -------------------------------------------------------

# The three things an approval queue fills with when nobody checks. Each is individually
# unactionable: a person reading "minimal impact, low cost, we can revert" has been told
# nothing and will approve it, which is how an approval step becomes a formality.
VAGUE: tuple[str, ...] = ("minimal", "low", "small", "negligible", "as needed", "tbd",
                          "we can revert", "should be fine", "n/a", "some", "various")


def _is_vague(text: str) -> bool:
    lowered = (text or "").strip().lower()
    return (not lowered) or any(lowered == v or lowered.startswith(v + " ") for v in VAGUE)


def owner_card(proposal: Proposal) -> dict:
    """The concise approval the requirement asks for, refused unless all three are exact."""
    tier = proposal.tier
    if tier.key in PRE_AUTHORISED:
        return {"queued": False, "tier": tier.key,
                "why": (f"{tier.key} is pre-authorised and does not need a person. Queueing "
                        f"one anyway trains whoever reads this queue to approve without "
                        f"reading")}

    problems: list[str] = []
    if not proposal.scope:
        problems.append("impact: no surfaces named")
    if _is_vague(proposal.rollback_to):
        problems.append(
            "rollback: name the exact thing to return to -- a version, a commit, a previous "
            "value. 'We can revert' is a hope with a plan's grammar")
    if proposal.spend_cad < 0:
        problems.append("cost: negative spend is not a cost")

    have = {e.kind for e in proposal.current_evidence()}
    missing = [need for need in tier.requires if need not in have
               and need != tiers.OWNER_APPROVAL]
    if missing:
        problems.append(
            f"evidence: {missing} still missing. An owner asked to approve before the "
            f"machine has finished checking is being asked to be the check")

    if problems:
        raise PipelineRefused(
            f"{proposal.key}: this approval card is not actionable -- " + "; ".join(problems))

    return {
        "queued": True,
        "key": proposal.key,
        "tier": tier.key,
        "why_it_needs_a_person": tier.why,
        "impact": {"surfaces": list(proposal.scope),
                   "hypothesis": proposal.hypothesis,
                   "author_role": proposal.author_role},
        "cost_cad": round(float(proposal.spend_cad), 2),
        "rollback_to": proposal.rollback_to,
        "evidence": [e.to_dict() for e in proposal.current_evidence()],
        "decision_needed": "approve or decline this promotion",
        "note": ("every number here is measured or declared rather than described: the "
                 "surfaces are the ones the change is bounded to, the cost is in CAD, and "
                 "the rollback names a target"),
    }


def state() -> dict:
    """What the pipeline adds to the governance that already existed."""
    return {
        "requirement": 190,
        "builds_on": {
            "improve.tiers": "classification by touched surface, cooldown, ceiling, evidence",
            "improve.governance": "what no self-improvement may go near",
            "improve.roles": "who may propose, and who may not",
        },
        "pre_authorised_tiers": list(PRE_AUTHORISED),
        "states": list(STATES),
        "refuses": [
            "evidence with no run reference -- an opinion in the shape of a fact",
            "evidence gathered against a version the proposal no longer is",
            "a run or promotion touching a surface outside the declared scope",
            "a surface the tier classifier does not know, which would take no tier at all",
            "an owner card whose impact, cost or rollback is vague",
            "an owner card queued for a tier that does not need a person",
        ],
        "note": ("auto-promotion reads the tier and never the proposal's own view of its "
                 "risk. A change that could argue itself into the fast lane by describing "
                 "itself carefully is exactly what classification-by-surface prevents, and a "
                 "confidence field here would undo it from the other side"),
    }
