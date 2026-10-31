"""Quality & Compliance as operational agents (W4-AGENTS department batch 1).

`validator`, `asset_truth`, `policy` and `quality_director` each held job types with no
handler (autonomy.map AM-10), so three of the four agents could never run anything. AM-10 kept
them unbuilt because a standalone handler would be "a second, uncertified verdict path". These
handlers are deliberately NOT a verdict path: they never certify, revoke, block or change a
release. They re-run, on releases that are ALREADY certified, the same deterministic stages
`gates.certificate.certify` ran (compile, digital twin, written pattern -> independent reverse
compile in US and UK terms, the title's shape/technique claims, the listing's policy and claim
checks), and a disagreement becomes one deduplicated P2 incident (non-halting) for the owner of
the code that drifted. That is regression detection: a compiler, writer or policy change that
silently breaks a release already on sale is caught the next day, not by a buyer.

P0-REVERIFY-WITHHOLD (OPUS2-P0, integrator-assigned): the certificate is still never changed,
but a failed check now also withholds PUBLICATION of that release (`publish.withholding`
kind `quality_reverify`, kept on the stored release so pruning the audit row cannot reopen it)
until the same check passes again. Drafting and rebuilding are not blocked.

* `gate.quality` (quality_director, daily cadence): enumerate the newest certified release per
  product and queue one re-verification of each kind under its owning agent.
* `cir.twin` / `cir.reverse` (validator), `gate.asset_truth` (asset_truth), `gate.policy`
  (policy): one release each. Deterministic, no model, no network, CA$0.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .worker import JobContext, handlers

READING = "quality.reverified"
CHECKS = {"cir.twin": "validator", "cir.reverse": "validator",
          "gate.asset_truth": "asset_truth", "gate.policy": "policy"}


def certified_releases(db) -> list[dict]:
    """The newest certified PatternVersion per product."""
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    out: dict[str, dict] = {}
    with db.session() as s:
        rows = s.execute(select(Product.slug, PatternVersion.version, PatternVersion.id,
                                PatternVersion.release_hash)
                         .join(PatternVersion, PatternVersion.product_id == Product.id)
                         .where(PatternVersion.certified == True)  # noqa: E712
                         .order_by(PatternVersion.id)).all()
    for slug, version, pid, rh in rows:
        out[slug] = {"slug": slug, "version": version, "release_hash": rh or ""}
    return sorted(out.values(), key=lambda r: r["slug"])


def _cir(db, slug: str, version: str):
    from sqlalchemy import select

    from ..cir.model import CIR
    from ..core.models import PatternVersion, Product

    with db.session() as s:
        pv = s.scalar(select(PatternVersion).join(Product, PatternVersion.product_id ==
                                                  Product.id)
                      .where(Product.slug == slug, PatternVersion.version == version,
                             PatternVersion.certified == True))  # noqa: E712
        return CIR.from_dict(pv.cir_json) if pv is not None else None


def _errors(findings) -> list[str]:
    return [f"{getattr(f, 'code', '?')}: {str(getattr(f, 'message', f))[:120]}"
            for f in findings if getattr(f, "is_error", False)
            or str(getattr(f, "severity", "")).upper() == "ERROR"]


def reverify(db, check: str, slug: str, version: str) -> dict:
    """Re-run one certificate stage on a certified release. Never raises for a finding."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    cir = _cir(db, slug, version)
    if cir is None:
        return {"check": check, "ok": None, "why": f"{slug}@{version} is not certified"}
    result = compile_cir(cir)
    problems = _errors(result.findings) if not result.ok else []
    if check == "cir.twin":
        from ..quality.physical import calibration_from_db

        if not problems:
            twin = build_twin(cir, result, calibration=calibration_from_db(db, cir))
            if not twin.stitch_types_used:
                problems.append("twin: no stitches modelled")
    elif check == "cir.reverse":
        from ..cir.reverse import compare
        from ..cir.writer import write_pattern

        if not problems:
            for term in ("US", "UK"):
                problems += [f"{term} {p}" for p in
                             _errors(compare(cir, write_pattern(cir, result, term), term))]
    elif check == "gate.asset_truth":
        from ..gates.asset_truth import check_shape_claims, check_technique_claims

        if not problems:
            twin = build_twin(cir, result)
            texts = [("cir.title", cir.title)] + [
                (f"listing.{k}", v) for k, v in _listing(db, slug, version).items()
                if k in ("title", "description") and v]
            for where, text in texts:
                problems += _errors(check_shape_claims(text, cir, twin, where))
                problems += _errors(check_technique_claims(text, cir, twin, where))
    elif check == "gate.policy":
        from ..gates.policy import ListingDraft, check_listing

        lst = _listing(db, slug, version)
        if not lst:
            return {"check": check, "ok": None, "why": "no drafted listing to check"}
        problems += _errors(check_listing(ListingDraft(
            title=lst["title"], description=lst["description"], tags=list(lst["tags"]),
            price_cad=float(lst["price_cad"] or 0)), cir))
    else:
        return {"check": check, "ok": None, "why": f"unknown check {check!r}"}
    return {"check": check, "ok": not problems, "problems": problems[:20]}


def _listing(db, slug: str, version: str) -> dict:
    from sqlalchemy import select

    from ..core.models import Listing

    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == version))
        return ({"title": row.title, "description": row.description, "tags": row.tags or [],
                 "price_cad": row.price_cad} if row is not None else {})


# L-2 (review of a14c9ef): scale readiness reads `Incident.signature LIKE '%policy%'` as an open
# policy risk. A detection-only re-verification incident must not flip that condition, so the
# signature names each check by an alias without the substring "policy".
SIGNATURE_ALIAS = {"cir.twin": "twin", "cir.reverse": "reverse",
                   "gate.asset_truth": "asset-truth", "gate.policy": "listing-rules"}


def signature(check: str, slug: str, version: str) -> str:
    return f"quality.reverify:{SIGNATURE_ALIAS.get(check, check)}:{slug}@{version}"[:200]


def _resolve(db, slug: str, version: str, check: str) -> int:
    """L-4: a later passing re-verification closes the open incident for the same check
    (and the pre-alias signature, so none is left open from before the rename)."""
    from sqlalchemy import select

    from ..core.models import Incident

    sigs = {signature(check, slug, version), f"quality.reverify:{check}:{slug}@{version}"[:200]}
    with db.session() as s:
        rows = list(s.scalars(select(Incident).where(Incident.signature.in_(sigs),
                                                     Incident.resolved == False)))  # noqa: E712
        for row in rows:
            row.resolved = True
            row.detail = {**(row.detail or {}),
                          "resolution": "a later re-verification of the same check passed",
                          "resolved_at": datetime.now(timezone.utc).isoformat()}
        return len(rows)


def _incident(db, slug: str, version: str, check: str, problems: list[str]) -> int | None:
    from sqlalchemy import select

    from ..core.models import Incident

    sig = signature(check, slug, version)
    with db.session() as s:
        row = s.scalar(select(Incident).where(Incident.signature == sig,
                                              Incident.resolved == False))  # noqa: E712
        if row is not None:
            row.report_count = (row.report_count or 1) + 1
            return None
        inc = Incident(severity="P2", product_slug=slug, signature=sig,
                       halts_publication=False,
                       summary=(f"certified {slug}@{version} no longer passes {check} on "
                                f"re-verification: {problems[0] if problems else ''}")[:500],
                       detail={"problems": problems[:20], "check": check,
                               "note": "regression detection only; the certificate is "
                                       "unchanged and nothing was blocked"})
        s.add(inc)
        s.flush()
        return inc.id


def _run_check(ctx: JobContext) -> dict:
    i = dict(ctx.job.inputs or {})
    slug, version, check = i.get("slug"), i.get("version"), ctx.job.job_type
    if not slug or not version:
        return {"ran": False, "why": "needs slug and version of a certified release"}
    try:
        r = reverify(ctx.db, check, slug, version)
    except Exception as exc:  # noqa: BLE001 - L-4: a check that raises is a finding, not silence
        r = {"check": check, "ok": False,
             "problems": [f"re-verification raised {type(exc).__name__}: {str(exc)[:300]}"],
             "raised": True}
    if r["ok"] is None:
        # Recorded as an UNKNOWN reading (never a pass), so freshness can see the check ran.
        ctx.audit(READING, artifact=f"{slug}@{version}",
                  detail={**r, "incident": None, "release_hash": i.get("release_hash", "")})
        return {"ran": False, **r}
    resolved = _resolve(ctx.db, slug, version, check) if r["ok"] else 0
    inc = None if r["ok"] else _incident(ctx.db, slug, version, check, r["problems"])
    # P0-REVERIFY-WITHHOLD (OPUS2-P0): the verdict is also kept on the stored release, which
    # retention never prunes, and publication refuses on it until this check passes again.
    from ..publish import withholding

    held = withholding.record_reverification(
        ctx.db, slug, version, check=check,
        problem=None if r["ok"] else ((r["problems"] or ["failed"])[0]))
    ctx.audit(READING, artifact=f"{slug}@{version}",
              detail={**r, "incident": inc, "resolved": resolved,
                      "withheld_checks": held.get("failed_checks", []),
                      "release_hash": i.get("release_hash", "")})
    return {**r, "slug": slug, "version": version, "incident": inc, "resolved": resolved,
            "certificate_changed": False, "withheld_checks": held.get("failed_checks", []),
            "work_done": 1}


for _jt in CHECKS:
    handlers.register(_jt)(_run_check)


@handlers.register("gate.quality")
def handle_gate_quality(ctx: JobContext) -> dict:
    """Queue the day's re-verification of every certified release under its owning agent."""
    day = datetime.now(timezone.utc).date().isoformat()
    queued = 0
    releases = certified_releases(ctx.db)
    for r in releases:
        key = f"{r['slug']}:{(r['release_hash'] or r['version'])[:16]}:{day}"
        # Literal job types, so the autonomy map sees each wake edge (AST, literals only).
        jobs = (ctx.enqueue("validator", "cir.twin", dict(r),
                            idempotency_key=f"reverify:cir.twin:{key}"),
                ctx.enqueue("validator", "cir.reverse", dict(r),
                            idempotency_key=f"reverify:cir.reverse:{key}"),
                ctx.enqueue("asset_truth", "gate.asset_truth", dict(r),
                            idempotency_key=f"reverify:gate.asset_truth:{key}"),
                ctx.enqueue("policy", "gate.policy", dict(r),
                            idempotency_key=f"reverify:gate.policy:{key}"))
        queued += sum(j is not None for j in jobs)
    unver = unverifiable(ctx.db)
    ctx.audit("quality.reverify_planned", detail={"releases": len(releases), "queued": queued,
                                                  "unverifiable": unver})
    return {"releases": len(releases), "queued": queued, "unverifiable": unver,
            "work_done": queued}


def unverifiable(db, *, days: int = 30) -> list[dict]:
    """Review b199cdb I-1: an UNKNOWN reading counts as "run" for freshness (never as a pass),
    so a check that can never read would otherwise go unreported. Each (release, check) whose
    newest reading is UNKNOWN is listed with how many UNKNOWN readings it has had in `days`."""
    from datetime import timedelta

    from sqlalchemy import select

    from ..core.models import AuditLog

    since = datetime.now(timezone.utc) - timedelta(days=days)
    newest: dict[tuple, dict] = {}
    unknown: dict[tuple, int] = {}
    with db.session() as s:
        for a in s.scalars(select(AuditLog).where(AuditLog.action == READING,
                                                  AuditLog.at >= since)
                           .order_by(AuditLog.id)):
            d = a.detail or {}
            key = (a.artifact, d.get("check"))
            newest[key] = d
            if d.get("ok") is None:
                unknown[key] = unknown.get(key, 0) + 1
    return [{"release": k[0], "check": k[1], "unknown_readings": unknown.get(k, 0),
             "why": (d.get("why") or "")[:200]}
            for k, d in sorted(newest.items(), key=lambda x: (str(x[0][0]), str(x[0][1])))
            if d.get("ok") is None]


FRESH_HOURS = 24


def next_work(db) -> list[dict]:
    """Product Truth's next_work provider (autonomy.generators.PROVIDERS): one internal item
    when any certified release has no re-verification in the last FRESH_HOURS. The COO turns
    it into a `gate.quality` mission, and Laura's idle priorities read the same candidates
    (laura.executive.loop._idle_priorities -> generators.candidates), so neither needs code of
    its own. Deterministic, read-only."""
    from datetime import timedelta

    from sqlalchemy import select

    from ..core.models import AuditLog

    releases = certified_releases(db)
    if not releases:
        return []
    since = datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)
    # L-4: fresh only when ALL four checks have a reading for the release in the window
    # (an UNKNOWN reading counts as having run; it is never counted as a pass).
    seen: dict[str, set] = {}
    with db.session() as s:
        for a, d in s.execute(select(AuditLog.artifact, AuditLog.detail).where(
                AuditLog.action == READING, AuditLog.at >= since)).all():
            seen.setdefault(a, set()).add((d or {}).get("check"))
    stale = [f"{r['slug']}@{r['version']}" for r in releases
             if not set(CHECKS) <= seen.get(f"{r['slug']}@{r['version']}", set())]
    if not stale:
        return []
    return [{"key": f"quality.reverify:{len(stale)}", "kind": "internal",
             "external_effect": False, "job_type": "gate.quality",
             "why": (f"{len(stale)} certified release(s) not re-verified in "
                     f"{FRESH_HOURS} h: {', '.join(stale[:5])}")}]



@handlers.register("visual.model_ledger")
def handle_model_ledger(ctx: JobContext) -> dict:
    """F-744: harvest every model experiment into the durable model evidence ledger
    (visual.model_ledger), so retention never erases a failed approach. Read-only, CA$0."""
    from ..visual import model_ledger

    out = model_ledger.harvest(ctx.db)
    ctx.audit("visual.model_ledger", detail=out)
    return {**out, "work_done": out["harvested"]}


# F-456/F-482: the shared contracts this module was built against. A contract that moves on
# without this module migrating fails here, at import, instead of drifting silently.
from ..core import contracts as _contracts  # noqa: E402

_contracts.require("cir", 1)
