"""The product stage register: one row per product, on the owner's fifteen stages (P0 §6).

The owner's P0 directive (2026-10-27, "Product inventory & production dashboard") names the
stages a product passes through on its way to sale, and what every product must carry:
identity, exact version, source digests, current stage, responsible department, last
successful job, next required action, cost, quality evidence, failure history and the
requirements the owner holds. It also asks that stalled workflows and repeated loops be
detected, and that the dashboard show production output rather than heartbeats.

Three registers already describe a product from different angles -- `products.lifecycle`
(the F-672 state machine), `products.pipeline_board` (the eight certification stages) and
`products.inventory` (blockers and who clears them). None of them answers the owner's
question in the owner's words, and none detects a loop. This module does both, and it does
them the way the other three do: **every stage is derived from rows the pipeline already
writes**, never from a status somebody typed, and a stage nobody has evidence for is not
reached. The derivation is deterministic, reads only this company's own tables, makes no
model or network call and costs CA$0.

What each stage means, and the row that proves it:

    RESEARCH_CANDIDATE          a concept presented to the pre-engineering gate and waiting
                                (`concept.gate_waiting`, `creative.winner_intake` waiting)
    RESEARCH_APPROVED           the gate passed or the winner was carried to engineering
    PATTERN_IN_DEVELOPMENT      a product row or an uncertified pattern version
    TECHNICALLY_VALIDATED       a certified pattern version (deterministic Product Truth)
    INDEPENDENT_REVIEW_PASSED   the re-verification sweep (`gate.quality`, W4-AGENTS batch 1)
                                queued its checks on that release and none opened a
                                disagreement incident
    PREMIUM_PDF_COMPLETED       an `assets.build` job completed for that version with the
                                customer PDF's sha256 in its output
    VISUAL_PACKAGE_COMPLETED    listing assets exist for that version and at least one is
                                approved
    LISTING_PACKAGE_COMPLETED   a listing row exists for that version
    PHYSICAL_TESTING_PENDING    Class B/C, and no passed physical test for that version
    PHYSICAL_TESTING_PASSED     a passed physical test for that version
    OWNER_APPROVAL_PENDING      every gated section of the approval packet passes and no
                                owner publication grant is recorded
    READY_FOR_PUBLICATION       a recorded owner publication grant for slug@version
    PUBLISHED                   a published listing, or one carrying an Etsy listing id
    REVISION_REQUIRED           an open publication-halting incident, or the newest
                                engineering event is a refusal/unrepairable revision
    REJECTED                    a recorded REJECTED/RETIRED lifecycle transition, a retired
                                duplicate alias, or a gate refusal with nothing later

Stalls and loops are measured, not inferred: a stall is a stage older than its allowance
with nothing held by the owner; a loop is the same job type completing on the same product
with no work done (`pipeline.did_no_work`) at least `LOOP_MIN` times in the window, or a
compile/revise cycle that repeated. Each is reported with the rows behind it.

Honest limits. The register reads evidence; it never moves a product, never enqueues work,
never opens an incident and never certifies. PUBLISHED is read from this database's listing
rows, which in Shadow Mode is nothing. "Independent review" here is the company's own
deterministic re-verification sweep; a human or vision review is reported where its rows
exist and is not required for the stage.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

STAGES: tuple[str, ...] = (
    "RESEARCH_CANDIDATE", "RESEARCH_APPROVED", "PATTERN_IN_DEVELOPMENT",
    "TECHNICALLY_VALIDATED", "INDEPENDENT_REVIEW_PASSED", "PREMIUM_PDF_COMPLETED",
    "VISUAL_PACKAGE_COMPLETED", "LISTING_PACKAGE_COMPLETED", "PHYSICAL_TESTING_PENDING",
    "PHYSICAL_TESTING_PASSED", "OWNER_APPROVAL_PENDING", "READY_FOR_PUBLICATION",
    "PUBLISHED", "REVISION_REQUIRED", "REJECTED",
)
# The forward order a product advances along. REVISION_REQUIRED and REJECTED are terminal
# or lateral states, not steps on it.
FORWARD: tuple[str, ...] = STAGES[:13]
TERMINAL = ("PUBLISHED", "REJECTED")

# Who is answerable for a product at each stage: the department whose job moves it on.
DEPARTMENT: dict[str, str] = {
    "RESEARCH_CANDIDATE": "intelligence", "RESEARCH_APPROVED": "product_design",
    "PATTERN_IN_DEVELOPMENT": "product_design", "TECHNICALLY_VALIDATED": "product_truth",
    "INDEPENDENT_REVIEW_PASSED": "visual", "PREMIUM_PDF_COMPLETED": "visual",
    "VISUAL_PACKAGE_COMPLETED": "store_commerce", "LISTING_PACKAGE_COMPLETED": "product_truth",
    "PHYSICAL_TESTING_PENDING": "owner", "PHYSICAL_TESTING_PASSED": "store_commerce",
    "OWNER_APPROVAL_PENDING": "owner", "READY_FOR_PUBLICATION": "store_commerce",
    "PUBLISHED": "growth", "REVISION_REQUIRED": "product_design", "REJECTED": "none",
}

# What has to happen next, per stage. The job named is the one that writes the next
# stage's evidence; an owner line is an owner action, which software never performs.
NEXT_ACTION: dict[str, str] = {
    "RESEARCH_CANDIDATE": "pre-engineering gate judgement (vision judge records "
                          "`concept.judged`; mjs.seasonal_sentinel re-presents it)",
    "RESEARCH_APPROVED": "cir.draft (crochet_engineer)",
    "PATTERN_IN_DEVELOPMENT": "cir.compile then gate.certify (validator, quality_director)",
    "TECHNICALLY_VALIDATED": "gate.quality re-verification sweep (quality_director, daily)",
    "INDEPENDENT_REVIEW_PASSED": "assets.build (publishing): customer PDFs, charts, frames",
    "PREMIUM_PDF_COMPLETED": "assets.build listing images / assets.owned_photography / "
                             "assets.model_photography, then an approved hero",
    "VISUAL_PACKAGE_COMPLETED": "listing.draft then listing.seo (listing)",
    "LISTING_PACKAGE_COMPLETED": "physical test for Class B/C (owner: tester), else the "
                                 "owner approval packet",
    "PHYSICAL_TESTING_PENDING": "owner: a tester works one sample; physical.record",
    "PHYSICAL_TESTING_PASSED": "the approval packet: every gated section must PASS",
    "OWNER_APPROVAL_PENDING": "owner: publication grant (owner session + step-up)",
    "READY_FOR_PUBLICATION": "store.publish (held in SHADOW; LIMITED PRODUCTION phase and "
                             "the first-customer gate required)",
    "PUBLISHED": "commerce.orders_ingest and performance learning",
    "REVISION_REQUIRED": "cir.revise / a new version through cir.draft; resolve the incident",
    "REJECTED": "nothing: the design does not continue under this slug",
}

# How long a product may sit at a stage before it is a stall, when nobody but the company
# holds it. These are this module's own allowances: no requirement row gives figures.
STALL_DAYS: dict[str, int] = {
    "RESEARCH_CANDIDATE": 14, "RESEARCH_APPROVED": 3, "PATTERN_IN_DEVELOPMENT": 3,
    "TECHNICALLY_VALIDATED": 3, "INDEPENDENT_REVIEW_PASSED": 3,
    "PREMIUM_PDF_COMPLETED": 7, "VISUAL_PACKAGE_COMPLETED": 3,
    "LISTING_PACKAGE_COMPLETED": 7, "PHYSICAL_TESTING_PASSED": 7,
    "READY_FOR_PUBLICATION": 14, "REVISION_REQUIRED": 7,
}
OWNER_HELD_STAGES = ("PHYSICAL_TESTING_PENDING", "OWNER_APPROVAL_PENDING")

LOOP_WINDOW_DAYS = 14
LOOP_MIN = 3          # the same no-op completing this often on one product is a loop
JOB_SCAN_LIMIT = 20000
READING_KIND = "products.stage_register"
AUDIT_ACTION = "products.stage_register"
UNMEASURED = "UNMEASURED"

# Audit actions that mean the product's newest engineering event went wrong.
_REFUSAL_ACTIONS = ("cir.draft_refused", "cir.revise_unrepairable", "gate.release_withheld",
                    "gate.halted", "gate.lane_release_refused")
_PROGRESS_ACTIONS = ("cir.drafted", "cir.compiled", "cir.revised", "gate.certified",
                     "gate.recertified", "assets.built", "listing.drafted",
                     "listing.seo_drafted")


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)


def _iso(v):
    v = _aware(v)
    return v.isoformat() if v else None


def _slug_of_job(job) -> str | None:
    """The product a job names, read from its inputs the way lifecycle.after_job does."""
    i = job.inputs or {}
    for key in ("slug", "product_slug"):
        if isinstance(i.get(key), str) and i[key]:
            return i[key]
    cir = i.get("cir")
    if isinstance(cir, dict) and isinstance(cir.get("slug"), str):
        return cir["slug"]
    return None


def _version_of_job(job) -> str | None:
    i = job.inputs or {}
    if isinstance(i.get("version"), str):
        return i["version"]
    cir = i.get("cir")
    if isinstance(cir, dict) and isinstance(cir.get("version"), str):
        return cir["version"]
    return None


def _artifact_slug(artifact: str | None) -> str | None:
    if not artifact:
        return None
    return artifact.split("@", 1)[0]


def cir_digest(cir_json: dict | None) -> str | None:
    if not cir_json:
        return None
    return hashlib.sha256(json.dumps(cir_json, sort_keys=True, default=str).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Reads


def _read(db, *, now: datetime) -> dict:
    """Every row the register needs, read once, grouped by product slug."""
    from sqlalchemy import select

    from ..core.models import (AuditLog, CostEntry, Incident, Job, JobStatus, Listing,
                               ListingAsset, OwnerAction, PatternVersion, PhysicalTest,
                               Product)
    from ..creative import intake, preengineering
    from ..ops import publication_authority as pa

    gate_actions = tuple(f"{preengineering.GATE_ACTION}_{d}" for d in
                         (preengineering.PASSED, preengineering.REFUSED,
                          preengineering.WAITING))
    actions = (gate_actions + (intake.INTAKE_ACTION, pa.APPROVED, "gate.quality",
                               "cir.compiled") + _REFUSAL_ACTIONS + _PROGRESS_ACTIONS)
    window_start = now - timedelta(days=LOOP_WINDOW_DAYS)
    out: dict = {"products": {}, "versions": {}, "listings": {}, "assets": {},
                 "tests": {}, "cost": {}, "incidents": {}, "owner_actions": [],
                 "audits": {}, "jobs": {}, "window_jobs": {}}
    with db.session() as s:
        for p in s.scalars(select(Product)):
            out["products"][p.slug] = {"id": p.id, "title": p.title, "status": p.status,
                                       "risk_class": p.risk_class,
                                       "created_at": _aware(p.created_at)}
        by_id = {v["id"]: slug for slug, v in out["products"].items()}
        for pv in s.scalars(select(PatternVersion).order_by(PatternVersion.id)):
            slug = by_id.get(pv.product_id)
            if slug is None:
                continue
            out["versions"].setdefault(slug, []).append({
                "version": pv.version, "certified": bool(pv.certified),
                "release_hash": pv.release_hash or "", "created_at": _aware(pv.created_at),
                "cir_digest": cir_digest(pv.cir_json),
                "certificate_findings": len((pv.certificate or {}).get("findings") or []),
                "granted": (pv.certificate or {}).get("granted") is True})
        for l in s.scalars(select(Listing).order_by(Listing.id)):
            out["listings"].setdefault(l.product_slug, []).append({
                "version": l.version, "state": l.state, "seo_score": l.seo_score,
                "etsy_listing_id": l.etsy_listing_id or "", "release_hash": l.release_hash,
                "created_at": _aware(l.created_at), "id": l.id})
        for a in s.scalars(select(ListingAsset).order_by(ListingAsset.id)):
            out["assets"].setdefault(a.product_slug, []).append({
                "version": a.version, "role": a.role, "approved": bool(a.approved),
                "blocked": list(a.blocked_reasons or []), "created_at": _aware(a.created_at)})
        for t in s.scalars(select(PhysicalTest).order_by(PhysicalTest.id)):
            out["tests"].setdefault(t.product_slug, []).append({
                "version": t.version, "passed": t.passed, "tester": t.tester_ref,
                "requested_at": _aware(t.requested_at), "completed_at": _aware(t.completed_at)})
        for slug, total in s.execute(
                select(CostEntry.product_slug, __import__("sqlalchemy").func.sum(
                    CostEntry.amount_cad)).where(CostEntry.product_slug != "")
                .group_by(CostEntry.product_slug)):
            out["cost"][slug] = round(float(total or 0.0), 4)
        for inc in s.scalars(select(Incident).where(Incident.resolved.is_(False))):
            if inc.product_slug:
                out["incidents"].setdefault(inc.product_slug, []).append({
                    "id": inc.id, "severity": inc.severity, "signature": inc.signature,
                    "halts_publication": bool(inc.halts_publication), "at": _aware(inc.at),
                    "summary": (inc.summary or "")[:200]})
        for oa in s.scalars(select(OwnerAction).where(OwnerAction.done.is_(False))):
            out["owner_actions"].append({
                "id": oa.id, "requirement_key": oa.requirement_key or "",
                "action": (oa.action or "")[:200], "blocks": (oa.blocks or "")[:200],
                "state": oa.state, "at": _aware(oa.at)})
        for row in s.execute(select(AuditLog.id, AuditLog.at, AuditLog.action,
                                    AuditLog.artifact, AuditLog.detail, AuditLog.actor)
                             .where(AuditLog.action.in_(actions)).order_by(AuditLog.id)):
            rid, at, action, artifact, detail, actor = row
            slug = _artifact_slug(artifact)
            if slug is None:
                continue
            out["audits"].setdefault(slug, []).append({
                "id": rid, "at": _aware(at), "action": action, "artifact": artifact,
                "actor": actor, "detail": detail if isinstance(detail, dict) else {}})
        jobs = list(s.scalars(select(Job).order_by(Job.id.desc()).limit(JOB_SCAN_LIMIT)))
        for j in jobs:
            slug = _slug_of_job(j)
            if slug is None:
                continue
            rec = {"id": j.id, "job_type": j.job_type, "agent": j.agent,
                   "status": j.status.value if hasattr(j.status, "value") else str(j.status),
                   "version": _version_of_job(j), "finished_at": _aware(j.finished_at),
                   "created_at": _aware(j.created_at), "attempts": j.attempts,
                   "last_error": (j.last_error or "")[:200], "outputs": j.outputs or {},
                   "cost_cad": float(j.cost_cad or 0.0)}
            out["jobs"].setdefault(slug, []).append(rec)
            fin = rec["finished_at"] or rec["created_at"]
            if fin is not None and fin >= window_start:
                out["window_jobs"].setdefault(slug, []).append(rec)
        out["job_status"] = {"done": JobStatus.DONE.value, "dead": JobStatus.DEAD.value,
                             "failed": JobStatus.FAILED.value}
    return out


# ---------------------------------------------------------------------------
# Derivation


def _newest(rows: list[dict], key: str = "at"):
    return max((r for r in rows if r.get(key) is not None), key=lambda r: r[key], default=None)


def _lifecycle_record(db, slug: str) -> dict | None:
    from ..autonomy import memory
    from ..products import lifecycle

    rec = memory.get(db, lifecycle.KEY + slug)
    return (rec or {}).get("body") if rec else None


def derive(db, slug: str, *, data: dict | None = None, now: datetime | None = None) -> dict:
    """One product's register row. `data` is `_read`'s result when deriving many."""
    now = _aware(now) or datetime.now(timezone.utc)
    data = data if data is not None else _read(db, now=now)
    from ..products import launch0

    product = data["products"].get(slug)
    versions = data["versions"].get(slug, [])
    listings = data["listings"].get(slug, [])
    assets = data["assets"].get(slug, [])
    tests = data["tests"].get(slug, [])
    incidents = data["incidents"].get(slug, [])
    audits = data["audits"].get(slug, [])
    jobs = data["jobs"].get(slug, [])
    done = data["job_status"]["done"]

    newest_version = versions[-1] if versions else None
    certified = [v for v in versions if v["certified"]]
    current = certified[-1] if certified else newest_version
    version = current["version"] if current else None
    release = current["release_hash"] if current else ""

    def for_version(rows):
        return [r for r in rows if version is not None and r.get("version") == version]

    evidence: dict[str, dict] = {}

    def reached(stage: str, when, **why):
        evidence[stage] = {"at": _iso(when), **why}

    # Research: the pre-engineering gate and the winner intake.
    gate_rows = [a for a in audits if a["action"].startswith("concept.gate_")
                 or a["action"] == "creative.winner_intake"]
    gate_newest = _newest(gate_rows)
    if gate_newest is not None:
        decision = gate_newest["action"].rsplit("_", 1)[-1] \
            if gate_newest["action"].startswith("concept.gate_") \
            else str(gate_newest["detail"].get("decision") or "")
        if decision in ("passed", "engineering", "exempt"):
            reached("RESEARCH_APPROVED", gate_newest["at"], row=gate_newest["id"],
                    decision=decision)
        elif decision in ("waiting",):
            reached("RESEARCH_CANDIDATE", gate_newest["at"], row=gate_newest["id"],
                    waiting_on=list(gate_newest["detail"].get("waiting_on") or []))
        elif decision in ("refused",):
            reached("RESEARCH_CANDIDATE", gate_newest["at"], row=gate_newest["id"],
                    decision=decision)
    if product is not None:
        reached("PATTERN_IN_DEVELOPMENT", product["created_at"], product_row=product["id"])
    if certified:
        reached("TECHNICALLY_VALIDATED", current["created_at"], version=version,
                release_hash=release, certificate_findings=current["certificate_findings"])
        # Independent re-verification: a gate.quality run that queued checks for this
        # release, and no open disagreement incident on this product.
        quality_runs = [j for j in jobs if j["job_type"] == "gate.quality"
                        and j["status"] == done and j["finished_at"] is not None
                        and j["finished_at"] >= current["created_at"]]
        checks = [j for j in jobs if j["job_type"] in ("cir.twin", "cir.reverse",
                                                       "gate.asset_truth", "gate.policy")
                  and j["status"] == done and j.get("version") == version]
        disagreement = [i for i in incidents if "regression" in i["signature"]
                        or "disagree" in i["signature"]]
        if checks and not disagreement:
            reached("INDEPENDENT_REVIEW_PASSED", max(c["finished_at"] for c in checks),
                    checks=sorted({c["job_type"] for c in checks}),
                    sweeps=[j["id"] for j in quality_runs][-3:])
        builds = [j for j in jobs if j["job_type"] == "assets.build" and j["status"] == done
                  and j.get("version") == version and (j["outputs"] or {}).get("pdf_sha256")]
        if builds:
            b = max(builds, key=lambda j: j["id"])
            reached("PREMIUM_PDF_COMPLETED", b["finished_at"], job=b["id"],
                    pdf_sha256=b["outputs"].get("pdf_sha256"),
                    pdf_sha256_by_terminology=b["outputs"].get("pdf_sha256_by_terminology"),
                    pages=b["outputs"].get("pages"))
        v_assets = for_version(assets)
        approved = [a for a in v_assets if a["approved"]]
        if approved:
            reached("VISUAL_PACKAGE_COMPLETED", max(a["created_at"] for a in approved),
                    assets=len(v_assets), approved=len(approved),
                    blocked=sum(1 for a in v_assets if a["blocked"]),
                    roles=sorted({a["role"] for a in approved}))
        v_listings = for_version(listings)
        if v_listings:
            l = v_listings[-1]
            reached("LISTING_PACKAGE_COMPLETED", l["created_at"], listing=l["id"],
                    state=l["state"], seo_score=l["seo_score"])
        risk = (product or {}).get("risk_class") or "A"
        passed_tests = [t for t in for_version(tests) if t["passed"] is True]
        if passed_tests:
            reached("PHYSICAL_TESTING_PASSED",
                    max(t["completed_at"] or t["requested_at"] for t in passed_tests),
                    tests=len(passed_tests))
        elif risk in ("B", "C") and "LISTING_PACKAGE_COMPLETED" in evidence:
            reached("PHYSICAL_TESTING_PENDING",
                    evidence["LISTING_PACKAGE_COMPLETED"]["at"] and
                    datetime.fromisoformat(evidence["LISTING_PACKAGE_COMPLETED"]["at"]),
                    risk_class=risk, requested=len(for_version(tests)))
        grants = [a for a in audits if a["action"] == "owner.publication.approved"
                  and a["artifact"] == f"{slug}@{version}"]
        packet = None
        if "LISTING_PACKAGE_COMPLETED" in evidence and release:
            from ..ops import publication_authority as pa

            try:
                packet = pa.evidence(db, slug, version, release)["summary"]
            except Exception as exc:  # noqa: BLE001 - the packet is evidence, never a crash
                packet = {"all_gated_sections_pass": False, "error": f"{type(exc).__name__}"}
            if packet.get("all_gated_sections_pass") and not grants:
                reached("OWNER_APPROVAL_PENDING", now, packet="all gated sections PASS")
        if grants:
            g = _newest(grants)
            reached("READY_FOR_PUBLICATION", g["at"], grant_row=g["id"])
        published = [l for l in v_listings if l["state"] == "published" or l["etsy_listing_id"]]
        if published:
            reached("PUBLISHED", published[-1]["created_at"], listing=published[-1]["id"],
                    etsy_listing_id=published[-1]["etsy_listing_id"] or None)

    # Lateral states.
    rec = _lifecycle_record(db, slug)
    retired = launch0.LEGACY_DUPLICATES.get(slug)
    rejected_why = None
    if retired is not None:
        rejected_why = f"retired duplicate alias: {retired.get('why', '')[:160]}"
    elif rec and rec.get("stage") in ("REJECTED", "RETIRED"):
        rejected_why = f"lifecycle {rec['stage']}: {str(rec.get('why', ''))[:160]}"
    elif (gate_newest is not None and not product
          and (gate_newest["action"].endswith("_refused")
               or gate_newest["detail"].get("decision") == "refused")):
        rejected_why = "pre-engineering gate refused; returned to ideation"
    halting = [i for i in incidents if i["halts_publication"]]
    eng_events = [a for a in audits if a["action"] in _REFUSAL_ACTIONS + _PROGRESS_ACTIONS]
    eng_newest = _newest(eng_events)
    revision_why = None
    if halting:
        revision_why = (f"open publication-halting incident {halting[0]['id']} "
                        f"({halting[0]['signature']})")
    elif eng_newest is not None and eng_newest["action"] in _REFUSAL_ACTIONS and product:
        revision_why = f"newest engineering event is {eng_newest['action']}"

    furthest = max((s for s in FORWARD if s in evidence), key=FORWARD.index, default=None)
    if rejected_why:
        stage, why = "REJECTED", rejected_why
    elif furthest == "PUBLISHED":
        stage, why = "PUBLISHED", "a published listing"
    elif revision_why:
        stage, why = "REVISION_REQUIRED", revision_why
    elif furthest is not None:
        stage, why = furthest, f"evidence: {evidence[furthest]}"
    else:
        stage, why = "RESEARCH_CANDIDATE", "known slug with no evidence past research"
        if not gate_rows:
            why = "no row at all: the slug is known only to the catalogue or a caller"

    stage_at = (evidence.get(stage) or {}).get("at")
    if stage == "REVISION_REQUIRED":
        stage_at = _iso(halting[0]["at"] if halting else eng_newest["at"])
    if stage == "REJECTED":
        stage_at = None
    age_days = ((now - datetime.fromisoformat(stage_at)).total_seconds() / 86400.0
                if stage_at else None)

    # Owner-held requirements: open owner actions naming this product, physical tests,
    # the publication grant.
    owner_held = [{"owner_action": oa["id"], "requirement_key": oa["requirement_key"],
                   "action": oa["action"]}
                  for oa in data["owner_actions"]
                  if slug in oa["requirement_key"] or slug in oa["action"]
                  or slug in oa["blocks"]]
    if stage == "PHYSICAL_TESTING_PENDING":
        owner_held.append({"requirement": "physical test", "version": version,
                           "why": f"Class {(product or {}).get('risk_class')} needs a worked "
                                  f"sample before publication"})
    if stage == "OWNER_APPROVAL_PENDING":
        owner_held.append({"requirement": "publication grant", "version": version})

    done_jobs = [j for j in jobs if j["status"] == done and j["finished_at"] is not None]
    last_ok = max(done_jobs, key=lambda j: j["finished_at"], default=None)
    failed = sorted((j for j in jobs if j["status"] in (data["job_status"]["dead"],
                                                         data["job_status"]["failed"])),
                    key=lambda j: j["id"], reverse=True)
    refusals = [a for a in audits if a["action"] in _REFUSAL_ACTIONS]

    stalled = (stage in STALL_DAYS and age_days is not None
               and age_days > STALL_DAYS[stage]
               and not any("owner_action" in h for h in owner_held))
    loops = detect_loops(data["window_jobs"].get(slug, []), done=done)

    quality = {
        "certified": bool(certified), "version": version, "release_hash": release or None,
        "certificate_findings": current["certificate_findings"] if current else None,
        "certificate_granted": current["granted"] if current else None,
        "independent_review": evidence.get("INDEPENDENT_REVIEW_PASSED"),
        "approved_assets": evidence.get("VISUAL_PACKAGE_COMPLETED", {}).get("approved"),
        "physical_tests": {"requested": len(for_version(tests)),
                           "passed": sum(1 for t in for_version(tests) if t["passed"] is True),
                           "failed": sum(1 for t in for_version(tests) if t["passed"] is False)},
        "open_incidents": [{"id": i["id"], "severity": i["severity"],
                            "signature": i["signature"]} for i in incidents],
    }
    return {
        "slug": slug,
        "title": (product or {}).get("title"),
        "version": version,
        "source_digests": {
            "cir_sha256": current["cir_digest"] if current else None,
            "release_hash": release or None,
            "pdf_sha256": evidence.get("PREMIUM_PDF_COMPLETED", {}).get("pdf_sha256"),
            "pdf_sha256_by_terminology": evidence.get("PREMIUM_PDF_COMPLETED", {}).get(
                "pdf_sha256_by_terminology"),
        },
        "stage": stage,
        "stage_index": STAGES.index(stage),
        "stage_since": stage_at,
        "stage_age_days": round(age_days, 2) if age_days is not None else None,
        "why": str(why)[:400],
        "department": DEPARTMENT[stage],
        "last_successful_job": ({"id": last_ok["id"], "job_type": last_ok["job_type"],
                                 "finished_at": _iso(last_ok["finished_at"])}
                                if last_ok else None),
        "next_required_action": NEXT_ACTION[stage],
        "cost_cad": data["cost"].get(slug, 0.0),
        "cost_basis": ("cost_entries.product_slug" if slug in data["cost"]
                       else "no cost entry names this product"),
        "quality_evidence": quality,
        "failure_history": {
            "dead_or_failed_jobs": [{"id": j["id"], "job_type": j["job_type"],
                                     "status": j["status"], "error": j["last_error"]}
                                    for j in failed[:10]],
            "refusals": [{"row": a["id"], "action": a["action"], "at": _iso(a["at"])}
                         for a in refusals[-10:]],
            "counts": {"dead_or_failed_jobs": len(failed), "refusals": len(refusals)},
        },
        "owner_held": owner_held,
        "stalled": bool(stalled),
        "stall": ({"allowance_days": STALL_DAYS[stage], "age_days": round(age_days, 2)}
                  if stalled else None),
        "loops": loops,
        "evidence": evidence,
    }


def detect_loops(window_jobs: list[dict], *, done: str = "done") -> list[dict]:
    """Repeated no-op completions and compile/revise cycles on one product, in the window."""
    from ..runtime.pipeline import did_no_work

    out: list[dict] = []
    by_type: dict[str, list[dict]] = {}
    for j in window_jobs:
        if j["status"] == done:
            by_type.setdefault(j["job_type"], []).append(j)
    for jt, rows in sorted(by_type.items()):
        noops = [j for j in rows if did_no_work(j["outputs"] or {}, jt)]
        if len(noops) >= LOOP_MIN:
            out.append({"kind": "repeated_no_op", "job_type": jt, "count": len(noops),
                        "window_days": LOOP_WINDOW_DAYS,
                        "jobs": [j["id"] for j in sorted(noops, key=lambda x: x["id"])][-5:],
                        "why": f"{jt} completed {len(noops)} times with no work done; the "
                               f"cadence re-asks a question whose answer has not changed"})
    revisions = [j for j in window_jobs if j["job_type"] == "cir.revise"
                 and j["status"] == done]
    if len(revisions) >= 2:
        out.append({"kind": "compile_revise_cycle", "job_type": "cir.revise",
                    "count": len(revisions),
                    "jobs": [j["id"] for j in revisions][-5:],
                    "why": "the engineer revised the same product more than once in the "
                           "window; the revision rule is not converging"})
    return out


def known_slugs(db, data: dict | None = None, *, now: datetime | None = None) -> list[str]:
    """Every slug with a row: products, listings, assets, tests, audits and jobs."""
    data = data if data is not None else _read(db, now=_aware(now) or datetime.now(timezone.utc))
    slugs: set[str] = set()
    for key in ("products", "versions", "listings", "assets", "tests", "audits", "jobs"):
        slugs |= set(data[key])
    return sorted(s for s in slugs if s)


def register(db, *, now: datetime | None = None, slugs=None) -> dict:
    """The whole register: every known product on its stage, with counts, stalls and loops."""
    now = _aware(now) or datetime.now(timezone.utc)
    data = _read(db, now=now)
    chosen = sorted(set(slugs)) if slugs else known_slugs(db, data)
    rows = [derive(db, slug, data=data, now=now) for slug in chosen]
    counts = {s: 0 for s in STAGES}
    for r in rows:
        counts[r["stage"]] += 1
    stalled = [r["slug"] for r in rows if r["stalled"]]
    looping = [{"slug": r["slug"], "loops": r["loops"]} for r in rows if r["loops"]]
    # Production output, not heartbeats: what moved forward and what was produced.
    produced = {
        "certified_versions": sum(1 for r in rows if r["quality_evidence"]["certified"]),
        "customer_pdfs": sum(1 for r in rows if r["source_digests"]["pdf_sha256"]),
        "visual_packages": sum(1 for r in rows
                               if "VISUAL_PACKAGE_COMPLETED" in r["evidence"]),
        "listing_packages": sum(1 for r in rows
                                if "LISTING_PACKAGE_COMPLETED" in r["evidence"]),
        "published": counts["PUBLISHED"],
    }
    return {"as_of": now.isoformat(), "stages": list(STAGES), "products": len(rows),
            "counts": counts, "stalled": stalled, "looping": looping,
            "produced": produced, "owner_held": sum(1 for r in rows if r["owner_held"]),
            "rows": rows}


def summary(reg: dict, *, keep_rows: int = 200) -> dict:
    """The durable reading: everything but the per-row evidence, rows capped."""
    rows = []
    for r in reg["rows"][:keep_rows]:
        rows.append({k: r[k] for k in ("slug", "version", "stage", "stage_since",
                                       "stage_age_days", "department", "next_required_action",
                                       "cost_cad", "stalled", "loops", "owner_held",
                                       "last_successful_job")})
    return {k: reg[k] for k in ("as_of", "stages", "products", "counts", "stalled", "looping",
                                "produced", "owner_held")} | {"rows": rows}


def record(db, reg: dict, *, period_key: str | None = None) -> dict:
    """Write today's reading once (unique on kind + period). Returns what was written."""
    from sqlalchemy import select

    from ..core.models import OperatingReading

    period_key = period_key or reg["as_of"][:10]
    payload = summary(reg)
    with db.session() as s:
        existing = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == READING_KIND, OperatingReading.period_key == period_key))
        if existing is None:
            s.add(OperatingReading(kind=READING_KIND, period_key=period_key, payload=payload))
            created = True
        else:
            existing.payload = payload
            created = False
    return {"kind": READING_KIND, "period_key": period_key, "created": created,
            "products": reg["products"]}


def latest(db) -> dict | None:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == READING_KIND)
                       .order_by(OperatingReading.id.desc()).limit(1))
        return dict(row.payload) if row is not None else None
