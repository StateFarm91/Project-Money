"""F-099 Provider Change Watch: versioned provider prices and availability, re-planned on change.

F-099: "Version provider pricing/model availability and re-run routing economics on material
change."

The prices the gateway charges against (`gateway.anthropic.PRICES_USD_PER_MTOK`), the model each
routing tier uses (`routing.TIERS`), and the availability `failover.health` reads from real
attempts are snapshotted daily (`ops.dependencies`). The snapshot is versioned by content hash
(`gateway.provider_snapshot` audit rows carry version n, its effective date and the hash). On a
material change -- a price, a tier's model, or a model going DOWN / coming back -- it records
`gateway.provider_change` with exactly what changed, re-runs the routing economics
(`routing.plan`) and records that review (`routing.economics_review`), and opens a P2 incident
`provider-change:<what>` that the next unchanged snapshot resolves. The first snapshot is a
baseline, never a "change". Reads and writes rows only; calls no provider.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

SNAPSHOT_ACTION = "gateway.provider_snapshot"
CHANGE_ACTION = "gateway.provider_change"
REVIEW_ACTION = "routing.economics_review"
SIGNATURE = "provider-change:"


def current(db) -> dict:
    from . import anthropic, failover, routing

    prices = {m: list(v) for m, v in sorted(anthropic.PRICES_USD_PER_MTOK.items())}
    tiers = {k: t.model for k, t in sorted(routing.TIERS.items())}
    try:
        health = failover.health(db)
        # Material availability only: DOWN or serving. The minute-to-minute health states
        # (UNKNOWN between attempts, DEGRADED on one error) would make every day a "change".
        availability = {k: ("down" if v.get("state") == failover.DOWN else "serving")
                        for k, v in sorted(health.items())}
    except Exception as exc:  # noqa: BLE001 - unreadable availability is not "all up"
        availability = {"_unreadable": f"{type(exc).__name__}"}
    return {"prices_usd_per_mtok": prices, "tier_models": tiers,
            "availability": availability}


def _hash(snap: dict) -> str:
    return hashlib.sha256(json.dumps(snap, sort_keys=True).encode()).hexdigest()


def diff(old: dict, new: dict) -> list[dict]:
    out = []
    for section in ("prices_usd_per_mtok", "tier_models", "availability"):
        a, b = old.get(section) or {}, new.get(section) or {}
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                out.append({"what": f"{section}:{k}", "from": a.get(k), "to": b.get(k)})
    return out


def watch(db, *, now: datetime | None = None) -> dict:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..ops import incident_lifecycle as lifecycle
    from . import routing

    now = now or datetime.now(timezone.utc)
    snap = current(db)
    digest = _hash(snap)
    with db.session() as s:
        last = s.scalar(select(AuditLog).where(AuditLog.action == SNAPSHOT_ACTION)
                        .order_by(desc(AuditLog.id)).limit(1))
        prev = dict(last.detail or {}) if last is not None else None
    if prev is not None and prev.get("sha256") == digest:
        with db.session() as s:
            resolved = lifecycle.reconcile(
                s, SIGNATURE, lambda _row: False,
                resolution=f"provider snapshot v{prev.get('version')} unchanged on "
                           f"{now.date().isoformat()}; routing economics re-reviewed",
                now=now)["resolved"]
        return {"version": prev.get("version"), "changed": [], "baseline": False,
                "resolved": resolved}
    version = int((prev or {}).get("version") or 0) + 1
    changes = diff(prev.get("snapshot") or {}, snap) if prev is not None else []
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=SNAPSHOT_ACTION, at=now,
                       detail={"version": version, "effective": now.isoformat(),
                               "sha256": digest, "snapshot": snap}))
    if prev is None:
        return {"version": version, "changed": [], "baseline": True}
    try:
        plan = routing.plan(db, now=now)
        review = {"ok": True, "plan": {k: plan.get(k) for k in list(plan)[:8]}}
    except Exception as exc:  # noqa: BLE001 - a failed review is recorded, never skipped
        review = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=CHANGE_ACTION, at=now,
                       detail={"from_version": version - 1, "to_version": version,
                               "changes": changes}))
        s.add(AuditLog(actor="orchestrator", action=REVIEW_ACTION, at=now,
                       detail={"trigger": f"provider snapshot v{version}",
                               "changes": [c["what"] for c in changes], **review}))
        for c in changes:
            lifecycle.open_or_restate(
                s, signature=f"{SIGNATURE}{c['what']}"[:200], severity="P2",
                summary=(f"provider {c['what']} changed {c['from']!r} -> {c['to']!r}; routing "
                         f"economics re-run (v{version}, F-099)"),
                detail={"change": c, "review_ok": review["ok"]}, now=now)
    # F-096: a changed provider needs a fresh compatibility pack before it is trusted; the
    # last recorded pack is shown, and it is stale by definition once the snapshot moved.
    from . import compat_pack

    last_pack = compat_pack.latest(db)
    return {"version": version, "changed": changes, "baseline": False,
            "review": review["ok"],
            "compat_pack": {"required": True, "families": list(compat_pack.FAMILIES),
                            "last": ({"at": last_pack["at"],
                                      "compatible": last_pack.get("compatible")}
                                     if last_pack else None),
                            "stale": True}}
