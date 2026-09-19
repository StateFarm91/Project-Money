"""How fast the company may change itself, graded by what the change can break.

Requirement 178, whose own sentence is the specification: never equate "continuous" with
"unsupervised rewriting of the company". Learning may happen as fast as evidence arrives.
*Promotion* may not, and the difference between the two is the entire requirement.

The mechanism is a tier, and one rule makes it work:

**A change is classified by what it touches, never by what it is called.** A spend limit
adjusted in a change described as a scoring tweak is a spend change, and the description is
the part somebody chooses. Classification reads the touched surfaces and takes the highest
tier any of them implies, so a proposal cannot talk its way into a faster lane. This is the
same shape as the weakening detector next door: the thing being defended against is a
rewording, so the check does not read wording.

From there each tier carries three limits that all have to be satisfied:

**Cooldown.** How long since the last promotion in this tier. A system that promotes six
changes to the same surface in an afternoon cannot attribute any outcome to any of them, and
the attribution is what makes the next change an improvement rather than a guess.

**Weekly ceiling.** How many promotions this tier may take in a rolling week. Continuous
learning with no ceiling is a company rewriting itself faster than it can observe the
results, which is the failure this requirement names.

**Evidence.** What must exist before promotion. A scoring change needs a baseline and a
sandbox result. A code change needs those plus a regression test and a rollback. A change to
a truth gate, a spend limit or release logic needs all of that and an owner decision, because
those are the surfaces where being wrong is not recoverable by reverting quickly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Evidence kinds a promotion can carry. Closed, because "we tested it" is not a kind.
BASELINE = "baseline"
SANDBOX_RESULT = "sandbox_result"
ROLLBACK = "rollback"
REGRESSION_TEST = "regression_test"
ADVERSARIAL_TEST = "adversarial_test"
OWNER_APPROVAL = "owner_approval"

EVIDENCE_KINDS: tuple[str, ...] = (BASELINE, SANDBOX_RESULT, ROLLBACK, REGRESSION_TEST,
                                   ADVERSARIAL_TEST, OWNER_APPROVAL)


@dataclass(frozen=True)
class Tier:
    key: str
    rank: int
    what: str
    cooldown_hours: float
    weekly_ceiling: int
    requires: tuple[str, ...]
    why: str

    @property
    def needs_owner(self) -> bool:
        return OWNER_APPROVAL in self.requires


TIERS: tuple[Tier, ...] = (
    Tier("scoring", 0, "weights, rankings and thresholds inside an existing tolerance",
         cooldown_hours=6, weekly_ceiling=14,
         requires=(BASELINE, SANDBOX_RESULT),
         why="a scoring change is visible in the next measurement and reverts by editing a "
             "number, so it is the one surface where frequency is genuinely cheap"),
    Tier("prompt", 1, "prompt text, wording and output schemas",
         cooldown_hours=24, weekly_ceiling=7,
         requires=(BASELINE, SANDBOX_RESULT, ROLLBACK),
         why="a prompt change moves every output downstream of it at once, and the damage "
             "is legible only in aggregate, which takes a day to see"),
    Tier("tooling", 2, "model routing, tool selection, retries and cadences",
         cooldown_hours=72, weekly_ceiling=3,
         requires=(BASELINE, SANDBOX_RESULT, ROLLBACK, REGRESSION_TEST),
         why="routing changes alter cost and reliability together, and a cheaper route that "
             "fails twice as often has not improved anything"),
    Tier("code", 3, "code paths, compilers, validators and the build itself",
         cooldown_hours=168, weekly_ceiling=1,
         requires=(BASELINE, SANDBOX_RESULT, ROLLBACK, REGRESSION_TEST, ADVERSARIAL_TEST),
         why="code is where a defect becomes silent: it keeps producing plausible output "
             "while being wrong, which is what the adversarial test is for"),
    Tier("gate", 4, "truth gates, policy, release logic, spend limits and publication",
         cooldown_hours=336, weekly_ceiling=1,
         requires=(BASELINE, SANDBOX_RESULT, ROLLBACK, REGRESSION_TEST, ADVERSARIAL_TEST,
                   OWNER_APPROVAL),
         why="these are the surfaces where being wrong is not recoverable by reverting "
             "quickly: a listing published, a limit exceeded, a policy breached. Continuous "
             "learning does not reach them without a person"),
)

TIER_BY_KEY: dict[str, Tier] = {t.key: t for t in TIERS}
TIER_BY_RANK: dict[int, Tier] = {t.rank: t for t in TIERS}

# Which tier a touched surface implies. The classifier takes the highest tier of everything a
# change touches, so a change is graded by its riskiest surface rather than its commonest.
SURFACE_TIER: dict[str, str] = {
    # scoring
    "weights": "scoring", "ranking": "scoring", "score": "scoring", "tolerance": "scoring",
    "priority": "scoring",
    # prompt
    "prompt": "prompt", "wording": "prompt", "schema": "prompt", "copy": "prompt",
    # tooling
    "model_routing": "tooling", "provider": "tooling", "retries": "tooling",
    "cadence": "tooling", "tool": "tooling",
    # code
    "code": "code", "compiler": "code", "validator": "code", "twin": "code",
    "reverse_compiler": "code", "build": "code",
    # gate
    "quality_gate": "gate", "asset_truth": "gate", "policy": "gate", "spend": "gate",
    "spend_limit": "gate", "release": "gate", "publication": "gate", "budget": "gate",
    "truth_gate": "gate", "disclosure": "gate",
}


class TierRefused(PermissionError):
    """A promotion that outruns the evidence, the cooldown or the ceiling for its tier."""


def classify(touches: tuple[str, ...]) -> Tier:
    """The tier a change belongs to, read from what it touches.

    An unknown surface is treated as `code` rather than as the cheapest tier. Defaulting
    downward would make "touch something the classifier has not heard of" the fast path,
    which is the first thing anybody would find.
    """
    if not touches:
        raise TierRefused(
            "a change that does not say what it touches cannot be graded, and an ungraded "
            "change takes whichever lane its author felt like")
    ranks = []
    for surface in touches:
        key = (surface or "").strip().lower()
        tier = SURFACE_TIER.get(key)
        ranks.append(TIER_BY_KEY[tier].rank if tier else TIER_BY_KEY["code"].rank)
    return TIER_BY_RANK[max(ranks)]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def recent_promotions(db, tier: Tier, *, now: datetime | None = None) -> list[datetime]:
    """When this tier last promoted, counted from rows rather than remembered."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    now = now or datetime.now(timezone.utc)
    week = now - timedelta(days=7)
    with db.session() as s:
        rows = [(_aware(a.at), (a.detail or {}).get("tier"))
                for a in s.scalars(select(AuditLog).where(
                    AuditLog.action == "improve.promoted"))]
    return sorted(at for at, key in rows if key == tier.key and at >= week)


def check_promotion(db, *, touches: tuple[str, ...], evidence: tuple[str, ...],
                    declared_tier: str | None = None,
                    now: datetime | None = None) -> dict:
    """Decide whether this change may be promoted now. Refuses rather than warns.

    Returns the tier and its state when allowed, so a caller records what it satisfied
    instead of asserting that it did.
    """
    now = now or datetime.now(timezone.utc)
    tier = classify(touches)

    if declared_tier and declared_tier != tier.key:
        declared = TIER_BY_KEY.get(declared_tier)
        if declared is None or declared.rank < tier.rank:
            raise TierRefused(
                f"this change was declared {declared_tier!r} and touches {list(touches)}, "
                f"which is {tier.key!r}. A change is classified by what it touches, never by "
                f"what it is called: a spend limit adjusted inside a scoring tweak is a "
                f"spend change, and the description is the part somebody chooses")

    unknown = [e for e in evidence if e not in EVIDENCE_KINDS]
    if unknown:
        raise TierRefused(
            f"evidence {unknown} is not a recognised kind: {list(EVIDENCE_KINDS)}. "
            f"'We tested it' is not a kind of evidence")

    missing = [need for need in tier.requires if need not in evidence]
    if missing:
        raise TierRefused(
            f"{tier.key} promotions require {list(tier.requires)} and this one is missing "
            f"{missing}. {tier.why}")

    history = recent_promotions(db, tier, now=now)
    if history:
        since = (now - history[-1]).total_seconds() / 3600.0
        if since < tier.cooldown_hours:
            raise TierRefused(
                f"the last {tier.key} promotion was {since:.1f} hours ago and the cooldown "
                f"is {tier.cooldown_hours:.0f}. Six changes to one surface in an afternoon "
                f"cannot be attributed to anything, and the attribution is what makes the "
                f"next change an improvement rather than a guess")
    if len(history) >= tier.weekly_ceiling:
        raise TierRefused(
            f"{tier.key} has had {len(history)} promotions in the last week against a "
            f"ceiling of {tier.weekly_ceiling}. Continuous learning with no ceiling is a "
            f"company rewriting itself faster than it can observe the result, which is what "
            f"#178 forbids by name")

    return {
        "tier": tier.key,
        "rank": tier.rank,
        "what": tier.what,
        "requires": list(tier.requires),
        "satisfied": list(evidence),
        "needs_owner": tier.needs_owner,
        "promotions_this_week": len(history),
        "weekly_ceiling": tier.weekly_ceiling,
        "cooldown_hours": tier.cooldown_hours,
        "note": ("allowed: this tier's cooldown, ceiling and evidence are all satisfied"
                 if not tier.needs_owner else
                 "allowed only because an owner approval is among the evidence; this tier "
                 "does not promote without a person"),
    }


def record_promotion(db, *, tier: str, summary: str, detail: dict | None = None) -> None:
    """Write the promotion the cooldown and ceiling are counted from."""
    from ..core.models import AuditLog

    if tier not in TIER_BY_KEY:
        raise TierRefused(f"{tier!r} is not a tier")
    with db.session() as s:
        s.add(AuditLog(actor="improvement", action="improve.promoted", artifact=tier,
                       detail={"tier": tier, "summary": summary, **(detail or {})}))


def state(db, *, now: datetime | None = None) -> dict:
    """What each tier has spent of its week, for a reader asking how fast this is moving."""
    now = now or datetime.now(timezone.utc)
    rows = []
    for tier in TIERS:
        history = recent_promotions(db, tier, now=now)
        last = history[-1] if history else None
        rows.append({
            "tier": tier.key, "what": tier.what, "why": tier.why,
            "promotions_this_week": len(history), "weekly_ceiling": tier.weekly_ceiling,
            "cooldown_hours": tier.cooldown_hours,
            "last_promotion": last.isoformat() if last else None,
            "hours_since": (round((now - last).total_seconds() / 3600, 1) if last else None),
            "requires": list(tier.requires), "needs_owner": tier.needs_owner,
        })
    return {"tiers": rows,
            "note": ("Learning may happen as fast as evidence arrives; promotion may not. "
                     "A change is graded by what it touches, never by what it is called "
                     "(#178).")}
