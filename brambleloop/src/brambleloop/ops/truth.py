"""Ops truth: one vocabulary for non-values, a claim-to-evidence contract, the evidence
envelope and drilldown, and the owner-facing truth provider (wave-3 K7).

F-127  UNKNOWN, UNMEASURED, NOT-YET-OBSERVED, NOT-YET-WALKED and NOT-APPLICABLE are distinct
       values, never zero/false/pass/fail. `is_non_value` and `NON_VALUES` are the shared
       vocabulary.
F-122  `rate(numerator, denominator)` returns UNMEASURED (or NOT-YET-OBSERVED) on a zero or
       missing denominator -- never 0%, pass, clean or failed. `audit_summary` flags any
       provider output that prints a 0 rate beside a zero denominator.
F-121  `claim(...)` refuses a positive claim whose only evidence is configuration, code
       existence or absence of errors; `audit_summary` flags an OK status with no sources.
F-665  `envelope(...)` is the evidence WHY: source, timestamp, transformation, confidence,
       reconciliation state and safe external ids (re-using `app.dashboard_truth.evidence`).
F-623  `drill(db, provider, index)` drills any Command Center provider's item to that envelope.
F-203  `observation_window(items)` exposes the as-of range of the rows a card summarises, so a
       mixed snapshot cannot silently read as one current state.

`summary(db)` is the provider-contract reader the Command Center shows (key `ops_truth`);
`sweep(db)` is run by the 15-minute `ops.health` handler.
"""
from __future__ import annotations

from datetime import datetime, timezone

UNKNOWN = "UNKNOWN"
UNMEASURED = "UNMEASURED"
NOT_YET_OBSERVED = "NOT-YET-OBSERVED"
NOT_YET_WALKED = "NOT-YET-WALKED"
NOT_APPLICABLE = "NOT-APPLICABLE"
NON_VALUES: frozenset[str] = frozenset({UNKNOWN, UNMEASURED, NOT_YET_OBSERVED, NOT_YET_WALKED,
                                        NOT_APPLICABLE})
# Module-local spellings that already exist across the codebase, mapped onto the vocabulary.
ALIASES: dict[str, str] = {"unknown": UNKNOWN, "unmeasured": UNMEASURED,
                           "not_yet_observed": NOT_YET_OBSERVED,
                           "NOT_YET_WALKED": NOT_YET_WALKED, "not_yet_walked": NOT_YET_WALKED,
                           "NOT_APPLICABLE": NOT_APPLICABLE, "not_applicable": NOT_APPLICABLE,
                           "UNVERIFIABLE": UNKNOWN, "UNRESOLVED": UNKNOWN}

POSITIVE_STATES = frozenset({"OK", "PASS", "PASSED", "COMPLETE", "HEALTHY", "VERIFIED",
                             "AVAILABLE", "READY", "CLEAN", "FRESH"})
# Evidence that is not outcome proof (F-121).
NON_OUTCOME_EVIDENCE = frozenset({"configuration", "code_exists", "no_errors"})
OUTCOME_EVIDENCE = frozenset({"row", "probe", "audit", "measurement", "round_trip",
                              "external_reading", "test_run"})
RATE_HINTS = ("rate", "ratio", "conversion", "share", "pct", "percent")
DENOMINATOR_HINTS = ("denominator", "exposure", "visits", "views", "impressions", "orders",
                     "n", "samples", "sessions", "listings")
SAFE_EXTERNAL_ID_KEYS = ("listing_id", "etsy_listing_id", "receipt_id", "job_id",
                         "incident_id", "audit_id", "release_hash", "sha256", "transaction_id")
MIXED_SNAPSHOT_SECONDS = 60 * 60


class ClaimRefused(ValueError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalise(value):
    """A module-local non-value spelling, mapped onto the shared vocabulary."""
    if isinstance(value, str) and value in ALIASES:
        return ALIASES[value]
    return value


def is_non_value(value) -> bool:
    return isinstance(value, str) and normalise(value) in NON_VALUES


def rate(numerator, denominator, *, never_observed: bool = False):
    """numerator/denominator, or a non-value -- never 0 on a zero denominator (F-122)."""
    if is_non_value(numerator) or is_non_value(denominator):
        return UNKNOWN
    if numerator is None or denominator is None:
        return UNKNOWN
    if denominator == 0:
        return NOT_YET_OBSERVED if never_observed else UNMEASURED
    return numerator / denominator


def claim(statement: str, state: str, evidence: list[dict]) -> dict:
    """A status claim with the direct evidence that proves it (F-121).

    Each evidence item is {kind, ref, as_of?}. A positive state needs at least one item whose
    kind is outcome evidence; configuration, code existence or absence of errors never is.
    """
    kinds = {str(e.get("kind")) for e in evidence or []}
    unknown_kinds = kinds - NON_OUTCOME_EVIDENCE - OUTCOME_EVIDENCE
    if unknown_kinds:
        raise ClaimRefused(f"evidence kinds {sorted(unknown_kinds)} are not in the contract")
    if str(state).upper() in POSITIVE_STATES and not (kinds & OUTCOME_EVIDENCE):
        raise ClaimRefused(
            f"{statement!r} claims {state} on {sorted(kinds) or 'no evidence'}; configuration, "
            f"code existence or absence of errors is not outcome proof")
    return {"claim": statement, "state": state, "evidence": list(evidence or [])}


def envelope(source: str, *, transform: str, confidence: str = "measured",
             reconciliation: str = "not reconciled", as_of: str | None = None,
             external_ids: list | None = None) -> dict:
    """The F-665 evidence envelope (one definition: `app.dashboard_truth.evidence`)."""
    from ..app.dashboard_truth import evidence

    return evidence(source, transform=transform, confidence=confidence,
                    reconciliation=reconciliation, as_of=as_of, external_ids=external_ids)


def _item_time(item: dict):
    for key in ("as_of", "at", "observed_at", "last_seen", "created_at", "recorded_at"):
        v = item.get(key) if isinstance(item, dict) else None
        if isinstance(v, str) and len(v) >= 10:
            try:
                d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                continue
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return None


def observation_window(items: list) -> dict:
    """F-203: the as-of range of the rows behind a card, and whether they are one snapshot."""
    times = [t for t in (_item_time(i) for i in items or []) if t is not None]
    if not times:
        return {"oldest": None, "newest": None, "mixed_snapshot": None,
                "rows_with_time": 0, "rows": len(items or []),
                "note": "no row carries an observation time; the card's as-of is query time"}
    lo, hi = min(times), max(times)
    return {"oldest": lo.isoformat(), "newest": hi.isoformat(),
            "mixed_snapshot": (hi - lo).total_seconds() > MIXED_SNAPSHOT_SECONDS,
            "rows_with_time": len(times), "rows": len(items or [])}


def _walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}" if path else str(k))
            yield path, obj
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:200]):
            yield from _walk(v, f"{path}[{i}]")


def audit_summary(name: str, out: dict) -> list[dict]:
    """Contract violations in one provider output (F-121, F-122, F-127, F-203)."""
    violations: list[dict] = []
    if not isinstance(out, dict):
        return [{"provider": name, "violation": "not a dict"}]
    if out.get("status") == "OK" and not out.get("sources"):
        violations.append({"provider": name, "violation": "OK with no sources (F-121)"})
    if out.get("status") == "UNKNOWN" and not out.get("reason"):
        violations.append({"provider": name, "violation": "UNKNOWN without a reason"})
    seen: set[int] = set()
    for path, d in _walk(out):
        if id(d) in seen or not isinstance(d, dict):
            continue
        seen.add(id(d))
        dens = {k: v for k, v in d.items()
                if isinstance(k, str) and k.lower() in DENOMINATOR_HINTS
                and isinstance(v, (int, float)) and not isinstance(v, bool)}
        if not dens or any(v != 0 for v in dens.values()):
            continue
        for k, v in d.items():
            if (isinstance(k, str) and any(h in k.lower() for h in RATE_HINTS)
                    and isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0):
                violations.append({"provider": name, "path": f"{path}.{k}" if path else k,
                                   "violation": "0 rate on a zero denominator (F-122)"})
    return violations


# ---- the provider ------------------------------------------------------------------------

PROVIDER_KEYS = ("autonomy", "improvement", "accounting", "store_foundation", "seo", "ads",
                 "slo")


def _contract_audit(db) -> dict:
    from ..app.command_center import providers

    rows, violations = [], []
    for key in PROVIDER_KEYS:
        out = providers.call(key, db)
        v = audit_summary(key, out)
        violations += v
        rows.append({"provider": key, "status": out.get("status"), "as_of": out.get("as_of"),
                     "window": observation_window(out.get("items") or []),
                     "violations": len(v)})
    return {"providers": rows, "violations": violations}


def drill(db, provider: str, index: int = 0) -> dict:
    """F-623 / F-665: any provider item -> source, timestamp, transformation, confidence,
    reconciliation state and safe external ids. Missing parts are named, never invented."""
    from ..app.command_center import providers

    if provider not in providers.PROVIDERS:
        return providers.unknown(f"provider must be one of {sorted(providers.PROVIDERS)}",
                                 "ops.truth.drill")
    out = providers.call(provider, db)
    items = out.get("items") or []
    if not (0 <= index < len(items)):
        return providers.unknown(f"{provider} has {len(items)} item(s); no item {index}",
                                 "ops.truth.drill", out.get("sources"))
    item = items[index] if isinstance(items[index], dict) else {"value": items[index]}
    when = _item_time(item)
    ev = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    ids = [{k: item[k]} for k in SAFE_EXTERNAL_ID_KEYS if item.get(k) not in (None, "")]
    env = {
        "source": ev.get("source") or item.get("source") or out.get("sources") or None,
        "timestamp": (ev.get("as_of") or (when.isoformat() if when else None)),
        "timestamp_basis": ("row observation time" if (ev.get("as_of") or when) else
                            "query time only (provider as_of); the row carries no time"),
        "provider_as_of": out.get("as_of"),
        "transformation": (ev.get("transform") or item.get("transform") or out.get("rule")
                           or out.get("note") or None),
        "confidence": ev.get("confidence") or item.get("basis") or out.get("basis"),
        "reconciliation": (ev.get("reconciliation") or item.get("reconciliation")
                           or item.get("reconciliation_state") or UNKNOWN),
        "external_ids": ev.get("external_ids") or ids,
    }
    missing = [k for k in ("source", "timestamp", "transformation") if not env[k]]
    return providers.envelope(
        out.get("status", "UNKNOWN"), [dict(item=item, evidence=env)],
        list(out.get("sources") or []), basis=out.get("basis", "unknown"),
        provider="ops.truth.drill", reason=out.get("reason"),
        drilled=provider, index=index, evidence_missing=missing)


def _section(name: str, fn) -> dict:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - one unreadable section is UNKNOWN, not fatal
        return {"status": UNKNOWN, "reason": f"{name} unreadable: {type(exc).__name__}"}


def summary(db) -> dict:
    """The owner's ops-truth card set, under the cross-lane provider contract."""
    import os

    from . import assurance, job_watch, owner_queue
    from .artefacts import coverage as prov_coverage, check, current_from_db, expected_from_db

    env = dict(os.environ)
    # The readers here take the `Database` facade. Handed a Session (the provider contract),
    # this raises AttributeError naming `session`, and `providers.call` retries with the facade.
    dbf = db
    dbf.new_session  # noqa: B018 - a Session has no new_session; see above
    sections: dict[str, dict] = {}
    sections["owner_inventory"] = _section("owner_inventory",
                                           lambda: owner_queue.inventory(dbf, env))
    sections["owner_lifecycle"] = _section("owner_lifecycle", lambda: owner_queue.history(dbf))
    sections["data_gates"] = _section("data_gates", lambda: owner_queue.data_gates(dbf, env))
    sections["tester_roster"] = _section("tester_roster",
                                         lambda: owner_queue.tester_status(dbf))
    sections["security_controls"] = _section(
        "security_controls", lambda: assurance.security_controls(dbf, env))
    sections["postconditions"] = _section("postconditions",
                                          lambda: assurance.postconditions(dbf, env))
    sections["rollback_baseline"] = _section("rollback_baseline",
                                             lambda: assurance.rollback_baseline(dbf, env))

    def prov():
        with dbf.session() as s:
            vs = check(s, current=current_from_db(s), expected=expected_from_db(s))
            return prov_coverage(vs)
    sections["provenance_coverage"] = _section("provenance_coverage", prov)

    def jobs():
        with dbf.session() as s:
            w = job_watch.watch(s)
            return {"activity": job_watch.activity(s), "over_envelope": w["over_envelope"],
                    "running": w["running"], "unassessable": len(w["unassessable"])}
    sections["jobs"] = _section("jobs", jobs)

    def incidents():
        from . import incident_lifecycle

        with dbf.session() as s:
            snap = incident_lifecycle.snapshot(s)
            return {"needs_owner_path": snap["needs_owner_path"],
                    "unconfirmed": snap["unconfirmed"], "learning": snap["learning"],
                    "systemic": incident_lifecycle.systemic_evidence(s)}
    sections["incidents"] = _section("incidents", incidents)
    sections["contract_audit"] = _section("contract_audit", lambda: _contract_audit(dbf))

    items = [{"section": k, "status": (v.get("status") if isinstance(v, dict) else None)
              or "OK", **({"reason": v["reason"]} if isinstance(v, dict) and v.get("reason")
                          else {})} for k, v in sections.items()]
    bad = [i["section"] for i in items if i["status"] in ("BLOCKED", "DEGRADED", UNKNOWN)]
    status = ("BLOCKED" if any(i["status"] == "BLOCKED" for i in items) else
              "DEGRADED" if bad else "OK")
    return {"status": status, "as_of": now_iso(), "basis": "measured", "items": items,
            "sections": sections,
            "sources": ["owner_actions", "audit_log", "incidents", "jobs",
                        "artefact_provenance", "cc_security_events", "physical_tests",
                        "build2/final_master_closure.json"],
            **({"reason": f"sections needing attention: {bad}"} if bad else {})}


def sweep(db, *, now: datetime | None = None) -> dict:
    """The mutating half, run by the ops.health cadence: owner-action expiry, systemic halt
    escalation, failing postconditions as incidents, the rollback baseline record and the
    daily readiness re-proof. Every part is guarded; one failure never stops the others."""
    from . import assurance, incident_lifecycle, owner_queue

    out: dict[str, object] = {}

    def run(name, fn):
        try:
            out[name] = fn()
        except Exception as exc:  # noqa: BLE001
            out[name] = {"error": type(exc).__name__}

    run("owner_actions", lambda: owner_queue.sweep(db, now=now))

    def systemic():
        with db.session() as s:
            return incident_lifecycle.escalate_systemic(s, now=now)
    run("systemic", systemic)

    def post():
        pcs = assurance.postconditions(db, now=now)
        violated = {p["postcondition"]: p for p in pcs["postconditions"]
                    if p["state"] == assurance.VIOLATED}
        with db.session() as s:
            life = incident_lifecycle.reconcile(
                s, "postcondition:", lambda inc: inc.signature.split(":", 1)[1] in violated,
                resolution="the postcondition reads back as verified again", now=now)
            for name, p in violated.items():
                incident_lifecycle.open_or_restate(
                    s, signature=f"postcondition:{name}", severity="P2",
                    summary=f"postcondition {name} violated: {p['why']}"[:500],
                    detail={"evidence": p["evidence"]}, now=now)
        return {"violated": sorted(violated), "resolved": life["resolved"]}
    run("postconditions", post)

    def learning():
        with db.session() as s:
            ln = incident_lifecycle.learning(s, now=now)
            recurred = {r["family"] for r in ln["recurred_after_prevention"]}
            life = incident_lifecycle.reconcile(
                s, "incident-recurrence:", lambda inc: inc.signature.split(":", 1)[1]
                in recurred, resolution="no open incident in this family any more", now=now)
            for fam in sorted(recurred):
                incident_lifecycle.open_or_restate(
                    s, signature=f"incident-recurrence:{fam}", severity="P2",
                    summary=(f"failure family {fam} recurred after its prevention was "
                             f"recorded; the prevention did not hold"), now=now)
            return {"gaps": len(ln["gaps"]), "recurred": sorted(recurred),
                    "resolved": life["resolved"]}
    run("incident_learning", learning)
    run("rollback_baseline", lambda: {k: v for k, v in assurance.record_baseline(db).items()
                                      if k in ("recorded", "recoverable", "missing", "digest")})

    def reproof():
        r = assurance.record_reproof(db, now=now)
        return None if r is None else {"status": r["status"],
                                       "failures": r["reproof_failures"]}
    run("readiness_reproof", reproof)
    return out
