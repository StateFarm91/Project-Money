"""Assurance readings that refuse to infer (wave-3 K7).

F-154  No security theatre: every security control in the inventory is exercised by a
       functional in-process probe, and one that is configured but does not work -- or whose
       working was never observed -- is reported unavailable, never "on".
F-124  Postcondition verification: after an operational change the claimed result is read
       back directly (restore digest matched, jobs actually completed with outputs, rebuilt
       artefacts fresh, credentials served a request, temp dirs cleaned, the deployed tree
       carries its release record). Each postcondition is VERIFIED, VIOLATED, or an explicit
       non-value -- never assumed.
F-176  Rollback baseline: one recoverable pre-launch baseline record -- code SHA, deployable
       tree digest, schema digest, config *names* (never values), coverage map, test
       evidence and restore proof -- with every missing component named.
F-199  Launch-readiness current-evidence audit: product-level clearance is recomputed against
       the current launch standard, and a past "ready" verdict that the current standard no
       longer supports is reported as failing re-proof rather than surviving.

All readers; `record_baseline` and `record_reproof` append audit rows. Nothing spends,
publishes or contacts anyone.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

from .truth import NOT_APPLICABLE, NOT_YET_OBSERVED, UNKNOWN

AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"
UNPROVEN = "UNPROVEN"          # configured, but working never observed -> reported unavailable
VERIFIED = "VERIFIED"
VIOLATED = "VIOLATED"

# Names only. A config name in the baseline says what the build expects; a value never appears.
CONFIG_PREFIXES = ("BRAMBLELOOP_", "ETSY_", "ANTHROPIC_", "OPENAI_", "RAILWAY_", "DATABASE_",
                   "OPS_", "CC_", "OFFSITE_", "R2_", "S3_", "GEMINI_")
LOGIN_PROOF_DAYS = 30


def _now(now=None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


# ---- F-154 -------------------------------------------------------------------------------

def _control(name: str, state: str, configured, probe: str, why: str) -> dict:
    return {"control": name, "state": state, "configured": configured,
            "available": state == AVAILABLE, "probe": probe, "why": why}


def _csp_probe() -> tuple[bool, str]:
    import asyncio

    from ..app.security import CONTENT_SECURITY_POLICY, SecurityHeadersMiddleware

    seen: dict = {}

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def send(message):
        if message["type"] == "http.response.start":
            seen.update({k.decode().lower(): v.decode() for k, v in message["headers"]})

    async def receive():
        return {"type": "http.request"}

    asyncio.run(SecurityHeadersMiddleware(app)({"type": "http", "method": "GET", "path": "/",
                                                "headers": []}, receive, send))
    ok = seen.get("content-security-policy") == CONTENT_SECURITY_POLICY
    return ok, ("a response passed through the middleware carried the CSP header" if ok
                else "a response passed through the middleware lacked the CSP header")


def security_controls(db, env: dict | None = None, *, now: datetime | None = None) -> dict:
    """Every control, probed functionally. Configured-but-unproven is not available."""
    from ..app import security
    from ..core import opsauth

    env = dict(os.environ) if env is None else env
    now = _now(now)
    out: list[dict] = []

    # Operator credential: the check path must accept the configured token and refuse another.
    health = opsauth.token_health(env)
    if not health["configured"]:
        out.append(_control("operator_credential", UNAVAILABLE, False, "opsauth.check",
                            "no operator credential is configured"))
    else:
        token = (env.get(opsauth.TOKEN_VAR) or "").strip()
        accepted = refused = False
        try:
            opsauth.check(f"Bearer {token}", env)
            accepted = True
        except Exception:  # noqa: BLE001
            accepted = False
        try:
            opsauth.check("Bearer " + "x" * max(len(token), opsauth.MIN_TOKEN_LENGTH), env)
        except opsauth.OpsAuthRefused:
            refused = True
        except Exception:  # noqa: BLE001
            refused = False
        state = AVAILABLE if accepted and refused else UNAVAILABLE
        out.append(_control("operator_credential", state, True,
                            "opsauth.check accepts the configured credential and refuses "
                            "another", "" if state == AVAILABLE else
                            health.get("reason") or "the check path did not behave"))

    # Default-deny for mutating routes: an unknown future route must require the operator.
    deny = security.requires_operator("POST", "/api/k7-probe-unregistered-route")
    out.append(_control("default_deny_mutations", AVAILABLE if deny else UNAVAILABLE, True,
                        "security.requires_operator('POST', <unregistered route>)",
                        "" if deny else "an unregistered mutating route is not denied"))

    # CSP headers: a response actually passed through the middleware.
    try:
        ok, why = _csp_probe()
    except Exception as exc:  # noqa: BLE001
        ok, why = False, f"probe failed: {type(exc).__name__}"
    out.append(_control("csp_headers", AVAILABLE if ok else UNAVAILABLE, True,
                        "SecurityHeadersMiddleware on a synthetic response", why))

    # Owner Command Center login: refusal of a wrong passphrase, and an observed success.
    try:
        from ..app.command_center import auth as cc_auth

        configured = cc_auth.login_configured(env)
        refuses = not cc_auth.verify_passphrase("k7-probe-wrong-passphrase", env)
        observed = _recent_login(db, now)
    except Exception as exc:  # noqa: BLE001
        configured, refuses, observed = None, False, None
        why = f"probe failed: {type(exc).__name__}"
    else:
        why = ""
    if configured is False:
        state, why = UNAVAILABLE, "owner login is not configured"
    elif not refuses:
        state, why = UNAVAILABLE, why or "a wrong passphrase was not refused"
    elif not observed:
        state = UNPROVEN
        why = (f"configured and refusing wrong passphrases, but no successful owner login is "
               f"recorded in {LOGIN_PROOF_DAYS} days, so it is not reported available")
    else:
        state = AVAILABLE
    out.append(_control("owner_login", state, configured,
                        "verify_passphrase(wrong) refused + cc_security_events login ok", why))

    # Offsite backup: only a real archive written offsite counts.
    try:
        from ..build2 import executor

        written = bool(executor._offsite_archive_written(db, env))
        st = AVAILABLE if written else UNAVAILABLE
        why = "" if written else "no continuity archive has been written offsite"
    except Exception as exc:  # noqa: BLE001
        st, why = UNAVAILABLE, f"probe failed: {type(exc).__name__}"
    out.append(_control("offsite_backup", st, None, "executor._offsite_archive_written", why))

    # Boot guard: on the platform it must have verified this tree; off it, not applicable.
    from . import release_record

    if not release_record.enforced(env):
        out.append(_control("boot_guard", NOT_APPLICABLE, None, "release_record.verify_build",
                            "not running on the hosting platform"))
    else:
        res = release_record.verify_build(env=env)
        out.append(_control("boot_guard", AVAILABLE if res["ok"] else UNAVAILABLE, True,
                            "release_record.verify_build", "; ".join(res["reasons"])[:300]))

    available = [c["control"] for c in out if c["available"]]
    unavailable = [c["control"] for c in out if c["state"] in (UNAVAILABLE, UNPROVEN)]
    return {"controls": out, "available": available, "unavailable": unavailable,
            "status": "OK" if not unavailable else "DEGRADED",
            "rule": ("a control is available only when a functional probe shows it working; "
                     "configured-but-unproven is reported unavailable (F-154)")}


def _recent_login(db, now: datetime) -> bool:
    from sqlalchemy import select

    from ..app.command_center.models import SecurityEvent

    with db.session() as s:
        try:
            at = s.scalar(select(SecurityEvent.at).where(
                SecurityEvent.kind == "login", SecurityEvent.outcome == "ok")
                .order_by(SecurityEvent.id.desc()).limit(1))
        except Exception:  # noqa: BLE001 - table absent -> never observed
            s.rollback()
            return False
    return at is not None and now - _aware(at) <= timedelta(days=LOGIN_PROOF_DAYS)


# ---- F-124 -------------------------------------------------------------------------------

def _pc(name: str, state: str, evidence: dict, why: str) -> dict:
    return {"postcondition": name, "state": state, "evidence": evidence, "why": why}


def postconditions(db, env: dict | None = None, *, now: datetime | None = None) -> dict:
    """Read back the claimed result of each kind of operational change."""
    from sqlalchemy import desc, func, select

    from ..core.models import AuditLog, Job, JobStatus
    from .dependencies import RESTORE_PROOF_MAX_AGE_DAYS

    env = dict(os.environ) if env is None else env
    now = _now(now)
    out: list[dict] = []
    with db.session() as s:
        restore = s.scalar(select(AuditLog).where(AuditLog.action == "continuity.verified")
                           .order_by(desc(AuditLog.id)).limit(1))
        since = now - timedelta(hours=24)
        done = list(s.scalars(select(Job).where(Job.status == JobStatus.DONE,
                                                Job.created_at >= since).limit(5000)))
        sentinel = s.scalar(select(AuditLog).where(AuditLog.action == "ops.sentinel")
                            .order_by(desc(AuditLog.id)).limit(1))
        rebuilding = s.scalar(select(func.count()).select_from(Job).where(
            Job.job_type == "chain.rebuild",
            Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING)))) or 0

    # Restore: a digest round trip recorded recently.
    if restore is None:
        out.append(_pc("restore_digest_matched", NOT_YET_OBSERVED, {},
                       "no continuity restore round trip has ever been recorded"))
    else:
        age = now - _aware(restore.at)
        ok = age <= timedelta(days=RESTORE_PROOF_MAX_AGE_DAYS)
        out.append(_pc("restore_digest_matched", VERIFIED if ok else UNKNOWN,
                       {"audit_id": restore.id, "at": _aware(restore.at).isoformat()},
                       "" if ok else f"the last round trip is {age.days} days old"))

    # Jobs: DONE must mean finished, with outputs.
    broken = [j.id for j in done if j.finished_at is None or j.outputs is None]
    if not done:
        out.append(_pc("jobs_completed", NOT_YET_OBSERVED, {"window_hours": 24},
                       "no job completed in the window"))
    else:
        out.append(_pc("jobs_completed", VIOLATED if broken else VERIFIED,
                       {"done": len(done), "done_without_finish_or_outputs": broken[:50]},
                       f"{len(broken)} DONE job(s) carry no finish time or outputs"
                       if broken else ""))

    # Rebuilds: the sentinel's latest stale count against rebuilds still in flight.
    if sentinel is None:
        out.append(_pc("artefacts_rebuilt", NOT_YET_OBSERVED, {},
                       "the stale-artefact sentinel has not run"))
    else:
        stale = int((sentinel.detail or {}).get("stale") or 0)
        state = (VERIFIED if stale == 0 else "PENDING" if rebuilding else VIOLATED)
        out.append(_pc("artefacts_rebuilt", state,
                       {"sentinel_audit_id": sentinel.id, "stale": stale,
                        "rebuilds_in_flight": int(rebuilding)},
                       "" if stale == 0 else
                       f"{stale} stale artefact(s); {rebuilding} rebuild(s) in flight"))

    # Credentials: a recorded probe served a request (the same reading health uses).
    from . import health

    with db.session() as s:
        readings = health.capability_readings(s, env)
    for r in readings:
        out.append(_pc(f"credential_served:{r.signal}",
                       VERIFIED if r.state == health.HEALTHY else UNKNOWN,
                       {"health_state": r.state}, r.why[:200]))

    # Cleanup: temp directories the handlers should have removed.
    try:
        facts = health.disk_facts()
        left = int(facts.get("temp_dirs_left_behind") or 0)
        out.append(_pc("cleanup_happened", VERIFIED if left == 0 else UNKNOWN,
                       {"temp_dirs_left_behind": left,
                        "prefixes": facts.get("temp_dir_prefixes")},
                       "" if left == 0 else
                       "directories remain: work in flight or a died call; not deleted here"))
    except Exception as exc:  # noqa: BLE001
        out.append(_pc("cleanup_happened", UNKNOWN, {}, f"unreadable: {type(exc).__name__}"))

    # Deploy: the running tree carries its committed release record.
    from . import release_record

    if not release_record.platform(env):
        out.append(_pc("deployed_tree_recorded", NOT_APPLICABLE, {},
                       "not running on the hosting platform"))
    else:
        res = release_record.verify_build(env=env)
        out.append(_pc("deployed_tree_recorded", VERIFIED if res["ok"] else VIOLATED,
                       {"tree_sha256": res.get("tree_sha256"), "record": res.get("record")},
                       "; ".join(res["reasons"])[:300]))

    violated = [p["postcondition"] for p in out if p["state"] == VIOLATED]
    return {"postconditions": out, "violated": violated,
            "status": "DEGRADED" if violated else "OK", "as_of": now.isoformat()}


# ---- F-176 -------------------------------------------------------------------------------

def schema_digest() -> dict:
    from ..core.db import Base

    tables = {t.name: sorted(c.name for c in t.columns) for t in Base.metadata.sorted_tables}
    blob = json.dumps(tables, sort_keys=True).encode()
    return {"tables": len(tables), "sha256": hashlib.sha256(blob).hexdigest()}


def rollback_baseline(db, env: dict | None = None) -> dict:
    """The baseline a rollback would return to, with every missing component named."""
    from sqlalchemy import desc, select

    from ..core import build
    from ..core.models import AuditLog
    from . import release_record

    env = dict(os.environ) if env is None else env
    comp: dict[str, dict] = {}
    sha = build.commit(env)
    comp["code_sha"] = {"value": sha, "ok": sha != build.UNKNOWN}
    try:
        tree = release_record.filesystem_digest()
        comp["tree_digest"] = {"value": tree, "ok": True}
    except OSError as exc:
        comp["tree_digest"] = {"value": None, "ok": False, "why": type(exc).__name__}
    try:
        comp["schema"] = dict(schema_digest(), ok=True)
    except Exception as exc:  # noqa: BLE001
        comp["schema"] = {"ok": False, "why": type(exc).__name__}
    names = sorted(k for k in env if k.startswith(CONFIG_PREFIXES))
    comp["config_names"] = {"names": names, "ok": bool(names),
                            "note": "names only; values are never read into the baseline"}
    try:
        from ..build2 import final_master

        fm = final_master.summary()
        comp["coverage_map"] = {"launch_critical": fm.get("launch_critical"),
                                "status": fm.get("status"), "ok": fm.get("status") != "UNKNOWN"}
    except Exception as exc:  # noqa: BLE001
        comp["coverage_map"] = {"ok": False, "why": type(exc).__name__}
    verified = release_record.verify_build(env=env)
    comp["tests"] = {"release_record": verified.get("record"), "ok": bool(verified["ok"]),
                     "why": "; ".join(verified.get("reasons") or [])[:300]}
    with db.session() as s:
        restore = s.scalar(select(AuditLog).where(AuditLog.action == "continuity.verified")
                           .order_by(desc(AuditLog.id)).limit(1))
    comp["restore_proof"] = ({"audit_id": restore.id, "at": _aware(restore.at).isoformat(),
                              "ok": True} if restore is not None else
                             {"ok": False, "why": "no continuity.verified round trip on file"})
    comp["rollback_target"] = release_record.known_good_predecessor(
        sha if sha != build.UNKNOWN else None)
    comp["rollback_target"]["ok"] = bool(comp["rollback_target"].get("sha"))
    missing = [k for k, v in comp.items() if not v.get("ok")]
    digest = hashlib.sha256(json.dumps(
        {k: {kk: vv for kk, vv in v.items() if kk not in ("why",)}
         for k, v in comp.items()}, sort_keys=True, default=str).encode()).hexdigest()
    return {"components": comp, "missing": missing, "recoverable": not missing,
            "digest": digest,
            "status": "OK" if not missing else "DEGRADED",
            "why": ("every component of the baseline is present" if not missing else
                    f"the baseline is not recoverable without: {missing}")}


def record_baseline(db, env: dict | None = None) -> dict:
    """Append the baseline to the audit trail when it changed (idempotent by digest)."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    base = rollback_baseline(db, env)
    with db.session() as s:
        last = s.scalar(select(AuditLog).where(AuditLog.action == "ops.rollback_baseline")
                        .order_by(desc(AuditLog.id)).limit(1))
        if last is not None and (last.detail or {}).get("digest") == base["digest"]:
            return dict(base, recorded=False)
        s.add(AuditLog(actor="ops.truth", action="ops.rollback_baseline",
                       artifact=f"baseline:{base['digest'][:16]}",
                       detail={"digest": base["digest"], "missing": base["missing"],
                               "recoverable": base["recoverable"],
                               "code_sha": base["components"]["code_sha"]["value"],
                               "tree_digest": base["components"]["tree_digest"].get("value"),
                               "schema_sha256": base["components"]["schema"].get("sha256"),
                               "config_names": base["components"]["config_names"]["names"],
                               "restore_proof": base["components"]["restore_proof"]}))
    return dict(base, recorded=True)


# ---- F-199 -------------------------------------------------------------------------------

REPROOF_ACTION = "launch.reproved"
REPROOF_EVERY_HOURS = 24


def readiness_reproof(db, *, survivors: list[str] | None = None) -> dict:
    """Re-prove the last 'ready' verdict and each product's clearance against today's standard."""
    from sqlalchemy import desc, select

    from ..app import dashboard_truth
    from ..core.models import AuditLog

    inv = dashboard_truth.launch_inventory(db, survivors=survivors)
    with db.session() as s:
        last = s.scalar(select(AuditLog).where(AuditLog.action == "launch.assessed")
                        .order_by(desc(AuditLog.id)).limit(1))
    said_ready = bool((last.detail or {}).get("ready")) if last is not None else None
    failing = []
    if said_ready and inv["launch_cleared"] == 0:
        failing.append("the last assessment said ready, but no product is launch-cleared "
                       "under the current launch standard")
    return {"products": [{"slug": p["slug"], "launch_cleared": p["launch_cleared"],
                          "failing": p["failing"]} for p in inv["products"]],
            "certified": inv["certified"], "launch_cleared": inv["launch_cleared"],
            "standard": {"criteria": inv["criteria"], "gauge_standard": inv["gauge_standard"]},
            "last_assessment_ready": said_ready,
            "last_assessment_at": _aware(last.at).isoformat() if last is not None else None,
            "reproof_failures": failing,
            "status": ("UNKNOWN" if last is None else "BLOCKED" if failing else "OK"),
            "rule": ("readiness stores no ready flags (launch.readiness recomputes every row "
                     "from current state); this re-proves the last verdict and every product "
                     "against the current standard, and a verdict it no longer supports fails")}


def record_reproof(db, *, now: datetime | None = None, force: bool = False) -> dict | None:
    """At most once per REPROOF_EVERY_HOURS, append the re-proof to the audit trail."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    now = _now(now)
    with db.session() as s:
        last = s.scalar(select(AuditLog).where(AuditLog.action == REPROOF_ACTION)
                        .order_by(desc(AuditLog.id)).limit(1))
    if not force and last is not None and now - _aware(last.at) < timedelta(
            hours=REPROOF_EVERY_HOURS):
        return None
    out = readiness_reproof(db)
    with db.session() as s:
        s.add(AuditLog(actor="ops.truth", action=REPROOF_ACTION, artifact="launch.readiness",
                       detail={k: out[k] for k in ("products", "certified", "launch_cleared",
                                                   "last_assessment_ready",
                                                   "reproof_failures", "status")}))
    return out
