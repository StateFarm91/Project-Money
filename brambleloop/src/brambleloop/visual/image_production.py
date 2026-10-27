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
    # W-VISNEXT2, stage A of the owner's manual method: Laura alone in the listing's outfit,
    # judged, then reused as identity context for every Laura frame of the listing.
    ("identity_anchor", "lifestyle_generation"),
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
IDENTITY_ANCHOR_ROLE = "laura_identity_anchor"   # stage A: an intermediate reference, not a frame
MAX_IDENTITY_ANCHOR_ATTEMPTS = 2   # one generation + one bounded proportion-correction pass
MAX_RESTARTS = 3                   # per run; a restart never resets attempts, calls or spend
RESTART_KEY = "_restart"           # the run's restart record inside `stages`


class Generator(Protocol):
    """What W-FLUXAPI's stage functions provide. `paid` providers need the gate open."""

    name: str
    paid: bool

    def prepare_references(self, *, slug: str, version: str, release: str,
                           cir_fingerprint: str | None) -> list[dict]:
        """[{"kind": one of candidate_gates.REFERENCE_KINDS, "data": bytes}]"""

    def generate(self, *, stage: str, role: str, brief: str, references: list[dict],
                 outfit: dict | None, attempt: int, repair: dict | None = None) -> dict:
        """{"data": bytes, "provider", "model", "prompt", "cost_cad", "latency_s",
        "identity_evidence" (optional; the conditioning receipt / judge readings)}"""


_GENERATORS: dict[str, object] = {}


def register_generator(name: str, factory) -> None:
    """W-FLUXAPI registers its stage functions here; nothing is registered in this branch."""
    _GENERATORS[name] = factory


def resolve_generator(db):
    """The registered generator. The FLUX 3 stages (W-FLUXAPI) register themselves on
    first use. A paid generator is still refused while the image_generation gate is closed."""
    if not _GENERATORS:
        try:
            from ..creative import flux3_generator

            flux3_generator.register(register_generator)
        except ImportError:
            return None
    names = sorted(_GENERATORS)
    if len(names) > 1:
        # F-739 (W4-C08): with a choice, on-model work goes to the best demonstrated
        # configuration (`provider_routing.route`), not to whichever name sorts first.
        from . import provider_routing

        gens = {n: _GENERATORS[n](db) for n in names}
        prov = {n: str(getattr(g, "provider", None) or n) for n, g in gens.items()}
        by_provider = {p: n for n, p in reversed(list(prov.items()))}
        pick = provider_routing.route(db, available=sorted(by_provider),
                                      default=prov[names[0]])
        return gens[by_provider.get(pick["provider"], names[0])]
    for _name, factory in sorted(_GENERATORS.items()):
        return factory(db)
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_key(slug: str, version: str, release: str, ns: str = "") -> str:
    """The run's identity. `ns` (W-VISNEXT2) separates a controlled-experiment run of a
    certified release from the release's ordinary production run, which it never touches."""
    return f"imgprod:{slug}@{version}@{release}" + (f"#{ns}" if ns else "")


def stage_key(slug: str, version: str, release: str, stage: str, round_: int = 0,
              epoch: int = 0, ns: str = "") -> str:
    """A stage job's idempotency key. `epoch` > 0 only after a restart (W-VISNEXT), so a
    restarted run's jobs never collide with the ones its first pass already ran."""
    return (run_key(slug, version, release, ns) + f":{stage}" + (f":{round_}" if round_ else "")
            + (f":e{epoch}" if epoch else ""))


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

def trigger(enqueue, *, slug: str, version: str, release: str, ns: str = "",
            controlled_run_id: int | None = None) -> dict:
    """Enqueue the workflow once per slug@version@release. `enqueue(inputs, key)` returns
    None on a duplicate key (JobContext.enqueue semantics). `ns` and `controlled_run_id`
    (W-VISNEXT2) start an owner-authorised controlled-experiment run of a certified release:
    its own run row, the authorization's caps in place of the image_generation gate, and an
    EXPERIMENT label on everything it makes."""
    if not (slug and version and release):
        return {"enqueued": False, "why": "slug, version and release are all required"}
    if bool(ns) != bool(controlled_run_id):
        return {"enqueued": False, "why": "a namespaced run is a controlled run, and back"}
    inputs = {"slug": slug, "version": version, "release": release,
              "stage": STAGES[0][0], "round": 0}
    if ns:
        inputs.update(ns=ns, controlled_run_id=int(controlled_run_id))
    job = enqueue(inputs, stage_key(slug, version, release, STAGES[0][0], ns=ns))
    return {"enqueued": job is not None, "run_key": run_key(slug, version, release, ns)}


# ---- run row -----------------------------------------------------------------------------

def _run(s, key: str):
    from sqlalchemy import select

    from .image_records import ImageProductionRun

    return s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))


def _ensure_run(db, slug, version, release, ns: str = ""):
    from .image_records import ImageProductionRun, ensure_tables

    ensure_tables(db)
    key = run_key(slug, version, release, ns)
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
            "restarts": int(((r.stages or {}).get(RESTART_KEY) or {}).get("epoch") or 0),
            "stages": sorted((k for k in (r.stages or {}) if not k.startswith("_")),
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
            checks={**verdict["checks"], "_publication": verdict.get("publication") or {},
                    # the generator's conditioning receipt (references sent, proven), kept
                    # so a re-verification reads the same evidence (W-VISNEXT)
                    "_identity_evidence": _receipt_summary(cand.get("identity_evidence"))},
            technical_status=tech,
            publishable=bool(verdict["publishable"]), outcome=outcome,
            failure_categories=list(verdict.get("failure_categories") or []),
            owner_visual_approval=owner_visual_approval, submitted_by=submitted_by[:120])
        s.add(row)
        s.flush()
        return {"candidate_id": row.id, "sha256": row.sha256, "outcome": outcome}


def _receipt_summary(ev) -> dict:
    ev = ev if isinstance(ev, dict) else {}
    out = {k: ev[k] for k in ("conditioning", "references", "request", "non_identity_references")
           if k in ev}
    if isinstance(out.get("request"), dict):
        out["request"] = {k: out["request"].get(k) for k in ("conditioning_proven",
                                                              "request_sha256")}
    return out


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
            "blockers": ((r.checks or {}).get("_publication") or {}).get("blockers"),
            "listing": r.listing, "version": r.version, "release": r.release,
            "cir_fingerprint": (r.binding or {}).get("cir_fingerprint"),
            "laura_present": r.laura_present, "outfit_id": r.outfit_id or None,
            "fidelity": _fidelity_summary(r.checks)}


def _fidelity_summary(checks: dict | None) -> dict:
    """What the fidelity verifier left unknown or failed on a stored candidate."""
    fid = ((checks or {}).get("product_truth") or {}).get("fidelity") or {}
    needs = sorted({f"{c['check']} needs a {c['needs']}" for c in fid.get("checks") or []
                    if c.get("needs") and c.get("status") == "UNKNOWN"})
    return {"status": fid.get("status"), "unknown": fid.get("unknown") or [],
            "failed": fid.get("failed") or [], "codes": fid.get("codes") or [],
            "needs": needs}


def _attempts(db, run: str, role: str) -> int:
    from sqlalchemy import func, select

    from .image_records import ImageCandidate

    with db.session() as s:
        return int(s.scalar(select(func.count()).select_from(ImageCandidate).where(
            ImageCandidate.run_key == run, ImageCandidate.role == role)) or 0)


# ---- one generation, through the budget --------------------------------------------------

class BudgetStop(RuntimeError):
    pass


class ConditioningRefused(RuntimeError):
    pass


class CapabilityBlocked(RuntimeError):
    """A missing capability (a closed gate), not a failed attempt: shown, not notified."""


def _spend_plan() -> dict:
    from . import spend_plan

    return spend_plan.build(
        hypothesis="one truthful gallery per certified release",
        provider_model="registered generator", call_count=MAX_GENERATION_CALLS,
        max_spend_cad=MAX_SPEND_CAD_PER_GALLERY,
        pass_criteria=["every generated role technical PASS under candidate_gates"],
        fail_criteria=["attempt cap reached", "any spend past the plan"])


def _generate(db, key: str, gen, *, slug, version, release, role, stage, brief, refs, outfit,
              laura: bool, judges, plan_attempt: int, evaluate: bool = True,
              repair: dict | None = None, exp=None) -> dict:
    from . import spend_plan
    from .gallery import gates_now

    with db.session() as s:
        r = _run(s, key)
        calls, spent = int(r.generation_calls or 0), float(r.spent_cad or 0.0)
    next_cost = float(getattr(gen, "max_cost_cad_per_call", 0.0))
    if exp is not None:
        # W4-WRAPTEST: an experiment's paid call needs the owner's recorded experiment approval
        # and headroom in its own hard budget; every ceiling below still applies on top.
        from .experiment import ExperimentBudgetStop

        if getattr(gen, "paid", True) and not exp.paid_authorised():
            raise CapabilityBlocked("experiment is not live: a paid generator may not be "
                                    "called (dry run uses the stub provider)")
        if getattr(gen, "paid", True):
            try:
                exp.guard_paid(next_cost)
            except ExperimentBudgetStop as exc:
                raise BudgetStop(str(exc)) from None
    elif _controlled_of(db, key) and getattr(gen, "paid", True):
        # W-VISNEXT2: an owner-authorised controlled run of a certified release. The owner's
        # step-up authorization, inside its (shared) cap, stands in for the image_generation
        # gate for this run only; every ceiling below still applies on top.
        from ..experiments import controlled as CX

        CX.guard_generation(db, _controlled_of(db, key), next_cost)
    elif getattr(gen, "paid", True) and not gates_now(db, keys=("image_generation",)).get(
            "image_generation"):
        raise CapabilityBlocked("image_generation gate closed: a paid generator may not be "
                                "called")
    try:
        spend_plan.guard(_spend_plan(), spent_cad=spent, calls_made=calls,
                         next_cost_cad=next_cost)
    except spend_plan.PlanRefused as exc:
        raise BudgetStop(str(exc)) from None
    _update(db, key, stage=stage, generation_calls=calls + 1)
    base = {"slug": slug, "version": version, "release": release, "role": role,
            "laura_present": laura, "outfit_id": (outfit or {}).get("outfit_id"),
            "listing": outfits.listing_of(slug), "prompt_version": prompt_version(db)}
    if exp is not None:
        base["experiment"] = True
    if hasattr(type(gen), "current_run_key"):
        gen.current_run_key = key         # the generator reads this run's own anchor
    try:
        kw = {"repair": repair} if repair else {}
        out = gen.generate(stage=stage, role=role, brief=brief, references=refs,
                           outfit=outfit, attempt=plan_attempt, **kw)
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
    ctl = _controlled_of(db, key)
    sha = store_bytes(db, data, key=f"{key}/{role}/{plan_attempt}",
                      why="generated listing-image candidate (AI; never a photograph)" + (
                          f"; {exp.label}" if exp is not None else "") + (
                          "; EXPERIMENT (controlled run)" if ctl else ""))
    if ctl:
        # marked as an experiment image before anything evaluates it
        from ..experiments import controlled as CX

        CX.record_generation(db, ctl, reserved_cad=next_cost if getattr(gen, "paid", True)
                             else 0.0, actual_cad=cost, sha256=sha)
    cand = {**base, "data": data, "sha256": sha, "provider": out.get("provider"),
            "model": out.get("model"), "prompt": out.get("prompt") or brief,
            "references": [{"sha256": r["sha256"], "kind": r["kind"]} for r in refs],
            "identity_evidence": out.get("identity_evidence"), "cost_cad": cost,
            "cost_basis": out.get("cost_basis") or "generator receipt",
            "latency_s": out.get("latency_s"), "provenance_kind": "ai_generated_autonomous",
            "repair": repair}
    if role == ANCHOR_ROLE:
        bind = _binding(db, exp, slug, version, release)
        pt = judges.product_truth({**cand, "role": ANCHOR_ROLE}, bind)
        q = CG.quality(data)
        verdict = {"sha256": sha, "listing": base["listing"], "publishable": False,
                   "checks": {"binding": bind, "product_truth": pt, "quality": q},
                   "technical_status": CG.worst(bind["status"], pt["status"], q["status"]),
                   "failure_categories": sorted(
                       {CG.FAILURE_CATEGORY[k] for k, c in (("binding", bind),
                        ("product_truth", pt), ("quality", q)) if c["status"] == CG.FAIL})
                   # the fidelity verifier's codes (W-FIDELITY), so learning and the
                   # repair router read the same words as for every other role
                   + [str(c) for c in pt.get("codes") or []]}
    elif role == IDENTITY_ANCHOR_ROLE:
        verdict = identity_anchor_verdict(db, cand, judges,
                                          _binding(db, exp, slug, version, release))
    else:
        verdict = CG.evaluate(db, cand, judges=judges)
    rec = record_candidate(db, cand, verdict, method="autonomous", run=key, stage=stage,
                           attempt=plan_attempt)
    return {**rec, "technical_status": verdict["technical_status"],
            "publishable": verdict["publishable"], "cost_cad": cost}


def identity_anchor_verdict(db, cand: dict, judges, bind: dict) -> dict:
    """The stage-A anchor's verdict: identity, body proportions, outfit (registry and
    consistency), anatomy and realism, plus the release binding. It is an intermediate
    reference, never a gallery frame, so the listing image-quality floor (2000 px) and the
    gallery role check do not apply to it, and it is never publishable."""
    reserved = outfits.get(db, cand["outfit_id"]) if cand.get("outfit_id") else None
    checks = {"binding": bind,
              "identity": CG._judge(judges, "identity", cand),
              "body_proportions": CG._judge(judges, "body_proportions", cand),
              "outfit_distinctness": outfits.distinctness(db, cand.get("outfit_id"),
                                                          cand.get("listing", "")),
              "outfit_consistency": (CG._judge(judges, "outfit_consistency", cand, reserved)
                                     if reserved else CG._c(CG.UNKNOWN, "no reserved outfit")),
              "anatomy": CG._judge(judges, "anatomy", cand),
              "realism": CG._judge(judges, "realism", cand)}
    tech = CG.worst(*(c["status"] for c in checks.values()))
    cats = sorted({CG.FAILURE_CATEGORY[k] for k, c in checks.items()
                   if c["status"] == CG.FAIL and k in CG.FAILURE_CATEGORY})
    for c in checks.values():
        if c.get("status") in (CG.FAIL, CG.UNKNOWN):
            cats += [str(x) for x in c.get("codes") or [] if str(x) not in cats]
    return {"sha256": cand["sha256"], "listing": cand.get("listing", ""), "checks": checks,
            "technical_status": tech, "publishable": False,
            "publication": {"publishable": False, "blockers": [
                "the identity anchor is an intermediate reference, never a gallery frame"]},
            "failure_categories": cats,
            "unknown": sorted(k for k, c in checks.items() if c["status"] == CG.UNKNOWN)}


def _controlled_of(db, key: str) -> int | None:
    """The controlled run a namespaced orchestrator run belongs to (W-VISNEXT2)."""
    if "#" not in key:
        return None
    rec = _stage_data(db, key).get("_controlled") or {}
    return int(rec.get("run_id") or 0) or None


def _binding(db, exp, slug, version, release) -> dict:
    """The release binding: the certified one, or (EXPERIMENT mode only) the experiment's
    content-identity binding, which is never a certification."""
    if exp is not None:
        from . import experiment as XP

        got = XP.binding(db, slug, version, release)
        if got is not None:
            return got
    return CG.binding(db, slug, version, release)


# ---- the stages --------------------------------------------------------------------------

def _next(stage: str) -> str | None:
    names = [s for s, _ in STAGES]
    i = names.index(stage)
    return names[i + 1] if i + 1 < len(names) else None


def run_stage(db, inputs: dict, *, follow, generator=None, judges=None) -> dict:
    """Run one stage and enqueue the next (see `_run_stage`). A controlled run (W-VISNEXT2)
    mirrors its end state onto its controlled-experiment record."""
    out = _run_stage(db, inputs, follow=follow, generator=generator, judges=judges)
    if inputs.get("controlled_run_id") and out.get("run_key"):
        from ..experiments import controlled as CX

        CX.sync_pipeline(db, int(inputs["controlled_run_id"]), out["run_key"])
    return out


def _run_stage(db, inputs: dict, *, follow, generator=None, judges=None) -> dict:
    """Run one stage and enqueue the next. `follow(inputs, idempotency_key)` enqueues."""
    slug, version, release = inputs["slug"], inputs["version"], str(inputs.get("release") or "")
    stage, round_ = inputs.get("stage") or STAGES[0][0], int(inputs.get("round") or 0)
    if stage not in STAGE_STATE:
        raise ValueError(f"unknown stage {stage!r}")
    exp = None
    if inputs.get("experiment"):
        # W4-WRAPTEST: EXPERIMENT mode. Scratch database, an opened experiment for this exact
        # content and an installed context, or a refusal; never a silent fallback.
        from . import experiment as XP

        exp = XP.context_for(db, slug, version, release)
    ns = str(inputs.get("ns") or "")
    controlled = int(inputs.get("controlled_run_id") or 0) or None
    if ns or controlled:
        from ..experiments import controlled as CX

        CX.require_pipeline_run(db, controlled, ns=ns, slug=slug, version=version,
                                release=release)
    key = _ensure_run(db, slug, version, release, ns)
    if controlled:
        from sqlalchemy.orm.attributes import flag_modified

        with db.session() as s:
            r_ = _run(s, key)
            st_ = dict(r_.stages or {})
            if not st_.get("_controlled"):
                st_["_controlled"] = {"run_id": controlled, "ns": ns}
                r_.stages = st_
                flag_modified(r_, "stages")
    run = get_run(db, key)
    epoch = int(inputs.get("epoch") or 0)
    if epoch != run.get("restarts", 0):
        # a job from before (or beyond) the run's current restart epoch: superseded
        return {"run_key": key, "skipped": True,
                "why": f"job epoch {epoch} is not the run's epoch {run.get('restarts', 0)}"}
    if run["state"] in ("blocked", "approved_for_publication") and stage != "repair":
        return {"run_key": key, "skipped": True, "why": f"run is {run['status']}"}
    judges = judges or (exp.judges(db) if exp is not None else CG.RealJudges(db))
    if generator is not None:
        gen = generator
    elif exp is not None:
        gen = exp.generator(db)
    else:
        gen = resolve_generator(db)
    if exp is not None:
        plan = exp.plan
    else:
        plan = SP.campaign_plan(run["listing"]) if _is_launch(run["listing"]) else None
    max_att = exp.max_attempts_per_role if exp is not None else MAX_ATTEMPTS_PER_ROLE

    def go(next_stage: str | None, *, rnd: int = 0):
        if next_stage is None:
            return None
        nxt = {"slug": slug, "version": version, "release": release, "stage": next_stage,
               "round": rnd}
        if exp is not None:
            nxt["experiment"] = True
        if epoch:
            nxt["epoch"] = epoch
        if ns:
            nxt.update(ns=ns, controlled_run_id=controlled)
        follow(nxt, stage_key(slug, version, release, next_stage, rnd, epoch, ns))
        return next_stage

    def block(why: str, *, exhausted: bool = False, record: dict | None = None):
        return {"run_key": key, **_update(db, key, stage=stage, blocked=why, exhausted=exhausted,
                                          record=record or {"outputs": {"blocked": why}})}

    st = STAGE_STATE[stage]
    if stage == "retrieve_release":
        try:  # the first learning example (owner manual wrap experiment); idempotent
            from .repair_routes import seed_experiments

            seed_experiments(db)
        except Exception:  # noqa: BLE001 - learning seed never blocks production
            pass
        bind = _binding(db, exp, slug, version, release)
        if bind["status"] == CG.FAIL and "no certified release" in bind["why"]:
            return {"run_key": key, **_update(db, key, stage=stage,
                                               status="awaiting_certified_pattern",
                                               record={"evidence": bind})}
        if bind["status"] != CG.PASS:
            return block(f"release binding {bind['status']}: {bind['why']}",
                         record={"evidence": bind})
        if plan is None:
            return block(f"{run['listing']} has no shot plan (not a Launch-0 listing)")
        rec = {"inputs": dict(inputs), "evidence": bind,
               "outputs": {"plan_roles": [r["role"] for r in plan["roles"]]}}
        if exp is not None:
            rec = {**rec, "experiment": True, "label": exp.label,
                   "certification": exp.reg["certification"]}
        _update(db, key, stage=stage, status=st, record=rec)
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
            # A regeneration after a fidelity FAIL carries the targeted repair for its codes
            # when every code has a route; otherwise it is a plain retry within the cap.
            prior = (_best(db, listing=run["listing"], role=ANCHOR_ROLE, run=key)
                     if attempt > 1 else None)
            repair = (_repair_for(prior) if prior and prior.get("technical_status") == "FAIL"
                      else None)
            got = _generate(db, key, gen, slug=slug, version=version, release=release,
                            role=ANCHOR_ROLE, stage=stage, laura=False, judges=judges,
                            brief="the finished piece alone, flat, plain background, every "
                                  "piece visible", refs=_refs_with_bytes(), outfit=None,
                            plan_attempt=attempt, repair=repair, exp=exp)
            _update(db, key, stage=stage, status=st,
                    record={"outputs": got, "cost_cad": got.get("cost_cad")})
            return {"run_key": key, "next": go(_next(stage), rnd=attempt - 1)}

        if stage == "fidelity_gate":
            if inputs.get("reverify"):
                # W-VISNEXT restart: the stored anchor bytes are judged again with today's
                # judges; nothing is regenerated and no attempt is added.
                b = _best(db, listing=run["listing"], role=ANCHOR_ROLE, run=key)
                if b:
                    reverify(db, b["candidate_id"], judges=judges, exp=exp)
            best = _best(db, listing=run["listing"], role=ANCHOR_ROLE, run=key)
            status = (best or {}).get("technical_status", "UNKNOWN")
            record = {"evidence": best}
            if status == "PASS":
                _update(db, key, stage=stage, status=st, record=record)
                return {"run_key": key, "next": go(_next(stage))}
            if status == "FAIL" and exp is not None and not (_repair_for(best) or {}).get(
                    "directives"):
                return block(f"{exp.label}: the flat lay failed a hard Product Truth check "
                             f"and no bounded correction is routable "
                             f"({(best or {}).get('failure_categories')}); stopped early, "
                             f"nothing more is spent", exhausted=True, record=record)
            if status == "FAIL" and _attempts(db, key, ANCHOR_ROLE) < max_att:
                n = _attempts(db, key, ANCHOR_ROLE)
                _update(db, key, stage=stage, status=st, record=record)
                return {"run_key": key, "next": go("product_generation", rnd=n)}
            if status == "FAIL":
                return block(f"product fidelity FAIL after {max_att} attempts: "
                             f"{(best or {}).get('failed')}", exhausted=True, record=record)
            fid = (best or {}).get("fidelity") or {}
            return block("product fidelity cannot be verified: the fidelity verifier "
                         f"(visual.fidelity) reads UNKNOWN on {fid.get('unknown') or '?'}"
                         + (f" ({'; '.join(fid['needs'])})" if fid.get("needs") else "")
                         + f". Unknown: {(best or {}).get('unknown')}", record=record)

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
            pick = outfits.reserved_for(db, run["listing"])
            styled = None
            retire = None
            if (exp is not None and pick is not None and exp.outfit_rejects is not None
                    and exp.outfit_rejects(pick)):
                # Experiment: the outfit already held for this listing (e.g. the owner's manual
                # test outfit, seeded as wardrobe history) is one the brief excludes; a new one
                # is chosen and the old one retired, never reused.
                retire, pick = pick["outfit_id"], None
            if pick is None:
                # D-W4-LAURA-FLUX3 §5: Creative chooses the outfit and concept; the owner
                # does not. Deterministic, and it avoids outfits/settings other listings use.
                from . import styling

                styled = (exp.outfit_selector(db, run["listing"])
                          if exp is not None and exp.outfit_selector is not None
                          else styling.select_for_listing(db, run["listing"]))
                if not styled.get("outfit"):
                    return block(f"automatic styling found no unused complete outfit: "
                                 f"{styled.get('why')}")
                o = styled["outfit"]
                try:
                    outfits.register(db, outfit_id=o["outfit_id"], garments=o["garments"],
                                     colours=o["colours"], concept=styled["concept"])
                    pick = outfits.approve(db, o["outfit_id"],
                                           approved_by=f"creative_director:{styling.STYLING_VERSION}")
                except outfits.OutfitRefused as exc:
                    return block(f"automatic styling refused by the wardrobe registry: {exc}")
            if retire:
                rep = outfits.replace(db, retire, pick["outfit_id"], run["listing"])
                got = (outfits.reserve(db, pick["outfit_id"], run["listing"])
                       if rep.get("replaced") else rep)
                got = {**got, "retired": retire}
            else:
                got = outfits.reserve(db, pick["outfit_id"], run["listing"])
            if got.get("status") != "PASS":
                return block(f"outfit reservation {got.get('status')}: {got.get('why')}")
            _update(db, key, stage=stage, status=st, outfit_id=pick["outfit_id"],
                    record={"outputs": {**got, "styling": styled,
                                        "concept": (outfits.get(db, pick["outfit_id"]) or {})
                                        .get("concept")}})
            return {"run_key": key, "next": go(_next(stage))}

        def laura_refs():
            from . import canonical
            out = []
            if canonical.verify().get("ok"):
                from pathlib import Path
                for frame, sha in canonical.CURRENT_REFERENCE_HASHES.items():
                    path = canonical.reference_file(frame)
                    if path:  # '' = not the recorded bytes: never a substitute
                        data_ = Path(path).read_bytes()
                        if hashlib.sha256(data_).hexdigest() == sha:
                            out.append({"kind": "laura_canonical", "sha256": sha,
                                        "frame": frame, "data": data_})
            if len(out) != len(canonical.CURRENT_REFERENCE_HASHES):
                # D-W4-LAURA-FLUX3 §1: never continue with reduced identity conditioning.
                raise ConditioningRefused(
                    f"{len(out)} of {len(canonical.CURRENT_REFERENCE_HASHES)} canonical Laura "
                    f"references validated; generation with reduced identity conditioning is "
                    f"refused")
            return out

        def gen_roles(roles, rnd_stage, repairs=None):
            outs = []
            outfit = outfits.get(db, run["outfit_id"]) if run["outfit_id"] else None
            for r in roles:
                attempt = _attempts(db, key, r["role"]) + 1
                if attempt > max_att:
                    continue
                refs_ = _refs_with_bytes() + (laura_refs() if r["laura"] else [])
                if (r["laura"] and outfit and outfit.get("approved_reference")
                        and getattr(gen, "accepts_outfit_reference", False)):
                    # OWNERIMG E6: the outfit's approved reference image, as a clothing
                    # reference only (kind prior_candidate; never an identity reference).
                    # Sent only to a generator that declares it can carry one.
                    from ..core.artifacts import ArtifactStore

                    ref = ArtifactStore().get(outfit["approved_reference"], db=db)
                    if ref:
                        refs_ = refs_ + [{"kind": "prior_candidate", "label": "outfit_reference",
                                          "sha256": outfit["approved_reference"], "data": ref}]
                if r["laura"] and getattr(gen, "accepts_staged_method", False):
                    # W-VISNEXT2 stage A: the listing's accepted identity anchor, as identity
                    # context after the canonical three (never instead of them).
                    ia = _accepted_identity_anchor(db, key)
                    if ia:
                        refs_ = refs_ + [ia]
                    # Stage D: a non-LIFESTYLE Laura role edits the accepted lifestyle frame,
                    # so the outfit stays identical across the listing.
                    if r["job"] != "LIFESTYLE":
                        base_ = _accepted_lifestyle(db, key, run["listing"], plan)
                        if base_:
                            refs_ = refs_ + [base_]
                outs.append(_generate(db, key, gen, slug=slug, version=version,
                                      release=release, role=r["role"], stage=rnd_stage,
                                      laura=r["laura"], judges=judges, brief=r["brief"] or
                                      f"{r['job']}: the finished piece", refs=refs_,
                                      outfit=outfit if r["laura"] else None,
                                      plan_attempt=attempt,
                                      repair=(repairs or {}).get(r["role"]), exp=exp))
            return outs

        if stage == "identity_anchor":
            return _stage_identity_anchor(db, key, run, inputs, gen=gen, judges=judges, exp=exp,
                                          laura_roles=laura_roles, st=st, go=go, block=block,
                                          refs=_refs_with_bytes, laura_refs=laura_refs,
                                          slug=slug, version=version, release=release)

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
            if inputs.get("reverify"):
                for r in roles:
                    b = _best(db, listing=run["listing"], role=r["role"], run=key)
                    if b:
                        reverify(db, b["candidate_id"], judges=judges, exp=exp)
            per = {r["role"]: _best(db, listing=run["listing"], role=r["role"], run=key)
                   for r in roles}
            failing = [r for r in roles if (per[r["role"]] or {}).get("technical_status")
                       == "FAIL" and _attempts(db, key, r["role"]) < max_att
                       and _repair_for(per[r["role"]]) is not None
                       # Experiment: only a routable correction is bought, never a re-roll
                       # of a failure regeneration cannot change.
                       and (exp is None or (_repair_for(per[r["role"]]) or {}).get(
                           "directives"))]
            _update(db, key, stage=stage, status=st, record={"evidence": per})
            if failing and round_ < MAX_REPAIR_ROUNDS:
                return {"run_key": key, "next": go("repair", rnd=round_ + 1)}
            return {"run_key": key, "next": go("gallery_assembly")}

        if stage == "repair":
            roles = SP.generated_roles(plan)
            repairs = {}
            for r in roles:
                b = _best(db, listing=run["listing"], role=r["role"], run=key) or {}
                if b.get("technical_status") == "FAIL" and _repair_for(b) is not None and (
                        exp is None or (_repair_for(b) or {}).get("directives")):
                    repairs[r["role"]] = _repair_for(b)
            failing = [r for r in roles if r["role"] in repairs]
            repick = any(d.get("kind") == "repick_outfit" for rp in repairs.values()
                         for d in rp.get("directives") or [])
            if repick and run["outfit_id"]:
                got = _repick_outfit(db, run["listing"], run["outfit_id"])
                if not got.get("replaced"):
                    return block(f"wardrobe repetition and no distinct outfit could be "
                                 f"re-picked: {got.get('why')}", exhausted=True)
                run["outfit_id"] = got["new"]
                _update(db, key, stage=stage, outfit_id=got["new"])
            outs = gen_roles(failing, stage, repairs)
            _update(db, key, stage=stage, status=st, record={
                "outputs": outs, "round": round_, "repairs": repairs,
                "cost_cad": sum(o.get("cost_cad") or 0 for o in outs)})
            return {"run_key": key, "next": go("verification", rnd=round_)}
    except BudgetStop as exc:
        return block(f"budget stop: {exc}", exhausted=True)
    except ConditioningRefused as exc:
        return block(f"conditioning refused: {exc}")
    except CapabilityBlocked as exc:
        return block(str(exc))
    except Exception as exc:  # noqa: BLE001 - a generator refusal is a recorded block
        if type(exc).__name__ in ("GeneratorRefused", "StageRefused"):
            return block(f"generator refused: {type(exc).__name__}: {str(exc)[:400]}")
        raise

    if stage == "gallery_assembly":
        view = readiness(db, run["listing"], run_key_=key,
                         plan=plan if exp is not None else None)
        if exp is not None:
            view = {**view, "experiment": True, "label": exp.label}
            if exp.gallery_builder is not None:
                view["experiment_gallery"] = exp.gallery_builder(db, key)
        _update(db, key, stage=stage, status=st, record={"outputs": view})
        return {"run_key": key, "next": go(_next(stage))}

    if stage == "owner_card":
        view = (data.get("gallery_assembly") or {}).get("outputs") or readiness(
            db, run["listing"], run_key_=key, plan=plan if exp is not None else None)
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
        card["campaign_consistency"] = view.get("campaign_consistency")
        if exp is None and _controlled_of(db, key):
            from ..experiments import controlled as CX
            from . import experiment as XP

            lbl = CX.label_of_run(db, _controlled_of(db, key))
            card.update(experiment=True, label=lbl, controlled_run_id=_controlled_of(
                db, key), certification={"granted": True, "reasons": [
                    "certified release; this gallery is a controlled experiment's output"]},
                publication_blockers=sorted(set(card["publication_blockers"]) | {
                    f"{lbl}: controlled experiment output, never published"}),
                approvals_are_separate={
                    "visual_approval": "the owner's look at these images only",
                    "technical_certification": "the stored verdicts",
                    "publication_authorization": "NOT AVAILABLE: experiments never publish"})
        if exp is not None:
            from . import experiment as XP

            card.update(experiment=True, label=exp.label,
                        certification=exp.reg["certification"],
                        content_hash=exp.reg["release"],
                        pdf_sha256_by_terminology=exp.reg["pdf_sha256_by_terminology"],
                        gallery=view.get("experiment_gallery"),
                        publication_blockers=sorted(set(card["publication_blockers"]) | set(
                            XP.publication_blockers({"experiment": True}))),
                        approvals_are_separate={
                            "visual_approval": "the owner's look at these images only",
                            "technical_certification": "REFUSED: " + "; ".join(
                                exp.reg["certification"]["reasons"])[:300],
                            "publication_authorization": "NOT AVAILABLE: experiments never "
                                                         "publish"})
        if (view.get("campaign_consistency") or {}).get("status") == CG.FAIL:
            not_ready = not_ready or [{"role": "gallery", "candidate": {
                "technical_status": "FAIL",
                "failed": {"campaign_consistency": view["campaign_consistency"]["why"]}}}]
        if exp is not None and not view["set_check"]["ok"]:
            # An experiment asks the owner for a look, not for a listing: the set check is a
            # publication check, reported as a blocker rather than stopping the card.
            card["publication_blockers"] = sorted(set(card["publication_blockers"]) | {
                f"gallery set check: {p.get('kind')}: {p.get('why')}"
                for p in view["set_check"]["problems"]})
        if not_ready or (not view["set_check"]["ok"] and exp is None):
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


# ---- re-verification and restart (W-VISNEXT; OWNERIMG E4) -----------------------------------

def reverify(db, candidate_id: int, *, judges, exp=None) -> dict:
    """Judge one stored candidate's bytes again with `judges`, in place.

    The same image, a new reading: nothing is generated, no attempt is added (attempts are
    counted from candidate rows), and the previous verdict is kept in
    `checks["_reverified"]`. Used when a restart follows a capability change (for example the
    vision judge being funded). UNKNOWN stays UNKNOWN unless the new reading resolves it."""
    from sqlalchemy.orm.attributes import flag_modified

    from ..core.artifacts import ArtifactStore
    from .image_records import ImageCandidate

    with db.session() as s:
        row = s.get(ImageCandidate, candidate_id)
        if row is None or not row.sha256:
            return {"reverified": False, "why": "no stored candidate"}
        cand = {"slug": row.slug, "version": row.version, "release": row.release,
                "role": row.role, "provider": row.provider, "model": row.model,
                "prompt": row.prompt, "references": list(row.references or []),
                "laura_present": row.laura_present, "outfit_id": row.outfit_id or None,
                "listing": row.listing, "provenance_kind": row.provenance_kind,
                "identity_evidence": (row.checks or {}).get("_identity_evidence") or {}}
        prev = {"technical_status": row.technical_status,
                "failure_categories": list(row.failure_categories or []),
                "unknown": sorted(k for k, c in (row.checks or {}).items()
                                  if isinstance(c, dict) and c.get("status") == "UNKNOWN"),
                "history": list(((row.checks or {}).get("_reverified") or {}).get(
                    "history") or [])}
        sha = row.sha256
    try:
        data = ArtifactStore().get(sha, db=db)
    except Exception as exc:  # noqa: BLE001 - bytes gone: nothing can be re-read
        return {"reverified": False, "why": f"bytes unavailable ({type(exc).__name__})"}
    cand = {**cand, "data": data, "sha256": sha}
    if exp is not None:
        cand["experiment"] = True
    if cand["role"] == ANCHOR_ROLE:
        bind = _binding(db, exp, cand["slug"], cand["version"], cand["release"])
        pt = judges.product_truth({**cand}, bind)
        q = CG.quality(data)
        verdict = {"checks": {"binding": bind, "product_truth": pt, "quality": q},
                   "technical_status": CG.worst(bind["status"], pt["status"], q["status"]),
                   "publishable": False, "publication": {},
                   "failure_categories": sorted(
                       {CG.FAILURE_CATEGORY[k] for k, c in (("binding", bind),
                        ("product_truth", pt), ("quality", q)) if c["status"] == CG.FAIL})
                   + [str(c) for c in pt.get("codes") or []]}
    elif cand["role"] == IDENTITY_ANCHOR_ROLE:
        verdict = identity_anchor_verdict(db, cand, judges, _binding(
            db, exp, cand["slug"], cand["version"], cand["release"]))
    else:
        verdict = CG.evaluate(db, cand, judges=judges, record_outfit_use=False)
    tech = verdict["technical_status"]
    with db.session() as s:
        row = s.get(ImageCandidate, candidate_id)
        row.checks = {**verdict["checks"], "_publication": verdict.get("publication") or {},
                      "_identity_evidence": cand["identity_evidence"],
                      "_reverified": {"history": prev["history"] + [{
                          "at": _now().isoformat(), "previous_status": prev["technical_status"],
                          "previous_failure_categories": prev["failure_categories"],
                          "previous_unknown": prev["unknown"]}]}}
        row.technical_status = tech
        row.publishable = bool(verdict["publishable"])
        row.outcome = {"PASS": "accepted", "FAIL": "rejected"}.get(tech, "unverified")
        row.failure_categories = list(verdict.get("failure_categories") or [])
        flag_modified(row, "checks")
        flag_modified(row, "failure_categories")
    return {"reverified": True, "candidate_id": candidate_id, "previous": prev["technical_status"],
            "technical_status": tech}


def _run_candidates_failed(db, key: str, listing: str) -> list[str]:
    """Roles whose best candidate in this run is a technical FAIL."""
    from sqlalchemy import select

    from .image_records import ImageCandidate

    with db.session() as s:
        roles = sorted({r for (r,) in s.execute(select(ImageCandidate.role).where(
            ImageCandidate.run_key == key))})
    return [r for r in roles if (_best(db, listing=listing, role=r, run=key) or {}).get(
        "technical_status") == "FAIL"]


def restartable(db, key: str) -> dict:
    """Whether a blocked run may be restarted, and from which stage.

    Allowed: a run blocked by a missing capability (gate closed, no generator, a check the
    verifier or the vision judge could not read), including an owner-card block whose only
    reason is UNKNOWN. Refused: experiments; budget stops; a run whose best candidate for some
    role FAILed (its attempts are spent; a new release or a repair decides that); more than
    `MAX_RESTARTS`. A restart never resets attempts, generation calls or spend."""
    run = get_run(db, key)
    if run is None:
        return {"restartable": False, "why": "no such run"}
    from . import experiment as XP

    if (run.get("card") or {}).get("experiment") or XP.is_experiment(db, run["slug"],
                                                                       run["version"]):
        return {"restartable": False, "why": f"{XP.LABEL}: an experiment run is one-shot"}
    if "#" in key:
        return {"restartable": False, "why": "a controlled experiment run is one-shot; "
                                             "submit a new run from the Command Center"}
    if run["state"] != "blocked":
        return {"restartable": False, "why": f"run is {run['status']}, not blocked"}
    if run.get("restarts", 0) >= MAX_RESTARTS:
        return {"restartable": False, "why": f"already restarted {run['restarts']} times "
                                             f"(cap {MAX_RESTARTS})"}
    reason = str(run.get("blocked_reason") or "")
    if reason.startswith("budget stop"):
        return {"restartable": False, "why": "a budget stop is final for this run: " + reason}
    failed = _run_candidates_failed(db, key, run["listing"])
    if failed:
        return {"restartable": False, "why": f"FAIL on {failed}: attempts were spent on a "
                                             f"failure, not a missing capability"}
    names = [st for st, _ in STAGES]
    blocked_at = run["stage"] if run["stage"] in names else names[0]
    has_anchor = _best(db, listing=run["listing"], role=ANCHOR_ROLE, run=key) is not None
    if names.index(blocked_at) >= names.index("verification"):
        resume, reverify_ = "verification", True
    elif blocked_at in ("product_generation", "fidelity_gate") and has_anchor:
        resume, reverify_ = "fidelity_gate", True
    elif blocked_at == "identity_anchor" and _best(
            db, listing=run["listing"], role=IDENTITY_ANCHOR_ROLE, run=key) is not None:
        resume, reverify_ = "identity_anchor", True
    else:
        resume, reverify_ = blocked_at, False
    return {"restartable": True, "resume_at": resume, "reverify": reverify_,
            "blocked_at": blocked_at, "blocked_reason": reason,
            "epoch": run.get("restarts", 0) + 1}


def restart(db, key: str, *, follow, by: str, reason: str = "") -> dict:
    """Restart a blocked run under a new epoch (W-VISNEXT; OWNERIMG E4).

    The next job carries `epoch` and its idempotency key ends `:e<epoch>`, so it never collides
    with the first pass; jobs from an older epoch are skipped. Attempts, generation calls and
    spend carry over (the per-role cap and the gallery spend plan still bind), and stored
    candidates are re-verified rather than regenerated where they exist."""
    from sqlalchemy.orm.attributes import flag_modified

    if not str(by or "").strip():
        raise ValueError("a restart names who asked for it")
    can = restartable(db, key)
    if not can["restartable"]:
        return {"restarted": False, **can}
    run = get_run(db, key)
    epoch = can["epoch"]
    with db.session() as s:
        r = _run(s, key)
        st = dict(r.stages or {})
        rec = dict(st.get(RESTART_KEY) or {})
        rec["epoch"] = epoch
        rec["history"] = list(rec.get("history") or []) + [{
            "epoch": epoch, "at": _now().isoformat(), "by": str(by)[:120],
            "reason": str(reason)[:500], "blocked_at": can["blocked_at"],
            "blocked_reason": can["blocked_reason"][:1000], "resume_at": can["resume_at"],
            "reverify": can["reverify"], "generation_calls": r.generation_calls,
            "spent_cad": round(r.spent_cad or 0.0, 4)}]
        st[RESTART_KEY] = rec
        r.stages = st
        flag_modified(r, "stages")
        r.status, r.blocked_reason, r.attempts_exhausted = (STAGE_STATE[can["resume_at"]], "",
                                                            False)
        r.stage = can["resume_at"]
        r.updated_at = _now()
    inputs = {"slug": run["slug"], "version": run["version"], "release": run["release"],
              "stage": can["resume_at"], "round": 0, "epoch": epoch}
    if can["reverify"]:
        inputs["reverify"] = True
    job = follow(inputs, stage_key(run["slug"], run["version"], run["release"],
                                   can["resume_at"], 0, epoch))
    return {"restarted": True, "epoch": epoch, "resume_at": can["resume_at"],
            "reverify": can["reverify"], "enqueued": job is not None, "run_key": key}


# ---- stage A and stage D (W-VISNEXT2) --------------------------------------------------------

def _prior_ref(db, sha: str, label: str) -> dict | None:
    from ..core.artifacts import ArtifactStore

    try:
        data = ArtifactStore().get(sha, db=db)
    except Exception:  # noqa: BLE001 - bytes gone: not handed in
        return None
    return {"kind": "prior_candidate", "label": label, "sha256": sha, "data": data} \
        if data else None


def _accepted_identity_anchor(db, key: str) -> dict | None:
    """The identity anchor this run accepted at stage A (PASS, or owner-confirmed review)."""
    rec = (_stage_data(db, key).get("identity_anchor") or {}).get("outputs") or {}
    sha = rec.get("accepted_sha256")
    return _prior_ref(db, sha, "identity_anchor") if sha else None


def _accepted_lifestyle(db, key: str, listing: str, plan: dict) -> dict | None:
    """The edit base for stage D: the run's best LIFESTYLE frame that no check FAILed and the
    owner did not reject. It is a generation input, not a verdict: the variant made from it is
    judged on its own."""
    roles = [r["role"] for r in SP.generated_roles(plan) if r["job"] == "LIFESTYLE"]
    for role in roles:
        b = _best(db, listing=listing, role=role, run=key)
        if b and b.get("sha256") and b.get("technical_status") != "FAIL" and \
                b.get("owner_visual_approval") is not False:
            return _prior_ref(db, b["sha256"], "edit_base")
    return None


def _drifted_dimensions(best: dict | None, db) -> list[str]:
    from .image_records import ImageCandidate

    if not best:
        return []
    with db.session() as s:
        row = s.get(ImageCandidate, best["candidate_id"])
        body = ((row.checks or {}).get("body_proportions") or {}) if row else {}
    if body.get("status") != "FAIL":
        return []
    return list(body.get("drifted") or ["bust and body proportions"])


def _stage_identity_anchor(db, key, run, inputs, *, gen, judges, exp, laura_roles, st, go,
                           block, refs, laura_refs, slug, version, release) -> dict:
    """Stage A. PASS: accepted and reused. A judged body-proportion drift gets exactly one
    correction pass. FAIL after that: blocked (attempts spent). UNKNOWN: an identity review is
    opened for the owner and the run stops at this gate with every image kept; it resumes only
    after the owner's review (then `restart`), and the review never turns the verdict into a
    PASS: the anchor becomes a reference, nothing more."""
    from . import identity_gate

    stage = "identity_anchor"
    if not laura_roles or exp is not None or not getattr(gen, "accepts_staged_method", False):
        why = ("no Laura in this listing's shot plan" if not laura_roles else
               "EXPERIMENT: the owner-approved plan has no stage A" if exp is not None else
               "the generator does not carry the staged method")
        _update(db, key, stage=stage, status=st, record={"outputs": {"skipped": why}})
        return {"run_key": key, "next": go(_next(stage))}
    outfit = outfits.get(db, run["outfit_id"]) if run["outfit_id"] else None
    if not outfit:
        return block("stage A needs the listing's reserved outfit")
    best = _best(db, listing=run["listing"], role=IDENTITY_ANCHOR_ROLE, run=key)
    if best and inputs.get("reverify"):
        reverify(db, best["candidate_id"], judges=judges, exp=exp)
        best = _best(db, listing=run["listing"], role=IDENTITY_ANCHOR_ROLE, run=key)

    def generate(repair=None):
        n = _attempts(db, key, IDENTITY_ANCHOR_ROLE) + 1
        return _generate(db, key, gen, slug=slug, version=version, release=release,
                         role=IDENTITY_ANCHOR_ROLE, stage=stage, laura=True, judges=judges,
                         brief="Laura alone in the listing's outfit", outfit=outfit,
                         refs=refs() + laura_refs(), plan_attempt=n, repair=repair, exp=exp)

    if best is None:
        got = generate()
        if got.get("provider_error"):
            return block(f"identity anchor: provider error {got['provider_error']}")
        best = _best(db, listing=run["listing"], role=IDENTITY_ANCHOR_ROLE, run=key)
    drift = _drifted_dimensions(best, db)
    if drift and _attempts(db, key, IDENTITY_ANCHOR_ROLE) < MAX_IDENTITY_ANCHOR_ATTEMPTS:
        generate(repair={"correction": drift, "codes": ["body_proportion_drift"],
                         "directives": []})
        best = _best(db, listing=run["listing"], role=IDENTITY_ANCHOR_ROLE, run=key)
    status = (best or {}).get("technical_status", "UNKNOWN")
    record = {"evidence": best}
    if status == "PASS":
        _update(db, key, stage=stage, status=st, record={
            **record, "outputs": {"accepted_sha256": best["sha256"], "basis": "PASS"}})
        return {"run_key": key, "next": go(_next(stage))}
    if status == "FAIL":
        return block(f"identity anchor FAIL after {_attempts(db, key, IDENTITY_ANCHOR_ROLE)} "
                     f"attempt(s) (one proportion correction at most): {best.get('failed')}",
                     exhausted=True, record=record)
    # UNKNOWN: the owner reviews the anchor (identity review band), never auto-passed.
    review = _anchor_review(db, best["sha256"])
    if review and review.get("decision") == "confirmed_same_person":
        _update(db, key, stage=stage, status=st, record={
            **record, "outputs": {"accepted_sha256": best["sha256"],
                                  "basis": "owner review confirmed_same_person; the anchor is "
                                           "identity context only, its verdict stays UNKNOWN",
                                  "review_id": review["id"]}})
        return {"run_key": key, "next": go(_next(stage))}
    if review and review.get("decision") in ("not_laura",):
        return block("identity anchor: the owner's review says not Laura", exhausted=True,
                     record=record)
    gate = {"review_required": True, "band": identity_gate.BAND_REVIEW,
            "why": f"identity anchor UNKNOWN on {best.get('unknown')}",
            "validity": None, "biometric": None, "judges": []}
    rid = identity_gate.open_review(db, product_class="laura_identity_anchor",
                                    subject=f"{key}:identity_anchor", gate=gate,
                                    image_sha256=best["sha256"])
    return block(f"identity anchor UNKNOWN ({best.get('unknown')}): held for owner review "
                 f"(identity review {rid}); every image so far is kept", record={
                     **record, "outputs": {"review_id": rid}})


def _anchor_review(db, sha: str) -> dict | None:
    """The latest identity review of this anchor's bytes, open or resolved."""
    from sqlalchemy import desc, select

    from .rnd import models as M

    if not M.tables_exist(db):
        return None
    with M.session(db) as s:
        r = s.scalar(select(M.VisualIdentityReview).where(
            M.VisualIdentityReview.image_sha256 == sha[:64])
            .order_by(desc(M.VisualIdentityReview.id)))
        return ({"id": r.id, "state": r.state, "decision": r.decision or None}
                if r is not None else None)


def resolve_identity_anchor_review(db, key: str, *, decision: str, by: str, note: str = "",
                                   follow=None) -> dict:
    """The owner's review of a held identity anchor, then (if confirmed) a restart.

    `confirmed_same_person` lets the anchor be used as identity context; it does not make
    any verdict PASS. `not_laura` ends the run's stage A. `inconclusive` keeps it held."""
    from . import identity_gate

    run = get_run(db, key)
    if run is None:
        return {"resolved": False, "why": "no such run"}
    best = _best(db, listing=run["listing"], role=IDENTITY_ANCHOR_ROLE, run=key)
    review = _anchor_review(db, best["sha256"]) if best else None
    if not review or review["state"] != "open":
        return {"resolved": False, "why": "no open identity review for this run's anchor"}
    out = identity_gate.resolve(db, review["id"], decision=decision, reviewer=by, note=note)
    restarted = None
    if decision in ("confirmed_same_person", "not_laura") and follow is not None:
        restarted = restart(db, key, follow=follow, by=by,
                            reason=f"identity anchor review: {decision}")
    return {"resolved": True, **out, "restart": restarted}


def _repick_outfit(db, listing: str, current: str) -> dict:
    """WARDROBE_REPETITION repair: a new distinct complete outfit, the current one excluded,
    replacing it for this listing. The old one stays bound to the listing (retired)."""
    from . import styling

    styled = styling.select_for_listing(db, listing, exclude=[current])
    o = styled.get("outfit")
    if not o:
        return {"replaced": False, "why": styled.get("why")}
    try:
        outfits.register(db, outfit_id=o["outfit_id"], garments=o["garments"],
                         colours=o["colours"], concept=styled["concept"])
        outfits.approve(db, o["outfit_id"],
                        approved_by=f"creative_director:{styling.STYLING_VERSION}")
    except outfits.OutfitRefused as exc:
        return {"replaced": False, "why": str(exc)}
    return outfits.replace(db, current, o["outfit_id"], listing)


def _repair_for(best: dict | None) -> dict | None:
    """Targeted repair for a failed candidate, or None when it cannot be repaired by
    regeneration (an unrouted code). Codes from the shared Product Truth set route to prompt
    negatives or a reference change. Other failures (identity, outfit, body proportions,
    quality) are regenerated with the same canonical references, and nothing is waived."""
    from . import repair_routes

    cats = list((best or {}).get("failure_categories") or [])
    shared = set(repair_routes.shared_codes()["codes"]) | set(repair_routes.ROUTES)
    codes = [c for c in cats if c in shared or c.isupper()]
    routed = repair_routes.route(codes)
    if routed["unrouted"]:
        return None
    return {"codes": codes, "directives": routed["directives"],
            "stays_unknown": routed["stays_unknown"],
            "regenerate_for": sorted(set(cats) - set(codes))}


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

def readiness(db, listing: str, *, run_key_: str | None = None, plan: dict | None = None) -> dict:
    """The shot plan with what fills each role, the set check and publication blockers."""
    from ..gates.asset_truth import AssetClass
    from ..publish import eligibility as el

    plan = plan or SP.campaign_plan(listing)
    roles, set_cands, blockers, chosen = [], [], set(), []
    for r in plan["roles"]:
        entry = {"position": r["position"], "role": r["role"], "job": r["job"],
                 "campaign_role": r.get("campaign_role"), "laura": r.get("laura"),
                 "required_by": r["required_by"], "conditional": r["conditional"],
                 "preferred_source": r["preferred_source"]}
        best = None
        if r.get("generate"):
            best = _best(db, listing=listing, role=r["role"], run=run_key_) or \
                (_best(db, listing=listing, role=r["role"]) if run_key_ else None)
            if best is not None:
                chosen.append(best)
                for b in best.get("blockers") or []:
                    blockers.add(b)
        if best is not None and best["publishable"]:
            entry.update(source="generated", candidate=best, status="publishable")
            set_cands.append(el.Candidate(asset_id=f"{listing}-{r['role']}", medium=CG.MEDIUM,
                                          purpose=el.CONVERSION_CREATIVE, job=r["job"],
                                          position=r["position"]))
        elif r["sources"][SP.DISCLOSED] == SP.SATISFIES:
            entry.update(source="generated" if r.get("generate") else "disclosed_render",
                         candidate=best,
                         status=("disclosed set (certified by the existing listing-set "
                                 "certificate path)" + (
                                     f"; generated candidate {best['technical_status']}, "
                                     f"not publishable" if best else
                                     "; generated candidate missing" if r.get("generate")
                                     else "")),
                         fallback="disclosed_render")
            medium, purpose = r["disclosed_medium"]
            set_cands.append(el.Candidate(asset_id=f"{listing}-{r['role']}",
                                          medium=AssetClass(medium), purpose=purpose,
                                          job=r["job"], position=r["position"]))
        else:
            entry.update(source="generated" if r.get("generate") else r["preferred_source"],
                         candidate=best,
                         status=("missing" if best is None else
                                 f"candidate {best['technical_status']}, not publishable"))
        if r.get("gap"):
            entry["gap"] = r["gap"]
        roles.append(entry)
    set_check = el.check_set(set_cands) if set_cands else {"ok": False, "problems": [
        {"kind": "no_valid_frames"}]}
    consistency = CG.campaign_consistency(chosen) if chosen else CG._c(
        CG.NA, "no generated images yet")
    return {"listing": listing, "category": plan["category"], "roles": roles,
            "image_count": plan["image_count"],
            "set_check": {"ok": set_check["ok"], "problems": set_check["problems"]},
            "campaign_consistency": consistency,
            "ruling_conflicts": plan.get("ruling_conflicts") or [],
            "publication_blockers": sorted(blockers),
            "gallery_ready": all(e["status"].startswith(("disclosed", "publishable"))
                                 for e in roles) and consistency["status"] != CG.FAIL,
            "basis": "visual.shot_plans.campaign_plan + candidate_gates + eligibility.check_set"}


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
            if "held for owner review" in (r.blocked_reason or ""):
                # W-VISNEXT2: stage A needs the owner's identity review; that is a decision
                # only the owner can make, so it is notified (once per epoch).
                ep = int(((r.stages or {}).get(RESTART_KEY) or {}).get("epoch") or 0)
                out.append({
                    "dedupe_key": f"image_identity_review:{r.run_key}:e{ep}",
                    "severity": "normal", "category": "decision",
                    "title": f"Laura identity anchor needs your review: {r.listing}"[:300],
                    "body": (f"{r.blocked_reason}. Confirming lets the anchor be used as "
                             f"identity context; it never makes any check PASS.")[:1000],
                    "consequence": "Laura frames for this listing wait until you review",
                    "evidence": [f"image_production_runs:{r.id}"],
                    "deep_link": f"/cc/#/images/{r.listing}", "count": 1})
            continue
        ready = r.status == "ready_for_owner_review"
        card = dict(r.card or {})
        if not card.get("experiment"):
            from . import experiment as XP

            if XP.is_experiment(db, r.slug, r.version):
                # stopped before the card stage (e.g. at the fidelity gate): still stamped
                reg = (XP._opened(db, r.slug, r.version) or [{}])[-1]
                card = {**card, "experiment": True, "label": XP.LABEL,
                        "certification": reg.get("certification") or {}}
        if card.get("experiment"):
            # W4-WRAPTEST: the experiment's card, stamped; it asks for a look, never for
            # publication.
            out.append({
                "dedupe_key": f"image_gallery:{r.run_key}:{r.status}:experiment",
                "severity": "normal", "category": "decision",
                "title": (f"{card.get('label')}: gallery "
                          f"{'ready for your look' if ready else 'stopped'}: {r.listing}")[:300],
                "body": (f"{card.get('label')}. Visual approval only. Pattern certification: "
                         + ("granted (certified release)" if (card.get("certification") or {})
                            .get("granted") else
                            f"REFUSED ({'; '.join((card.get('certification') or {}).get('reasons') or [])[:300]})")
                         + ". "
                         f"Publication authorization: not available for an experiment. "
                         + ("" if ready else f"Stopped: {r.blocked_reason}"))[:1000],
                "consequence": ("nothing publishes: an experiment can never reach "
                                "store.publish, export or listing approval")[:1000],
                "evidence": [f"image_production_runs:{r.id}"],
                "deep_link": f"/cc/#/images/{r.listing}", "count": 1})
            continue
        ep = int(((r.stages or {}).get(RESTART_KEY) or {}).get("epoch") or 0)
        out.append({
            # a restarted run that reaches the same state again is news again
            "dedupe_key": f"image_gallery:{r.run_key}:{r.status}" + (f":e{ep}" if ep else ""),
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
    from . import experiment as XP

    if (run.get("card") or {}).get("experiment"):
        XP.refuse_if_experiment(db, run["slug"], run["version"], action="listing approval")
        raise XP.ExperimentRefused(f"{XP.LABEL}: an experiment run is never approved for "
                                   f"publication")
    XP.refuse_if_experiment(db, run["slug"], run["version"], action="listing approval")
    XP.refuse_if_experiment_image(db, [((r.get("candidate") or {}).get("sha256"))
                                       for r in (run.get("card") or {}).get("roles") or []],
                                  action="listing approval")
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
        r.owner_decision = {**dict(r.owner_decision or {}), **decision, "approved_look": True,
                            "publication_requested": True}
        flag_modified(r, "owner_decision")
        if not blockers:
            r.status = "approved_for_publication"
    if blockers:
        return {"approved": False, "owner_look_recorded": True,
                "why": "publication gates still block; approval is recorded but cannot "
                       "override them", "blockers": decision["blockers"]}
    # W-VISNEXT (OWNERIMG E5): the approved frames go to ListingAsset only after a fresh
    # re-verification, and the set is re-certified by release_gates.listing_set.
    from .gallery_persist import persist_approved

    return {"approved": True, "state": "approved_for_publication",
            "listing_assets": persist_approved(db, key)}


def record_visual_approval(db, key: str, *, decided_by: str, approved: bool,
                           note: str = "") -> dict:
    """The owner's look at the images, recorded on its own (W-VISNEXT gallery card).

    It is not technical certification and not publication authorization: no gate reads it,
    the run's state does not change, and `approve` (the publication decision, step-up) still
    re-checks every gate."""
    from sqlalchemy.orm.attributes import flag_modified

    if not str(decided_by or "").strip():
        raise ValueError("a visual approval names who decided")
    run = get_run(db, key)
    if run is None:
        return {"recorded": False, "why": "no such run"}
    if run["state"] not in ("ready_for_owner_review", "blocked", "approved_for_publication"):
        return {"recorded": False, "why": f"run is {run['status']}: no gallery to look at yet"}
    entry = {"approved_look": bool(approved), "by": str(decided_by)[:120],
             "at": _now().isoformat(), "note": str(note or "")[:1000],
             "is_technical_certification": False, "is_publication_authorization": False}
    with db.session() as s:
        r = _run(s, key)
        od = dict(r.owner_decision or {})
        od["visual"] = entry
        od["visual_history"] = list(od.get("visual_history") or []) + [entry]
        r.owner_decision = od
        flag_modified(r, "owner_decision")
    return {"recorded": True, "visual_approval": entry, "state": run["state"]}


def _anchor_card(db, key: str, run: dict) -> dict | None:
    """Stage A's anchor as the card shows it: the image, its verdict and any owner review."""
    b = _best(db, listing=run["listing"], role=IDENTITY_ANCHOR_ROLE, run=key)
    if not b:
        return None
    review = _anchor_review(db, b["sha256"]) if b.get("sha256") else None
    return {"image_url": f"/api/cc/images/candidates/{b['candidate_id']}/image",
            "sha256": b["sha256"], "technical_status": b["technical_status"],
            "unknown": b.get("unknown") or [], "failed": b.get("failed") or {},
            "review": review, "attempts": _attempts(db, key, IDENTITY_ANCHOR_ROLE),
            "label": "Laura identity anchor (intermediate reference, never a gallery frame)",
            "review_needed": bool(review and review.get("state") == "open")}


def gallery_card(db, key: str) -> dict | None:
    """The Command Center gallery approval card: every frame with its image, and three
    decisions kept apart (W-VISNEXT).

    * visual approval: the owner's look (`record_visual_approval`); never a gate input;
    * technical certification: every generated frame's technical verdict, the set check and
      campaign consistency, from the stored candidates;
    * publication authorization: available only when no publication blocker remains, and
      then only through `approve` (step-up), which re-checks every gate."""
    run = get_run(db, key)
    if run is None:
        return None
    card = dict(run.get("card") or {})
    roles = card.get("roles")
    if roles is None:   # no card yet (blocked earlier): show what candidates exist
        try:
            roles = readiness(db, run["listing"], run_key_=key)["roles"]
        except Exception:  # noqa: BLE001 - no plan: no roles to show
            roles = []
    frames, tech = [], []
    for r in roles or []:
        c = r.get("candidate") or {}
        img = (f"/api/cc/images/candidates/{c['candidate_id']}/image"
               if c.get("candidate_id") and c.get("sha256") else None)
        frames.append({"position": r.get("position"), "role": r.get("role"),
                       "job": r.get("job"), "source": r.get("source"),
                       "status": r.get("status"), "laura": r.get("laura"),
                       "image_url": img, "sha256": c.get("sha256"),
                       "technical_status": c.get("technical_status"),
                       "failed": c.get("failed") or {}, "unknown": c.get("unknown") or [],
                       "fidelity": c.get("fidelity") or {},
                       "label": "AI-generated concept image, never a photograph"
                       if img else None})
        if r.get("source") == "generated" and c:
            tech.append(c.get("technical_status") or "UNKNOWN")
    blockers = sorted(set(card.get("publication_blockers") or []))
    tech_status = CG.worst(*tech) if tech else CG.UNKNOWN
    set_ok = (card.get("set_check") or {}).get("ok")
    od = dict(run.get("owner_decision") or {})
    visual = od.get("visual")
    experiment = bool(card.get("experiment"))
    pub_available = (run["state"] == "ready_for_owner_review" and not blockers and not
                     experiment and tech_status == CG.PASS and bool(set_ok))
    return {
        "run_key": key, "listing": run["listing"], "slug": run["slug"],
        "version": run["version"], "release": run["release"], "state": run["state"],
        "status": run["status"], "experiment": experiment, "label": card.get("label"),
        "frames": frames, "spent_cad": run["spent_cad"],
        "generation_calls": run["generation_calls"], "restarts": run.get("restarts", 0),
        "restartable": restartable(db, key) if run["state"] == "blocked" else
        {"restartable": False, "why": f"run is {run['status']}"},
        "outfit_id": run.get("outfit_id"),
        "identity_anchor": _anchor_card(db, key, run),
        "decisions": {
            "visual_approval": {
                "state": ("approved" if visual and visual.get("approved_look") else
                          "rejected" if visual else "not_recorded"),
                "record": visual, "affects_gates": False,
                "what": "your look at these images only"},
            "technical_certification": {
                "state": tech_status, "set_check": card.get("set_check"),
                "campaign_consistency": card.get("campaign_consistency"),
                "certification": card.get("certification"),
                "what": "automated verification of every generated frame; UNKNOWN is never "
                        "PASS and your approval cannot change it"},
            "publication_authorization": {
                "state": ("approved" if run["state"] == "approved_for_publication" else
                          "available" if pub_available else "not_available"),
                "blockers": blockers,
                "requires": "step-up; every gate is re-checked at the moment you approve",
                "what": "whether these frames may go to the listing"}},
        "recommended_fix": card.get("recommended_fix") or []}

