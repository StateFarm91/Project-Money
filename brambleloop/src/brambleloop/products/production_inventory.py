"""W5-INVENTORY: the exact product inventory, one state per product/version, derived from rows.

The owner asked for an inventory he can trust: every product the company is making, at exactly
one of fifteen states, with the evidence for it. There is no status column here and nothing is
written: each state is computed, on every read, from the records the release chain already
keeps --

* `jobs`                -- `radar.score`, `research.*`, `cir.draft/revise/compile`, `gate.*`,
                           `cir.twin/reverse`, `chain.rebuild`, `listing.draft`, `assets.build`,
                           `visual.*`, `pricing.position`, `listing.seo`, `launch.plan`, `store.*`;
* `PatternVersion`      -- the certified release (`certified`, `release_hash`, `certificate`,
                           including `physical_test_required` and the withholding record);
* `AuditLog`            -- `assets.built` (PDF hashes, read through
                           `runtime.pipeline._certified_pdf_hashes`, the reader `store.publish`
                           uses), `assets.listing_images_built/blocked`, `listing.seo_drafted/
                           blocked`, `quality.reverified`, `store.release_gates`,
                           `listing.parity`;
* `Listing`, `DraftIntent`, `PhysicalTest`, `OwnerVeto` (`intel.mission_runtime.active_veto`),
  `OwnerAction` and publication authority (`ops.publication_authority.resolve`).

**Ready for publication is never re-implemented.** It requires, all at once:
  1. the product gates `store.publish` enforces -- `publish.release_gates.for_publish` and the
     #75 creative parity verdict -- read either as the verdict `store.publish` itself recorded
     (`store.release_gates` / `listing.parity` audit rows, mode `recorded`, read-only, and only
     when newer than the product's last change) or computed now by the same functions (mode
     `live`: `for_publish(read_only=True)` and `publication_authority._parity`);
  2. any required physical sample passed;
  3. no unreconciled remote draft intent;
  4. the effective phase permits publication (`core.phase.effective`, the phase
     `store.publish` re-resolves), and
  5. a valid sealed owner publication grant for this exact release
     (`ops.publication_authority.resolve`, which also applies the global kill-switch).
An unreadable or stale gate is UNKNOWN and UNKNOWN is never a pass.

**Three tiers (owner clarification 2026-10-27).** *Internal* -- development, validation,
independent review, premium PDF, visuals and the listing package -- is never blocked by a
missing sample photo. *Private Etsy draft* needs the product gates, the phase and the owner's
draft grant (`tiers.private_draft`). *Public publication* needs all of that plus the physical
sample where the certificate requires one (`tiers.public`). The physical sample is therefore an
attribute (`physical_sample.status`) beside the furthest internal state; "Physical sample
pending/passed" are tallied from it, and a product awaiting its sample is never "Ready for
publication" nor "Owner approval pending".

`derive(db)` is the whole inventory; `production_summary(db)` is the private-data-free
projection for the readback endpoint (counts only).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

# ---- the fifteen states, in pipeline order ---------------------------------------------------

RESEARCH_CANDIDATE = "research_candidate"
RESEARCH_APPROVED = "research_approved"
PATTERN_IN_DEVELOPMENT = "pattern_in_development"
PATTERN_VALIDATED = "pattern_technically_validated"
REVIEW_PASSED = "independent_review_passed"
PDF_COMPLETED = "premium_pdf_completed"
VISUAL_COMPLETED = "visual_package_completed"
LISTING_COMPLETED = "listing_package_completed"
PHYSICAL_PENDING = "physical_sample_pending"
PHYSICAL_PASSED = "physical_sample_passed"
OWNER_APPROVAL_PENDING = "owner_approval_pending"
READY = "ready_for_publication"
PUBLISHED = "published"
REVISION_REQUIRED = "revision_required"
REJECTED = "rejected"

STATES: tuple[tuple[str, str], ...] = (
    (RESEARCH_CANDIDATE, "Research candidate"),
    (RESEARCH_APPROVED, "Research approved"),
    (PATTERN_IN_DEVELOPMENT, "Pattern in development"),
    (PATTERN_VALIDATED, "Pattern technically validated"),
    (REVIEW_PASSED, "Independent review passed"),
    (PDF_COMPLETED, "Premium PDF completed"),
    (VISUAL_COMPLETED, "Visual package completed"),
    (LISTING_COMPLETED, "Listing package completed"),
    (PHYSICAL_PENDING, "Physical sample pending"),
    (PHYSICAL_PASSED, "Physical sample passed"),
    (OWNER_APPROVAL_PENDING, "Owner approval pending"),
    (READY, "Ready for publication"),
    (PUBLISHED, "Published"),
    (REVISION_REQUIRED, "Revision required"),
    (REJECTED, "Rejected"),
)
STATE_KEYS = tuple(k for k, _ in STATES)
# Owner clarification (2026-10-27): the physical sample is an ATTRIBUTE beside the furthest
# internal state, never a step internal work passes through. These two labels are therefore
# never a row's `state`; they are tallied from `physical_sample.status` (`physical_counts`)
# and shown beside the state counts. Every other key is a primary state, one per row.
ATTRIBUTE_STATES = (PHYSICAL_PENDING, PHYSICAL_PASSED)
PRIMARY_STATES = tuple(k for k in STATE_KEYS if k not in ATTRIBUTE_STATES)
PHYSICAL_STATUSES = ("not_required", "pending", "passed", "failed", "unknown")
LABEL = dict(STATES)
RANK = {k: i for i, k in enumerate(STATE_KEYS)}

# Listing states that mean a customer can buy it. `published_manually` is the W-ADOPT state
# (an owner-made Etsy listing linked to its certified release, `publish.manual_adoption`).
PUBLISHED_LISTING_STATES = ("published", "active", "published_manually")
# Remote draft-creation intents that are not settled (`publish.draft_intent`).
UNSETTLED_INTENTS = ("CREATING", "RECONCILE_REQUIRED")

# HELD reasons (flow health and the CC view read these).
HOLD_OWNER, HOLD_PHYSICAL, HOLD_PAID, HOLD_POLICY = "owner", "physical", "paid_approval", "policy"
HOLD_KINDS = (HOLD_OWNER, HOLD_PHYSICAL, HOLD_PAID, HOLD_POLICY)

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
GATE_MODES = ("recorded", "live")

# ---- stage map: every product job type -> the stage it works on -------------------------------

STAGE_OF_JOB: dict[str, str] = {
    "radar.scan": "research", "radar.score": "research",
    "cir.draft": "development", "cir.revise": "development", "cir.reengineer": "development",
    "cir.compile": "validation",
    "gate.certify": "independent_review", "cir.twin": "independent_review",
    "cir.reverse": "independent_review", "gate.asset_truth": "independent_review",
    "gate.policy": "independent_review", "gate.lanes": "independent_review",
    "gate.quality": "independent_review",
    "chain.rebuild": "rebuild",
    "listing.draft": "pdf", "assets.build": "pdf",
    "pricing.position": "listing", "listing.seo": "listing", "launch.plan": "listing",
    "marketing.schedule": "listing", "listing.taxonomy_refresh": "listing",
    "physical.record": "physical", "physical.photo": "physical",
    "assets.physical_upgrade": "physical",
}
STAGE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("research.", "research"), ("visual.", "visual"), ("store.", "publication"),
    ("gate.", "independent_review"), ("assets.", "visual"), ("listing.", "listing"),
    ("physical.", "physical"), ("cir.", "development"),
)
# What `derive` loads from `jobs`: the exact types above plus every type under these prefixes.
JOB_PREFIXES = ("radar.score", "research.", "cir.", "gate.", "chain.rebuild", "listing.",
                "assets.", "visual.", "pricing.position", "launch.plan", "store.", "physical.",
                "marketing.schedule")

AUDIT_ACTIONS = ("assets.built", "assets.listing_images_built", "assets.listing_images_blocked",
                 "listing.seo_drafted", "listing.seo_blocked", "quality.reverified",
                 "store.release_gates", "listing.parity", "pricing.refused",
                 "launch.held")
# Retention (ported idea from FABLE-P0): every action above has a decision in
# `ops.retention.KNOWN_READ_ACTIONS`. The ones a state is derived from are lifetime_total
# (pruning would move a product to an earlier state). `quality.reverified` and
# `listing.parity` are windowed: their readers take the newest row, rewritten daily / on every
# publish attempt, and a pruned parity verdict reads UNKNOWN, which is never Ready.
# `pricing.refused` is `latest`: it only annotates a hold, never sets a state.


def stage_of(job_type: str) -> str:
    if job_type in STAGE_OF_JOB:
        return STAGE_OF_JOB[job_type]
    for prefix, stage in STAGE_PREFIXES:
        if job_type.startswith(prefix):
            return stage
    return "other"


# ---- helpers -----------------------------------------------------------------------------------

def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)


def _iso(v) -> str | None:
    v = _aware(v)
    return v.isoformat() if v else None


def _status(job) -> str:
    st = job.status
    return getattr(st, "value", str(st))


# Inputs that differ between two enqueues of the same work (job_watch's set, plus the chain's
# rebuild token and date pin): they do not make the work different.
VOLATILE_INPUT_KEYS = frozenset({"cadence", "request_id", "enqueued_at", "at", "tick", "rebuild",
                                 "as_of", "retry_for_commit"})


def input_digest(inputs) -> str:
    data = {k: v for k, v in (inputs or {}).items() if k not in VOLATILE_INPUT_KEYS}
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:16]


def output_digest(outputs) -> str:
    return hashlib.sha256(json.dumps(outputs or {}, sort_keys=True,
                                     default=str).encode()).hexdigest()[:16]


def job_identity(inputs, outputs) -> tuple[str | None, str | None, str]:
    """(slug, version, release) a chain job works on, from its own inputs/outputs."""
    i = inputs if isinstance(inputs, dict) else {}
    o = outputs if isinstance(outputs, dict) else {}
    slug, version = i.get("slug"), i.get("version")
    cir = i.get("cir")
    if not slug and isinstance(cir, dict):
        slug, version = cir.get("slug"), cir.get("version")
    if not slug:
        art = o.get("artifact") or o.get("slug")
        if isinstance(art, str) and art:
            slug, _, ver = art.partition("@")
            version = version or (ver or None)
    if slug and not version and isinstance(o.get("artifact"), str) and "@" in o["artifact"]:
        a_slug, _, a_ver = o["artifact"].partition("@")
        if a_slug == slug:
            version = a_ver or None
    release = str(i.get("release") or i.get("release_hash") or o.get("release_hash") or "")
    return (str(slug) if slug else None, str(version) if version else None, release)


class _Job:
    """A detached, plain copy of the job columns the inventory reads."""

    __slots__ = ("id", "agent", "job_type", "status", "inputs", "outputs", "created_at",
                 "started_at", "finished_at", "run_after", "cost_cad", "last_error", "attempts",
                 "slug", "version", "release")

    def __init__(self, row):
        self.id = row.id
        self.agent = row.agent
        self.job_type = row.job_type
        self.status = _status(row)
        self.inputs = row.inputs or {}
        self.outputs = row.outputs or {}
        self.created_at = _aware(row.created_at)
        self.started_at = _aware(row.started_at)
        self.finished_at = _aware(row.finished_at)
        self.run_after = _aware(row.run_after)
        self.cost_cad = float(row.cost_cad or 0.0)
        self.last_error = row.last_error or ""
        self.attempts = row.attempts or 0
        self.slug, self.version, self.release = job_identity(self.inputs, self.outputs)


class _Audit:
    __slots__ = ("id", "at", "action", "artifact", "job_id", "detail")

    def __init__(self, row):
        self.id = row.id
        self.at = _aware(row.at)
        self.action = row.action
        self.artifact = row.artifact or ""
        self.job_id = row.job_id
        self.detail = row.detail or {}


def load_records(db) -> dict:
    """Every row the inventory reads, detached, in one pass. Read-only."""
    from sqlalchemy import or_, select

    from ..core.models import (AuditLog, CostEntry, Job, Listing, OwnerAction, PatternVersion,
                               PhysicalTest, Product)

    with db.session() as s:
        products = {p.id: (p.slug, p.title) for p in s.scalars(select(Product))}
        versions = []
        for pv in s.scalars(select(PatternVersion).order_by(PatternVersion.id)):
            slug = products.get(pv.product_id, (None,))[0]
            if slug:
                versions.append({"id": pv.id, "slug": slug, "version": pv.version,
                                 "certified": bool(pv.certified),
                                 "release_hash": pv.release_hash or "",
                                 "certificate": dict(pv.certificate or {}),
                                 "created_at": _aware(pv.created_at)})
        listings = {(r.product_slug, r.version): {
            "id": r.id, "state": r.state or "", "release_hash": r.release_hash or "",
            "seo_score": r.seo_score, "price_cad": r.price_cad,
            "etsy_listing_id": r.etsy_listing_id or "", "created_at": _aware(r.created_at)}
            for r in s.scalars(select(Listing))}
        tests: dict[tuple, list] = {}
        for t in s.scalars(select(PhysicalTest).order_by(PhysicalTest.id)):
            tests.setdefault((t.product_slug, t.version), []).append({
                "id": t.id, "passed": t.passed, "requested_at": _iso(t.requested_at),
                "completed_at": _iso(t.completed_at)})
        conds = [Job.job_type.like(p + "%") for p in JOB_PREFIXES]
        jobs = [_Job(j) for j in s.scalars(select(Job).where(or_(*conds)).order_by(Job.id))]
        audits = [_Audit(a) for a in s.scalars(
            select(AuditLog).where(AuditLog.action.in_(AUDIT_ACTIONS)).order_by(AuditLog.id))]
        costs = [(c.id, c.product_slug or "", c.job_id, float(c.amount_cad or 0.0))
                 for c in s.scalars(select(CostEntry))]
        owner_open = [{"id": a.id, "text": " ".join([a.requirement_key or "", a.action or "",
                                                      a.blocks or ""]),
                       "max_cost": a.max_cost_known, "action": (a.action or "")[:160]}
                      for a in s.scalars(select(OwnerAction).where(
                          OwnerAction.done == False))]  # noqa: E712
    intents = {}
    try:
        from ..publish.draft_intent import DraftIntent

        with db.session() as s:
            intents = {(d.slug, d.version): {"state": d.state, "release": d.release,
                                             "at": _iso(d.at)}
                       for d in s.scalars(select(DraftIntent))}
    except Exception:  # noqa: BLE001 - a table not yet created holds no intent
        intents = {}
    return {"products": products, "versions": versions, "listings": listings, "tests": tests,
            "jobs": jobs, "audits": audits, "costs": costs, "owner_open": owner_open,
            "intents": intents}


def _version_key(v: str | None):
    parts = []
    for p in str(v or "").split("."):
        parts.append((0, int(p)) if p.isdigit() else (1, p))
    return parts


def rows_from(rec: dict) -> list[dict]:
    """The product/version rows: every version on record, and one row for a slug with none."""
    slugs: dict[str, set] = {}
    titles = {slug: title for slug, title in rec["products"].values()}
    order: dict[tuple, int] = {}
    for pv in rec["versions"]:
        slugs.setdefault(pv["slug"], set()).add(pv["version"])
        order[(pv["slug"], pv["version"])] = pv["id"]
    for slug, version in rec["listings"]:
        slugs.setdefault(slug, set()).add(version)
    for slug, version in rec["tests"]:
        slugs.setdefault(slug, set()).add(version)
    for j in rec["jobs"]:
        if j.slug:
            slugs.setdefault(j.slug, set())
            if j.version:
                slugs[j.slug].add(j.version)
    for slug, _t in rec["products"].values():
        slugs.setdefault(slug, set())
    out = []
    for slug in sorted(slugs):
        vers = sorted(slugs[slug], key=lambda v: (order.get((slug, v), 0), _version_key(v)))
        if not vers:
            vers = [None]
        for v in vers:
            out.append({"slug": slug, "version": v, "head": v == vers[-1],
                        "title": titles.get(slug)})
    return out


def _jobs_for(rec: dict, slug: str, version: str | None, head: bool) -> list:
    """A row's jobs: its own versioned jobs, and (head row only) its slug's unversioned ones."""
    return [j for j in rec["jobs"] if j.slug == slug
            and (j.version == version or (head and j.version is None))]


def _latest(jobs, job_type: str, *, statuses=("done",)):
    found = [j for j in jobs if j.job_type == job_type and j.status in statuses]
    return max(found, key=lambda j: j.id) if found else None


def _audits_for(rec: dict, slug: str, version: str | None, actions) -> list:
    art = f"{slug}@{version}" if version else slug
    return [a for a in rec["audits"] if a.action in actions and a.artifact == art]


# ---- gate readers (the only places publication's gates are consulted) -------------------------

def _recorded_product_gates(rec: dict, slug: str, version: str, changed_at) -> dict:
    """The verdict store.publish itself recorded: `store.release_gates` (the output of
    `release_gates.for_publish`) and `listing.parity` (`_listing_parity`), both newer than the
    product's last change. Anything missing or older is UNKNOWN."""
    gates = [a for a in rec["audits"] if a.action == "store.release_gates"
             and a.artifact == slug and a.detail.get("version") == version]
    # CHAIN FINDING: `listing.parity` is audited under the slug alone with no version in its
    # detail, so it is bound to a version here through the store.publish job that wrote it.
    # A parity row with no job, or a job for another version, is not this version's verdict.
    publish_versions = {j.id: j.version for j in rec["jobs"] if j.job_type == "store.publish"}
    parity = [a for a in rec["audits"] if a.action == "listing.parity" and a.artifact == slug
              and a.job_id is not None and publish_versions.get(a.job_id) == version]
    g = max(gates, key=lambda a: a.id) if gates else None
    p = max(parity, key=lambda a: a.id) if parity else None
    out = {"mode": "recorded", "release_gates_audit": g.id if g else None,
           "parity_audit": p.id if p else None, "checked_at": _iso(g.at) if g else None}
    if g is None or p is None:
        missing = [n for n, a in (("release gates", g), ("creative parity", p)) if a is None]
        return {**out, "state": UNKNOWN, "reasons": [
            f"not yet evaluated by store.publish: no recorded {' or '.join(missing)} verdict"]}
    stale = [n for n, a in (("release gates", g), ("creative parity", p))
             if changed_at is not None and a.at is not None and a.at < changed_at]
    if stale:
        return {**out, "state": UNKNOWN, "reasons": [
            f"the recorded {' and '.join(stale)} verdict predates this product's last change "
            f"({_iso(changed_at)}); re-evaluation required"]}
    reasons = [str(r)[:300] for r in (g.detail.get("reasons") or [])]
    if g.detail.get("blocks_release") is not False:
        reasons = reasons or ["release gates blocked with no reason recorded"]
    if p.detail.get("blocks_release") is not False:
        reasons.append(f"creative parity (#75): {str(p.detail.get('why') or p.detail.get('verdict') or 'blocks')[:300]}")
    return {**out, "state": FAIL if reasons else PASS, "reasons": reasons}


def _live_product_gates(db, slug: str, version: str) -> dict:
    """The same gate functions, computed now: `for_publish(read_only=True)` -- exactly the call
    store.publish's `_release_gates` makes -- and the read-only #75 parity assessment."""
    from ..ops import publication_authority
    from ..publish import release_gates

    reasons: list[str] = []
    try:
        from ..visual.experiment import refuse_if_experiment

        refuse_if_experiment(db, slug, version, action="store.publish")
    except Exception as exc:  # noqa: BLE001 - an experiment refusal is a closed gate
        reasons.append(f"experiment: {str(exc)[:300]}")
    try:
        verdict = release_gates.for_publish(db, slug=slug, version=version, read_only=True,
                                            positioning=_positioning(db, slug, version))
        if verdict.get("blocks_release") is not False:
            reasons.extend(str(r)[:300] for r in (verdict.get("reasons") or
                                                  ["release gates blocked"]))
    except Exception as exc:  # noqa: BLE001 - a crashed gate is a closed gate
        reasons.append(f"release gates could not be evaluated: {type(exc).__name__}")
    try:
        parity = publication_authority._parity(db, slug, version)
        if parity.get("state") != publication_authority.PASS:
            reasons.append(f"creative parity (#75): {str(parity.get('why'))[:300]}")
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"creative parity could not be evaluated: {type(exc).__name__}")
    return {"mode": "live", "state": FAIL if reasons else PASS, "reasons": reasons,
            "checked_at": datetime.now(timezone.utc).isoformat()}


def _positioning(db, slug: str, version: str) -> str | None:
    from ..products.inventory import _positioning as positioning

    return positioning(db, slug, version)


def _phase_refusal(db) -> str | None:
    """Why the effective phase forbids publication now (store.publish re-resolves it)."""
    from ..core import phase as phase_mod
    from ..integrations.etsy import PHASES_THAT_MAY_PUBLISH

    live = phase_mod.effective(db, record_incident=False)
    if live not in PHASES_THAT_MAY_PUBLISH:
        return f"effective phase is {live!r}; publication needs one of {list(PHASES_THAT_MAY_PUBLISH)}"
    return None


def _grant_refusal(db, slug: str, version: str, release: str) -> str | None:
    """Why there is no valid sealed owner publication grant for this release (fails closed)."""
    from ..ops import publication_authority

    refusal, _grant = publication_authority.resolve(db, slug=slug, version=version,
                                                    release=release)
    return refusal


def owner_gates(db, slug: str, version: str, release: str) -> dict:
    reasons = []
    for name, fn in (("phase", lambda: _phase_refusal(db)),
                     ("publication_grant", lambda: _grant_refusal(db, slug, version, release))):
        try:
            why = fn()
        except Exception as exc:  # noqa: BLE001 - unreadable authority is a closed gate
            why = f"could not be read: {type(exc).__name__}"
        if why:
            reasons.append(f"{name}: {str(why)[:300]}")
    return {"state": FAIL if reasons else PASS, "reasons": reasons}


# ---- derivation --------------------------------------------------------------------------------

def _hold(kind: str, why: str, **evidence) -> dict:
    return {"kind": kind, "why": str(why)[:300], **({"evidence": evidence} if evidence else {})}


def _cost(rec: dict, slug: str, job_ids: set) -> float:
    seen, total = set(), 0.0
    for cid, pslug, jid, amount in rec["costs"]:
        if (pslug == slug or (jid is not None and jid in job_ids)) and cid not in seen:
            seen.add(cid)
            total += amount
    return round(total, 4)


def physical_status(pv: dict | None, tests: list) -> dict:
    """The physical-sample ATTRIBUTE: not_required | pending | passed | failed | unknown.

    `unknown` before certification (the certificate is what says whether a sample is
    required). It is recorded beside the state; only the public tier waits on it."""
    passed = [t for t in tests if t["passed"] is True]
    completed = [t for t in tests if t["passed"] is not None]
    required = bool(pv and (pv.get("certificate") or {}).get("physical_test_required"))
    base = {"required": required if pv and pv.get("certified") else None,
            "tests": len(tests)}
    if passed:
        return {**base, "status": "passed", "test_id": passed[-1]["id"]}
    if completed and completed[-1]["passed"] is False:
        return {**base, "status": "failed", "test_id": completed[-1]["id"]}
    if not (pv and pv.get("certified")):
        return {**base, "status": "unknown"}
    return {**base, "status": "pending" if required else "not_required"}


def derive_row(db, rec: dict, row: dict, *, gate_mode: str = "recorded") -> dict:
    """One product/version's single state, with its evidence. Read-only in `recorded` mode."""
    slug, version, head = row["slug"], row["version"], row["head"]
    jobs = _jobs_for(rec, slug, version, head)
    pv = next((p for p in reversed(rec["versions"]) if p["slug"] == slug
               and p["version"] == version), None)
    listing = rec["listings"].get((slug, version)) if version else None
    tests = rec["tests"].get((slug, version), []) if version else []
    intent = rec["intents"].get((slug, version)) if version else None
    release = (pv or {}).get("release_hash") or ""
    stages: list[dict] = []
    holds: list[dict] = []
    scores: dict[str, Any] = {}
    physical = physical_status(pv, tests)
    tiers: dict[str, dict] = {
        "internal": {"complete": False},
        "private_draft": {"ready": False, "reasons": ["internal package not complete"]},
        "public": {"ready": False, "reasons": ["internal package not complete"]}}

    def reach(stage: str, **ev):
        stages.append({"stage": stage, **{k: v for k, v in ev.items() if v not in (None, [], {})}})

    def result(state: str, why: str, **extra) -> dict:
        job_ids = {j.id for j in jobs}
        return {"slug": slug, "version": version, "head": head, "title": row.get("title"),
                "state": state, "label": LABEL[state], "why": str(why)[:400],
                "release_hash": release or None, "holds": holds,
                "physical_sample": physical, "tiers": tiers,
                "evidence": {"stages": stages, "job_ids": sorted(job_ids)[-25:],
                             "cost_to_date_cad": _cost(rec, slug, job_ids),
                             "quality_scores": scores, **extra}}

    # Published: a listing a customer can buy (incl. W-ADOPT's `published_manually`).
    if listing and listing["state"] in PUBLISHED_LISTING_STATES:
        reach("published", listing_id=listing["id"], listing_state=listing["state"],
              draft_intent=(intent or {}).get("state"))
        return result(PUBLISHED, f"listing state {listing['state']!r}")

    # Owner decision: an active veto rejects the product (#228), whatever else exists.
    try:
        from ..intel.mission_runtime import active_veto

        veto = active_veto(db, slug)
    except Exception:  # noqa: BLE001
        veto = {"vetoed": False}
    if veto.get("vetoed"):
        reach("owner_veto", ruling_id=veto.get("ruling_id"))
        return result(REJECTED, veto.get("why") or "owner veto")

    # Research.
    score = _latest(jobs, "radar.score")
    if score is not None:
        scores["radar_score"] = score.outputs.get("score")
        reach("research_candidate", job_ids=[score.id], input_digest=input_digest(score.inputs))
    elif any(j.job_type == "radar.score" for j in jobs):
        reach("research_candidate", job_ids=[j.id for j in jobs if j.job_type == "radar.score"])
    drafts = [j for j in jobs if j.job_type in ("cir.draft", "cir.revise", "cir.reengineer")]
    compiles = [j for j in jobs if j.job_type == "cir.compile"]
    has_build = bool(drafts or compiles or pv or listing)
    approved = bool((score is not None and score.outputs.get("promoted") is True) or has_build)
    if not approved:
        if score is not None and score.outputs.get("promoted") is False:
            gate = score.outputs.get("gate") or {}
            if gate.get("decision") == "waiting":
                holds.append(_hold(HOLD_POLICY, "pre-engineering gate waiting on: "
                                   + ", ".join(gate.get("waiting_on") or ["a judgement"])))
                return result(RESEARCH_CANDIDATE, "pre-engineering gate waiting")
            why = (gate.get("reasons") or [None])[0] or score.outputs.get("reason") or (
                f"score {score.outputs.get('score')} did not clear the promotion bar")
            return result(REJECTED, f"research: {why}")
        return result(RESEARCH_CANDIDATE, "scored for research; not yet promoted"
                      if score is None and stages else "on record; no research verdict yet")
    reach("research_approved", job_ids=[score.id] if score is not None else [])

    # Development.
    retired = [d for d in drafts if d.status == "done" and d.outputs.get("retired_alias")]
    if retired and not pv and not compiles:
        return result(REJECTED, "retired concept alias routed to "
                      + ", ".join(retired[-1].outputs.get("routed_to") or []))
    if not (drafts or compiles or pv):
        return result(RESEARCH_APPROVED, "promoted; no pattern draft queued yet")
    reach("pattern_in_development", job_ids=[d.id for d in drafts][-5:])

    # Technical validation (the deterministic compiler).
    comp = _latest(compiles, "cir.compile")
    certified = bool(pv and pv["certified"] and release)
    if comp is not None and comp.outputs.get("compiled") is False and not certified:
        revise = [j for j in jobs if j.job_type == "cir.revise" and j.id > comp.id]
        return result(REVISION_REQUIRED, "compile failed: "
                      + "; ".join(str(e)[:120] for e in (comp.outputs.get("errors") or [])[:3]),
                      failed_stage="validation", job_id=comp.id,
                      revise_job=revise[-1].id if revise else comp.outputs.get("revise_job"))
    if comp is None and not certified:
        return result(PATTERN_IN_DEVELOPMENT, "CIR drafted; not yet compiled")
    reach("pattern_technically_validated",
          job_ids=[comp.id] if comp is not None else [],
          input_digest=input_digest(comp.inputs) if comp is not None else None)

    # Independent review: certification (independent reverse compile US+UK, twin, gates) and
    # the post-certification re-verifications of the same release.
    certify = _latest(jobs, "gate.certify")
    if not certified:
        if certify is not None and certify.outputs.get("granted") is False:
            if certify.outputs.get("halted_by_incident"):
                holds.append(_hold(HOLD_POLICY, "certification halted by an open P0/P1 incident",
                                   job_id=certify.id))
                return result(PATTERN_VALIDATED, "certification halted by an open incident")
            return result(REVISION_REQUIRED, "certification refused: " + "; ".join(
                str(r)[:120] for r in (certify.outputs.get("reasons") or [])[:3]),
                failed_stage="independent_review", job_id=certify.id)
        return result(PATTERN_VALIDATED, "compiled; certification not yet granted")
    cert = pv["certificate"]
    reverified = {}
    for a in _audits_for(rec, slug, version, ("quality.reverified",)):
        if a.detail.get("check") in ("cir.twin", "cir.reverse") and (
                not a.detail.get("release_hash") or a.detail.get("release_hash") == release):
            reverified[a.detail["check"]] = a
    failing = {c: a for c, a in reverified.items() if a.detail.get("ok") is False}
    if failing:
        return result(REVISION_REQUIRED, "independent re-verification failed: " + ", ".join(
            sorted(failing)), failed_stage="independent_review",
            audit_ids=[a.id for a in failing.values()])
    from ..publish import withholding

    try:
        held = withholding.reasons(db, slug, version)
    except Exception:  # noqa: BLE001
        held = {"blocks_build": False, "reasons": {}}
    if held.get("blocks_build"):
        return result(REVISION_REQUIRED, "release withheld: " + "; ".join(
            str(v.get("reason"))[:160] for v in held["reasons"].values()),
            failed_stage="independent_review")
    reach("independent_review_passed", job_ids=[certify.id] if certify is not None else [],
          digests={"release_hash": release, "content_hash": cert.get("content_hash")},
          reverified={c: a.detail.get("ok") for c, a in reverified.items()})

    # Premium PDF: the per-terminology hashes assets.build recorded for THIS release.
    from ..runtime.pipeline import _certified_pdf_hashes

    pdfs = _certified_pdf_hashes(db, slug, version, release)
    builds = [j for j in jobs if j.job_type == "assets.build" and j.release in ("", release)]
    if not pdfs:
        return result(REVIEW_PASSED, "certified; no PDF built for this release yet")
    reach("premium_pdf_completed", job_ids=[b.id for b in builds][-3:], digests={"pdf": pdfs})

    # Visual package: the deterministic listing image set assets.build verified.
    vis = [a for a in _audits_for(rec, slug, version, ("assets.listing_images_built",
                                                      "assets.listing_images_blocked"))
           if not builds or a.job_id is None or a.job_id in {b.id for b in builds}]
    latest_vis = max(vis, key=lambda a: a.id) if vis else None
    if latest_vis is None:
        return result(PDF_COMPLETED, "PDF built; listing images not yet verified")
    if latest_vis.action == "assets.listing_images_blocked":
        return result(REVISION_REQUIRED, "listing images blocked: " + "; ".join(
            str(b)[:120] for b in (latest_vis.detail.get("blocking") or [])[:3]),
            failed_stage="visual", audit_id=latest_vis.id)
    reach("visual_package_completed", audit_id=latest_vis.id,
          frames=latest_vis.detail.get("frames"))

    # Listing package: copy and SEO drafted and bound to this release.
    seo = [a for a in _audits_for(rec, slug, version, ("listing.seo_drafted",
                                                      "listing.seo_blocked"))]
    latest_seo = max(seo, key=lambda a: a.id) if seo else None
    if latest_seo is not None and latest_seo.action == "listing.seo_blocked":
        return result(REVISION_REQUIRED, "listing blocked: " + "; ".join(
            str(b)[:120] for b in (latest_seo.detail.get("blocking") or [])[:3]),
            failed_stage="listing", audit_id=latest_seo.id)
    if listing is not None and listing["state"] == "withdrawn":
        return result(REVISION_REQUIRED, "listing withdrawn by a failed re-certification",
                      failed_stage="listing")
    if latest_seo is None or listing is None or listing["release_hash"] != release:
        priced = [a for a in rec["audits"] if a.action == "pricing.refused" and a.artifact == slug
                  and a.id > latest_vis.id]
        if priced:
            holds.append(_hold(HOLD_POLICY, "pricing refused", audit_id=priced[-1].id))
        return result(VISUAL_COMPLETED, "visuals verified; no listing bound to this release yet")
    scores.update({"seo_score": listing.get("seo_score"),
                   "search_share": latest_seo.detail.get("search_share")})
    seo_job = _latest(jobs, "listing.seo")
    reach("listing_package_completed", listing_id=listing["id"], audit_id=latest_seo.id,
          job_ids=[seo_job.id] if seo_job else [])
    state, why = LISTING_COMPLETED, "listing package complete"
    tiers["internal"] = {"complete": True, "furthest": LISTING_COMPLETED}
    plan = _latest(jobs, "launch.plan")
    if plan is not None and plan.outputs.get("held"):
        holds.append(_hold(HOLD_POLICY, "launch held: " + str(
            (plan.outputs.get("window_decision") or {}).get("why") or "seasonal window"),
            job_id=plan.id))

    # The internal tier ends here: everything above is reachable with no sample photo.
    # Physical sample (owner clarification 2026-10-27): an ATTRIBUTE recorded beside the
    # furthest internal state, never a step internal work passes through. It gates only the
    # public tier. A sample that was made and FAILED is different from one not yet made: it
    # shows the pattern does not make what it claims, which is a revision.
    if physical["status"] == "failed":
        return result(REVISION_REQUIRED, "physical sample failed",
                      failed_stage="physical", physical_test_id=physical.get("test_id"))
    if physical["status"] == "pending":
        holds.append(_hold(HOLD_PHYSICAL, "the certificate requires a physical sample "
                           "before public publication", tests_requested=len(tests)))

    # Private Etsy draft tier: the product gates (the same functions store.publish uses),
    # a settled remote draft intent, the phase and the owner's draft grant. No sample needed.
    changed = [j.finished_at for j in jobs if j.status == "done" and j.finished_at
               and not j.job_type.startswith(("store.", "marketing."))]
    changed_at = max(changed) if changed else None
    gates = (_live_product_gates(db, slug, version) if gate_mode == "live"
             else _recorded_product_gates(rec, slug, version, changed_at))
    if intent is not None and intent.get("state") in UNSETTLED_INTENTS:
        gates = {**gates, "state": FAIL, "reasons": list(gates.get("reasons") or []) + [
            f"remote draft intent {intent['state']}: reconcile before any publication"]}
    owner = (owner_gates(db, slug, version, release) if gates["state"] == PASS
             else {"state": UNKNOWN, "reasons": ["not read: product gates are not passing"]})
    tiers["private_draft"] = {
        "ready": gates["state"] == PASS and owner["state"] == PASS,
        "reasons": (list(gates["reasons"]) + list(owner["reasons"]))[:8]}
    # Public tier: everything the private draft needs, plus the physical sample.
    public_reasons = list(tiers["private_draft"]["reasons"])
    if physical["status"] == "pending":
        public_reasons.insert(0, "physical sample required and not yet passed")
    tiers["public"] = {"ready": tiers["private_draft"]["ready"] and physical["status"] in (
        "passed", "not_required"), "reasons": public_reasons[:8]}

    if gates["state"] != PASS:
        holds.append(_hold(HOLD_POLICY, "; ".join(gates["reasons"][:3]) or "publication gates",
                           gate_state=gates["state"]))
        return result(state, why, product_gates=gates)
    if physical["status"] == "pending":
        # Never Ready, never Owner approval pending while the sample is outstanding: the
        # furthest internal state stands, with the physical hold beside it.
        return result(state, "listing package complete; public publication waits on the "
                      "physical sample", product_gates=gates, owner_gates=owner)
    if owner["state"] != PASS:
        holds.append(_hold(HOLD_OWNER, "; ".join(owner["reasons"][:2])))
        return result(OWNER_APPROVAL_PENDING, "every product gate passes; owner authority "
                      "is not in place", product_gates=gates, owner_gates=owner)
    reach("ready_for_publication", gate_mode=gates["mode"])
    return result(READY, "every required gate passes", product_gates=gates, owner_gates=owner)


def _paid_holds(rec: dict, item: dict) -> None:
    """An open owner action that names this product and carries a cost is a paid approval."""
    for a in rec["owner_open"]:
        if item["slug"] in a["text"] and (a["max_cost"] is None or a["max_cost"] > 0):
            item["holds"].append(_hold(HOLD_PAID, a["action"], owner_action_id=a["id"],
                                       max_cost_cad=a["max_cost"]))


def derive(db, *, gate_mode: str = "recorded", records: dict | None = None) -> dict:
    """The whole inventory: every product/version, exactly one state each, counted."""
    if gate_mode not in GATE_MODES:
        raise ValueError(f"gate_mode must be one of {GATE_MODES}")
    rec = records if records is not None else load_records(db)
    items = []
    for row in rows_from(rec):
        try:
            item = derive_row(db, rec, row, gate_mode=gate_mode)
        except Exception as exc:  # noqa: BLE001 - one unreadable product never hides the rest
            item = {"slug": row["slug"], "version": row["version"], "head": row["head"],
                    "title": row.get("title"), "state": REVISION_REQUIRED,
                    "label": LABEL[REVISION_REQUIRED],
                    "why": f"state could not be derived: {type(exc).__name__}: {str(exc)[:200]}",
                    "holds": [], "physical_sample": {"status": "unknown"},
                    "tiers": {"internal": {"complete": False},
                              "private_draft": {"ready": False, "reasons": ["underivable"]},
                              "public": {"ready": False, "reasons": ["underivable"]}},
                    "evidence": {"stages": [], "job_ids": [],
                                              "derivation_error": True}}
        _paid_holds(rec, item)
        items.append(item)
    counts = {k: 0 for k in PRIMARY_STATES}
    physical = {k: 0 for k in PHYSICAL_STATUSES}
    for it in items:
        counts[it["state"]] += 1
        physical[(it.get("physical_sample") or {}).get("status", "unknown")] += 1
    return {"as_of": datetime.now(timezone.utc).isoformat(), "gate_mode": gate_mode,
            "states": [{"key": k, "label": l, "kind": ("attribute" if k in ATTRIBUTE_STATES
                                                       else "state")} for k, l in STATES],
            "counts": counts, "physical_counts": physical,
            "attribute_counts": {PHYSICAL_PENDING: physical["pending"],
                                 PHYSICAL_PASSED: physical["passed"]},
            "public_ready": sum(1 for it in items if it["tiers"]["public"]["ready"]),
            "private_draft_ready": sum(1 for it in items
                                       if it["tiers"]["private_draft"]["ready"]),
            "total": len(items), "items": items}


def production_summary(db, *, now: datetime | None = None) -> dict:
    """The readback projection: counts only -- no slug, title, cost, error text or customer.

    Plugs into W-READBACK's `ops.production_evidence.SECTIONS` as
    `SECTIONS["production_inventory"] = production_summary` (same `(db, *, now)` signature,
    same `readable` convention: an unreadable inventory raises and `_section` reports it as
    unreadable, never as a pass)."""
    from ..ops import flow_health

    now = _aware(now) or datetime.now(timezone.utc)
    rec = load_records(db)
    inv = derive(db, records=rec)
    flow = flow_health.flow(db, inventory=inv, records=rec, now=now)
    activity = flow_health.useful_split(db, now=now)
    held: dict[str, int] = {k: 0 for k in HOLD_KINDS}
    for it in inv["items"]:
        for kind in {h["kind"] for h in it["holds"]}:
            held[kind] = held.get(kind, 0) + 1
    return {"readable": True, "as_of": now.isoformat(), "gate_mode": inv["gate_mode"],
            "products": inv["total"], "by_state": dict(inv["counts"]),
            "physical_sample": dict(inv["physical_counts"]),
            "ready_for_publication": inv["counts"][READY],
            "private_draft_ready": inv["private_draft_ready"],
            "stalled": flow["stalled_count"], "looping": flow["looping_count"],
            "held_by_reason": held,
            "useful_vs_noop": {w: {"useful": activity[w]["useful"],
                                   "no_op": activity[w]["no_op"]} for w in activity}}
