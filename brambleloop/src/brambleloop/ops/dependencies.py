"""What this company stands on, and what happens when one of them goes away.

Requirement 50. A dependency map written by hand in a baseline document is a snapshot of what
somebody remembered on a Tuesday. The useful version answers a question nobody asks until it
is urgent: *if this disappeared tonight, what would we lose and how would we get it back?*

The design decision that matters is refusing a dependency with no recovery strategy. The
natural map lists nine things and marks three of them "critical", which is a feeling rather
than a plan — and the three marked critical are the ones somebody was already worried about,
not the ones that would actually end the company. So every dependency here carries what
happens when it fails, and a recovery of "we would have a problem" is refused at construction.

Impact is graded by what stops, not by how important the vendor feels. Postgres holds the
company's memory; GitHub holds a copy of code that also exists on disk. One of those is an
outage and one is an inconvenience, and vendor prestige gets that backwards routinely.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# What stops when this dependency does. Ordered by how much of the company goes with it.
FATAL = "fatal"            # the company's memory or its legal ability to trade
HALTING = "halting"        # work stops until it returns
DEGRADING = "degrading"    # some capability is lost, the rest continues
INCONVENIENT = "inconvenient"

IMPACTS: tuple[str, ...] = (FATAL, HALTING, DEGRADING, INCONVENIENT)


class DependencyRefused(ValueError):
    """A dependency with no recovery strategy, which is a dependency nobody has thought about."""


@dataclass(frozen=True)
class Dependency:
    key: str
    what: str
    impact: str
    if_it_fails: str
    recovery: str
    recovery_minutes: int
    env_probe: tuple[str, ...] = ()
    owner_only: bool = False

    def __post_init__(self) -> None:
        if self.impact not in IMPACTS:
            raise DependencyRefused(f"{self.key}: {self.impact!r} is not an impact: {IMPACTS}")
        if len(self.recovery.split()) < 6:
            raise DependencyRefused(
                f"{self.key}: 'we would have a problem' is not a recovery strategy. Say what "
                f"would actually be done, or this is a dependency nobody has thought about")
        if len(self.if_it_fails.split()) < 5:
            raise DependencyRefused(f"{self.key}: say what stops when this does")

    def present(self, env: dict[str, str] | None = None) -> bool | None:
        """Whether the dependency is configured. `None` where the code cannot tell."""
        if not self.env_probe:
            return None
        e = env if env is not None else os.environ
        return all((e.get(v) or "").strip() for v in self.env_probe)

    def to_dict(self, env: dict[str, str] | None = None) -> dict:
        return {"key": self.key, "what": self.what, "impact": self.impact,
                "if_it_fails": self.if_it_fails, "recovery": self.recovery,
                "recovery_minutes": self.recovery_minutes,
                "owner_only": self.owner_only,
                "configured": self.present(env),
                "probe": list(self.env_probe)}


DEPENDENCIES: tuple[Dependency, ...] = (
    Dependency(
        "postgres", "the company's entire memory: patterns, evidence, ledger, build state",
        FATAL,
        "every record the company has ever made becomes unreachable",
        ("restore from the most recent continuity export, whose restore is proved daily "
         "rather than assumed; the export is portable JSONL and needs no Railway"),
        recovery_minutes=60,
        env_probe=("DATABASE_URL",)),
    Dependency(
        "railway", "the host running the worker, scheduler and API",
        HALTING,
        "scheduled work stops and the dashboard goes dark; nothing is lost",
        ("the container builds from the repository Dockerfile and runs anywhere with a "
         "Postgres URL; redeploy elsewhere and point it at the restored database"),
        recovery_minutes=120),
    Dependency(
        "github", "the code, and the history of why it looks like this",
        DEGRADING,
        "no new deploys until a remote exists, and the decision log is unreachable",
        ("every clone is a full copy: push to a new remote from any working checkout, and "
         "the running container is unaffected because it already has the code"),
        recovery_minutes=30),
    Dependency(
        "etsy_account", "the only place the company can currently sell",
        FATAL,
        "the business has no route to a customer at all",
        ("owner-only to restore, and the pattern catalogue, assets and listing copy are all "
         "held here rather than there, so a second marketplace is a publishing target away"),
        recovery_minutes=0,
        env_probe=("ETSY_SHOP_ID",),
        owner_only=True),
    Dependency(
        "model_provider", "language and vision capability for the agent swarm",
        DEGRADING,
        "the deterministic spine keeps running; nothing can read an image or write in a voice",
        ("the gateway already routes across providers and refuses rather than degrading; "
         "swap the key for another vendor's without touching the callers"),
        recovery_minutes=10,
        env_probe=("ANTHROPIC_API_KEY",)),
    Dependency(
        "domain_email", "how a customer reaches a human, and how updates are sent",
        HALTING,
        "support and version notices cannot be delivered, and buyers hear nothing",
        ("the support queue is stored here and nothing is lost while delivery is down; "
         "re-point the domain or send from a fallback address once one is authorised"),
        recovery_minutes=240,
        owner_only=True),
    Dependency(
        "payment_rails", "how money actually arrives",
        FATAL,
        "sales may complete and the company cannot be paid for them",
        ("owner-only: the marketplace holds the payout relationship, so recovery is the "
         "account holder re-verifying rather than anything this system can do"),
        recovery_minutes=0,
        owner_only=True),
    Dependency(
        "tester_network", "the people who crochet a sample before a customer does",
        DEGRADING,
        "Class B and C products cannot be certified; Class A releases continue",
        ("physical test records are stored here, so a new tester inherits the calibration "
         "rather than starting it; the gate holds releases rather than waving them through"),
        recovery_minutes=0,
        owner_only=True),
    Dependency(
        "traffic_channels", "how anybody finds the listings",
        HALTING,
        "the catalogue exists and nobody arrives at it",
        ("the growth loop registry records which channels ever produced attributable "
         "traffic, so rebuilding starts from evidence rather than from a fresh guess"),
        recovery_minutes=0),
)

BY_KEY: dict[str, Dependency] = {d.key: d for d in DEPENDENCIES}


def map_state(db=None, env: dict[str, str] | None = None) -> dict:
    """The live map: what exists, what is configured, and what the worst loss would be.

    Grouped by impact rather than by vendor, because the question being answered is "what
    would stop", and vendor prestige gets that backwards routinely — Postgres holds the
    company's memory and GitHub holds a copy of code that also exists on disk.
    """
    rows = [d.to_dict(env) for d in DEPENDENCIES]
    by_impact: dict[str, list] = {}
    for row in rows:
        by_impact.setdefault(row["impact"], []).append(row["key"])

    unconfigured = [r["key"] for r in rows if r["configured"] is False]
    single_points = [r["key"] for r in rows if r["impact"] == FATAL]
    owner_only = [r["key"] for r in rows if r["owner_only"]]

    return {
        "dependencies": rows,
        "by_impact": {k: by_impact.get(k, []) for k in IMPACTS},
        "single_points_of_failure": single_points,
        "unconfigured": unconfigured,
        "owner_only_to_recover": owner_only,
        "worst_case_recovery_minutes": max(
            (r["recovery_minutes"] for r in rows if r["impact"] == FATAL), default=0),
        "note": ("Every dependency carries what stops and how it comes back; a recovery of "
                 "'we would have a problem' is refused at construction, because the natural "
                 "map marks three things critical and those are the three somebody was "
                 "already worried about (#50)."),
    }


def drill(key: str) -> dict:
    """The recovery for one dependency, in the form somebody would follow at 3am."""
    dependency = BY_KEY.get(key)
    if dependency is None:
        raise DependencyRefused(f"{key!r} is not a mapped dependency: {sorted(BY_KEY)}")
    return {
        "key": key,
        "impact": dependency.impact,
        "if_it_fails": dependency.if_it_fails,
        "recovery": dependency.recovery,
        "estimated_minutes": dependency.recovery_minutes,
        "owner_only": dependency.owner_only,
        "note": ("this one cannot be recovered by the system: it needs the account holder"
                 if dependency.owner_only else
                 "this recovery is within the system's own authority"),
    }
