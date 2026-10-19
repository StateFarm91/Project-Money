"""Autonomous listing-image production: an event-driven, resumable workflow (W-OWNERIMG).

The owner redirected on 2026-10-19: autonomous production is the primary architecture, and
an owner upload is only an optional fallback. Both paths share one set of gates
(`visual.candidate_gates.evaluate`), and no criterion differs by method.

**Engine.** There is no new engine. Each stage is one execution of the job type
`visual.image_production` on the durable `JobQueue`, run by the `publishing` agent. That
gives the stage the agent's permission, its CA$2.00/day ceiling and the queue's lease,
retry, dead-letter and checkpoint semantics. The workflow works like this:

* A stage stores its inputs, outputs, evidence and cost on the run row
  (`image_records.ImageProductionRun`).
* It then enqueues the next stage with the idempotency key
  `imgprod:<slug>@<version>@<release>:<stage>[:<round>]`. A duplicate event therefore
  becomes a deduplicated job, never a second gallery.
* **Trigger:** the `assets.build` handler calls `trigger` once its certified release has
  produced a usable disclosed render set.

**Stages** (see `STAGES`):

1. retrieve the certified release and its PDF hash;
2. prepare references (generator interface);
3. generate the product-only candidate;
4. gate on fidelity;
5. load Laura's references;
6. reserve an outfit;
7. generate the lifestyle candidate;
8. generate the remaining shot-plan roles;
9. run the independent checks;
10. bounded repair;
11. assemble the gallery;
12. make the owner approval card.

**Generators.** W-FLUXAPI owns the provider adapter, multi-reference transmission, the
deterministic pattern-reference generator and the stage generation functions, with their
receipts and costs. This module calls them only through the `Generator` interface. Until
that branch registers one, `resolve_generator` returns None and a run stops at
`blocked(no image generator is wired)`. That is a status, not a notification. Tests inject a
stub.

**Budget.** The bounds are:

* `MAX_ATTEMPTS_PER_ROLE`, `MAX_GENERATION_CALLS` and `MAX_REPAIR_ROUNDS`;
* a per-gallery `visual.spend_plan` whose `guard` runs before every call;
* the `image_generation` gate, which must be open before any paid generator is called.

The adapter's own `gateway.images.reserve_render` (W-FLUXAPI) still applies on top.
Nothing loops: every repeat is a new, counted, idempotency-keyed job.

**Notifications.** There are two triggers, and nothing else notifies:

* `ready_for_owner_review`;
* `blocked` after the permitted attempts.

`notification_candidates` feeds the existing deduplicated owner-notification refresh
(`app.command_center.notifications.candidates`).

**Learning.** Every candidate row records its outcome, its failure categories, cost and
latency. `learning_summary` reports cost per accepted image, which is undefined (None) when
nothing has been accepted. Brief changes are adopted only as promoted `improve.league`
prompt versions (`PROMPT_KEY`). Nothing here relaxes a gate.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Protocol

from . import candidate_gates as CG
from . import outfits
from . import shot_plans as SP

JOB_TYPE = "visual.image_production"
AGENT = "publishing"
PROMPT_KEY = "image_production:briefs"

# (stage, Command Center state while it runs)
STAGES: tuple[tuple[str, str], ...] = (
    ("retrieve_release", "reference_preparation"),
    ("prepare_references", "reference_preparation"),
    ("product_generation", "product_generation"),
    ("fidelity_gate", "product_generation"),
    ("load_laura_references", "lifestyle_generation"),
    ("reserve_outfit", "lifestyle_generation"),
    ("lifestyle_generation", "lifestyle_generation"),
    ("remaining_roles", "lifestyle_generation"),
    ("verification", "automated_verification"),
    ("repair", "automated_verification"),
    ("gallery_assembly", "gallery_assembly"),
    ("owner_card", "ready_for_owner_review"),
)
STAGE_STATE = dict(STAGES)
STATES = ("awaiting_certified_pattern", "reference_preparation", "product_generation",
          "lifestyle_generation", "gallery_assembly", "automated_verification",
          "ready_for_owner_review", "blocked", "approved_for_publication")
NOTIFY_STATES = ("ready_for_owner_review", "blocked")

MAX_ATTEMPTS_PER_ROLE = 3          # one generation + two repairs
MAX_REPAIR_ROUNDS = 2
MAX_GENERATION_CALLS = 12          # per gallery, every role and repair included
MAX_SPEND_CAD_PER_GALLERY = 2.00   # = the publishing agent's daily ceiling; never raised here
ANCHOR_ROLE = "product_anchor"     # the product-only candidate: a fidelity anchor, not a frame


class Generator(Protocol):
    """What W-FLUXAPI's stage functions provide. `paid` providers need the gate open."""

    name: str
    paid: bool

    def prepare_references(self, *, slug: str, version: str, release: str,
                           cir_fingerprint: str | None) -> list[dict]:
        """[{"kind": one of candidate_gates.REFERENCE_KINDS, "data": bytes}]"""

    def generate(self, *, stage: str, role: str, brief: str, references: list[dict],
                 outfit: dict | None, attempt: int) -> dict:
        """{"data": bytes, "provider", "model", "prompt", "cost_cad", "latency_s",
        "identity_evidence" (optional; the conditioning receipt / judge readings)}"""


_GENERATORS: dict[str, object] = {}


def register_generator(name: str, factory) -> None:
    """W-FLUXAPI registers its stage functions here; nothing is registered in this branch."""
    _GENERATORS[name] = factory


def resolve_generator(db):
    for _name, factory in sorted(_GENERATORS.items()):
        return factory(db)
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_key(slug: str, version: str, release: str) -> str:
    return f"imgprod:{slug}@{version}@{release}"


def stage_key(slug: str, version: str, release: str, stage: str, round_: int = 0) -> str:
    return run_key(slug, version, release) + f":{stage}" + (f":{round_}" if round_ else "")


def prompt_version(db) -> str:
    try:
        from ..improve.league import incumbent_payload

        inc = incumbent_payload(db, kind="prompt", key=PROMPT_KEY)
        if inc:
            return f"league:{inc['config_id']}:{inc['version']}"
    except Exception:  # noqa: BLE001 - an unreadable registry falls back to the code default
        pass
    blob = json.dumps(SP.LIFESTYLE_BRIEF, sort_keys=True).encode()
    return f"code-default:{hashlib.sha256(blob).hexdigest()[:12]}"


# ---- trigger -----------------------------------------------------------------------------

def trigger(enqueue, *, slug: str, version: str, release: str) -> dict:
    """Enqueue the workflow once per slug@version@release. `enqueue(inputs, key)` returns
    None on a duplicate key (JobContext.enqueue semantics)."""
    if not (slug and version and release):
        return {"enqueued": False, "why": "slug, version and release are all required"}
    job = enqueue({"slug": slug, "version": version, "release": release,
                   "stage": STAGES[0][0], "round": 0},
                  stage_key(slug, version, release, STAGES[0][0]))
    return {"enqueued": job is not None, "run_key": run_key(slug, version, release)}


# ---- run row -----------------------------------------------------------------------------

def _run(s, key: str):
    from sqlalchemy import select

    from .image_records import ImageProductionRun

    return s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))


def _ensure_run(db, slug, version, release):
    from .image_records import ImageProductionRun, ensure_tables

    ensure_tables(db)
    key = run_key(slug, version, release)
    with db.session() as s:
        if _run(s, key) is None:
            s.add(ImageProductionRun(run_key=key, slug=slug, version=version, release=release,
                                     listing=outfits.listing_of(slug), stages={}))
    return key


def _update(db, key: str, *, stage: str, status: str | None = None, record: dict | None = None,
            blocked: str = "", exhausted: bool = False, **fields) -> dict:
    from sqlalchemy.orm.attributes import flag_modified

    with db.session() as s:
        r = _run(s, key)
        r.stage = stage
        if record is not None:
            st = dict(r.stages or {})
            st[stage] = {**record, "at": _now().isoformat()}
            r.stages = st
            flag_modified(r, "stages")
        if blocked:
            r.status, r.blocked_reason, r.attempts_exhausted = "blocked", blocked[:2000], exhausted
        elif status:
            r.status, r.blocked_reason = status, ""
        for k, v in fields.items():
            setattr(r, k, v)
            if isinstance(v, (dict, list)):
                flag_modified(r, k)
        r.updated_at = _now()
        return _run_view(r)


def _run_view(r) -> dict:
    status = r.status if r.status != "blocked" else f"blocked({r.blocked_reason})"
    return {"run_key": r.run_key, "slug": r.slug, "version": r.version, "release": r.release,
            "listing": r.listing, "stage": r.stage, "state": r.status, "status": status,
            "blocked_reason": r.blocked_reason or None,
            "attempts_exhausted": bool(r.attempts_exhausted),
            "generation_calls": r.generation_calls, "spent_cad": round(r.spent_cad or 0.0, 4),
            "outfit_id": r.outfit_id or None, "card": dict(r.card or {}),
            "owner_decision": dict(r.owner_decision or {}),
            "stages": sorted((r.stages or {}).keys(),
                             key=lambda k: [s for s, _ in STAGES].index(k)
                             if k in STAGE_STATE else 99),
            "updated_at": r.updated_at.isoformat() if r.updated_at else None}


def get_run(db, key: str) -> dict | None:
    from .image_records import ensure_tables

    ensure_tables(db)
    with db.session() as s:
        r = _run(s, key)
        return _run_view(r) if r else None


def _stage_data(db, key: str) -> dict:
    with db.session() as s:
        return dict(_run(s, key).stages or {})


# ---- candidates and learning ------------------------------------------------------------

def store_bytes(db, data: bytes, *, key: str, why: str) -> str:
    from ..core.artifacts import ArtifactStore

    return ArtifactStore().put(key, data, "image/png", db=db, keep=why).sha256


def record_candidate(db, cand: dict, verdict: dict, *, method: str, run: str = "",
                     stage: str = "", attempt: int = 1, owner_visual_approval=None,
                     submitted_by: str = "", outcome: str | None = None) -> dict:
    """One learning/provenance row per candidate, whatever made it."""
    from .image_records import ImageCandidate, ensure_tables

    ensure_tables(db)
    q = verdict["checks"].get("quality") or {}
    tech = verdict["technical_status"]
    outcome = outcome or {"PASS": "accepted", "FAIL": "rejected"}.get(tech, "unverified")
    prompt = str(cand.get("prompt") or "")
    with db.session() as s:
        row = ImageCandidate(
            sha256=verdict["sha256"], run_key=run, method=method,
            provenance_kind=cand.get("provenance_kind") or f"ai_generated_{method}",
            slug=cand.get("slug", ""), version=cand.get("version", ""),
            release=cand.get("release", ""), listing=verdict.get("listing", ""),
            role=cand.get("role", ""), stage=stage, attempt=attempt,
            provider=str(cand.get("provider") or "")[:80],
            model=str(cand.get("model") or "")[:120], prompt=prompt[:8000],
            prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            prompt_version=str(cand.get("prompt_version") or "")[:80],
            references=[{"sha256": r.get("sha256"), "kind": r.get("kind")}
                        for r in cand.get("references") or []],
            laura_present=bool(cand.get("laura_present")),
            outfit_id=str(cand.get("outfit_id") or "")[:80],
            cost_cad=cand.get("cost_cad"), cost_basis=str(cand.get("cost_basis") or "")[:200],
            latency_s=cand.get("latency_s"), width=q.get("width"), height=q.get("height"),
            binding={k: v for k, v in verdict["checks"]["binding"].items()},
            checks={**verdict["checks"], "_publication": verdict.get("publication") or {}},
            technical_status=tech,
            publishable=bool(verdict["publishable"]), outcome=outcome,
            failure_categories=list(verdict.get("failure_categories") or []),
            owner_visual_approval=owner_visual_approval, submitted_by=submitted_by[:120])
        s.add(row)
        s.flush()
        return {"candidate_id": row.id, "sha256": row.sha256, "outcome": outcome}


def learning_summary(db, *, slug: str | None = None) -> dict:
    from sqlalchemy import select

    from .image_records import ImageCandidate, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        q = select(ImageCandidate)
        if slug:
            q = q.where(ImageCandidate.slug == slug)
        rows = list(s.scalars(q))
    cats: dict[str, int] = {}
    for r in rows:
        for c in r.failure_categories or []:
            cats[c] = cats.get(c, 0) + 1
    spent = sum(r.cost_cad for r in rows if r.cost_cad is not None)
    unknown_cost = sum(1 for r in rows if r.cost_cad is None)
    accepted = sum(1 for r in rows if r.outcome == "accepted")
    lat = [r.latency_s for r in rows if r.latency_s is not None]
    return {"candidates": len(rows), "accepted": accepted,
            "outcomes": {o: sum(1 for r in rows if r.outcome == o)
                         for o in ("accepted", "rejected", "unverified", "provider_error")},
            "failure_categories": cats, "spent_cad": round(spent, 4),
            "candidates_with_unknown_cost": unknown_cost,
            "cost_per_accepted_cad": (round(spent / accepted, 4) if accepted and not
                                      unknown_cost else None),
            "latency_s": ({"min": min(lat), "max": max(lat),
                           "mean": round(sum(lat) / len(lat), 2)} if lat else None),
            "note": ("cost per accepted image is undefined when nothing was accepted or any "
                     "cost is unknown; never reported as zero")}


def _best(db, *, listing: str, role: str, run: str | None = None) -> dict | None:
    from sqlalchemy import select

    from .image_records import ImageCandidate

    with db.session() as s:
        q = select(ImageCandidate).where(ImageCandidate.listing == listing,
                                         ImageCandidate.role == role)
        if run:
            q = q.where(ImageCandidate.run_key == run)
        rows = list(s.scalars(q.order_by(ImageCandidate.id.desc())))
    if not rows:
        return None
    rank = {"PASS": 0, "UNKNOWN": 1, "FAIL": 2}
    r = sorted(rows, key=lambda x: (not x.publishable, rank.get(x.technical_status, 3),
                                    -x.id))[0]
    return {"candidate_id": r.id, "sha256": r.sha256, "method": r.method,
            "technical_status": r.technical_status, "publishable": r.publishable,
            "attempt": r.attempt, "outcome": r.outcome,
            "failure_categories": list(r.failure_categories or []),
            "owner_visual_approval": r.owner_visual_approval,
            "unknown": sorted(k for k, c in (r.checks or {}).items()
                              if c.get("status") == "UNKNOWN"),
            "failed": {k: c.get("why") for k, c in (r.checks or {}).items()
                       if c.get("status") == "FAIL"},
            "blockers": ((r.checks or {}).get("_publication") or {}).get("blockers")}


def _attempts(db, run: str, role: str) -> int:
    from sqlalchemy import func, select

    from .image_records import ImageCandidate

    with db.session() as s:
        return int(s.scalar(select(func.count()).select_from(ImageCandidate).where(
            ImageCandidate.run_key == run, ImageCandidate.role == role)) or 0)


# ---- one generation, through the budget --------------------------------------------------

class BudgetStop(RuntimeError):
    pass


def _spend_plan() -> dict:
    from . import spend_plan

    return spend_plan.build(
        hypothesis="one truthful gallery per certified release",
        provider_model="registered generator", call_count=MAX_GENERATION_CALLS,
        max_spend_cad=MAX_SPEND_CAD_PER_GALLERY,
        pass_criteria=["every generated role technical PASS under candidate_gates"],
        fail_criteria=["attempt cap reached", "any spend past the plan"])


def _generate(db, key: str, gen, *, slug, version, release, role, stage, brief, refs, outfit,
              laura: bool, judges, plan_attempt: int, evaluate: bool = True) -> dict:
    from . import spend_plan
    from .gallery import gates_now

    with db.session() as s:
        r = _run(s, key)
        calls, spent = int(r.generation_calls or 0), float(r.spent_cad or 0.0)
    if getattr(gen, "paid", True) and not gates_now(db, keys=("image_generation",)).get(
            "image_generation"):
        raise BudgetStop("image_generation gate closed: a paid generator may not be called")
    try:
        spend_plan.guard(_spend_plan(), spent_cad=spent, calls_made=calls,
                         next_cost_cad=float(getattr(gen, "max_cost_cad_per_call", 0.0)))
    except spend_plan.PlanRefused as exc:
        raise BudgetStop(str(exc)) from None
    _update(db, key, stage=stage, generation_calls=calls + 1)
    base = {"slug": slug, "version": version, "release": release, "role": role,
            "laura_present": laura, "outfit_id": (outfit or {}).get("outfit_id"),
            "listing": outfits.listing_of(slug), "prompt_version": prompt_version(db)}
    try:
        out = gen.generate(stage=stage, role=role, brief=brief, references=refs,
                           outfit=outfit, attempt=plan_attempt)
    except Exception as exc:  # noqa: BLE001 - a provider error is a recorded outcome
        from .image_records import ImageCandidate

        with db.session() as s:
            s.add(ImageCandidate(sha256="", run_key=key, method="autonomous",
                                 provenance_kind="ai_generated_autonomous", slug=slug,
                                 version=version, release=release, listing=base["listing"],
                                 role=role, stage=stage, attempt=plan_attempt,
                                 provider=getattr(gen, "name", "?")[:80],
                                 technical_status="UNKNOWN", outcome="provider_error",
                                 failure_categories=["provider_error"],
                                 checks={"provider": {"status": "FAIL",
                                                      "why": f"{type(exc).__name__}: "
                                                             f"{str(exc)[:300]}"}}))
        return {"provider_error": f"{type(exc).__name__}: {str(exc)[:300]}"}
    cost = out.get("cost_cad")
    _update(db, key, stage=stage, spent_cad=spent + float(cost or 0.0))
    data = out["data"]
    sha = store_bytes(db, data, key=f"{key}/{role}/{plan_attempt}",
                      why="generated listing-image candidate (AI; never a photograph)")
    cand = {**base, "data": data, "sha256": sha, "provider": out.get("provider"),
            "model": out.get("model"), "prompt": out.get("prompt") or brief,
            "references": [{"sha256": r["sha256"], "kind": r["kind"]} for r in refs],
            "identity_evidence": out.get("identity_evidence"), "cost_cad": cost,
            "cost_basis": out.get("cost_basis") or "generator receipt",
            "latency_s": out.get("latency_s"), "provenance_kind": "ai_generated_autonomous"}
    if role == ANCHOR_ROLE:
        bind = CG.binding(db, slug, version, release)
        pt = judges.product_truth({**cand, "role": ANCHOR_ROLE}, bind)
        q = CG.quality(data)
        verdict = {"sha256": sha, "listing": base["listing"], "publishable": False,
                   "checks": {"binding": bind, "product_truth": pt, "quality": q},
                   "technical_status": CG.worst(bind["status"], pt["status"], q["status"]),
                   "failure_categories": sorted(
                       {CG.FAILURE_CATEGORY[k] for k, c in (("binding", bind),
                        ("product_truth", pt), ("quality", q)) if c["status"] == CG.FAIL})}
    else:
        verdict = CG.evaluate(db, cand, judges=judges)
    rec = record_candidate(db, cand, verdict, method="autonomous", run=key, stage=stage,
                           attempt=plan_attempt)
    return {**rec, "technical_status": verdict["technical_status"],
            "publishable": verdict["publishable"], "cost_cad": cost}


# ---- the stages --------------------------------------------------------------------------

def _next(stage: str) -> str | None:
    names = [s for s, _ in STAGES]
    i = names.index(stage)
    return names[i + 1] if i + 1 < len(names) else None


def run_stage(db, inputs: dict, *, follow, generator=None, judges=None) -> dict:
    """Run one stage and enqueue the next. `follow(inputs, idempotency_key)` enqueues."""
    slug, version, release = inputs["slug"], inputs["version"], str(inputs.get("release") or "")
    stage, round_ = inputs.get("stage") or STAGES[0][0], int(inputs.get("round") or 0)
    if stage not in STAGE_STATE:
        raise ValueError(f"unknown stage {stage!r}")
    key = _ensure_run(db, slug, version, release)
    run = get_run(db, key)
    if run["state"] in ("blocked", "approved_for_publication") and stage != "repair":
        return {"run_key": key, "skipped": True, "why": f"run is {run['status']}"}
    judges = judges or CG.RealJudges(db)
    gen = generator if generator is not None else resolve_generator(db)
    plan = SP.plan_for(run["listing"]) if _is_launch(run["listing"]) else None

    def go(next_stage: str | None, *, rnd: int = 0):
        if next_stage is None:
            return None
        follow({"slug": slug, "version": version, "release": release, "stage": next_stage,
                "round": rnd}, stage_key(slug, version, release, next_stage, rnd))
        return next_stage

    def block(why: str, *, exhausted: bool = False, record: dict | None = None):
        return {"run_key": key, **_update(db, key, stage=stage, blocked=why, exhausted=exhausted,
                                          record=record or {"outputs": {"blocked": why}})}

    st = STAGE_STATE[stage]
    if stage == "retrieve_release":
        bind = CG.binding(db, slug, version, release)
        if bind["status"] == CG.FAIL and "no certified release" in bind["why"]:
            return {"run_key": key, **_update(db, key, stage=stage,
                                               status="awaiting_certified_pattern",
                                               record={"evidence": bind})}
        if bind["status"] != CG.PASS:
            return block(f"release binding {bind['status']}: {bind['why']}",
                         record={"evidence": bind})
        if plan is None:
            return block(f"{run['listing']} has no shot plan (not a Launch-0 listing)")
        _update(db, key, stage=stage, status=st,
                record={"inputs": dict(inputs), "evidence": bind,
                        "outputs": {"plan_roles": [r["role"] for r in plan["roles"]]}})
        return {"run_key": key, "next": go(_next(stage))}

    data = _stage_data(db, key)
    bind = (data.get("retrieve_release") or {}).get("evidence") or {}

    if gen is None and stage in ("prepare_references", "product_generation",
                                 "lifestyle_generation", "remaining_roles", "repair"):
        return block("no image generator is wired: W-FLUXAPI's stage functions have not "
                     "landed (gateway/images.py and the reference generator)")

    try:
        if stage == "prepare_references":
            refs = []
            for r in gen.prepare_references(slug=slug, version=version, release=release,
                                            cir_fingerprint=bind.get("cir_fingerprint")):
                if r.get("kind") not in CG.REFERENCE_KINDS:
                    return block(f"generator returned an unknown reference kind {r.get('kind')!r}")
                sha = store_bytes(db, r["data"], key=f"{key}/ref", why="image reference")
                refs.append({"kind": r["kind"], "sha256": sha, "label": r.get("label", "")})
            _update(db, key, stage=stage, status=st,
                    record={"outputs": {"references": refs}, "cost_cad": 0.0})
            return {"run_key": key, "next": go(_next(stage))}

        refs = (data.get("prepare_references") or {}).get("outputs", {}).get("references", [])
        ref_bytes = None

        def _refs_with_bytes():
            from ..core.artifacts import ArtifactStore

            nonlocal ref_bytes
            if ref_bytes is None:
                ref_bytes = [{**r, "data": ArtifactStore().get(r["sha256"], db=db)}
                             for r in refs]
            return ref_bytes

        if stage == "product_generation":
            attempt = _attempts(db, key, ANCHOR_ROLE) + 1
            got = _generate(db, key, gen, slug=slug, version=version, release=release,
                            role=ANCHOR_ROLE, stage=stage, laura=False, judges=judges,
                            brief="the finished piece alone, flat, plain background, every "
                                  "piece visible", refs=_refs_with_bytes(), outfit=None,
                            plan_attempt=attempt)
            _update(db, key, stage=stage, status=st,
                    record={"outputs": got, "cost_cad": got.get("cost_cad")})
            return {"run_key": key, "next": go(_next(stage), rnd=attempt - 1)}

        if stage == "fidelity_gate":
            best = _best(db, listing=run["listing"], role=ANCHOR_ROLE, run=key)
            status = (best or {}).get("technical_status", "UNKNOWN")
            record = {"evidence": best}
            if status == "PASS":
                _update(db, key, stage=stage, status=st, record=record)
                return {"run_key": key, "next": go(_next(stage))}
            if status == "FAIL" and _attempts(db, key, ANCHOR_ROLE) < MAX_ATTEMPTS_PER_ROLE:
                n = _attempts(db, key, ANCHOR_ROLE)
                _update(db, key, stage=stage, status=st, record=record)
                return {"run_key": key, "next": go("product_generation", rnd=n)}
            if status == "FAIL":
                return block(f"product fidelity FAIL after {MAX_ATTEMPTS_PER_ROLE} attempts: "
                             f"{(best or {}).get('failed')}", exhausted=True, record=record)
            return block("product fidelity cannot be verified: no qualified verifier for "
                         "generated product images (product_authority: UNKNOWN). "
                         f"Unknown: {(best or {}).get('unknown')}", record=record)

        laura_roles = [r for r in SP.generated_roles(plan) if r["laura"]]
        if stage == "load_laura_references":
            from . import canonical

            if not laura_roles:
                _update(db, key, stage=stage, status=st,
                        record={"outputs": {"laura": "not in this listing's shot plan"}})
                return {"run_key": key, "next": go(_next(stage))}
            check = canonical.verify()
            if not check.get("ok"):
                return block(f"Laura's canonical references failed verification: "
                             f"{check.get('problems')}")
            _update(db, key, stage=stage, status=st, record={"outputs": {
                "identity_id": canonical.IDENTITY_ID,
                "references": dict(canonical.CURRENT_REFERENCE_HASHES)}})
            return {"run_key": key, "next": go(_next(stage))}

        if stage == "reserve_outfit":
            if not laura_roles:
                _update(db, key, stage=stage, status=st, record={"outputs": {"outfit": None}})
                return {"run_key": key, "next": go(_next(stage))}
            pick = outfits.for_listing(db, run["listing"])
            if pick is None:
                return block("no approved, unreserved Laura outfit exists for "
                             f"{run['listing']}; the owner approves one (D-W4-LAURA-OUTFIT)")
            got = outfits.reserve(db, pick["outfit_id"], run["listing"])
            if got["status"] != "PASS":
                return block(f"outfit reservation {got['status']}: {got['why']}")
            _update(db, key, stage=stage, status=st, outfit_id=pick["outfit_id"],
                    record={"outputs": got})
            return {"run_key": key, "next": go(_next(stage))}

        def laura_refs():
            from . import canonical
            out = []
            if canonical.verify().get("ok"):
                from pathlib import Path
                for frame, sha in canonical.CURRENT_REFERENCE_HASHES.items():
                    path = canonical.reference_file(frame)
                    if path:  # '' = not the recorded bytes: never a substitute
                        out.append({"kind": "laura_canonical", "sha256": sha,
                                    "data": Path(path).read_bytes()})
            return out

        def gen_roles(roles, rnd_stage):
            outs = []
            outfit = outfits.get(db, run["outfit_id"]) if run["outfit_id"] else None
            for r in roles:
                attempt = _attempts(db, key, r["role"]) + 1
                if attempt > MAX_ATTEMPTS_PER_ROLE:
                    continue
                refs_ = _refs_with_bytes() + (laura_refs() if r["laura"] else [])
                outs.append(_generate(db, key, gen, slug=slug, version=version,
                                      release=release, role=r["role"], stage=rnd_stage,
                                      laura=r["laura"], judges=judges, brief=r["brief"] or
                                      f"{r['job']}: the finished piece", refs=refs_,
                                      outfit=outfit if r["laura"] else None,
                                      plan_attempt=attempt))
            return outs

        if stage == "lifestyle_generation":
            roles = [r for r in SP.generated_roles(plan) if r["job"] == "LIFESTYLE"]
            outs = gen_roles(roles, stage)
            _update(db, key, stage=stage, status=st, record={
                "outputs": outs, "cost_cad": sum(o.get("cost_cad") or 0 for o in outs)})
            return {"run_key": key, "next": go(_next(stage))}

        if stage == "remaining_roles":
            roles = [r for r in SP.generated_roles(plan) if r["job"] != "LIFESTYLE"]
            outs = gen_roles(roles, stage)
            _update(db, key, stage=stage, status=st, record={
                "outputs": outs or {"note": "every other role is covered by the disclosed set "
                                            "or needs a photograph"},
                "cost_cad": sum(o.get("cost_cad") or 0 for o in outs)})
            return {"run_key": key, "next": go(_next(stage))}

        if stage == "verification":
            roles = SP.generated_roles(plan)
            per = {r["role"]: _best(db, listing=run["listing"], role=r["role"], run=key)
                   for r in roles}
            failing = [r for r in roles if (per[r["role"]] or {}).get("technical_status")
                       == "FAIL" and _attempts(db, key, r["role"]) < MAX_ATTEMPTS_PER_ROLE]
            _update(db, key, stage=stage, status=st, record={"evidence": per})
            if failing and round_ < MAX_REPAIR_ROUNDS:
                return {"run_key": key, "next": go("repair", rnd=round_ + 1)}
            return {"run_key": key, "next": go("gallery_assembly")}

        if stage == "repair":
            roles = SP.generated_roles(plan)
            failing = [r for r in roles if (_best(db, listing=run["listing"], role=r["role"],
                                                   run=key) or {}).get("technical_status")
                       == "FAIL"]
            outs = gen_roles(failing, stage)
            _update(db, key, stage=stage, status=st, record={
                "outputs": outs, "round": round_,
                "cost_cad": sum(o.get("cost_cad") or 0 for o in outs)})
            return {"run_key": key, "next": go("verification", rnd=round_)}
    except BudgetStop as exc:
        return block(f"budget stop: {exc}", exhausted=True)

    if stage == "gallery_assembly":
        view = readiness(db, run["listing"], run_key_=key)
        _update(db, key, stage=stage, status=st, record={"outputs": view})
        return {"run_key": key, "next": go(_next(stage))}

    if stage == "owner_card":
        view = (data.get("gallery_assembly") or {}).get("outputs") or readiness(
            db, run["listing"], run_key_=key)
        gen_roles_ = [r for r in view["roles"] if r["source"] == "generated"]
        not_ready = [r for r in gen_roles_ if (r.get("candidate") or {}).get(
            "technical_status") != "PASS"]
        card = {"listing": run["listing"], "slug": slug, "version": version,
                "release": release, "roles": view["roles"],
                "set_check": view["set_check"],
                "publication_blockers": view["publication_blockers"],
                "spent_cad": get_run(db, key)["spent_cad"],
                "recommended_fix": _recommend(not_ready, view),
                "owner_approval_is_not_technical_verification": True}
        if not_ready or not view["set_check"]["ok"]:
            why = "; ".join(f"{r['role']}: {(r.get('candidate') or {}).get('technical_status', 'no candidate')}"
                            f" (failed {sorted(((r.get('candidate') or {}).get('failed') or {}))},"
                            f" unknown {(r.get('candidate') or {}).get('unknown')})"
                            for r in not_ready) or str(view["set_check"]["problems"])[:500]
            return {"run_key": key, **_update(db, key, stage=stage, blocked=why[:1500],
                                               exhausted=True, card=card,
                                               record={"outputs": card})}
        return {"run_key": key, **_update(db, key, stage=stage,
                                           status="ready_for_owner_review", card=card,
                                           record={"outputs": card})}
    raise ValueError(f"stage {stage!r} fell through")


def _recommend(not_ready: list, view: dict) -> list[str]:
    out = []
    for r in not_ready:
        c = r.get("candidate") or {}
        if "identity" in (c.get("failed") or {}):
            out.append(f"{r['role']}: identity drift; regenerate with the canonical references")
        if "product_truth" in (c.get("failed") or {}):
            out.append(f"{r['role']}: product fidelity failed; a qualified sample photo "
                       f"reference (physical_upgrade.intake) is the truthful fix")
        for u in c.get("unknown") or []:
            out.append(f"{r['role']}: {u} UNKNOWN; fund/qualify the verifier, never waive it")
    if any("F-852" in b for b in view["publication_blockers"]):
        out.append("publication: F-852 refuses generated product imagery; an owner policy "
                   "decision is required (VISREF E4), or a photo of a made sample")
    return sorted(set(out))


def _is_launch(listing: str) -> bool:
    from ..products import launch0

    return listing in launch0.LAUNCH0_SLUGS


# ---- gallery assembly / readiness (both methods) ----------------------------------------

def readiness(db, listing: str, *, run_key_: str | None = None) -> dict:
    """The shot plan with what fills each role, the set check and publication blockers."""
    from ..gates.asset_truth import AssetClass
    from ..publish import eligibility as el

    plan = SP.plan_for(listing)
    roles, set_cands, blockers = [], [], set()
    for r in plan["roles"]:
        entry = {"position": r["position"], "role": r["role"], "job": r["job"],
                 "required_by": r["required_by"], "conditional": r["conditional"],
                 "preferred_source": r["preferred_source"]}
        if r["sources"][SP.DISCLOSED] == SP.SATISFIES:
            entry.update(source="disclosed_render",
                         status="disclosed set (certified by the existing listing-set "
                                "certificate path)")
            medium, purpose = r["disclosed_medium"]
            set_cands.append(el.Candidate(asset_id=f"{listing}-{r['role']}",
                                          medium=AssetClass(medium), purpose=purpose,
                                          job=r["job"], position=r["position"]))
        else:
            best = _best(db, listing=listing, role=r["role"], run=run_key_) or \
                (_best(db, listing=listing, role=r["role"]) if run_key_ else None)
            entry.update(source="generated" if r in SP.generated_roles(plan) else r[
                "preferred_source"], candidate=best,
                         status=("missing" if best is None else
                                 "publishable" if best["publishable"] else
                                 f"candidate {best['technical_status']}, not publishable"))
            if r.get("gap"):
                entry["gap"] = r["gap"]
            for b in (best or {}).get("blockers") or []:
                blockers.add(b)
            if best is not None and best["publishable"]:
                set_cands.append(el.Candidate(asset_id=f"{listing}-{r['role']}",
                                              medium=CG.MEDIUM, purpose=el.CONVERSION_CREATIVE,
                                              job=r["job"], position=r["position"]))
        roles.append(entry)
    set_check = el.check_set(set_cands) if set_cands else {"ok": False, "problems": [
        {"kind": "no_valid_frames"}]}
    return {"listing": listing, "category": plan["category"], "roles": roles,
            "set_check": {"ok": set_check["ok"], "problems": set_check["problems"]},
            "publication_blockers": sorted(blockers),
            "gallery_ready": all(e["status"].startswith(("disclosed", "publishable"))
                                 for e in roles if not e["conditional"]),
            "basis": "visual.shot_plans + candidate_gates + eligibility.check_set"}


# ---- Command Center ---------------------------------------------------------------------

def status_board(db) -> dict:
    from sqlalchemy import select

    from ..products import launch0
    from .image_records import ImageProductionRun, ensure_tables

    ensure_tables(db)
    out = []
    with db.session() as s:
        for listing in launch0.LAUNCH0_SLUGS:
            r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.listing == listing)
                         .order_by(ImageProductionRun.updated_at.desc()))
            out.append(_run_view(r) if r else {
                "listing": listing, "state": "awaiting_certified_pattern",
                "status": "awaiting_certified_pattern",
                "why": "no certified release has triggered image production yet"})
    return {"products": out, "states": list(STATES),
            "learning": learning_summary(db)}


def notification_candidates(db) -> list[dict]:
    """Owner notifications, only for ready_for_owner_review or blocked after attempts."""
    from sqlalchemy import select

    from .image_records import ImageProductionRun, ensure_tables

    ensure_tables(db)
    out = []
    with db.session() as s:
        rows = list(s.scalars(select(ImageProductionRun).where(
            ImageProductionRun.status.in_(NOTIFY_STATES))))
    for r in rows:
        if r.status == "blocked" and not r.attempts_exhausted:
            continue
        ready = r.status == "ready_for_owner_review"
        card = dict(r.card or {})
        out.append({
            "dedupe_key": f"image_gallery:{r.run_key}:{r.status}",
            "severity": "normal" if ready else "high",
            "category": "decision" if ready else "anomaly",
            "title": (f"Gallery ready for your review: {r.listing}" if ready else
                      f"Gallery blocked after permitted attempts: {r.listing}")[:300],
            "body": ("every generated role passed automated verification; publication "
                     "blockers: " + "; ".join(card.get("publication_blockers") or [])[:600]
                     if ready else f"cause: {r.blocked_reason}"[:1000]),
            "consequence": ("nothing publishes until you approve and every publication gate "
                            "passes" if ready else
                            "LIFESTYLE stays unfilled for this listing; recommended fix: " +
                            "; ".join(card.get("recommended_fix") or [])[:500]),
            "evidence": [f"image_production_runs:{r.id}"],
            "deep_link": f"/cc/#/images/{r.listing}", "count": 1})
    return out


def approve(db, key: str, *, decided_by: str) -> dict:
    """The owner's approval. It never bypasses a gate: every candidate is re-checked now."""
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from .image_records import ImageCandidate

    run = get_run(db, key)
    if run is None:
        return {"approved": False, "why": "no such run"}
    if run["state"] != "ready_for_owner_review":
        return {"approved": False, "why": f"run is {run['status']}, not ready_for_owner_review"}
    blockers = list(run["card"].get("publication_blockers") or [])
    with db.session() as s:
        for r in run["card"].get("roles") or []:
            c = r.get("candidate")
            if r.get("source") == "generated" and c:
                row = s.get(ImageCandidate, c["candidate_id"])
                if row is None or not row.publishable:
                    blockers.append(f"{r['role']}: candidate not publishable")
    decision = {"by": decided_by, "at": _now().isoformat(), "blockers": sorted(set(blockers))}
    with db.session() as s:
        r = _run(s, key)
        r.owner_decision = {**decision, "approved_look": True}
        flag_modified(r, "owner_decision")
        if not blockers:
            r.status = "approved_for_publication"
    if blockers:
        return {"approved": False, "owner_look_recorded": True,
                "why": "publication gates still block; approval is recorded but cannot "
                       "override them", "blockers": decision["blockers"]}
    return {"approved": True, "state": "approved_for_publication"}
