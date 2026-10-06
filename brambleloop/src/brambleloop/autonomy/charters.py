"""The eleven department charters (F-890, F-892, F-918).

Each charter is the department's explicit contract: mission, the agents that staff it, the job
types it owns, the work the Executive Orchestrator may generate for it when it is idle, the
actions it may never take on its own, its inputs, outputs, KPIs (each with anti-gaming
guardrails), escalation rule, evidence requirement and the departments it hands off to.

Authority cannot silently expand: `generatable` is a closed allowlist checked again at the
enqueue boundary (`orchestrator._enqueue_mission`), every generatable job type must be one a
registered GREEN-or-drafting agent already holds, and no protected job type may ever appear in
it (`validate()` refuses at import, and a test asserts it).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Job types that publish, activate, spend, message a customer, or change price live. The
# orchestrator never enqueues these; a candidate that would need one becomes an owner approval
# item instead (F-929, F-930).
PROTECTED_JOB_TYPES: frozenset[str] = frozenset({
    "store.publish", "store.activate", "store.update",
    "ads.campaign", "ads.adjust",
    "support.reply",
    "pricing.experiment",
})

# Job types the orchestrator may generate from idleness, with the reason each is safe. Every
# entry is deterministic or a read of stored rows, spends no model/ad money and makes no
# external write. The reason is the handler's own declared authority, quoted from its
# docstring or cadence comment in runtime/*.py, not a guess.
SAFE_GENERATED: dict[str, str] = {
    "autonomy.department_review": "reads jobs/memory, writes KPI snapshot + lessons; no spend",
    "autonomy.morning_handoff": "reads jobs/costs/incidents/owner actions, writes a brief",
    "scale.trajectory": "nightly scenario analysis over stored orders; no external call",
    "radar.score": "scores the coverage gap queue; listed non-spending in swarm BACKLOG_JOBS",
    "intel.benchmark_refresh": "benchmark refresh recommendations; cadence comment: 'free'",
    "intel.pod_learning": "pod capability readings from stored observations",
    "seasonal.sentinel": "docstring: 'publishes nothing, spends nothing, contacts nobody'",
    "creative.outcome_learning": "read-only learner over recorded outcomes (#82/#89)",
    "ops.sentinel": "docstring: 'changes no artefact and spends nothing'",
    "physical.upgrade_impact": "reads physical-proof readings; UNMEASURED until listings live",
    "visual.identity_drift": "docstring: 'GREEN: reads audit rows, writes a reading'",
    "seasonal.remerchandising": "cadence comment: 'free ... changes no listing'",
    "support.triage": "drafts only; replies stay drafts (protected_phase) and are never sent "
                      "by this job",
    "finance.reconcile": "books from observed entries only; writes audit",
    "commerce.readings": "daily readings of gated commerce machinery (read-only)",
    "commerce.order_readings": "reads stored orders",
    "finance.escalation_check": "reads the ledger, writes at most one owner action a month",
    "growth.journey": "buyer-journey audit from the database (GREEN)",
    "growth.distribution": "distribution planning from the database (GREEN)",
    "growth.conclude": "concludes registered experiments from stored readings",
    "improve.mine": "docstring: 'reads incidents, refusals and dead letters; writes lessons'",
    "improve.retrospective": "weekly retrospective over stored improvements; no model",
    "improve.measure": "one deterministic query per capability cell",
    "ops.queue_check": "re-drives fixed dead letters once per deploy; reads the queue",
    "ops.maturity_disagreements": "completion claims vs maturity measurement (read-only)",
    # v1.1 integrator wiring: the lane cycles, each GREEN by its handler's docstring.
    "seo.cycle": "seo.handler: 'No external effect: reads the database and writes only seo_* "
                 "rows and one audit row'",
    "finance.accounting.cycle": "finance.accounting.job: 'GREEN: reads and writes rows only, "
                                "spends nothing, messages nobody, makes no network call'",
    "marketing.ads_readiness": "runtime.v11_wiring: eligibility re-evaluated; spends and "
                               "activates nothing (refuses if it ever reports either)",
    "ops.slo": "ops.slo.check: 'The only side effect is incident rows'",
    # W3 lane D wiring for lane H: the Visual R&D cycle. Deterministic renders and rows only;
    # paid challengers are planned (queued for an owner decision), never executed; the handler
    # refuses if a cycle ever reports a paid execution.
    "visual.rnd.cycle": "autonomy.visual_rnd_job: deterministic, CA$0, no network; paid arms "
                        "are only planned for the owner",
    # W3 lane D, closure K15 (F-909/F-916): the accountant's tax pack and handoff pack built
    # for the last closed month as a memory record. Preparation only: files nothing, writes no
    # file, moves no money.
    "finance.accounting.period_pack": "autonomy.period_packs: tax_pack.pack + handoff.pack "
                                      "read the books; one company_memory row; files nothing",
    "improve.sandbox": "docstring: 'Spends nothing and calls no model'; promotes only a "
                       "pre-authorised tier, every other tier goes to the owner queue",
    "improve.monitor": "docstring: 'GREEN: reads capability points, may revert an "
                       "improvement row, writes an audit record'",
    "learn.scan": "learn agent: 'no publication/spend', CA$0 ceiling",
}


@dataclass(frozen=True)
class KPI:
    key: str
    description: str
    direction: str            # "up" | "down"
    reads: str
    # Anti-gaming (F-918): what makes the reading VOID rather than good, whatever its value.
    guardrails: tuple[str, ...] = ()


@dataclass(frozen=True)
class Handoff:
    """A durable producer -> consumer link: rows newer than the consumer's last successful run
    of `consumer_job_type` are evidence the consumer department has work."""

    table: str                 # core.models class name
    time_column: str
    consumer_job_type: str
    why: str
    where: tuple[tuple[str, object], ...] = ()   # simple equality filters


@dataclass(frozen=True)
class Charter:
    key: str
    name: str
    mission: str
    agents: tuple[str, ...]
    prefixes: tuple[str, ...]
    job_types: frozenset[str]
    generatable: tuple[str, ...]
    forbidden: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    kpis: tuple[KPI, ...]
    escalation: str
    evidence_requirement: str
    handoff_to: tuple[str, ...]
    consumes: tuple[Handoff, ...] = ()
    gates: tuple[str, ...] = ()           # build2.executor gate keys this department waits on
    protected_kind: int = 9               # lower = served first by the orchestrator
    review_hours: int = 6                 # fallback self-review cadence when idle
    extra: dict = field(default_factory=dict)


_GENERIC_GUARDS = (
    "VOID when a department job was permission-denied, budget-refused or provenance-refused "
    "in the window",
    "a repeated identical output counts once (fingerprinted); a no-op run counts zero",
    "orchestrator-generated work counts only when it produced work (did_no_work is false)",
)

_GENERIC_KPIS = (
    KPI("useful_completions_24h", "distinct useful job outputs in 24 h", "up",
        "jobs: done, outputs not did_no_work, distinct by output fingerprint", _GENERIC_GUARDS),
    KPI("defect_dead_letters_24h", "dead letters classified DEFECT in 24 h", "down",
        "jobs: dead, queue.durable.classify_dead_letter == defect"),
    KPI("cadence_freshness", "share of the department's cadences with a success inside two "
        "periods", "up", "jobs: last done per cadence job type vs worker.CADENCES period",
        ("a dead or failed run never refreshes a cadence",
         "an early out-of-window re-run cannot raise freshness above 1.0 (it is a share)")),
)


def _c(**kw) -> Charter:
    kw.setdefault("kpis", _GENERIC_KPIS)
    kw["job_types"] = frozenset(kw.get("job_types", ()))
    return Charter(**kw)


CHARTERS: tuple[Charter, ...] = (
    _c(key="executive", name="Executive / COO",
       mission="Prioritise company work across departments, keep every department supplied "
               "with the next highest-value safe work, and present only genuine owner "
               "decisions upward (F-893, F-894).",
       agents=("coo", "orchestrator", "swarm_steward", "laura"),
       # "laura.": Laura's executive tick (W3-D) sits above the COO in the executive
       # department, so it is never paused (F-889) and never counted as department work.
       prefixes=("autonomy.", "plan.", "swarm.", "portfolio.", "laura."),
       job_types={"scale.trajectory", "launch.readiness", "launch.plan", "ops.capacity",
                  "build.tick"},
       generatable=("autonomy.morning_handoff", "scale.trajectory",
                    "autonomy.department_review"),
       forbidden=("publish, activate, spend, message a customer or change a live price",
                  "approve its own proposals"),
       inputs=("jobs", "company_memory", "owner_actions", "build2 gate states"),
       outputs=("jobs (missions)", "company_memory mission/brief", "company_timeline",
                "owner_actions (approval items)"),
       escalation="protected actions and owner-gated capabilities become owner_actions",
       evidence_requirement="every mission names the durable rows that justified it",
       handoff_to=("intelligence", "product_design", "product_truth", "visual",
                   "store_commerce", "support", "finance", "growth", "learn", "platform"),
       protected_kind=5),
    _c(key="intelligence", name="Intelligence",
       mission="Observe demand, benchmarks, trends and seasonality from sanctioned sources "
               "and turn them into scored opportunities.",
       agents=("market_radar",),
       prefixes=("radar.", "mjs.", "intel.", "culture."),
       job_types={"etsy.probe", "teardown.enforce"},
       generatable=("radar.score", "intel.benchmark_refresh", "intel.pod_learning",
                    "autonomy.department_review"),
       forbidden=("copy competitor instructions, charts or photography",
                  "buy benchmarks or spend beyond its ceiling"),
       inputs=("benchmark_listings", "coverage_gaps", "culture_signals", "serp_snapshots"),
       outputs=("coverage_gaps scores", "audit radar.*", "jobs cir.draft"),
       escalation="benchmark purchases and new paid sources are owner decisions",
       evidence_requirement="scores cite stored observations; directional data labelled so",
       handoff_to=("product_design", "growth"),
       consumes=(Handoff("CoverageGap", "updated_at", "radar.score",
                         "coverage gaps changed since the last scoring run"),),
       gates=("benchmark_observation", "etsy_api")),
    _c(key="product_design", name="Product & Design",
       mission="Turn scored opportunities into CIR-first product concepts and keep the "
               "seasonal programme on time.",
       agents=("creative_director", "crochet_engineer"),
       prefixes=("creative.", "seasonal."),
       job_types={"cir.draft", "cir.revise", "collection.assemble"},
       generatable=("seasonal.sentinel", "creative.outcome_learning",
                    "autonomy.department_review"),
       forbidden=("create a beauty image and ask a model to guess instructions",
                  "certify its own pattern"),
       inputs=("coverage_gaps", "pattern_versions", "lessons"),
       outputs=("CIR drafts", "seasonal plans", "audit creative.*"),
       escalation="spend above the creative ceiling and model-identity decisions go to owner",
       evidence_requirement="every concept is a CIR validated by deterministic code",
       handoff_to=("product_truth", "visual", "store_commerce"),
       consumes=(Handoff("PatternVersion", "created_at", "seasonal.sentinel",
                         "new pattern versions need launch dates recomputed"),),
       gates=("model_provider",)),
    _c(key="product_truth", name="Product Truth / QA",
       mission="Prove every claim a product makes: compile, twin, certify, keep artefacts "
               "fresh and block anything that misrepresents the pattern.",
       agents=("quality_director", "validator", "asset_truth", "policy"),
       prefixes=("gate.", "physical.", "cir.compile", "cir.twin", "cir.reverse"),
       job_types={"ops.sentinel", "ops.provenance_backfill", "cir.compile", "cir.twin",
                  "cir.reverse"},
       generatable=("ops.sentinel", "physical.upgrade_impact", "autonomy.department_review"),
       forbidden=("weaken a gate", "certify without deterministic validation"),
       inputs=("pattern_versions", "artefact_provenance", "incidents", "listing_assets"),
       outputs=("certificates", "incidents", "audit ops.sentinel"),
       escalation="P0/P1 incidents halt publication and reach the owner",
       evidence_requirement="deterministic validation wins even if every model disagrees",
       handoff_to=("visual", "store_commerce", "learn"),
       consumes=(Handoff("PatternVersion", "created_at", "ops.sentinel",
                         "new releases must be swept for stale or unproven artefacts"),),
       protected_kind=1),
    _c(key="visual", name="Visual",
       mission="Produce truthful, disclosed imagery for certified releases and watch the "
               "canonical model's identity for drift.",
       agents=("publishing",),
       prefixes=("assets.", "visual."),
       job_types={"creative.image_benchmark", "creative.model_tournament",
                  "creative.model_reference_pack", "creative.model_freeze",
                  "creative.photoreal_calibration", "seasonal.cycle_proof"},
       generatable=("visual.identity_drift", "visual.rnd.cycle",
                    "autonomy.department_review"),
       forbidden=("generate imagery that misrepresents the pattern",
                  "buy renders from idleness (renders stay on their budgeted cadences)"),
       inputs=("pattern_versions", "listing_assets", "model_identities"),
       outputs=("listing_assets", "identity drift readings"),
       escalation="identity freezes and provider trials are owner-approved",
       evidence_requirement="asset truth gate passes before any image is used",
       handoff_to=("store_commerce", "product_truth"),
       consumes=(Handoff("ListingAsset", "created_at", "visual.identity_drift",
                         "new listing assets must be read into the identity series"),),
       gates=("image_generation", "canonical_model", "image_vision")),
    _c(key="store_commerce", name="Store / Commerce",
       mission="Turn certified releases into correct listings, keep the shop's read-back true, "
               "and prepare (never perform) publication for owner approval.",
       agents=("listing", "store_operator", "pricing"),
       prefixes=("listing.", "store.", "pricing.", "etsy.credential", "etsy.shop",
                 "etsy.listing", "seo."),
       job_types={"chain.rebuild", "seasonal.remerchandising", "etsy.credential_health",
                  "etsy.shop_snapshot", "etsy.listing_census"},
       generatable=("seasonal.remerchandising", "seo.cycle", "autonomy.department_review"),
       forbidden=("publish or activate a listing without owner authority",
                  "change a live price"),
       inputs=("pattern_versions", "listings", "etsy snapshots"),
       outputs=("listings (drafts)", "owner approval items for publication"),
       escalation="publication/activation is owner-approved per release",
       evidence_requirement="a listing exists only from a certified release",
       handoff_to=("growth", "finance", "support"),
       consumes=(Handoff("Listing", "created_at", "seasonal.remerchandising",
                         "new listing drafts are reviewed for seasonal merchandising"),),
       gates=("etsy_api", "live_listings")),
    _c(key="support", name="Customer Support",
       mission="Triage every customer case against the pattern version it concerns and "
               "draft truthful answers; mine cases for product defects.",
       agents=("support",),
       prefixes=("support.",),
       job_types=set(),
       generatable=("support.triage", "autonomy.department_review"),
       forbidden=("send a message without authority (CASL)",
                  "silently patch a canonical pattern"),
       inputs=("support_cases", "pattern_versions", "lessons"),
       outputs=("support_cases drafts", "defect lessons"),
       escalation="unanswerable or safety cases escalate to the owner",
       evidence_requirement="answers cite the pattern version",
       handoff_to=("product_truth", "learn"),
       consumes=(Handoff("SupportCase", "at", "support.triage",
                         "cases arrived since the last triage"),),
       gates=("customers",),
       protected_kind=0),
    _c(key="finance", name="Finance / Accounting",
       mission="Keep the books from observed entries only, reconcile, govern spend and "
               "challenge any proposal that breaks margin or cash policy.",
       agents=("cfo",),
       prefixes=("finance.", "commerce."),
       job_types=set(),
       generatable=("finance.reconcile", "commerce.order_readings", "commerce.readings",
                    "finance.escalation_check", "finance.accounting.cycle",
                    "finance.accounting.period_pack", "autonomy.department_review"),
       forbidden=("move money, file tax, borrow, sign contracts or change bank details",
                  "present an estimate as an actual"),
       inputs=("cost_entries", "ledger", "orders", "spend_reservations"),
       outputs=("P&L readings", "incidents", "spend holds", "owner actions"),
       escalation="80% of a ceiling and every anomaly reach the owner",
       evidence_requirement="every figure traces to source rows; UNKNOWN is never 0",
       handoff_to=("executive", "growth"),
       consumes=(Handoff("CostEntry", "at", "finance.reconcile",
                         "new cost entries since the last reconciliation"),
                 Handoff("Order", "at", "commerce.order_readings",
                         "new orders since the last order reading")),
       gates=("transactions_r",),
       protected_kind=3),
    _c(key="growth", name="Growth / Marketing",
       mission="Plan distribution and the buyer journey, pre-register experiments and "
               "conclude them honestly; propose (never self-approve) spend.",
       agents=("growth", "ads", "experiment_steward"),
       prefixes=("growth.", "ads.", "marketing."),
       job_types={"content.draft"},
       generatable=("growth.journey", "growth.distribution", "growth.conclude",
                    "marketing.ads_readiness", "autonomy.department_review"),
       forbidden=("spend on ads without owner authority and Finance clearance",
                  "fake reviews, engagement or deceptive discounts"),
       inputs=("listings", "experiments", "cohorts"),
       outputs=("distribution plans", "experiment packs", "spend proposals"),
       escalation="every spend proposal is challenged by Finance then owner-approved",
       evidence_requirement="experiments carry owner, expected value and a kill rule",
       handoff_to=("finance", "learn"),
       consumes=(Handoff("Listing", "created_at", "growth.journey",
                         "new listing drafts change the buyer journey"),
                 Handoff("Experiment", "created_at", "growth.conclude",
                         "experiments registered since the last conclusion run")),
       gates=("ad_authority", "owned_surfaces")),
    _c(key="learn", name="Learn / Improvement",
       mission="Mine failures and outcomes into routed lessons, propose challengers, and "
               "promote only measured improvements with rollback.",
       agents=("learn", "orchestrator", "evaluator", "failure_miner", "experiment_designer",
               "prompt_tool_challenger", "cost_optimiser", "reliability_engineer",
               "creative_critic", "lesson_router"),
       prefixes=("improve.", "learn."),
       job_types=set(),
       generatable=("improve.mine", "improve.retrospective", "improve.measure",
                    "improve.sandbox", "improve.monitor", "learn.scan",
                    "autonomy.department_review"),
       forbidden=("promote a change without evaluation and rollback",
                  "weaken Product Truth, accounting truth, authorization or spend controls"),
       inputs=("incidents", "dead letters", "lessons", "company_memory lessons"),
       outputs=("lessons", "improvements"),
       escalation="tier-3 promotions require the owner",
       evidence_requirement="a lesson cites the evidence row it was mined from",
       handoff_to=("executive",),
       consumes=(Handoff("Incident", "at", "improve.mine",
                         "incidents raised since the last mining run"),
                 Handoff("Job", "finished_at", "improve.mine",
                         "dead letters since the last mining run",
                         where=(("status", "dead"),)),
                 Handoff("Lesson", "at", "improve.retrospective",
                         "lessons routed since the last retrospective")),
       protected_kind=6),
    _c(key="platform", name="Platform / Reliability",
       mission="Keep the runtime alive and honest: health, continuity, retention, "
               "dependencies, thrash and dead-letter recovery.",
       agents=("orchestrator",),
       prefixes=("ops.", "model.probe"),
       job_types={"ops.heartbeat", "ops.queue_check", "ops.health", "ops.continuity",
                  "ops.offsite_archive", "ops.retention", "ops.dependencies",
                  "ops.capability_probes", "ops.thrash", "ops.policy_watch",
                  "ops.maturity_disagreements", "model.probe"},
       generatable=("ops.queue_check", "ops.maturity_disagreements", "ops.slo",
                    "autonomy.department_review"),
       forbidden=("deploy, merge or mutate hosting", "delete evidence a gate reads"),
       inputs=("jobs", "incidents", "audit_log"),
       outputs=("incidents", "continuity proofs", "health readings"),
       escalation="sustained outage, failed restore or spend on hosting goes to the owner",
       evidence_requirement="online means useful work progressing (#185)",
       handoff_to=("learn", "executive"),
       consumes=(Handoff("Job", "finished_at", "ops.queue_check",
                         "dead letters since the last queue check",
                         where=(("status", "dead"),)),),
       gates=("offsite_storage",),
       protected_kind=2),
)

BY_KEY: dict[str, Charter] = {c.key: c for c in CHARTERS}

# Exact job types first (they win over prefixes), then prefixes longest-first.
_EXACT: dict[str, str] = {}
for _ch in CHARTERS:
    for _jt in _ch.job_types:
        _EXACT[_jt] = _ch.key
_PREFIXES: list[tuple[str, str]] = sorted(
    ((p, ch.key) for ch in CHARTERS for p in ch.prefixes), key=lambda t: -len(t[0]))


def department_of(job_type: str) -> str | None:
    """The department that owns a job type, or None when no charter claims it."""
    if job_type in _EXACT:
        return _EXACT[job_type]
    for prefix, key in _PREFIXES:
        if job_type.startswith(prefix):
            return key
    return None


def validate() -> list[str]:
    """Structural problems with the charters. Empty means sound."""
    problems: list[str] = []
    if len(CHARTERS) != 11 or len(BY_KEY) != 11:
        problems.append("there must be exactly eleven departments")
    for ch in CHARTERS:
        for jt in ch.generatable:
            if jt in PROTECTED_JOB_TYPES:
                problems.append(f"{ch.key}: protected {jt} is generatable")
            if jt not in SAFE_GENERATED:
                problems.append(f"{ch.key}: {jt} generatable without a SAFE_GENERATED reason")
            if jt != "autonomy.department_review" and department_of(jt) != ch.key:
                problems.append(f"{ch.key}: generatable {jt} belongs to {department_of(jt)}")
        for h in ch.consumes:
            if h.consumer_job_type not in ch.generatable:
                problems.append(f"{ch.key}: consumes into non-generatable "
                                f"{h.consumer_job_type}")
        if not ch.kpis or any(not k.guardrails for k in ch.kpis if k.direction == "up"):
            problems.append(f"{ch.key}: every upward KPI needs an anti-gaming guardrail")
    return problems


_PROBLEMS = validate()
if _PROBLEMS:  # pragma: no cover - a charter defect is a build defect
    raise RuntimeError("autonomy charters invalid: " + "; ".join(_PROBLEMS))
