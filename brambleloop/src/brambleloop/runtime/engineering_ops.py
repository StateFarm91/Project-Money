"""Product Development: `cir.revise` (crochet_engineer) -- W4-AGENTS department batch 3.

Before this, a CIR that failed `cir.compile` simply died there ("the concept dies here") and
`cir.revise` was a permission with no handler. Now a failed compile is handed back to the
Crochet Engineer once, with the compiler's findings, and the engineer applies only repair
rules that change *declared geometry parameters* and never the design's idea -- then the
revised CIR goes back through `cir.compile` -> `gate.certify` exactly like a new draft.
Deterministic validation still decides: a revision is a candidate, nothing more.

Like `cir.draft`, this is deterministic (the draft path calls no model; Master Plan s2 forbids
asking a model to supply instructions). No model, no network, CA$0 -- well inside the
crochet_engineer CA$4.00 daily ceiling, which stays the bound if a model rule is ever added.

Rules (each one names the finding it answers):

* `REPEAT_DIVISIBILITY` -- answers compiler `REPEAT`/`COUNT_MISMATCH` on a uniform-width flat
  panel (the `concept_to_cir` shape: plain rows of W stitches alternating with a to-end
  repeat of unit u). W becomes the nearest multiple of u (ties upward, at least u); every
  plain row, declared count and the foundation move together. The width change is recorded.
* `GAUGE_FROM_YARN_BAND` (W5-A5) -- answers the certificate's
  `GAUGE_OUTSIDE_DECLARED_YARN_BAND`: the gauge is replaced by the middle of the declared
  yarn's published single-crochet band (`creative.prototype.gauge_for`, the same derivation
  `products.reengineer` uses). Only a single-crochet gauge with one recognisable declared
  weight is touched; anything else is UNREPAIRABLE rather than converted by a guessed ratio.

Anything else is recorded as UNREPAIRABLE with its finding codes -- honest, and a lesson for
`improve.mine` -- rather than guessed at.

P0-CORRECTION-LOOP (W5-A5): the bounded correction loop
----------------------------------------------------------
Every stage that can refuse a CIR for a reason a rule above might answer routes the refusal
through `route_failure`: `cir.compile` (compile errors), `gate.certify` (a refused
certificate), the post-certification re-verifications (`runtime.quality_ops`) and
`assets.build` (Asset Truth errors on the listing frames). Each refusal ends in exactly one
of three places, with no model and no manual step:

1. **Revision.** A rule answers one of the codes and the bound is not spent: one `cir.revise`
   job, keyed `revise:<slug>:<version>:<fingerprint>` (one revision per failing design,
   whatever stage or event raised it). The revision goes back through `cir.compile` ->
   `gate.certify` like any new design. A certified release is never edited in place: a
   revision of one (re-verification, assets) is a new minor version carrying the
   `correction` relation `buyer_trust.on_certified` reads.
2. **Named hold.** No rule answers, the rule cannot apply to this design, the revision does
   not compile, or the bound is spent: the correction loop stops for that product version.
   Compile and certify refusals open one P2 incident `correction-hold:<slug>@<version>`
   (non-halting; `ops.incident_lifecycle` family `correction-hold`) and write a
   `cir.correction_held` audit row naming the stage, codes, attempts and reason. A
   re-verification or assets refusal already has its own named hold (withholding kind
   `quality_reverify` / incident `chain-deadend:assets:...`), which stands as the hold; the
   audit row names it. A held version enqueues nothing further from this loop.
3. **Evidence wait.** Every blocking code is a missing-evidence code (`EVIDENCE_WAIT`: a
   physical make, an uncalibrated primitive) -- not a design defect, and not answerable by
   any revision. Nothing is revised and nothing is held here; the physical-retest owner
   action and the tester plan are that product's path.

The bound: `MAX_REVISIONS` = 1 deterministic revision per product version (counted
durably: distinct revised fingerprints in `cir.revised` audit rows, plus the `revision`
counter carried on the chain's job inputs), and at most one per failing fingerprint (the
idempotency key). One, because every rule is a single-shot geometry/gauge parameter repair
whose output is re-validated by every gate: a revised design that still fails is outside
what deterministic repair can reach without changing the design's idea, and stacking a
second edit on the first is how a concept drifts away from its brief. A revision applies
every rule whose finding is present at once, so one revision covers a design with both a
repeat and a gauge defect.
"""
from __future__ import annotations

import copy
import re

from .worker import JobContext, handlers

MAX_REVISIONS = 1

HOLD_PREFIX = "correction-hold:"
HOLD_AUDIT = "cir.correction_held"
REVISED_AUDIT = "cir.revised"
STAGES = ("compile", "certify", "quality", "assets")
# Blocking codes that name missing evidence, not a design defect. No revision answers them,
# and they have their own path (`pipeline._request_physical_retest`, the tester plan).
EVIDENCE_WAIT = frozenset({"PHYSICAL_TEST_REQUIRED", "UNCALIBRATED_PRIMITIVE",
                           "RISK_CLASS_DOWNGRADE_UNJUSTIFIED"})
_CODE = re.compile(r"^\s*(?:(?:ERROR|WARNING|US|UK)\s+)*"
                   r"([A-Z][A-Z0-9_]{3,})\s*:")


def _unit(node) -> int | None:
    from ..cir.model import Op, Repeat

    if isinstance(node, Repeat) and node.times is None and all(isinstance(o, Op)
                                                               for o in node.ops):
        return sum(int(o.count) for o in node.ops)
    return None


def repair_repeat_divisibility(cir) -> tuple[object | None, dict]:
    """The REPEAT_DIVISIBILITY rule. (revised CIR or None, what it did / why not)."""
    from ..cir.model import Op

    if len(cir.components) != 1:
        return None, {"why": "rule covers single-panel CIRs only"}
    comp = cir.components[0]
    if comp.construction != "flat_rows" or not comp.rows:
        return None, {"why": "rule covers flat-row panels only"}
    widths, units = set(), set()
    for row in comp.rows:
        if len(row.ops) != 1:
            return None, {"why": f"row {row.index} is not a single plain op or repeat"}
        node = row.ops[0]
        if isinstance(node, Op):
            widths.add(int(node.count))
        else:
            u = _unit(node)
            if u is None:
                return None, {"why": f"row {row.index} repeat is not a plain to-end repeat"}
            units.add(u)
        if row.declared_count is not None:
            widths.add(int(row.declared_count))
    if comp.foundation:
        widths.add(int(comp.foundation))
    if len(widths) != 1 or len(units) != 1:
        return None, {"why": f"not a uniform panel (widths {sorted(widths)}, units "
                             f"{sorted(units)})"}
    (w,), (u,) = widths, units
    if w % u == 0:
        return None, {"why": f"width {w} already divides by the repeat unit {u}"}
    lower, upper = (w // u) * u, (w // u + 1) * u
    new_w = upper if (upper - w) <= (w - lower) or lower < u else lower
    revised = copy.deepcopy(cir)
    rc = revised.components[0]
    for row in rc.rows:
        node = row.ops[0]
        if isinstance(node, Op):
            node.count = new_w
        if row.declared_count is not None:
            row.declared_count = new_w
    if rc.foundation:
        rc.foundation = new_w
    return revised, {"rule": "REPEAT_DIVISIBILITY", "width_from": w, "width_to": new_w,
                     "unit": u, "rows_changed": len(rc.rows),
                     "note": "finished width changes accordingly; certification re-derives "
                             "size and yardage from the revised CIR"}


def repair_gauge_band(cir) -> tuple[object | None, dict]:
    """The GAUGE_FROM_YARN_BAND rule. (revised CIR or None, what it did / why not).

    Fires only when the certificate's own gauge check (`gates.certificate.gauge_findings`)
    refuses the gauge as outside the declared yarn's band, and replaces it with the band's
    middle (`creative.prototype.gauge_for`). Every finished size and yardage figure is
    re-derived from the new gauge by certification; nothing here restates a dimension."""
    from dataclasses import replace

    from ..creative.prototype import PrototypeRefused, gauge_for
    from ..gates.certificate import declared_weight, gauge_findings

    codes = {f.code for f in gauge_findings(cir) if f.is_error}
    if "GAUGE_OUTSIDE_DECLARED_YARN_BAND" not in codes:
        return None, {"why": "the gauge is not refused as outside its declared yarn's band"}
    if (cir.gauge.stitch_type or "sc") != "sc":
        return None, {"why": "the band is a single-crochet band; a converted ratio would be "
                             "a guess"}
    weight = declared_weight(cir)
    try:
        new_gauge = gauge_for(weight or "")
    except PrototypeRefused as exc:
        return None, {"why": str(exc)[:200]}
    # Preserve hook, row and chain gauges; the finding authorizes stitch gauge only.
    revised = replace(cir, gauge=replace(
        cir.gauge, stitches_per_10cm=new_gauge.stitches_per_10cm))
    if any(f.is_error for f in gauge_findings(revised)):
        return None, {"why": "the band's own gauge is still refused for this yarn"}
    return revised, {"rule": "GAUGE_FROM_YARN_BAND", "yarn_weight": new_gauge.yarn_weight,
                     "gauge_from": cir.gauge.stitches_per_10cm,
                     "gauge_to": new_gauge.stitches_per_10cm,
                     "basis": "publish.substitution yarn band (creative.prototype.gauge_for)",
                     "note": "finished size and yardage are re-derived by certification "
                             "from the revised gauge"}


RULES = (("REPEAT_DIVISIBILITY", ("REPEAT", "COUNT_MISMATCH", "UNDERRUN", "OVERRUN"),
          repair_repeat_divisibility),
         ("GAUGE_FROM_YARN_BAND", ("GAUGE_OUTSIDE_DECLARED_YARN_BAND",), repair_gauge_band))


# ---- P0-CORRECTION-LOOP (W5-A5): route, bound, hold -------------------------------------

def codes_of(problems) -> list[str]:
    """Finding codes named in refusal strings (`ERROR CODE: ...`, `US CODE: ...`)."""
    out: set[str] = set()
    for p in problems or ():
        match = _CODE.match(str(p))
        if match and match.group(1) not in {"ERROR", "WARNING", "NOTE"}:
            out.add(match.group(1))
    return sorted(out)


def live_codes(cir) -> set[str]:
    """Codes a rule self-detects on the design itself (deterministic, no context needed)."""
    from ..gates.certificate import gauge_findings

    try:
        return {f.code for f in gauge_findings(cir) if f.is_error}
    except Exception:  # noqa: BLE001 - a design the check cannot read answers nothing
        return set()


def answering_rules(codes) -> list[str]:
    codes = set(codes or ())
    return [name for name, answers, _ in RULES if codes & set(answers)]


def hold_signature(slug: str, version: str) -> str:
    return f"{HOLD_PREFIX}{slug}@{version}"[:200]


def open_hold(db, slug: str, version: str) -> dict | None:
    """The open named correction hold of slug@version, if any."""
    from sqlalchemy import select

    from ..core.models import Incident

    with db.session() as s:
        row = s.scalar(select(Incident).where(
            Incident.signature == hold_signature(slug, version),
            Incident.resolved == False))  # noqa: E712
        return None if row is None else {"id": row.id, "signature": row.signature,
                                         "detail": dict(row.detail or {})}


def _trusted_revision(audit, job, slug: str, version: str) -> bool:
    """A review record must bind to the queued producer and exact source CIR."""
    from ..cir.model import CIR

    detail = audit.detail if isinstance(audit.detail, dict) else {}
    if (job is None or audit.actor != "crochet_engineer" or job.agent != "crochet_engineer"
            or job.job_type != "cir.revise" or job.started_at is None
            or not isinstance(job.inputs, dict)):
        return False
    try:
        cir = CIR.from_dict(job.inputs["cir"])
        expected_target = _bump(version) if job.inputs.get("bump_version") else version
        return (cir.slug == slug and cir.version == version
                and cir.fingerprint == detail.get("from_fingerprint")
                and detail.get("to_version") == expected_target)
    except Exception:  # noqa: BLE001 - damaged provenance cannot establish a safe bound
        return False


def _lineage_attempts(session, slug: str, version: str) -> int:
    """Count authenticated revisions in this version's ancestry; uncertainty holds."""
    from sqlalchemy import select
    from ..core.models import AuditLog, Job

    prefix = f"{slug}@"
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    records = list(session.execute(select(AuditLog, Job).outerjoin(
        Job, Job.id == AuditLog.job_id).where(
            AuditLog.action == REVISED_AUDIT,
            AuditLog.artifact.like(escaped + "%", escape="\\"))))
    parents: dict[str, list[tuple]] = {}
    by_source: dict[str, list[tuple]] = {}
    for audit, job in records:
        source = (audit.artifact or "")[len(prefix):]
        detail = audit.detail if isinstance(audit.detail, dict) else {}
        target = detail.get("to_version")
        row = (audit, job, source, detail)
        by_source.setdefault(source, []).append(row)
        if isinstance(target, str) and target and target != source:
            parents.setdefault(target, []).append(row)

    def trusted(row) -> bool:
        return _trusted_revision(row[0], row[1], slug, row[2])

    # A corrupted or forged edge could hide the very parent we are looking
    # for. Every record for this product must be authentic before traversing.
    if any(not trusted(row) for rows in by_source.values() for row in rows):
        return MAX_REVISIONS
    chain, cursor = set(), version
    while True:
        if cursor in chain:
            return MAX_REVISIONS  # a cycle cannot establish a safe lineage
        chain.add(cursor)
        incoming = parents.get(cursor, [])
        if not incoming:
            break
        if any(not trusted(row) for row in incoming):
            return MAX_REVISIONS
        sources = {row[2] for row in incoming}
        if len(sources) != 1:
            return MAX_REVISIONS
        cursor = next(iter(sources))
    relevant = [row for source in chain for row in by_source.get(source, [])]
    if any(not trusted(row) for row in relevant):
        return MAX_REVISIONS
    return len({(row[2], row[3].get("from_fingerprint")) for row in relevant})


def revision_attempts(db, slug: str, version: str) -> int:
    """Count revisions across the authenticated source-version chain, not just its tip."""
    with db.session() as session:
        return _lineage_attempts(session, slug, version)


# Serialize the final audit decision across all workers. A database transaction,
# not an in-process mutex, enforces the cap when Railway has multiple replicas.
_REVISION_LOCK = 734543626
_HOLD_LOCK = 734543627


def _claim_revision(ctx, artifact: str, fingerprint: str, detail: dict) -> tuple[bool, bool]:
    """Atomically claim one source version. Same-fingerprint replays may resume."""
    from sqlalchemy import select, text
    from ..core.db import is_postgres
    from ..core.models import AuditLog

    with ctx.db.session() as session:
        if is_postgres(ctx.db.engine):
            session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _REVISION_LOCK})
        else:
            session.execute(text("BEGIN IMMEDIATE"))
        from ..core.models import Job

        prior = list(session.execute(select(AuditLog, Job).outerjoin(
            Job, Job.id == AuditLog.job_id).where(
                AuditLog.action == REVISED_AUDIT, AuditLog.artifact == artifact)))
        slug, version = artifact.rsplit("@", 1)
        matching = [(audit, job) for audit, job in prior
                    if (audit.detail or {}).get("from_fingerprint") == fingerprint]
        if matching:
            # A redelivery may resume only authenticated evidence for the same result.
            same = all(_trusted_revision(audit, job, slug, version)
                       and all((audit.detail or {}).get(k) == detail.get(k) for k in
                               ("to_fingerprint", "to_version", "rules", "stage"))
                       for audit, job in matching)
            return same, same
        if _lineage_attempts(session, slug, version) >= MAX_REVISIONS:
            return False, False
        session.add(AuditLog(actor=ctx.job.agent, action=REVISED_AUDIT, artifact=artifact,
                             job_id=ctx.job.id, phase=ctx.phase, detail=detail))
        return True, False


def _bump(version: str) -> str:
    from ..products.reengineer import _bump as bump

    return bump(version)


def record_hold(ctx: JobContext, cir, *, stage: str, reason: str, codes, problems=(),
                attempts: int = 0, existing_hold: str | None = None) -> dict:
    """The named terminal hold. Idempotent: one open row per slug@version, restated."""
    from ..ops import incident_lifecycle as lifecycle

    slug, version = cir.slug, cir.version
    sig = existing_hold or hold_signature(slug, version)
    detail = {"kind": "correction_hold", "stage": stage, "reason": reason,
              "codes": sorted(codes or ())[:20],
              "problems": [str(p)[:200] for p in problems or ()][:5],
              "attempts": attempts, "cap": MAX_REVISIONS, "fingerprint": cir.fingerprint,
              "department": "product_design (crochet_engineer)",
              "next": "a new design version or a new deterministic repair rule; the "
                      "correction loop enqueues nothing more for this version"}
    opened = False
    if existing_hold is None:
        from sqlalchemy import select, text
        from ..core.db import is_postgres
        from ..core.models import AuditLog, Incident, Job, JobStatus, utcnow
        from ..queue.effects import LeaseLost

        # Serialize A5 writers so a repeated delivery cannot create duplicate incidents or
        # lose the audit for an opened/changed hold after a crash. Incident restatement and
        # its audit must commit together; incident last_seen/report_count still advance.
        with ctx.db.session() as s:
            if is_postgres(ctx.db.engine):
                s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _HOLD_LOCK})
            else:
                s.execute(text("BEGIN IMMEDIATE"))
            # Lock the producer job in this transaction so a reclaimed worker cannot
            # overwrite a current incident after validating an obsolete lease.
            token = getattr(ctx.job, "lease_token", None)
            job_id = getattr(ctx.job, "id", None)
            job = (s.scalar(select(Job).where(Job.id == job_id).with_for_update())
                   if job_id is not None else None)
            if job_id is not None and job is None:
                raise LeaseLost(f"job {job_id}: correction hold producer is unavailable")
            if token is None and job is not None and job.lease_token is not None:
                raise LeaseLost(f"job {job_id}: correction hold requires its current lease")
            if token is not None:
                expiry = job.lease_expires_at if job is not None else None
                if expiry is not None and expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=utcnow().tzinfo)
                if (job is None or job.status != JobStatus.RUNNING or job.lease_token != token
                        or expiry is None or expiry <= utcnow()):
                    raise LeaseLost(f"job {ctx.job.id}: correction hold lease no longer current")
            current = s.scalar(select(Incident).where(
                Incident.signature == sig, Incident.resolved == False))  # noqa: E712
            previous = dict(current.detail or {}) if current is not None else {}
            changed = current is None or any(previous.get(k) != v for k, v in detail.items())
            _row, opened = lifecycle.open_or_restate(
                s, signature=sig, severity="P2", product_slug=slug,
                summary=(f"correction loop held {slug}@{version} at {stage}: {reason}")[:500],
                detail=detail, halts_publication=False)
            if changed:
                s.add(AuditLog(actor=ctx.job.agent, action=HOLD_AUDIT,
                               artifact=f"{slug}@{version}", job_id=ctx.job.id,
                               phase=ctx.phase,
                               detail={**detail, "signature": sig, "opened": opened}))
    else:
        # A hold owned by another department has its own incident lifecycle.
        ctx.audit(HOLD_AUDIT, artifact=f"{slug}@{version}",
                  detail={**detail, "signature": sig, "opened": opened})
    return {"held": True, "hold": sig, "reason": reason, "opened": opened}


def route_failure(ctx: JobContext, cir, *, stage: str, codes=(), problems=(),
                  revision: int = 0, bump_version: bool = False, correction=None,
                  existing_hold: str | None = None) -> dict:
    """A stage refused `cir`: one revision, a named hold, or an evidence wait. Never more.

    `revision` is the lineage counter the chain carries; `existing_hold` names the hold a
    stage already records for itself (re-verification, assets). See the module docstring."""
    assert stage in STAGES, stage
    slug, version = cir.slug, cir.version
    codes = set(codes or ()) | set(codes_of(problems))
    held = open_hold(ctx.db, slug, version)
    if held is not None:
        # Already terminal: restate the hold, enqueue nothing.
        return {**record_hold(ctx, cir, stage=stage, reason=held["detail"].get(
            "reason", "held"), codes=codes, problems=problems,
            attempts=held["detail"].get("attempts", 0)), "already_held": True}
    defects = codes - EVIDENCE_WAIT
    if codes and not defects:
        return {"held": False, "waiting_on_evidence": sorted(codes)}
    rules = answering_rules(codes)
    attempts = max(max(0, int(revision or 0)), revision_attempts(ctx.db, slug, version))
    if not rules:
        return record_hold(ctx, cir, stage=stage, codes=codes, problems=problems,
                           attempts=attempts, existing_hold=existing_hold,
                           reason=f"no deterministic revision answers {sorted(codes)[:8]}")
    if attempts >= MAX_REVISIONS:
        return record_hold(ctx, cir, stage=stage, codes=codes, problems=problems,
                           attempts=attempts, existing_hold=existing_hold,
                           reason=f"revision cap {MAX_REVISIONS} reached ({attempts} made); "
                                  f"{sorted(codes)[:8]} still blocks")
    inputs = {"cir": cir.to_dict(), "revision": max(0, int(revision or 0)), "stage": stage,
              "codes": sorted(codes)}
    if bump_version:
        inputs["bump_version"] = True
    if isinstance(correction, dict):
        inputs["correction"] = correction
    if existing_hold:
        inputs["existing_hold"] = existing_hold
    job = ctx.enqueue("crochet_engineer", "cir.revise", inputs,
                      idempotency_key=f"revise:{slug}:{version}:{cir.fingerprint}")
    return {"held": False, "revise_job": getattr(job, "id", None), "rules": rules,
            "duplicate": job is None}


@handlers.register("cir.revise")
def handle_cir_revise(ctx: JobContext) -> dict:
    from dataclasses import replace

    from ..cir.compiler import compile_cir
    from ..cir.model import CIR

    i = dict(ctx.job.inputs or {})
    if not isinstance(i.get("cir"), dict):
        return {"ran": False, "why": "cir.revise needs the failed CIR"}
    cir = CIR.from_dict(i["cir"])
    stage = i.get("stage") if i.get("stage") in STAGES else "compile"
    existing_hold = i.get("existing_hold") or None
    revision = max(0, int(i.get("revision") or 0)) + 1   # I-3: a negative input is 0
    artifact = f"{cir.slug}@{cir.version}"
    if open_hold(ctx.db, cir.slug, cir.version) is not None:
        return {"ran": False, "artifact": artifact, "held": True,
                "why": "this version is on a named correction hold"}
    if revision > MAX_REVISIONS:
        record_hold(ctx, cir, stage=stage, codes=i.get("codes") or (), attempts=revision - 1,
                    existing_hold=existing_hold,
                    reason=f"revision cap {MAX_REVISIONS} reached")
        return {"ran": False, "held": True,
                "why": f"revision limit {MAX_REVISIONS} reached; the concept stops here"}
    fingerprint = cir.fingerprint
    attempts = revision_attempts(ctx.db, cir.slug, cir.version)
    from sqlalchemy import select

    from ..core.models import AuditLog

    with ctx.db.session() as s:
        already = any((d or {}).get("from_fingerprint") == fingerprint for d in s.scalars(
            select(AuditLog.detail).where(AuditLog.action == REVISED_AUDIT,
                                          AuditLog.artifact == artifact)))
    if attempts >= MAX_REVISIONS and not already:
        record_hold(ctx, cir, stage=stage, codes=i.get("codes") or (), attempts=attempts,
                    existing_hold=existing_hold,
                    reason=f"revision cap {MAX_REVISIONS} reached ({attempts} made)")
        return {"ran": False, "held": True, "artifact": artifact,
                "why": f"revision limit {MAX_REVISIONS} reached for {artifact}"}
    result = compile_cir(cir)
    if stage == "compile" and result.ok:
        return {"ran": False, "why": "the CIR compiles; nothing to revise"}
    # A rule may answer only the refusal that caused this revision. Compiler
    # errors are authoritative only when this is a compiler refusal.
    codes = sorted(set(i.get("codes") or ()) |
                   ({f.code for f in result.errors} if stage == "compile" else set()))
    current, applied = cir, []
    for name, answers, rule in RULES:
        if not set(codes) & set(answers):
            continue
        revised, what = rule(current)
        if revised is not None:
            current = revised
            applied.append((name, what))
    if not applied:
        ctx.audit("cir.revise_unrepairable", artifact=artifact,
                  detail={"codes": codes, "errors": [str(f)[:160] for f in result.errors][:10],
                          "rules_tried": [n for n, _, _ in RULES], "revision": revision,
                          "stage": stage})
        hold = record_hold(ctx, cir, stage=stage, codes=codes, attempts=attempts,
                           problems=[str(f) for f in result.errors],
                           existing_hold=existing_hold,
                           reason=f"no deterministic rule can revise this design for "
                                  f"{codes[:8]}")
        return {"artifact": artifact, "revised": False, "unrepairable": True, "codes": codes,
                "hold": hold["hold"], "work_done": 1}
    correction = i.get("correction") if isinstance(i.get("correction"), dict) else None
    if i.get("bump_version"):
        # A certified release is immutable (PT-03): its revision is a new minor version and
        # declares what it corrects, so buyers of the old one are found (CB2-O09).
        current = replace(current, version=_bump(cir.version))
        # Never overwrite an occupied release, including an uncertified draft.
        # The certification conflict path also records a hold if another writer
        # occupies this version after this check.
        from ..core.models import PatternVersion, Product
        with ctx.db.session() as session:
            occupied = session.scalar(select(PatternVersion.id).join(
                Product, Product.id == PatternVersion.product_id).where(
                    Product.slug == cir.slug, PatternVersion.version == current.version))
        if occupied is not None:
            hold = record_hold(ctx, cir, stage=stage, codes=codes, attempts=attempts,
                               existing_hold=existing_hold,
                               reason=f"correcting version {current.version} is already occupied")
            return {"artifact": artifact, "revised": False, "held": True,
                    "hold": hold["hold"], "work_done": 1}
        correction = {"of_versions": [cir.version],
                      "of_release_hashes": list((correction or {}).get("of_release_hashes")
                                                or []),
                      "what_changed": "; ".join(n for n, _ in applied)
                                      + f" (correction loop, {stage})"}
    check = compile_cir(current)
    names = [n for n, _ in applied]
    detail = {}
    for _n, what in applied:
        detail.update({k: v for k, v in what.items() if k != "rule"})
    claimed, already = _claim_revision(
        ctx, artifact, fingerprint,
        {"rule": "+".join(names), "rules": names, "codes": codes, **detail,
         "compiles": check.ok, "from_fingerprint": fingerprint,
         "to_fingerprint": current.fingerprint, "revision": revision,
         "stage": stage, "to_version": current.version})
    if not claimed:
        hold = record_hold(ctx, cir, stage=stage, codes=codes, attempts=MAX_REVISIONS,
                           existing_hold=existing_hold,
                           reason="another revision has already claimed this version")
        return {"artifact": artifact, "revised": False, "held": True,
                "hold": hold["hold"], "work_done": 1}
    if not check.ok:
        hold = record_hold(ctx, cir, stage=stage, codes=codes, attempts=attempts + 1,
                           problems=[str(f) for f in check.errors],
                           existing_hold=existing_hold,
                           reason=f"the revision ({'+'.join(names)}) does not compile")
        return {"artifact": artifact, "revised": False, "unrepairable": True, "codes": codes,
                "hold": hold["hold"], "work_done": 1}
    # Back through the ordinary chain: compile, then certify. Literal job type so the
    # autonomy map sees the edge.
    nxt = {"cir": current.to_dict(), "revision": revision, "revision_of": fingerprint}
    if correction:
        nxt["correction"] = correction
    ctx.enqueue("validator", "cir.compile", nxt,
                idempotency_key=f"compile:{current.slug}:{current.version}:"
                                f"{current.fingerprint}")
    return {"artifact": artifact, "revised": True, "rule": "+".join(names), "rules": names,
            "codes": codes, "detail": detail, "stage": stage, "duplicate": already,
            "to_version": current.version, "work_done": 1}


@handlers.register("creative.family_engine")
def handle_family_engine(ctx: JobContext) -> dict:
    """Product Family Engine (creative_director): the certified catalogue's families, bundle
    readiness, recolour duplicates, next members and evidence-gated amplification. Reads our
    own rows only; one reading a day; creates no product. Deterministic, CA$0."""
    from ..creative.family_engine import family_report
    from .etsy_ops import store_reading

    rep = family_report(ctx.db)
    if not rep["certified"]:
        return {"ran": False, "why": "no certified release to group into families"}
    # W4-INTELREC G5: proven families are amplified through the ordinary funnel.
    from ..creative.family_engine import amplify

    amp = amplify(ctx.db, rep, enqueue=ctx.enqueue)
    rep["amplification_decisions"] = amp["decisions"]
    store_reading(ctx.db, "creative.family_engine", rep)
    ctx.audit("creative.family_engine", detail={
        "amplification_decisions": amp["decisions"][:10],
        "families": len(rep["families"]), "singles": len(rep["single_products"]),
        "bundle_ready": rep["portfolio_has_bundle_ready_family"],
        "recolour_duplicates": rep["recolour_duplicates"][:5]})
    return {"families": len(rep["families"]), "single_products": len(rep["single_products"]),
            "portfolio_has_bundle_ready_family": rep["portfolio_has_bundle_ready_family"],
            "recolour_duplicates": len(rep["recolour_duplicates"]),
            "amplification_decisions": len(amp["decisions"]),
            "work_done": len(rep["families"]) + len(rep["single_products"])}



@handlers.register("creative.salvage_review")
def handle_salvage_review(ctx: JobContext) -> dict:
    """F-113: re-gate legacy certified products today. RECOMMENDS only -- never deletes,
    unlists, deactivates or edits a product or listing. One reading; CA$0."""
    from ..creative import salvage
    from .etsy_ops import store_reading

    rep = salvage.review(ctx.db)
    if not rep["count"]:
        return {"ran": False, "why": "no legacy certified product outside the launch scope"}
    store_reading(ctx.db, "creative.salvage_review", rep)
    # W4-C07 F-114: which legacy products to rescue is the owner's decision. Rescue
    # candidates become one owner card; nothing here enqueues `cir.reengineer`.
    rescue = sorted(r["slug"] for r in rep["legacy"]
                    if r["recommendation"] == "rescue_candidate")
    if rescue:
        reengineer_card(ctx.db, rescue)
    ctx.audit("creative.salvage_review", detail={"legacy": rep["count"],
                                                 "retire_recommended": rep["retire_recommended"]})
    return {"legacy": rep["count"], "retire_recommended": len(rep["retire_recommended"]),
            "writes": 0, "work_done": rep["count"]}


@handlers.register("listing.cross_sell_graph")
def handle_cross_sell_graph(ctx: JobContext) -> dict:
    """F-775: the cross-sell graph of the certified catalogue. One reading; CA$0."""
    from ..commerce import cross_sell
    from .etsy_ops import store_reading

    g = cross_sell.graph(ctx.db)
    if not g["products"]:
        return {"ran": False, "why": "no certified product to link"}
    store_reading(ctx.db, "listing.cross_sell_graph", g)
    return {"products": g["products"], "work_done": g["products"]}


@handlers.register("creative.capability_scorecard")
def handle_capability_scorecard(ctx: JobContext) -> dict:
    """Build 2 #94: the complete creativity capability scorecard over time. Reads the rows the
    company writes; unmeasured is UNMEASURED, never 0. One reading a day; CA$0."""
    from ..creative import capability_scorecard as cs
    from .etsy_ops import store_reading

    rep = cs.scorecard(ctx.db)
    store_reading(ctx.db, "creative.capability_scorecard", rep)
    ctx.audit("creative.capability_scorecard", detail={
        "periods": len(rep["periods"]), "objective": rep["objective"]["verdict"],
        "pending_market_evidence": rep["pending_market_evidence"]})
    return {"periods": len(rep["periods"]), "objective": rep["objective"]["verdict"],
            "winner_rate": rep["market"]["winner_rate"],
            "work_done": max(1, len(rep["periods"]))}



@handlers.register("creative.photo_principles")
def handle_photo_principles(ctx: JobContext) -> dict:
    """F-224: the photographic-principles profile and the Launch-0 plan comparison."""
    from ..visual import photo_principles as PP
    from .etsy_ops import store_reading

    out = PP.run(ctx.db)
    store_reading(ctx.db, PP.READING, out)
    # F-231 (W4-INTELREC C05): the same judged galleries quantified as gallery grammar.
    from ..intel import gallery_grammar

    store_reading(ctx.db, gallery_grammar.READING, gallery_grammar.grammar(ctx.db))
    measured = sum(1 for p in out["profile"]["pods"].values() if p["state"] == "MEASURED")
    ctx.audit(PP.READING, detail={"judged_listings": out["profile"]["judged_listings"],
                                  "pods_measured": measured, "gaps": out["gaps"]})
    return {"judged_listings": out["profile"]["judged_listings"], "pods_measured": measured,
            "gaps": out["gaps"], "plans_changed": 0, "work_done": measured}

# F-456/F-482: the shared contracts this module was built against. A contract that moves on
# without this module migrating fails here, at import, instead of drifting silently.
from ..core import contracts as _contracts  # noqa: E402

_contracts.require("cir", 2)


REENGINEER_CARD = "creative.reengineer:owner_choice"


def reengineer_card(db, rescue: list[str]) -> int:
    """One open owner card naming the F-113 rescue candidates; refreshed, never duplicated."""
    from sqlalchemy import select

    from ..core.models import OwnerAction

    with db.session() as s:
        card = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == REENGINEER_CARD,
            OwnerAction.done == False))  # noqa: E712
        text = (f"Choose which legacy products to re-engineer (F-114). Rescue candidates from "
                f"today's salvage test: {', '.join(rescue)}. A chosen product is re-derived "
                f"through the yarn band, compiler, twin and reverse compiler and goes back "
                f"through every certification gate as a new version; nothing is re-engineered "
                f"until you choose.")
        if card is None:
            card = OwnerAction(requirement_key=REENGINEER_CARD, action=text,
                               reason="F-113 salvage test recommends these for rescue",
                               max_cost_cad=0.0, minutes=5,
                               consequence_of_delay="legacy products stay as they are",
                               blocks="F-114")
            s.add(card)
        else:
            card.action = text
        s.flush()
        return card.id


@handlers.register("cir.reengineer")
def handle_cir_reengineer(ctx: JobContext) -> dict:
    """F-114: each OWNER-CHOSEN product re-engineered (`products.reengineer.plan`) and, when
    READY, handed to the ordinary release chain at `cir.compile` (which runs `gate.certify`).

    Not scheduled and enqueued by nothing: it runs only with `owner_action_id` naming a
    decided owner card and `slugs` the owner chose. Nothing here certifies; a plan that does
    not compile or reverse-compile stops here."""
    from ..core.models import OwnerAction
    from ..products import reengineer

    aid = ctx.job.inputs.get("owner_action_id")
    with ctx.db.session() as s:
        card = s.get(OwnerAction, int(aid)) if aid is not None else None
        decided = bool(card is not None and card.done
                       and card.requirement_key == REENGINEER_CARD)
    if not decided:
        return {"ran": False, "work_done": 0,
                "why": "re-engineering needs the owner's decided choice (F-114 card); none given"}
    out = []
    for slug in ctx.job.inputs.get("slugs") or []:
        p = reengineer.plan(ctx.db, slug)
        row = {"slug": slug, "state": p["state"], "why": p.get("why")}
        if p["state"] == reengineer.READY:
            from ..cir.model import CIR

            cir = CIR.from_dict(p["cir"])
            ctx.enqueue("validator", "cir.compile",
                        {"cir": p["cir"], "reengineered_from": p["from_version"]},
                        idempotency_key=f"compile:{cir.slug}:{cir.version}:{cir.fingerprint}")
            row["version"] = p["version"]
        ctx.audit("cir.reengineered", artifact=slug, detail={k: v for k, v in row.items()
                                                             if k != "slug"})
        out.append(row)
    sent = sum(1 for r in out if r["state"] == reengineer.READY)
    return {"plans": out, "sent_to_release_chain": sent, "work_done": len(out)}
