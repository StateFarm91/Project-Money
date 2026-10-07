"""Incidents close when their condition stops holding, and they say what closed them.

Production on 2026-09-26 held seventeen open incidents. Every detector in this system knew
how to *open* a row -- "if the condition is true and no open row carries this signature, add
one" -- and almost none knew how to close it. So the rows accumulated: a product that had
missed its window stayed "at risk", a health signal that recovered stayed "bad for three
sweeps", and a stall whose ready work was later parked stayed stalled. A channel where nothing
ever closes is a channel nobody reads, and a row that is still open is indistinguishable from
one somebody is still worried about.

Two rules, applied by every detector that imports this module:

**A condition that still holds is restated, not re-raised.** The open row's `detail.last_seen`
moves forward and its report count increments, so "this has been true since Tuesday and was
still true an hour ago" is one row rather than a new one per run.

**A condition that no longer holds is resolved with evidence.** `detail.resolution` says in
words what changed, `detail.resolved_at` says when, and `detail.last_seen` says when it was
last observed true. A resolution without evidence would be a checkbox, and a checkbox on an
incident is how the next one gets ignored.

The signature is the identity. Detectors that used to omit the thing that made a condition
unique -- the event's year, the event itself -- opened one row per day because yesterday's
signature never matched today's; a signature that names what the condition is *about* is what
lets `reconcile` recognise the same condition across runs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

from ..core.models import Incident

# Incidents resolved this recently still show on the incident page, because the question an
# operator asks after a red row disappears is "what closed it", and a row that vanishes
# answers nothing.
RESOLVED_VISIBLE_HOURS = 24


def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat()


def kind_of(signature: str) -> str:
    """The detector family a signature belongs to: everything before the first colon."""
    return signature.split(":", 1)[0]


def _restate(incident: Incident, now: datetime | None = None,
             detail: dict | None = None) -> None:
    """Move the open row's last-seen forward. A JSON column is replaced, never mutated in
    place, because SQLAlchemy does not see an in-place change."""
    merged = dict(incident.detail or {})
    if detail:
        merged.update(detail)
    merged["last_seen"] = _now_iso(now)
    incident.detail = merged
    incident.report_count = int(incident.report_count or 1) + 1


def open_or_restate(session, *, signature: str, severity: str, summary: str,
                    detail: dict | None = None, product_slug: str | None = None,
                    halts_publication: bool = False,
                    now: datetime | None = None) -> tuple[Incident, bool]:
    """Raise a condition once and restate it while it holds.

    Returns the row and whether it was newly opened. The open row's `detail` is refreshed
    with the caller's latest reading so that the page shows what is true now rather than what
    was true the day the row opened; `first_seen` is kept from the original.
    """
    from sqlalchemy import select

    existing = session.scalar(select(Incident).where(
        Incident.signature == signature, Incident.resolved == False))  # noqa: E712
    if existing is not None:
        _restate(existing, now, detail)
        return existing, False
    stamped = dict(detail or {})
    stamped.setdefault("first_seen", _now_iso(now))
    stamped["last_seen"] = _now_iso(now)
    row = Incident(severity=severity, signature=signature, summary=summary[:2000],
                   product_slug=product_slug, halts_publication=halts_publication,
                   detail=stamped)
    session.add(row)
    session.flush()
    return row, True


def reconcile(session, signature_prefix: str, still_true: Callable[[Incident], bool], *,
              resolution: str | Callable[[Incident], str],
              now: datetime | None = None) -> dict:
    """Resolve every open incident under the prefix whose condition no longer holds.

    `still_true(incident)` is the detector's own current reading of that row's condition.
    Rows it says are still true have `detail.last_seen` restated; rows it says are false are
    resolved, with `resolution` (a string, or a function of the row for a per-row sentence)
    written into `detail.resolution` and the time into `detail.resolved_at`.

    Returns the signatures it resolved and the ones it left open, so a handler can put both
    in its audit record: a reconciliation that reports nothing is one nobody can check.
    """
    from sqlalchemy import select

    # LIKE narrows in SQL; `startswith` makes it exact, because `_` and `%` in a prefix
    # ("seasonal.at_risk:") are LIKE wildcards and would otherwise match their neighbours.
    rows = [row for row in session.scalars(select(Incident).where(
        Incident.signature.like(f"{signature_prefix}%"),
        Incident.resolved == False))  # noqa: E712
        if row.signature.startswith(signature_prefix)]
    resolved, kept = [], []
    for row in rows:
        if still_true(row):
            _restate(row, now)
            kept.append(row.signature)
            continue
        text = resolution(row) if callable(resolution) else resolution
        if not str(text or "").strip():
            raise ValueError(
                f"refusing to resolve {row.signature!r} without a resolution: a closed "
                f"incident that does not say what closed it is a checkbox")
        merged = dict(row.detail or {})
        merged["resolution"] = str(text)
        merged["resolved_at"] = _now_iso(now)
        merged.setdefault("last_seen", merged.get("first_seen") or row.at.isoformat())
        row.detail = merged
        row.resolved = True
        resolved.append(row.signature)
    return {"prefix": signature_prefix, "resolved": resolved, "still_open": kept}


def resolve_signatures(session, signatures: Iterable[str], *, resolution: str,
                       now: datetime | None = None) -> list[str]:
    """Resolve specific open rows with one stated reason. A convenience over `reconcile` for
    the case where the detector already knows exactly which rows stopped being true."""
    from sqlalchemy import select

    wanted = set(signatures)
    if not wanted:
        return []
    if not str(resolution or "").strip():
        raise ValueError("refusing to resolve without a resolution")
    # Only the named rows are touched. Going through `reconcile` with an empty prefix would
    # restate every other open incident in the table as a side effect.
    resolved = []
    for row in session.scalars(select(Incident).where(
            Incident.signature.in_(sorted(wanted)),
            Incident.resolved == False)):  # noqa: E712
        merged = dict(row.detail or {})
        merged["resolution"] = str(resolution)
        merged["resolved_at"] = _now_iso(now)
        merged.setdefault("last_seen", merged.get("first_seen") or row.at.isoformat())
        row.detail = merged
        row.resolved = True
        resolved.append(row.signature)
    return resolved


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# F-195 (wave-3 K7): every open incident names who owns its remediation and by what path.
# Keyed by detector family (`kind_of`). A family missing here is reported with
# `needs_owner_path: true` rather than given an owner nobody assigned.
REMEDIATION: dict[str, tuple[str, str]] = {
    "health": ("ops.health sweep", "resolves itself when the signal reads healthy again"),
    "stale-artefact": ("ops.sentinel + rebuild graph",
                       "rebuild enqueued by the sentinel; resolves when upstreams match"),
    # W4-OWNER: a stale reading is refreshed by the company -- a build session re-reads the
    # search-engine excerpt of the official page into gates.policy_knowledge (dated, basis
    # declared), as the 2026-09-26 readings were. Software must not spoof a browser past
    # Etsy's 403; an owner page reading supersedes the excerpt but is never required.
    "policy_stale": ("company", "a build session refreshes the dated search-engine-excerpt "
                                "reading in gates.policy_knowledge (basis declared) and "
                                "ops.policy_watch re-reads it; optionally the owner records a "
                                "page reading with POST /api/policy/snapshot (operator "
                                "credential), which supersedes the excerpt. Software is "
                                "refused by Etsy (HTTP 403) and must not spoof a browser"),
    "policy_changed": ("owner", "review the material policy change and record the review on "
                                "the snapshot; the affected workflows re-test"),
    "authority_chain_tamper": ("owner", "inspect the sealed authority chain; publication "
                                        "stays refused until it verifies"),
    "spend-anomaly": ("finance.reconcile", "explained or reversed by the finance close"),
    "support.first_response": ("support.response_watch", "a recorded response closes it"),
    "release.unproven_build": ("deploy guard", "deploy a build with a committed release "
                                               "record (ops/deploy_guard.py record)"),
    "rebuild-incomplete": ("ops.rebuild_graph", "the outstanding rebuild completes"),
    "systemic-halt": ("ops.truth sweep", "resolves when the systemic evidence stops holding"),
    "incident-recurrence": ("ops.truth sweep", "the family's prevention is fixed and the "
                                               "regression check passes"),
    "postcondition": ("ops.truth sweep", "the postcondition reads VERIFIED again"),
    "etsy.oauth.needs_owner": ("owner", "re-authorise the Etsy app in a browser"),
    "etsy.auth_needs_owner": ("owner", "re-authorise the Etsy app in a browser"),
    # W4-OWNER: the families production actually held open on 2026-10-06 (18 rows), each
    # with the detector that reconciles it. None of them is the owner's.
    "seasonal.at_risk": ("seasonal.sentinel", "re-keyed by event and year; resolves when the "
                                              "product is no longer at risk, its occasion "
                                              "does not match, or the occurrence passes"),
    "seasonal.calendar_behind": ("seasonal.sentinel", "resolves when the milestones have "
                                                      "evidence, no lane can still reach a "
                                                      "customer, or the occurrence passes"),
    "seasonal.preparation_late": ("seasonal.sentinel", "resolves when the stream's "
                                                       "preparation evidence is recorded"),
    "build.stalled": ("build.tick", "resolves when the watchdog verdict is not a claimed-"
                                    "but-idle stall (moving / awaiting a build session / "
                                    "waiting on gates)"),
    "scheduler.cadence_failed": ("ops.health hygiene", "resolves when the cadence enqueues "
                                                       "a job again after the failure"),
    "paid_call.unresolved": ("operator", "reconcile the paid call's outcome at the provider; "
                                         "never re-sent automatically (F-339)"),
    "effect.reconcile": ("operator", "reconcile the external effect's outcome; automatic "
                                     "repeat is refused"),
}


# ---- W4-OWNER: rule-based hygiene. Closing is by rule with a stated reason, never deletion.

def close_duplicates(session, *, now: datetime | None = None) -> list[dict]:
    """Two open rows with one signature are one condition: keep the oldest, fold the others'
    report counts into it and resolve them as duplicates of it (with resolved_at)."""
    from sqlalchemy import select

    by_sig: dict[str, list[Incident]] = {}
    for row in session.scalars(select(Incident).where(
            Incident.resolved == False).order_by(Incident.id)):  # noqa: E712
        by_sig.setdefault(row.signature, []).append(row)
    out = []
    for sig, rows in by_sig.items():
        if len(rows) < 2:
            continue
        keep, dups = rows[0], rows[1:]
        keep.report_count = int(keep.report_count or 1) + sum(int(d.report_count or 1)
                                                               for d in dups)
        for d in dups:
            merged = dict(d.detail or {})
            merged["resolution"] = (f"duplicate of incident #{keep.id} (same signature "
                                    f"{sig!r}); its reports were folded into that row")
            merged["resolved_at"] = _now_iso(now)
            merged["duplicate_of"] = keep.id
            merged.setdefault("last_seen", merged.get("first_seen") or _aware(d.at).isoformat())
            d.detail = merged
            d.resolved = True
            out.append({"id": d.id, "duplicate_of": keep.id, "signature": sig})
    return out


CADENCE_FAILED = "scheduler.cadence_failed:"


def close_recovered_cadences(session, *, now: datetime | None = None) -> list[str]:
    """`scheduler.cadence_failed:<name>` stops holding once that cadence's job type has been
    enqueued again after the failure was last seen."""
    from sqlalchemy import select

    from ..core.models import Job

    resolved = []
    for row in session.scalars(select(Incident).where(
            Incident.signature.like(f"{CADENCE_FAILED}%"),
            Incident.resolved == False)):  # noqa: E712
        detail = row.detail or {}
        job_type = detail.get("job_type")
        if not job_type:
            continue
        last = detail.get("last_seen")
        try:
            since = _aware(datetime.fromisoformat(last)) if last else _aware(row.at)
        except ValueError:
            since = _aware(row.at)
        job = session.scalar(select(Job).where(Job.job_type == job_type)
                             .order_by(Job.id.desc()).limit(1))
        if job is None or job.created_at is None or _aware(job.created_at) <= since:
            continue
        merged = dict(detail)
        merged["resolution"] = (f"cadence recovered: {job_type} job #{job.id} was enqueued at "
                                f"{_aware(job.created_at).isoformat()}, after the failure")
        merged["resolved_at"] = _now_iso(now)
        merged.setdefault("last_seen", _aware(row.at).isoformat())
        row.detail = merged
        row.resolved = True
        resolved.append(row.signature)
    return resolved


def hygiene(session, *, now: datetime | None = None) -> dict:
    """The rule-based closes run on the ops.health sweep. Never deletes a row."""
    return {"duplicates": close_duplicates(session, now=now),
            "cadences_recovered": close_recovered_cadences(session, now=now)}
CONFIRMED_WITHIN_HOURS = 48


def actionability(incident: Incident, *, now: datetime | None = None) -> dict:
    """F-195: last-confirmed time, current applicability and the owning remediation/gate."""
    now = now or datetime.now(timezone.utc)
    detail = incident.detail or {}
    kind = kind_of(incident.signature)
    last = detail.get("last_seen") or detail.get("first_seen")
    try:
        last_dt = _aware(datetime.fromisoformat(last)) if last else _aware(incident.at)
    except ValueError:
        last_dt = _aware(incident.at)
    owner, path = REMEDIATION.get(kind, (None, None))
    if detail.get("owner_action") and not path:
        owner, path = "owner", str(detail["owner_action"])
    age_h = (now - last_dt).total_seconds() / 3600
    if incident.resolved:
        applicability = "resolved"
    elif age_h <= CONFIRMED_WITHIN_HOURS:
        applicability = "current"
    else:
        applicability = "UNCONFIRMED"
    return {"last_confirmed": last_dt.isoformat(),
            "applicability": applicability,
            "remediation_owner": owner, "remediation_path": path,
            "needs_owner_path": owner is None,
            "why": ("" if applicability != "UNCONFIRMED" else
                    f"no detector has re-confirmed this for {round(age_h)}h; it may no longer "
                    f"hold, and it is not called current")}


# F-392 (wave-3 K7): incident learning. A meaningful incident carries, once resolved, a root
# cause, a durable prevention reference, regression coverage and its failure family; a family
# that recurs after its prevention was recorded is surfaced, never silent.
MEANINGFUL_PREFIXES = ("health", "spend", "stale-artefact", "authority_chain_tamper",
                       "finance.", "support.", "release.", "rebuild", "identity_drift",
                       "customer", "policy_changed", "systemic-halt", "postcondition")


def meaningful(incident: Incident) -> bool:
    return incident.severity in ("P0", "P1") or any(
        incident.signature.startswith(p) for p in MEANINGFUL_PREFIXES)


def record_learning(session, incident_id: int, *, root_cause: str, prevention_ref: str,
                    regression_ref: str, family: str | None = None,
                    now: datetime | None = None) -> dict:
    """Attach the learning to an incident. Every field is required; none may be blank."""
    row = session.get(Incident, incident_id)
    if row is None:
        raise KeyError(incident_id)
    fields = {"root_cause": root_cause, "prevention_ref": prevention_ref,
              "regression_ref": regression_ref}
    blank = [k for k, v in fields.items() if not str(v or "").strip()]
    if blank:
        raise ValueError(f"incident learning needs {blank}: a learning record with a blank "
                         f"field is how the same failure recurs silently")
    merged = dict(row.detail or {})
    merged["learning"] = dict({k: str(v)[:1000] for k, v in fields.items()},
                              family=family or kind_of(row.signature),
                              recorded_at=_now_iso(now))
    row.detail = merged
    return merged["learning"]


def learning(session, *, now: datetime | None = None, days: int = 30) -> dict:
    """Meaningful resolved incidents lacking learning, and families recurring after it."""
    from sqlalchemy import select

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    gaps, learned_families, recurred = [], {}, []
    rows = list(session.scalars(select(Incident).order_by(Incident.id.desc()).limit(2000)))
    for row in rows:
        detail = row.detail or {}
        if row.resolved and detail.get("learning"):
            fam = detail["learning"].get("family") or kind_of(row.signature)
            learned_families.setdefault(fam, detail["learning"].get("recorded_at"))
    for row in rows:
        detail = row.detail or {}
        if not meaningful(row):
            continue
        if row.resolved and not detail.get("learning") and _aware(row.at) >= since:
            gaps.append({"id": row.id, "signature": row.signature,
                         "severity": row.severity, "resolution": detail.get("resolution")})
        fam = kind_of(row.signature)
        if not row.resolved and fam in learned_families:
            recorded = learned_families[fam]
            try:
                after = recorded and _aware(row.at) >= _aware(datetime.fromisoformat(recorded))
            except ValueError:
                after = False
            if after:
                recurred.append({"id": row.id, "signature": row.signature, "family": fam,
                                 "prevention_recorded_at": recorded})
    return {"gaps": gaps, "recurred_after_prevention": recurred,
            "families_with_learning": sorted(learned_families), "window_days": days,
            "status": ("DEGRADED" if gaps or recurred else "OK"),
            "rule": ("every meaningful incident (P0/P1, or reliability/spend/evidence/"
                     "customer family) needs root_cause, prevention_ref and regression_ref "
                     "once resolved; an open incident in a family whose prevention is "
                     "recorded is a recurrence and is surfaced")}


# F-168 (wave-3 K7): halts are per product slug unless evidence shows systemic corruption.
SYSTEMIC_SIGNATURE = "systemic-halt:publication"
SYSTEMIC_MIN_SLUGS = 3
SYSTEMIC_SHARE = 0.5
INTEGRITY_FAMILIES = ("authority_chain_tamper",)


def systemic_evidence(session) -> dict:
    """Whether open halting incidents amount to systemic corruption, and the evidence."""
    from sqlalchemy import select

    from ..core.models import Product

    open_rows = list(session.scalars(select(Incident).where(
        Incident.resolved == False)))  # noqa: E712
    tamper = [r.signature for r in open_rows
              if kind_of(r.signature) in INTEGRITY_FAMILIES]
    products = len(list(session.scalars(select(Product.id))))
    by_family: dict[str, set[str]] = {}
    for r in open_rows:
        if r.halts_publication and r.product_slug:
            by_family.setdefault(kind_of(r.signature), set()).add(r.product_slug)
    widespread = {fam: sorted(slugs) for fam, slugs in by_family.items()
                  if len(slugs) >= SYSTEMIC_MIN_SLUGS and products
                  and len(slugs) / products >= SYSTEMIC_SHARE}
    return {"systemic": bool(tamper or widespread), "integrity_failures": tamper,
            "widespread_families": widespread, "products": products,
            "rule": (f"one failure family halting >= {SYSTEMIC_MIN_SLUGS} products and >= "
                     f"{int(SYSTEMIC_SHARE * 100)}% of the catalogue, or any open "
                     f"integrity failure ({', '.join(INTEGRITY_FAMILIES)}), escalates to a "
                     f"company-wide publication halt; otherwise halts stay per product")}


def escalate_systemic(session, *, now: datetime | None = None) -> dict:
    """Open (or restate) the company-wide halt while the evidence holds; resolve it after."""
    ev = systemic_evidence(session)
    life = reconcile(session, SYSTEMIC_SIGNATURE, lambda _inc: ev["systemic"],
                     resolution="the systemic evidence no longer holds; halts are per product "
                                "again", now=now)
    opened = False
    if ev["systemic"]:
        _row, opened = open_or_restate(
            session, signature=SYSTEMIC_SIGNATURE, severity="P0", product_slug=None,
            halts_publication=True,
            summary=("systemic corruption evidence: publication halted company-wide "
                     f"(integrity: {ev['integrity_failures']}; widespread: "
                     f"{sorted(ev['widespread_families'])})"),
            detail={"evidence": ev}, now=now)
    return dict(ev, opened=opened, resolved=life["resolved"])


def _row(incident: Incident) -> dict:
    detail = incident.detail or {}
    return {
        "id": incident.id,
        "signature": incident.signature,
        "kind": kind_of(incident.signature),
        "severity": incident.severity,
        "product_slug": incident.product_slug,
        "summary": incident.summary,
        "halts_publication": bool(incident.halts_publication),
        "report_count": int(incident.report_count or 1),
        "opened_at": _aware(incident.at).isoformat(),
        "first_seen": detail.get("first_seen"),
        "last_seen": detail.get("last_seen"),
        "resolved": bool(incident.resolved),
        "resolved_at": detail.get("resolved_at"),
        "resolution": detail.get("resolution"),
        "learning": detail.get("learning"),
        **actionability(incident),
    }


def snapshot(session, *, now: datetime | None = None,
             resolved_within_hours: int = RESOLVED_VISIBLE_HOURS) -> dict:
    """Open incidents and recently resolved ones, grouped by detector family.

    Resolved rows are selected by `detail.resolved_at`, which only this module writes; a row
    closed by hand or by older code that set `resolved` without saying why has no timestamp
    and is listed under `resolved_without_evidence` so the omission is visible rather than
    hidden by a filter.
    """
    from sqlalchemy import select

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=resolved_within_hours)

    open_rows = [_row(i) for i in session.scalars(
        select(Incident).where(Incident.resolved == False)  # noqa: E712
        .order_by(Incident.severity, Incident.at.desc()))]
    # The resolved set is bounded by the row's own `at` first, in SQL, so this never walks
    # the whole history: a row resolved in the last day was opened at most however long the
    # longest-lived condition ran, and a generous SQL bound keeps the Python filter small.
    candidates = list(session.scalars(
        select(Incident).where(Incident.resolved == True)  # noqa: E712
        .order_by(Incident.id.desc()).limit(500)))
    recently, without_evidence = [], 0
    for incident in candidates:
        stamp = (incident.detail or {}).get("resolved_at")
        if not stamp:
            without_evidence += 1
            continue
        try:
            when = datetime.fromisoformat(stamp)
        except ValueError:
            without_evidence += 1
            continue
        if _aware(when) >= since:
            recently.append(_row(incident))

    by_kind: dict[str, dict] = {}
    for row in open_rows:
        by_kind.setdefault(row["kind"], {"open": [], "resolved": []})["open"].append(row)
    for row in recently:
        by_kind.setdefault(row["kind"], {"open": [], "resolved": []})["resolved"].append(row)

    return {
        "as_of": now.isoformat(),
        "open_total": len(open_rows),
        "resolved_last_hours": resolved_within_hours,
        "resolved_recently_total": len(recently),
        "resolved_without_evidence_in_sample": without_evidence,
        "by_kind": {kind: by_kind[kind] for kind in sorted(by_kind)},
        # F-195: open rows nobody owns, or that no detector has re-confirmed recently.
        "needs_owner_path": [r["signature"] for r in open_rows if r["needs_owner_path"]],
        "unconfirmed": [r["signature"] for r in open_rows
                        if r["applicability"] == "UNCONFIRMED"],
        # F-392: learning gaps and recurrences.
        "learning": learning(session, now=now),
        "note": ("An incident closes when its condition stops holding and says what closed "
                 "it (detail.resolution, detail.resolved_at). A row that only says "
                 "'resolved' is counted under resolved_without_evidence rather than shown "
                 "as closed with a reason it does not have."),
    }
