"""WS4 stop watch (design §5.1; §9 M6 increment 8): the standing policy's automatic stops.

`conditions(db, content, *, now)` reads every stop condition of design §5.1 from rows, each as
``{"state": PASS|FAIL|UNKNOWN, "value": ..., "why": ...}``. A condition that HOLDS reads FAIL;
a source that cannot be read reads UNKNOWN, and UNKNOWN counts as STOP. `holding(...)` is the
list of every condition that does not read PASS -- empty only when every one reads PASS.

The job `policy.stop_watch` (class OBSERVE, every 5 minutes) records one reading per tick
(`standing_policy.stop_watch_reading`). The reading's age is the silence fact: the issuer and
the worker refuse when the newest reading is older than the policy's
`stop_watch_max_silence_minutes` (never more than the code ceiling, 30).

What a holding condition does depends on whether the policy is ACTIVATED:

* activated -> `standing_policy.suspend` (sealed, deny-only, sticky) naming the condition,
  its reading and the time; a P1 incident `standing_policy_suspended:{policy_id}`; the
  Command Center standing-policy card already shows a suspended policy with its resume and
  revoke acts. A suspension never clears by itself: only the owner's `resume` (step-up) does,
  and `resume` refuses while `holding` is non-empty (this module is its default reader).
* approved but not activated (the shadow period) -> the reading records `would_suspend`
  and nothing else. Suspending a policy that cannot issue would only raise noise, and the
  publishing-phase condition holds by construction in SHADOW; that one condition is
  recorded as ASSUMED in shadow, as the issuer records its activation-time facts.

Standing-policy lineage. A condition scoped to "a product the SP published" needs the SEG
lineage (consumed grant <-> listing). No standing grant has ever been issued -- there is no
grant store until the Mode T increment -- so the lineage is exactly empty, a fact read from
`lineage()`, not an assumption. The per-lineage conditions are read for real over that set
and are exercised with a non-empty set in the tests. Shop-wide conditions (refunds, Etsy
notices, P0, tamper, dead letters, platform-policy freshness) are not scoped to the lineage:
they stop the policy whatever product they concern.

Nothing here signs a grant or can widen authority: every write is deny-direction.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import standing_boundary as SB
from . import standing_policy as SP

JOB_TYPE = "policy.stop_watch"
ACTOR = "standing_stop_watch"
READING = "standing_policy.stop_watch_reading"
INCIDENT_PREFIX = "standing_policy_suspended:"
CADENCE_SECONDS = 5 * 60
TAMPER_PREFIX = "authority_chain_tamper:"
# The publishing-phase condition holds by construction before activation (the shadow period
# runs in SHADOW); recorded as ASSUMED in shadow, read for real once the policy is activated.
ASSUMED_IN_SHADOW = ("phase_publishes",)
PUBLISHING_PHASES = ("limited_production", "production")


def _now(now=None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _fact(state: str, value=None, why: str | None = None) -> dict:
    return {"state": state, "value": value, "why": why}


def _guard(fn):
    """An unreadable source is UNKNOWN, and UNKNOWN is a stop."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return _fact(SB.UNKNOWN, None, f"source unreadable ({type(exc).__name__})")


def _aware(at):
    if at is None:
        return None
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------------------------
# Standing-policy lineage
# ---------------------------------------------------------------------------------------------

def lineage(db, policy_id: str) -> dict:
    """The products and Etsy listings a standing grant of `policy_id` published.

    Exactly empty today: no standing grant has been issued (the grant store and the issuer
    process are the Mode T increment). Returned with that reason so a reading says so."""
    return {"products": set(), "listing_ids": set(),
            "why": "no standing grant has been issued, so no product is in standing lineage"}


# ---------------------------------------------------------------------------------------------
# The conditions (design §5.1), each read from rows
# ---------------------------------------------------------------------------------------------

def _open_incidents(db, *, prefix: str | None = None, severity: str | None = None) -> list:
    from sqlalchemy import select

    from ..core.models import Incident

    q = select(Incident.signature, Incident.severity, Incident.product_slug).where(
        Incident.resolved == False)  # noqa: E712
    if prefix is not None:
        q = q.where(Incident.signature.like(f"{prefix}%"))
    if severity is not None:
        q = q.where(Incident.severity == severity)
    with db.session() as s:
        return [r for r in s.execute(q)
                if prefix is None or str(r.signature).startswith(prefix)]


def _defects(db, products: set, threshold: int) -> dict:
    """Open support-defect incidents (`support.defects._active`) on a lineage product."""
    from sqlalchemy import select

    from ..core.models import Incident
    from ..support import defects

    if not products:
        return _fact(SB.PASS, 0, "no product is in standing lineage")
    with db.session() as s:
        rows = [i for i in s.scalars(select(Incident).where(
            Incident.signature.like(f"{defects.SIGNATURE}%")))
            if i.signature.startswith(defects.SIGNATURE) and defects._active(i)]
        hits = sorted(i.signature for i in rows
                      if i.signature[len(defects.SIGNATURE):].split(":", 1)[0] in products)
    if len(hits) >= threshold:
        return _fact(SB.FAIL, len(hits), f"{len(hits)} open defect incident(s) on standing "
                                         f"products (stop at {threshold}): {hits[:3]}")
    return _fact(SB.PASS, len(hits))


def _refunds(db, now: datetime, count_7d: int, rate_30d_pct: float) -> dict:
    """Shop-wide: refunds in 7 days, and the refund rate over 30 days, of every order whose
    money is in the books (`orders_ingest.booked_orders`: countable or voided)."""
    from sqlalchemy import select

    from ..commerce import orders_ingest
    from ..core.models import Order

    since30 = now - timedelta(days=30)
    since7 = now - timedelta(days=7)
    with db.session() as s:
        rows = [(_aware(o.at), bool(o.refunded)) for o in orders_ingest.booked_orders(
            s, select(Order).where(Order.at >= since30))]
    rows = [(at, r) for at, r in rows if at is not None and at >= since30]
    refunds_7d = sum(1 for at, r in rows if r and at >= since7)
    refunded_30d = sum(1 for _at, r in rows if r)
    rate = (100.0 * refunded_30d / len(rows)) if rows else 0.0
    value = {"refunds_7d": refunds_7d, "orders_30d": len(rows),
             "refund_rate_30d_pct": round(rate, 2)}
    why = []
    if refunds_7d >= count_7d:
        why.append(f"{refunds_7d} refund(s) in 7 days (stop at {count_7d})")
    if rate > rate_30d_pct:
        why.append(f"refund rate {rate:.1f}% over 30 days (stop above {rate_30d_pct:g}%)")
    return _fact(SB.FAIL, value, "; ".join(why)) if why else _fact(SB.PASS, value)


def _etsy_notices(db) -> dict:
    """Any open Etsy policy-violation incident (any severity) or suspected takedown."""
    from ..commerce import policy_violations as pv

    hits = sorted(r.signature for r in _open_incidents(db, prefix=pv.PREFIX)) + sorted(
        r.signature for r in _open_incidents(db, prefix=pv.SUSPECTED))
    if hits:
        return _fact(SB.FAIL, len(hits), f"open Etsy policy notice(s): {hits[:3]}")
    return _fact(SB.PASS, 0)


def _platform_policy(db, now: datetime) -> dict:
    from ..gates import platform_policy

    f = platform_policy.freshness(db, today=now.date())
    bad = ([f"never read: {s}" for s in f.get("never_checked") or []]
           + [f"stale: {e['source']}" for e in f.get("stale") or []]
           + [f"changed, unreviewed: {s}" for s in f.get("changed_unreviewed") or []])
    if bad or f.get("all_fresh") is not True:
        return _fact(SB.FAIL, False, "platform-policy reading: " + "; ".join(bad[:4]))
    return _fact(SB.PASS, True)


def _spend(db, lin: dict) -> dict:
    """Spend over the policy's cap (zero: drafts only, ads NONE) or a SpendGuard refusal
    naming standing lineage. Spend can carry standing lineage only through a lineage
    product; with none, nothing can have been spent under the policy. A non-empty lineage
    needs the grant store's spend join (Mode T increment): until then it reads UNKNOWN, and
    UNKNOWN stops."""
    if not lin["products"]:
        return _fact(SB.PASS, 0, "no product is in standing lineage")
    return _fact(SB.UNKNOWN, None, "spend under standing lineage is not readable until the "
                                   "grant store exists")


def _dead_letters(db, now: datetime, threshold: int) -> dict:
    """Unexpected dead letters in the last 60 minutes (deliberate refusals excluded, as the
    production-evidence reading classifies them)."""
    from . import production_evidence

    out = production_evidence.dead_letters(db, now=now, hours=1)
    n = int(out["unexpected_total"])
    if n >= threshold:
        return _fact(SB.FAIL, n, f"{n} unexpected dead letter(s) in 60 minutes (stop at "
                                 f"{threshold})")
    return _fact(SB.PASS, n)


def _p0(db) -> dict:
    hits = sorted(r.signature for r in _open_incidents(db, severity="P0"))
    return (_fact(SB.FAIL, len(hits), f"open P0 incident(s): {hits[:3]}") if hits
            else _fact(SB.PASS, 0))


def _tamper(db) -> dict:
    hits = sorted(r.signature for r in _open_incidents(db, prefix=TAMPER_PREFIX))
    return (_fact(SB.FAIL, len(hits), f"authority chain tamper: {hits[:3]}") if hits
            else _fact(SB.PASS, 0))


def _publish_incomplete(db, lin: dict) -> dict:
    from ..runtime import etsy_ops

    if not lin["products"]:
        return _fact(SB.PASS, 0, "no product is in standing lineage")
    hits = sorted(r.signature for r in _open_incidents(db, prefix=etsy_ops.PUBLISH_INCOMPLETE)
                  if r.signature[len(etsy_ops.PUBLISH_INCOMPLETE):].split("@", 1)[0]
                  in lin["products"])
    return (_fact(SB.FAIL, len(hits), f"publish incomplete on standing product(s): "
                                      f"{hits[:3]}") if hits else _fact(SB.PASS, 0))


def _census_drift(db, lin: dict) -> dict:
    from ..runtime import etsy_ops

    if not lin["listing_ids"]:
        return _fact(SB.PASS, 0, "no Etsy listing is in standing lineage")
    ids = {str(i) for i in lin["listing_ids"]}
    hits = sorted(r.signature for r in _open_incidents(db, prefix=etsy_ops.LISTING_DRIFT)
                  if r.signature[len(etsy_ops.LISTING_DRIFT):] in ids)
    return (_fact(SB.FAIL, len(hits), f"census drift on standing listing(s): {hits[:3]}")
            if hits else _fact(SB.PASS, 0))


def _phase(db) -> dict:
    from ..core import phase

    p = phase.effective(db, record_incident=False)
    if p in PUBLISHING_PHASES:
        return _fact(SB.PASS, p)
    return _fact(SB.FAIL, p, f"effective phase is {p}, below limited_production")


def conditions(db, content: dict, *, now: datetime | None = None, activated: bool = True,
               lin: dict | None = None) -> dict:
    """Every §5.1 condition except silence (which is a fact about the readings themselves,
    `silence`), each guarded. `content` supplies the thresholds; content that fails the code
    ceilings is itself a stop."""
    now = _now(now)
    if SP.ceiling_refusals(content if isinstance(content, dict) else {}):
        return {"policy_content": _fact(SB.FAIL, None, "policy content fails the code "
                                                        "ceilings")}
    st = content["stop_conditions"]
    lin_fact = _guard(lambda: _fact(SB.PASS, lineage(db, content["policy_id"])))
    if lin is None and lin_fact["state"] == SB.PASS:
        lin = lin_fact["value"]
    out: dict[str, dict] = {}
    if lin is None:
        for name in ("open_defect_incident_on_policy_product", "spend",
                     "publish_incomplete_any", "census_drift_on_policy_listing"):
            out[name] = lin_fact
    else:
        out["open_defect_incident_on_policy_product"] = _guard(lambda: _defects(
            db, set(lin["products"]), int(st["open_defect_incident_on_policy_product"])))
        out["spend"] = _guard(lambda: _spend(db, lin))
        out["publish_incomplete_any"] = _guard(lambda: _publish_incomplete(db, lin))
        out["census_drift_on_policy_listing"] = _guard(lambda: _census_drift(db, lin))
    out["refunds"] = _guard(lambda: _refunds(db, now, int(st["refunds_7d_count"]),
                                             float(st["refund_rate_30d_pct"])))
    out["etsy_policy_notice_any"] = _guard(lambda: _etsy_notices(db))
    out["platform_policy_fresh"] = _guard(lambda: _platform_policy(db, now))
    out["dead_letters_60m"] = _guard(lambda: _dead_letters(db, now,
                                                           int(st["dead_letters_60m"])))
    out["open_p0_any"] = _guard(lambda: _p0(db))
    out["authority_tamper_any"] = _guard(lambda: _tamper(db))
    if activated:
        out["phase_publishes"] = _guard(lambda: _phase(db))
    else:
        out["phase_publishes"] = _fact(SB.PASS, None, "assumed for shadow: the policy is "
                                                      "not activated")
    return out


def _reasons(conds: dict) -> list[str]:
    out = []
    for name, f in sorted(conds.items()):
        state = f.get("state") if isinstance(f, dict) else None
        if state != SB.PASS:
            why = (f or {}).get("why") if isinstance(f, dict) else None
            out.append(f"{name}: {state if state in (SB.FAIL, SB.UNKNOWN) else 'UNKNOWN'}"
                       + (f" ({why})" if why else ""))
    return out


# ---------------------------------------------------------------------------------------------
# Readings and silence
# ---------------------------------------------------------------------------------------------

def last_reading(db, policy_id: str) -> dict | None:
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == READING,
                                              AuditLog.artifact == str(policy_id))
                       .order_by(AuditLog.id.desc()).limit(1))
        return dict(row.detail or {}) if row is not None else None


def silence_limit_minutes(content: dict) -> int:
    """The policy's limit, never above the code ceiling."""
    try:
        own = int((content.get("stop_conditions") or {}).get(
            "stop_watch_max_silence_minutes"))
    except (TypeError, ValueError):
        own = SP.MAX_STOP_WATCH_SILENCE_MINUTES
    return max(1, min(own, SP.MAX_STOP_WATCH_SILENCE_MINUTES))


def silence(db, content: dict, *, now: datetime | None = None) -> dict:
    """PASS when the newest reading of this policy is younger than its silence limit."""
    now = _now(now)
    limit = silence_limit_minutes(content)
    last = last_reading(db, content.get("policy_id"))
    at = SP._when((last or {}).get("read_at"))
    if at is None:
        return _fact(SB.UNKNOWN, None, "the stop watch has no reading of this policy")
    age = (now - at).total_seconds() / 60.0
    if age < 0:
        return _fact(SB.UNKNOWN, age, "the newest stop-watch reading is in the future")
    if age > limit:
        return _fact(SB.FAIL, round(age, 1), f"the stop watch has been silent {age:.0f} "
                                             f"minutes (limit {limit})")
    return _fact(SB.PASS, round(age, 1))


def holding(db, policy_id: str, *, now: datetime | None = None) -> list[str]:
    """Every stop condition that does not read PASS for `policy_id`, including silence. The
    default reader of `standing_policy.resume`. A policy that cannot be found holds."""
    now = _now(now)
    found = _policy(db, policy_id)
    if found is None:
        return [f"policy {policy_id} is not an approved policy in the current chain: UNKNOWN"]
    content, activated = found
    conds = conditions(db, content, now=now, activated=activated)
    conds["stop_watch_silence"] = silence(db, content, now=now)
    return _reasons(conds)


def issue_facts(db, content: dict, *, now: datetime | None = None,
                activated: bool = False) -> dict:
    """The issuer's two facts (`stop_conditions_clear`, `stop_watch_fresh`), read inline."""
    now = _now(now)
    conds = _guard(lambda: _fact(SB.PASS, conditions(db, content, now=now,
                                                     activated=activated)))
    if conds["state"] != SB.PASS:
        clear = conds
    else:
        reasons = _reasons(conds["value"])
        clear = (_fact(SB.FAIL, False, "; ".join(reasons)[:400]) if reasons
                 else _fact(SB.PASS, True))
    return {"stop_conditions_clear": clear,
            "stop_watch_fresh": _guard(lambda: silence(db, content, now=now))}


# ---------------------------------------------------------------------------------------------
# The job
# ---------------------------------------------------------------------------------------------

def _policy(db, policy_id: str) -> tuple[dict, bool] | None:
    """(content, activated) of the newest approval of `policy_id` in the current segment."""
    c, rows = SP._segment(db)
    if not c["valid"]:
        return None
    approvals = {rid: d for rid, d in rows if d.get("event") == SP.APPROVED
                 and (d.get("content") or {}).get("policy_id") == policy_id}
    if not approvals:
        return None
    aid = max(approvals)
    activated = any(d.get("event") == SP.ACTIVATED and d.get("approval_id") == aid
                    for _rid, d in rows)
    return approvals[aid].get("content") or {}, activated


def _suspended(db, policy_id: str) -> bool:
    _c, rows = SP._segment(db)
    state = False
    for _rid, d in rows:
        if d.get("policy_id") == policy_id:
            if d.get("event") == SP.SUSPENDED:
                state = True
            elif d.get("event") == SP.RESUMED:
                state = False
    return state


def watched(db, *, now: datetime | None = None) -> list[dict]:
    """The policies the stop watch reads: the newest approved policy that is not revoked or
    expired (the shadow policy), plus the activated one if that is a different policy."""
    from . import standing_issuer as SI

    now = _now(now)
    out: dict[str, dict] = {}
    shadow = SI.shadow_policy(db, now=now)
    if shadow is not None:
        out[shadow["content"]["policy_id"]] = shadow["content"]
    eff = SP.effective(db, now=now)
    if eff.get("activation_id") and eff.get("content"):
        out.setdefault(eff["content"]["policy_id"], eff["content"])
    return [out[k] for k in sorted(out)]


def run(db, *, now: datetime | None = None) -> dict:
    """One tick: read every watched policy, record the reading, and suspend an activated
    policy on any holding condition (sticky; deny-direction only)."""
    from ..core.models import AuditLog
    from . import incident_lifecycle

    now = _now(now)
    summary = {"policies": 0, "holding": 0, "suspended": 0, "would_suspend": 0}
    for content in watched(db, now=now):
        pid = content["policy_id"]
        found = _policy(db, pid)
        activated = bool(found and found[1])
        conds = conditions(db, content, now=now, activated=activated)
        reasons = _reasons(conds)
        already = activated and _suspended(db, pid)
        action = ("suspended" if activated and reasons and not already else
                  "already_suspended" if already else
                  "would_suspend" if reasons else "clear")
        summary["policies"] += 1
        summary["holding"] += bool(reasons)
        summary["would_suspend"] += action == "would_suspend"
        detail = {"policy_id": pid, "read_at": now.isoformat(), "activated": activated,
                  "holding": reasons, "action": action,
                  "states": {k: v.get("state") for k, v in sorted(conds.items())},
                  "assumed": [] if activated else list(ASSUMED_IN_SHADOW)}
        if action == "suspended":
            reason = ("stop watch: " + "; ".join(reasons))[:1000]
            SP.suspend(db, pid, reason=reason, by=ACTOR, now=now)
            summary["suspended"] += 1
            with db.session() as s:
                incident_lifecycle.open_or_restate(
                    s, signature=f"{INCIDENT_PREFIX}{pid}"[:200], severity="P1",
                    summary=(f"Standing policy {pid} suspended by the stop watch at "
                             f"{now.isoformat()}: {'; '.join(reasons[:3])}. It stays "
                             f"suspended until the owner resumes it (step-up), and resume "
                             f"refuses while any condition still holds.")[:2000],
                    detail={"policy_id": pid, "holding": reasons[:12],
                            "read_at": now.isoformat()}, now=now)
        with db.session() as s:
            s.add(AuditLog(actor=ACTOR, action=READING, artifact=pid, detail=detail))
    return summary
