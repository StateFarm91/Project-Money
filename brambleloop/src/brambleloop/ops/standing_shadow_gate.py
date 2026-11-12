"""WS4 Stage D acceptance: the G-SHADOW reading (design §7.3; §9 M6 item 10).

G-SHADOW is the gate a standing policy passes before it may leave SHADOW. Its criteria:

1. every §7.1 test and §7.2 mutant run is green -- measured by the test run, not by the
   running system, so this reading names it EXTERNAL and never claims it;
2. an SP is approved by the owner under step-up (a verified approval in the policy chain);
3. at least 7 days (or the policy's own longer shadow period) and at least 10 real candidates
   of `standing_policy.shadow_decision` rows for that approval;
4. each would-issue decision agrees with what the owner decided for that exact release through
   today's per-product grant: ZERO cases where the policy would have issued and the owner
   refused (revoked) or held (never granted). An undecided release is not agreement;
5. the stop watch read the policy with no silence over 30 minutes for the last 7 days.

`g_shadow(db)` reads each criterion from rows as {state, value, why}; the verdict is MET only
when 2-5 are PASS (and then still owes criterion 1 to the test run). It is a reading: it
records itself (`standing_policy.g_shadow`) and authorises nothing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import standing_boundary as SB
from . import standing_policy as SP

READING = "standing_policy.g_shadow"
MIN_CANDIDATES = 10
STOP_WATCH_DAYS = 7
EXTERNAL = "EXTERNAL"


def _now(now=None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _fact(state, value=None, why=None) -> dict:
    return {"state": state, "value": value, "why": why}


def _rows(db, action: str, artifact: str) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        return [dict(d or {}) for d in s.scalars(select(AuditLog.detail).where(
            AuditLog.action == action, AuditLog.artifact == artifact).order_by(AuditLog.id))]


def _shadow_rows(db, policy_id: str, approval_id: int) -> list[dict]:
    return [d for d in _rows(db, SP.SHADOW_DECISION, policy_id)
            if d.get("approval_id") == approval_id and d.get("shadow") is True]


def _period(policy: dict, rows: list[dict], now: datetime) -> dict:
    days = max(SP.MIN_SHADOW_DAYS, int((policy["content"].get("evidence") or {}).get(
        "min_shadow_days_before_activation") or 0))
    times = [t for t in (SP._when(d.get("decided_at")) for d in rows) if t is not None]
    releases = {(d.get("slug"), d.get("version"), d.get("release")) for d in rows}
    value = {"days_required": days, "first_decision_at": min(times).isoformat()
             if times else None, "distinct_releases": len(releases),
             "candidates_required": MIN_CANDIDATES}
    why = []
    if not times or now - min(times) < timedelta(days=days):
        why.append(f"shadow decisions span less than {days} days")
    if len(releases) < MIN_CANDIDATES:
        why.append(f"{len(releases)} distinct candidate release(s); {MIN_CANDIDATES} needed")
    return _fact(SB.FAIL, value, "; ".join(why)) if why else _fact(SB.PASS, value)


def _owner_grants(db) -> dict[tuple[str, str, str], str]:
    """(slug, version, release) -> "approved" | "revoked", from the VERIFIED per-product owner
    publication grant chain. A chain that does not verify raises (the caller reads UNKNOWN)."""
    from ..core.sealed_chain import load
    from . import publication_authority as pub

    c = pub.LEDGER.chain(db)
    if not c.get("valid"):
        raise ValueError(f"the owner publication grant chain does not verify: {c.get('why')}")
    flags = {rid: ok for rid, ok, _why in c.get("rows") or []}
    start = int(c.get("start_id") or 0)
    with db.session() as s:
        rows = [(rid, d) for rid, d in load(s, pub.LEDGER.actions)
                if rid >= start and flags.get(rid)]
    revoked = {d.get("approval_id") for _rid, d in rows if d.get("event") == pub.REVOKED}
    out: dict[tuple[str, str, str], str] = {}
    for rid, d in rows:
        if d.get("event") != pub.APPROVED:
            continue
        slug, _, version = str(d.get("scope") or "").partition("@")
        key = (slug, version, str(d.get("release") or ""))
        state = "revoked" if rid in revoked else "approved"
        # Any revocation of a grant for this exact release is a refusal, whatever came later.
        out[key] = "revoked" if out.get(key) == "revoked" else state
    return out


def _agreement(db, rows: list[dict]) -> dict:
    would = sorted({(d.get("slug"), d.get("version"), d.get("release")) for d in rows
                    if d.get("decision") == "ISSUE"})
    grants = _owner_grants(db)
    refused = [w for w in would if grants.get(w) == "revoked"]
    undecided = [w for w in would if w not in grants]
    value = {"would_issue": len(would), "owner_approved": len(would) - len(refused)
             - len(undecided), "owner_refused": len(refused), "undecided": len(undecided)}
    if refused:
        return _fact(SB.FAIL, value, "the policy would have issued releases the owner refused: "
                     + ", ".join(f"{s}@{v}:{str(r)[:12]}" for s, v, r in refused[:5]))
    if undecided:
        return _fact(SB.FAIL, value, "would-issue releases the owner has not decided (held): "
                     + ", ".join(f"{s}@{v}:{str(r)[:12]}" for s, v, r in undecided[:5]))
    return _fact(SB.PASS, value, None if would else "no would-issue decision to compare")


def _stop_watch(db, policy_id: str, now: datetime) -> dict:
    from . import standing_stop

    since = now - timedelta(days=STOP_WATCH_DAYS)
    times = sorted(t for t in (SP._when(d.get("read_at"))
                               for d in _rows(db, standing_stop.READING, policy_id))
                   if t is not None and t <= now)
    if not times or times[0] > since:
        return _fact(SB.FAIL, {"first_reading_at": times[0].isoformat() if times else None},
                     f"the stop watch has not read this policy for {STOP_WATCH_DAYS} days")
    window = [since] + [t for t in times if t > since] + [now]
    # The reading at or before the window start covers its beginning.
    window[0] = max(t for t in times if t <= since)
    gaps = [(b - a).total_seconds() / 60 for a, b in zip(window, window[1:])]
    worst = max(gaps) if gaps else 0.0
    value = {"readings": len(window) - 1, "longest_silence_minutes": round(worst, 1)}
    if worst > SP.MAX_STOP_WATCH_SILENCE_MINUTES:
        return _fact(SB.FAIL, value, f"the stop watch was silent {worst:.0f} minutes (over "
                                     f"{SP.MAX_STOP_WATCH_SILENCE_MINUTES})")
    return _fact(SB.PASS, value)


def g_shadow(db, *, now: datetime | None = None, record: bool = True) -> dict:
    """The G-SHADOW reading for the owner's newest approved policy."""
    from . import standing_issuer as SI

    now = _now(now)
    criteria: dict[str, dict] = {
        "tests_and_mutants": _fact(EXTERNAL, None, "measured by the §7 test and mutant run, "
                                                   "not by the running system"),
    }
    policy = SI.shadow_policy(db, now=now)
    if policy is None:
        criteria["policy_approved"] = _fact(SB.FAIL, None, "no approved standing policy")
        out = {"verdict": "NOT_MET", "policy_id": None, "approval_id": None,
               "criteria": criteria, "read_at": now.isoformat()}
        return _record(db, out, None) if record else out
    pid, aid = policy["content"]["policy_id"], policy["approval_id"]
    criteria["policy_approved"] = _fact(SB.PASS, aid)
    rows = _shadow_rows(db, pid, aid)
    for name, fn in (("shadow_period", lambda: _period(policy, rows, now)),
                     ("owner_agreement", lambda: _agreement(db, rows)),
                     ("stop_watch_continuity", lambda: _stop_watch(db, pid, now))):
        try:
            criteria[name] = fn()
        except Exception as exc:  # noqa: BLE001 - unreadable is not met
            criteria[name] = _fact(SB.UNKNOWN, None, f"unreadable ({type(exc).__name__}: "
                                                     f"{str(exc)[:120]})")
    met = all(c["state"] == SB.PASS for k, c in criteria.items() if k != "tests_and_mutants")
    out = {"verdict": "MET" if met else "NOT_MET", "policy_id": pid, "approval_id": aid,
           "owes": ["tests_and_mutants"] if met else [],
           "criteria": criteria, "read_at": now.isoformat()}
    return _record(db, out, pid) if record else out


def _record(db, out: dict, policy_id: str | None) -> dict:
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="standing_issuer", action=READING,
                       artifact=policy_id or "none", detail=out))
    return out
