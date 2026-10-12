"""Progressive Authority (F-669) and Build vs Operate Separation (F-497).

Every action the company can take is one of eleven classes. Five are the company's own
initiative and run autonomously inside the existing permission layer; six are consequential
external or irreversible actions and are *gated*: an agent runs one only when the code
declares that agent for it with a non-GREEN grade, or when the owner has recorded an
`AuthorityPolicy` for it (`authority.policy`). Nothing an agent does can move a job type from
one class to another: the table is code, reviewed like code, and a test asserts every job type
the runtime knows is in it.

Classification fails closed. A job type missing from the table is classified by the words in
its name, and any consequential word (publish, activate, spend, refund, credential, deploy,
tax...) makes it gated. Only a name with no consequential word and no table entry is
`UNCLASSIFIED`, which is never gated-by-default autonomy: `policy.check_dispatch` treats it as
ordinary (non-consequential) work, and the coverage test keeps production job types out of it.
"""
from __future__ import annotations

import enum
import re


class ActionClass(str, enum.Enum):
    OBSERVE = "OBSERVE"
    RESEARCH = "RESEARCH"
    BUILD = "BUILD"
    TEST = "TEST"
    DRAFT = "DRAFT"
    DEPLOY = "DEPLOY"
    SPEND = "SPEND"
    PUBLISH = "PUBLISH"
    LEGAL_TAX = "LEGAL-TAX"
    CUSTOMER_REMEDY = "CUSTOMER-REMEDY"
    CREDENTIALS = "CREDENTIALS"


ALL_CLASSES: tuple[ActionClass, ...] = tuple(ActionClass)
AUTONOMOUS: frozenset[ActionClass] = frozenset({
    ActionClass.OBSERVE, ActionClass.RESEARCH, ActionClass.BUILD, ActionClass.TEST,
    ActionClass.DRAFT})
GATED: frozenset[ActionClass] = frozenset(set(ActionClass) - AUTONOMOUS)
# Irreversible enough that the earned-autonomy ladder never rises above "owner approves each"
# (F-703: "begin with conservative authority for irreversible/external actions").
LADDER_CAPPED: frozenset[ActionClass] = frozenset({
    ActionClass.DEPLOY, ActionClass.LEGAL_TAX, ActionClass.CREDENTIALS})

UNCLASSIFIED = "UNCLASSIFIED"

_O, _R, _B, _T, _D = (ActionClass.OBSERVE, ActionClass.RESEARCH, ActionClass.BUILD,
                      ActionClass.TEST, ActionClass.DRAFT)

# The explicit table. Each entry is the handler's declared effect, not a guess from its name.
JOB_CLASS: dict[str, ActionClass] = {
    # gated: the consequential external actions
    "store.publish": ActionClass.PUBLISH, "store.activate": ActionClass.PUBLISH,
    "store.update": ActionClass.PUBLISH,
    "pricing.experiment": ActionClass.PUBLISH,       # changes a live price
    "ads.campaign": ActionClass.SPEND, "ads.adjust": ActionClass.SPEND,
    "support.reply": ActionClass.CUSTOMER_REMEDY,    # a message/remedy to a customer
    # observe: reads state, writes readings/snapshots only
    "autonomy.department_review": _O, "commerce.order_readings": _O,
    "commerce.orders_ingest": _O, "commerce.readings": _O,
    "etsy.credential_health": _O, "etsy.listing_census": _O, "etsy.probe": _O,
    "etsy.shop_snapshot": _O, "etsy.openapi_reverify": _O, "store.live_drift": _O,
    "finance.accounting.cycle": _O, "finance.challenge": _O,
    "finance.escalation_check": _O, "finance.governor": _O, "finance.reconcile": _O,
    "growth.journey": _O, "improve.measure": _O, "improve.monitor": _O,
    "launch.readiness": _O, "listing.outcomes": _O, "listing.search_visibility_watch": _O,
    "marketing.ads_readiness": _O, "ops.capacity": _O, "ops.dependencies": _O,
    "ops.health": _O, "ops.heartbeat": _O, "ops.maturity_disagreements": _O,
    "ops.policy_watch": _O, "ops.provenance_backfill": _O, "ops.queue_check": _O,
    "ops.sentinel": _O, "ops.slo": _O, "ops.thrash": _O, "physical.photo": _O,
    "physical.record": _O, "physical.upgrade_impact": _O, "portfolio.review": _O,
    "seasonal.harvest": _O, "seasonal.sentinel": _O, "swarm.review": _O,
    "visual.identity_drift": _O, "mjs.seasonal_sentinel": _O,
    # research: intelligence, learning, measurement experiments that change nothing live
    "creative.benchmark_memory": _R, "creative.blind_review": _R, "creative.blinded": _R,
    "creative.expedition": _R, "creative.four_season": _R, "creative.grid_tournament": _R,
    "creative.image_benchmark": _R, "creative.model_reference_pack": _R,
    "creative.model_tournament": _R, "creative.north_star": _R,
    "creative.outcome_learning": _R, "creative.photoreal_calibration": _R,
    "creative.reference_reading": _R, "creative.style_learning": _R,
    "creative.tournament": _R, "creative.white_space": _R, "culture.sweep": _R,
    "improve.mine": _R, "improve.retrospective": _R, "intel.acceptance": _R,
    "intel.benchmark_health": _R, "intel.benchmark_refresh": _R,
    "intel.gallery_analysis": _R, "intel.panel_discovery": _R, "intel.pod_learning": _R,
    "intel.serp_capture": _R, "learn.scan": _R, "listing.taxonomy_refresh": _R,
    "mjs.reviews": _R, "mjs.scan": _R, "pricing.position": _R,
    "radar.competitor_snapshot": _R, "radar.scan": _R, "radar.score": _R,
    "scale.trajectory": _R, "visual.provider_trial": _R, "visual.rnd.cycle": _R,
    # build: internal artefacts, code/config/process changes, work generation
    "assets.build": _B, "assets.model_photography": _B, "assets.owned_photography": _B,
    "assets.physical_upgrade": _B, "assets.render": _B, "autonomy.orchestrate": _B,
    "build.tick": _B, "chain.rebuild": _B, "cir.draft": _B, "cir.revise": _B,
    "collection.assemble": _B, "creative.candidates_file": _B, "creative.model_freeze": _B, "growth.steer": _B,
    "improve.nightly": _B, "improve.role_work": _B, "improve.weekly": _B,
    "laura.executive_tick": _B, "ops.offsite_archive": _B, "ops.retention": _B,
    "plan.cycle": _B, "seasonal.cycle_proof": _B, "seasonal.engine": _B,
    "swarm.allocate": _B, "swarm.backlog": _B, "swarm.orphans": _B,
    "teardown.enforce": _B, "visual.portrait_repair": _B,
    # test: validation, certification, sandbox trials, probes
    "cir.compile": _T, "cir.reverse": _T, "cir.twin": _T, "gate.asset_truth": _T,
    "gate.certify": _T, "gate.lanes": _T, "gate.policy": _T, "gate.quality": _T,
    "growth.conclude": _T, "growth.experiments": _T, "improve.league": _T,
    "improve.replay": _T, "improve.sandbox": _T, "model.probe": _T,
    "ops.capability_probes": _T, "ops.continuity": _T,
    # draft: prepares public/customer-facing material; publishes nothing
    "autonomy.morning_handoff": _D, "content.draft": _D, "finance.accounting.period_pack": _D,
    "growth.distribution": _D, "growth.preproduction": _D, "launch.plan": _D,
    "listing.draft": _D, "listing.seo": _D, "marketing.schedule": _D, "plan.strategy": _D,
    "seasonal.remerchandising": _D, "seo.cycle": _D, "support.triage": _D,
}

# Name words that make an unlisted job type consequential. Ordered: the first class whose
# words appear wins, most restrictive first.
_GATED_WORDS: tuple[tuple[ActionClass, tuple[str, ...]], ...] = (
    (ActionClass.CREDENTIALS, ("credential", "credentials", "secret", "secrets", "oauth",
                               "apikey", "api_key", "password", "rotate_key")),
    (ActionClass.LEGAL_TAX, ("tax", "taxes", "gst", "hst", "legal", "contract", "kyc",
                             "filing", "file_return", "terms")),
    (ActionClass.DEPLOY, ("deploy", "deployment", "release_prod", "promote_phase",
                          "phase_transition", "railway")),
    (ActionClass.SPEND, ("spend", "ads", "ad", "campaign", "bid", "purchase", "buy", "pay",
                         "payout", "transfer", "bank", "banking")),
    (ActionClass.CUSTOMER_REMEDY, ("refund", "remedy", "compensate", "compensation",
                                   "chargeback", "reply", "message_customer", "email")),
    (ActionClass.PUBLISH, ("publish", "activate", "listing_update", "go_live", "post",
                           "unpublish", "deactivate", "price_change", "reprice")),
)


def _words(job_type: str) -> list[str]:
    low = (job_type or "").lower()
    parts = re.split(r"[.\-\s]+", low)
    return parts + [w for p in parts for w in p.split("_")]


def classify(job_type: str) -> ActionClass | str:
    """The class of a job type: the table, else consequential words, else UNCLASSIFIED."""
    jt = (job_type or "").strip()
    if jt in JOB_CLASS:
        return JOB_CLASS[jt]
    words = set(_words(jt))
    for cls, needles in _GATED_WORDS:
        if words & set(needles):
            return cls
    return UNCLASSIFIED


def is_gated(job_type: str) -> bool:
    cls = classify(job_type)
    return isinstance(cls, ActionClass) and cls in GATED


def class_value(job_type: str) -> str:
    cls = classify(job_type)
    return cls.value if isinstance(cls, ActionClass) else str(cls)


# ---- F-497: build plane vs operate plane --------------------------------------------------
#
# Development (build-plane) work changes the company itself: its code, configuration,
# thresholds, prompts and process (the improvement loop's sandbox and promotions, the
# Build-2 executor). Operating work changes the world: publication, spend, customer remedies,
# credentials, legal/tax positions, deploys. One agent may never hold both, so a defect or a
# runaway in the improvement loop cannot publish, spend or message anyone, and an operator
# cannot rewrite the rules it operates under. DEPLOY is held by no agent at all: a production
# deploy is the owner's `production_deploy` gate.
BUILD_PLANE_JOB_TYPES: frozenset[str] = frozenset({
    "build.tick", "improve.sandbox", "improve.nightly", "improve.weekly",
    "improve.role_work", "improve.league", "improve.replay", "teardown.enforce"})


def plane_of(job_type: str) -> str:
    if job_type in BUILD_PLANE_JOB_TYPES:
        return "build"
    return "operate" if is_gated(job_type) else "internal"


def plane_violations(agents: list[dict]) -> list[str]:
    """Declared agents that hold both a build-plane change type and a gated operate type,
    or that hold DEPLOY at all."""
    out: list[str] = []
    for a in agents:
        types = set(a.get("allowed_job_types") or ())
        build = sorted(types & BUILD_PLANE_JOB_TYPES)
        operate = sorted(t for t in types if is_gated(t))
        if build and operate:
            out.append(f"{a['name']}: build-plane {build} with operate-plane {operate}")
        deploy = sorted(t for t in types if classify(t) == ActionClass.DEPLOY)
        if deploy:
            out.append(f"{a['name']}: holds DEPLOY {deploy}; deploy is owner-only")
    return out


def runtime_role(env: dict | None = None) -> str:
    """`build` for a development/build runtime (BRAMBLELOOP_RUNTIME_ROLE=build), else
    `operate`. A build runtime may never execute a gated class, whatever its database says."""
    import os

    raw = ((env if env is not None else os.environ).get("BRAMBLELOOP_RUNTIME_ROLE") or "")
    return "build" if raw.strip().lower() == "build" else "operate"


def describe() -> dict:
    return {"classes": [c.value for c in ALL_CLASSES],
            "autonomous": sorted(c.value for c in AUTONOMOUS),
            "gated": sorted(c.value for c in GATED),
            "ladder_capped": sorted(c.value for c in LADDER_CAPPED),
            "build_plane_job_types": sorted(BUILD_PLANE_JOB_TYPES),
            "classified_job_types": len(JOB_CLASS)}
