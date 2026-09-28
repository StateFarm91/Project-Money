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
    # F-128 / F-131: `configured` is a fact about variables and stays named as one; it is never
    # the capability. Where a dependency has a probe-based executor gate, `capability` reads
    # that gate -- the same recorded probe the executor trusts -- and a configured dependency
    # whose probe has not succeeded reads UNPROVEN, not configured-therefore-fine. Without a
    # database nothing can be proven, so capability is UNKNOWN rather than inferred.
    for row in rows:
        row["capability"] = _capability(row["key"], db, row["configured"])
    by_impact: dict[str, list] = {}
    for row in rows:
        by_impact.setdefault(row["impact"], []).append(row["key"])

    unconfigured = [r["key"] for r in rows if r["configured"] is False]
    unproven = [r["key"] for r in rows if r["capability"]["state"] == "UNPROVEN"]
    single_points = [r["key"] for r in rows if r["impact"] == FATAL]
    owner_only = [r["key"] for r in rows if r["owner_only"]]

    return {
        "dependencies": rows,
        "by_impact": {k: by_impact.get(k, []) for k in IMPACTS},
        "single_points_of_failure": single_points,
        "unconfigured": unconfigured,
        "configured_but_unproven": unproven,
        "capability_source": ("executor gate predicates over recorded probes "
                              "(build2.executor.GATE_BY_KEY); environment presence is "
                              "reported as `configured` and never read as capability"),
        "owner_only_to_recover": owner_only,
        "worst_case_recovery_minutes": max(
            (r["recovery_minutes"] for r in rows if r["impact"] == FATAL), default=0),
        "note": ("Every dependency carries what stops and how it comes back; a recovery of "
                 "'we would have a problem' is refused at construction, because the natural "
                 "map marks three things critical and those are the three somebody was "
                 "already worried about (#50)."),
    }


def _capability(key: str, db, configured: bool | None) -> dict:
    """PROVEN / UNPROVEN / UNKNOWN for one dependency, from its executor gate's probe."""
    gate_key = PROBE_GATES.get(key)
    if gate_key is None:
        return {"state": "UNKNOWN", "gate": None,
                "why": "no probe-based gate exists for this dependency; UNKNOWN, not healthy"}
    if db is None:
        return {"state": "UNKNOWN", "gate": gate_key,
                "why": "no database was consulted, so no probe could be read"}
    from ..build2 import executor

    try:
        ok = bool(executor.GATE_BY_KEY[gate_key].open(db))
    except Exception as exc:  # noqa: BLE001 -- unreadable evidence is not evidence
        return {"state": "UNKNOWN", "gate": gate_key,
                "why": f"the probe could not be read: {type(exc).__name__}"}
    if ok:
        return {"state": "PROVEN", "gate": gate_key,
                "why": f"the {gate_key} gate is open on a recorded probe"}
    return {"state": "UNPROVEN" if configured else "UNKNOWN", "gate": gate_key,
            "why": (f"the {gate_key} gate is closed: "
                    + ("configured, but no recorded probe has succeeded -- a variable is a "
                       "label, not a capability" if configured else
                       "nothing configured and nothing proven"))}


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


# ---------------------------------------------------------------------------
# #50 continuously (C-69): the map run daily against live evidence, and acted on.

DEPENDENCY_SIGNATURE = "dependency"
# The postgres recovery strategy is the continuity restore; it counts only while proved.
RESTORE_PROOF_MAX_AGE_DAYS = 2
# What each dependency's live probe reads, beyond environment configuration.
PROBE_GATES: dict[str, str] = {"model_provider": "model_provider", "etsy_account": "etsy_api",
                               "tester_network": "tester_roster"}


# The health sweep's cadence (runtime.worker CADENCES: ops.health every 15 minutes) is the
# evidence the container is being kept running; a gap of this many minutes between sweeps in
# the last day is an outage the host let happen.
HEALTH_SWEEP_MINUTES = 15
RAILWAY_MAX_GAP_MINUTES = 120
RAILWAY_ENV_MARKERS = ("RAILWAY_ENVIRONMENT", "RAILWAY_GIT_COMMIT_SHA", "RAILWAY_SERVICE_ID",
                       "RAILWAY_PROJECT_ID")


def _railway_probe(session, env: dict, now) -> dict:
    """Whether the host has kept the container running, from the health sweep's own rows.

    C-80 defect 9: this was `{"ok": True, "why": "this probe is running on it"}`, a constant.
    Now: not on Railway at all (no RAILWAY_* marker in the environment) is UNKNOWN, not
    healthy; on Railway, the `ops.health` sweep rows of the last 24 hours are the evidence --
    none yet is UNKNOWN, a gap longer than RAILWAY_MAX_GAP_MINUTES is a failed probe, and a
    continuous record is ok.
    """
    from datetime import timedelta, timezone

    from sqlalchemy import select

    from ..core.models import AuditLog

    markers = sorted(m for m in RAILWAY_ENV_MARKERS if (env or {}).get(m))
    if not markers:
        return {"ok": None, "on_railway": False,
                "why": "no RAILWAY_* environment marker: this process is not running on "
                       "Railway, so the host cannot be probed from here; UNKNOWN, not healthy"}
    since = now - timedelta(hours=24)
    stamps = sorted((r if r.tzinfo else r.replace(tzinfo=timezone.utc)) for r in
                    session.scalars(select(AuditLog.at).where(AuditLog.action == "ops.health",
                                                              AuditLog.at >= since)))
    if not stamps:
        return {"ok": None, "on_railway": True, "markers": markers, "health_rows_24h": 0,
                "why": "on Railway, but no ops.health sweep has been recorded in 24h yet; "
                       "UNKNOWN until the first sweep"}
    gaps = [(b - a).total_seconds() / 60 for a, b in zip(stamps, stamps[1:])]
    latest_age = (now - stamps[-1]).total_seconds() / 60
    max_gap = max(gaps + [latest_age])
    ok = max_gap <= RAILWAY_MAX_GAP_MINUTES
    return {"ok": ok, "on_railway": True, "markers": markers, "health_rows_24h": len(stamps),
            "max_gap_minutes": round(max_gap, 1), "latest_sweep_age_minutes": round(latest_age, 1),
            "why": (f"the health sweep ran {len(stamps)} time(s) in 24h with no gap over "
                    f"{RAILWAY_MAX_GAP_MINUTES} min: the host kept the container running"
                    if ok else
                    f"a {max_gap:.0f}-minute gap in the health sweep's 24h record (cadence "
                    f"{HEALTH_SWEEP_MINUTES} min): the host did not keep the container running")}


def probe(db, env: dict[str, str] | None = None) -> dict:
    """Each dependency checked against the database: reachable, proven, or UNKNOWN."""
    import os
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import desc, select, text

    from ..core.models import AuditLog, CostEntry

    env = dict(os.environ) if env is None else env
    now = datetime.now(timezone.utc)
    out: dict[str, dict] = {}
    railway = None
    try:
        with db.session() as s:
            s.execute(text("select 1"))
            restore = s.scalar(select(AuditLog.at).where(
                AuditLog.action == "continuity.verified").order_by(desc(AuditLog.id)).limit(1))
            providers = sorted({(c.provider or "").strip() for c in s.scalars(
                select(CostEntry).where(CostEntry.at >= now - timedelta(days=30)))
                if (c.provider or "").strip()})
            railway = _railway_probe(s, env, now)
        reachable = True
    except Exception as exc:  # noqa: BLE001 - an unreachable database is the finding
        reachable, restore, providers = False, None, []
        out["postgres"] = {"ok": False, "why": f"{type(exc).__name__}: {exc}"[:200]}
    if reachable:
        at = (None if restore is None else
              restore if restore.tzinfo else restore.replace(tzinfo=timezone.utc))
        proved = at is not None and now - at <= timedelta(days=RESTORE_PROOF_MAX_AGE_DAYS)
        out["postgres"] = {"ok": proved, "recovery_proved": proved,
                           "last_restore_proof": at.isoformat() if at else None,
                           "why": ("reachable, and its recovery (the continuity restore) was "
                                   "proved recently" if proved else
                                   "reachable, but its recovery strategy has not been proved "
                                   f"within {RESTORE_PROOF_MAX_AGE_DAYS} days")}
    out["railway"] = railway or {"ok": None, "why": "the database was unreachable, so the "
                                                      "health record could not be read; UNKNOWN"}
    from ..build2 import executor

    for key, gate_key in PROBE_GATES.items():
        try:
            ok = bool(executor.GATE_BY_KEY[gate_key].open(db))
        except Exception:  # noqa: BLE001
            ok = False
        out[key] = {"ok": ok, "gate": gate_key,
                    "why": f"the {gate_key} gate is {'open' if ok else 'closed'}"}
    for d in DEPENDENCIES:
        out.setdefault(d.key, {"ok": None, "why": "no live probe exists for this dependency; "
                                                  "UNKNOWN, not healthy"})
    return {"probes": out, "providers_in_use": providers}


def sweep(db, env: dict[str, str] | None = None) -> dict:
    """Map, probe and act: an incident per failed probe, per unmapped dependency in use and
    per recovery strategy that is missing or unproved; resolved when the probe recovers."""
    from sqlalchemy import select

    from ..core.models import Incident

    state = map_state(db, env)
    live = probe(db, env)
    mapped = {d.key for d in DEPENDENCIES}
    # A provider the company is paying that the map does not name is a dependency nobody
    # planned a recovery for -- found from the cost ledger, not remembered.
    provider_keys = {"anthropic": "model_provider", "openai": "model_provider",
                     "google": "model_provider", "gemini": "model_provider"}
    unmapped = sorted(p for p in live["providers_in_use"]
                      if provider_keys.get(p.lower(), p.lower()) not in mapped)
    findings: dict[str, dict] = {}
    for key, p in live["probes"].items():
        d = BY_KEY.get(key)
        if p.get("ok") is False and d is not None and not d.owner_only:
            findings[f"{DEPENDENCY_SIGNATURE}:{key}"] = {
                "severity": "P1" if d.impact == FATAL else "P2",
                "summary": f"dependency {key} failed its live probe: {p['why']}",
                "detail": {"dependency": key, "impact": d.impact, "probe": p,
                           "recovery": d.recovery}}
    for name in unmapped:
        findings[f"{DEPENDENCY_SIGNATURE}:unmapped:{name}"] = {
            "severity": "P2",
            "summary": (f"{name} is billed in the cost ledger and has no mapped recovery "
                        f"strategy (#50)"),
            "detail": {"provider": name}}
    opened, resolved = [], []
    with db.session() as s:
        open_rows = {i.signature: i for i in s.scalars(select(Incident).where(
            Incident.resolved.is_(False),
            Incident.signature.like(f"{DEPENDENCY_SIGNATURE}:%")))}
        for sig, f in findings.items():
            row = open_rows.get(sig)
            if row is None:
                s.add(Incident(severity=f["severity"], signature=sig, summary=f["summary"],
                               halts_publication=False, detail=f["detail"]))
                opened.append(sig)
            else:
                row.report_count = (row.report_count or 1) + 1
                row.detail = f["detail"]
        for sig, row in open_rows.items():
            if sig not in findings:
                row.resolved = True
                resolved.append(sig)
    return {"map": {k: state[k] for k in ("single_points_of_failure", "unconfigured",
                                          "owner_only_to_recover")},
            "probes": live["probes"], "providers_in_use": live["providers_in_use"],
            "unmapped": unmapped, "incidents_opened": opened, "incidents_resolved": resolved,
            "failing": sorted(k for k, p in live["probes"].items() if p.get("ok") is False),
            "unknown": sorted(k for k, p in live["probes"].items() if p.get("ok") is None)}
