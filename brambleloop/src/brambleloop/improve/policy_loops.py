"""Measured policy loops: outcome -> proposal -> shadow evaluation -> promote/rollback -> lesson.

Directive §4 (v1.1) asks for the loop *measure -> diagnose -> propose challenger ->
independent evaluation -> sandbox -> promote -> execute -> measure post-change outcome ->
retain or rollback -> persist lesson -> affect future decisions*, with real consumers. The
improvement department already had one loop that closed end to end (the job-priority replay,
`improve.replay`) and one that adopts a standard (`self_audit`). Everything else either
measured without proposing, or -- the lesson bus -- changed decisions with no evaluation,
no baseline and no rollback at all (`consume.matching` applied any lesson that shared two
words, and its benefit was recorded as "unmeasured" for ever).

This module is the general form of the replay loop for the five launch decisions, each one
parameter a runtime consumer reads:

==========================  =================  ===========  =================================
loop                        decides            family       consumer
==========================  =================  ===========  =================================
seo_lesson_match            listing tag slots  replay       improve.consume.matching (seo)
support_lesson_match        case lessons       replay       improve.consume.matching (support)
pattern_defect_watch        extra QA review    predictor    defect_watchlist / next_work
visual_gate_precheck        pre-gate review    predictor    visual_precheck / next_work
release_cost_watch          cost review        predictor    cost_watch / next_work
==========================  =================  ===========  =================================

Two evaluation families, both deterministic functions of recorded rows:

* **replay** -- the parameter changes the action and the action changes the outcome, so a
  challenger is scored by the replay estimator on logged decisions: the mean outcome of the
  decisions where the challenger would have done what was actually done. Biased when
  coverage is thin, which is why each policy needs MIN_MATCHED matched decisions on the
  shared set and on the holdout before a comparison exists at all.
* **predictor** -- the parameter decides what gets *extra* scrutiny (a review, a precheck,
  a cost look) and the outcome happens regardless, so the counterfactual is exact: F1 of the
  flags against the outcomes, with each subject's feature computed only from subjects
  observed before it (no leakage). These policies only ever add scrutiny on top of the
  protected gates; they never remove one.

The rules that keep it honest, and the existing machinery each one reuses:

1. **Guardrail first.** Every proposal -- generated here or submitted by any agent -- passes
   `improve.invariants` (the hard-coded protected list) before anything is evaluated, again
   when the cross-agent challenger reviews it, and again when the promotion executes. A
   refusal is a durable `learn_proposals` row (state REFUSED) and an audit row.
2. **Baseline before change, holdout never tuned.** The incumbent's reading on the frozen
   dataset is the baseline `cells.propose` records; the newest fifth of the dataset is a
   holdout the challenger may not lose on.
3. **Anti-gaming (F-918).** Each loop has a guardrail KPI beside its metric (conversion
   beside click-through, resolution beside escalation-free, review load beside F1); a
   challenger that wins the metric by losing the guardrail is challenged out.
4. **Cross-agent challenge (F-919).** A specialist from another department -- never the
   proposer -- re-checks invariants, sample sufficiency, holdout and guardrail before the
   proposal enters the improvement pipeline.
5. **Promotion is the pipeline's, not ours.** A proposal is an ordinary `Improvement` row
   with trial `policy_loop`; `improve.runner` sandboxes it (re-deriving the value from the
   frozen rows), records regression and adversarial tests, has the evaluator approve it and
   promotes it through the scoring tier's cooldown and ceiling. The executor makes the
   challenger the registry incumbent (`ConfigVersion`, kind `scoring`), which is what the
   consumer reads on its next call.
6. **Post-change measurement decides retain or rollback.** `runner.monitor_trials` calls
   `monitor` here on decisions taken *after* the promotion; a reading worse than the
   baseline by more than REGRESSION_MARGIN rolls the registry back (verified by reading the
   active value back) and opens the rollback incident.
7. **Memory changes the next decision (F-920).** Promotions, rollbacks, refusals and
   challenges are persisted as `learn_policy_lessons`. The next cycle reads them: a value
   rolled back or challenged out in the last LESSON_MEMORY_DAYS is not proposed again, and
   that skip is itself recorded.

UNKNOWN is never zero: a loop without enough observed outcomes reports `UNMEASURED` with the
table that has to fill, and proposes nothing.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import invariants

ACTION = "learn.improve"
TRIAL = "policy_loop"
KIND = "scoring"
KEY_PREFIX = "learn."
# The surface every policy-loop proposal declares: the scoring tier (pre-authorised, with its
# cooldown and weekly ceiling). One open policy-loop proposal at a time, so two loops never
# hold the same surface against each other in the Director.
SURFACE = "score"

# Evidence floors. UPPERCASE in a protected package: `improve.governance` discovers them, so
# a hypothesis that names one is refused, and `invariants` refuses a parameter spelled like
# one. The loop cannot lower the sample size it is judged on.
MIN_DECISIONS = 12
MIN_MATCHED = 6
MIN_HOLDOUT_MATCHED = 2
MIN_POSITIVES = 3
HOLDOUT_SHARE = 0.2
GAIN_MARGIN = 0.02
HOLDOUT_SLIP = 0.02
GUARDRAIL_SLIP = 0.01
MAX_FLAG_SHARE = 0.5
MIN_FRESH = 6
REGRESSION_MARGIN = 0.02
LESSON_MEMORY_DAYS = 30
MIN_IMPRESSIONS = 20
DEFECT_OBSERVATION_DAYS = 14
COST_OBSERVATION_DAYS = 7
EARLY_COST_ENTRIES = 3
OVERSPEND_FACTOR = 2.0
MIN_PRIOR_SUBJECTS = 3

# Proposal states in `learn_proposals`.
REFUSED = "REFUSED"                  # the invariant guard refused it
CHALLENGED_OUT = "CHALLENGED_OUT"    # the cross-agent challenger objected
NO_GAIN = "NO_GAIN"                  # evaluated; no challenger beat the incumbent
MEMORY_SKIPPED = "MEMORY_SKIPPED"    # a persisted lesson said not to try this again
HELD = "HELD"                        # good, waiting for the in-flight proposal to settle
PROPOSED = "PROPOSED"                # in the improvement pipeline
PROMOTED = "PROMOTED"                # the registry incumbent; consumers read it
REJECTED = "REJECTED"                # the sandbox or a judge rejected it
ROLLED_BACK = "ROLLED_BACK"          # post-change measurement regressed; verified restored
OPEN_STATES = (PROPOSED,)


class LoopRefused(ValueError):
    """A request the loop engine cannot honour (unknown loop, malformed data)."""


@dataclass(frozen=True)
class Loop:
    key: str
    title: str
    cell: str
    family: str                  # "replay" | "predictor"
    param: str
    default: float
    lo: float
    hi: float
    step: float
    integer: bool
    metric: str
    guardrail: str
    proposer: str                # improve.roles key with PROPOSE
    challenger: str              # a specialist from another department; never the proposer
    consumer: str
    consumer_status: str         # "live" | "live_reads; decision logging needs W-B1" | ...
    outcome_source: str

    def tunable(self) -> dict:
        return {"param": self.param, "lo": self.lo, "hi": self.hi, "integer": self.integer}

    @property
    def registry_key(self) -> str:
        return KEY_PREFIX + self.key


LOOPS: tuple[Loop, ...] = (
    Loop("seo_lesson_match", "Listing / SEO lesson tag slots", "seo_search", "replay",
         "min_shared", 2, 1, 4, 1, True,
         "listing click-through (visits / impressions) after the decision",
         "conversion (orders / visits) where orders are observed",
         "experiment_designer", "quality",
         "improve.consume.matching(cell='seo_search'), called by runtime.release listing.seo "
         "to give lesson-matched queries a tag slot",
         "live: release.py reads it now; decision logging needs WIRING REQUEST W-B1 "
         "(pass subject=slug)",
         "listing_outcomes (impressions, visits, orders) per product_slug"),
    Loop("support_lesson_match", "Support lessons attached to cases", "customer_experience",
         "replay", "min_shared", 1, 1, 4, 1, True,
         "share of cases resolved without escalation",
         "share of decided cases resolved at all",
         "experiment_designer", "quality",
         "improve.consume.matching(cell='customer_experience'), called by runtime.release "
         "support.mine to attach lessons to open cases",
         "live: release.py reads it now; decision logging needs WIRING REQUEST W-B1 "
         "(pass subject='support_case:<id>')",
         "support_cases (resolved, escalated)"),
    Loop("pattern_defect_watch", "Pattern quality defect watch", "quality", "predictor",
         "min_topic_defect_rate", 0.5, 0.05, 1.0, 0.1, False,
         "F1 of extra-review flags against releases that later had a defect",
         "review load: flagged share of releases (cap 0.5)",
         "failure_miner", "pattern_engineering",
         "improve.policy_loops.defect_watchlist / requires_extra_review; learn.improvement_"
         "status.next_work emits quality.extra_review items",
         "live via next_work (lane A enqueues); release-gate read needs WIRING REQUEST W-B3",
         "pattern_versions x incidents / troubleshooter support_cases per product"),
    Loop("visual_gate_precheck", "Visual gate pre-check", "creative_assets", "predictor",
         "precheck_flag_rate", 0.5, 0.05, 1.0, 0.1, False,
         "F1 of pre-check flags against assets the visual gate later blocked",
         "review load: flagged share of assets (cap 0.5)",
         "experiment_designer", "quality",
         "improve.policy_loops.visual_precheck; next_work emits visual.precheck items",
         "live via next_work (lane A enqueues); render-path read needs WIRING REQUEST W-B4",
         "listing_assets (approved, blocked_reasons) by asset_class/role"),
    Loop("release_cost_watch", "Cost per release watch", "finance", "predictor",
         "early_cost_flag_cad", 1.0, 0.1, 20.0, 0.5, False,
         "F1 of early cost-review flags against releases whose actual cost ended above "
         "twice the median of earlier releases",
         "review load: flagged share of releases (cap 0.5)",
         "cost_optimiser", "reliability_engineer",
         "improve.policy_loops.cost_watch; next_work emits finance.cost_review items",
         "live via next_work (lane A enqueues). Flags only: never raises or lowers a spend "
         "ceiling (spend controls are a protected invariant)",
         "cost_entries (amount_cad, actual only) per product_slug"),
)

BY_KEY: dict[str, Loop] = {lp.key: lp for lp in LOOPS}
LOOP_FOR_CELL: dict[str, str] = {"seo_search": "seo_lesson_match",
                                 "customer_experience": "support_lesson_match"}


def _assert_loops_safe() -> None:
    """A loop declaring a protected parameter tunable is a build failure, not a runtime one."""
    for lp in LOOPS:
        verdict = invariants.check(lp.param, lp.default, tunable=lp.tunable())
        if not verdict.ok:
            raise LoopRefused(f"loop {lp.key} declares {lp.param}: {verdict.reason}")
        if lp.proposer == lp.challenger:
            raise LoopRefused(f"loop {lp.key}: the challenger may not be the proposer")


_assert_loops_safe()


def loop(key: str) -> Loop:
    try:
        return BY_KEY[key]
    except KeyError:
        raise LoopRefused(f"unknown policy loop {key!r}; loops are {sorted(BY_KEY)}") from None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _num(lp: Loop, value) -> float | int:
    return int(round(float(value))) if lp.integer else round(float(value), 6)


# ---- the active policy (what consumers read) -------------------------------------------------


def active(db, key: str) -> dict:
    """The value a consumer uses now: the registry incumbent, or the code default.

    Re-checked on read: a registry payload that fails the invariant guard (outside bounds,
    an undeclared key) is not used -- the code default is, and the reading says why.
    """
    from . import league

    lp = loop(key)
    row = league.incumbent_payload(db, kind=KIND, key=lp.registry_key)
    if row is None:
        return {"loop": key, "param": lp.param, "value": _num(lp, lp.default),
                "config_id": None, "version": None, "source": "code_default"}
    try:
        payload = json.loads(row.get("payload") or "{}")
    except (TypeError, ValueError):
        payload = {}
    bad = invariants.check_payload(payload, tunable=lp.tunable())
    if bad:
        return {"loop": key, "param": lp.param, "value": _num(lp, lp.default),
                "config_id": None, "version": None, "source": "code_default",
                "refused_registry_value": {"config_id": row["config_id"],
                                           "why": bad[0].reason}}
    return {"loop": key, "param": lp.param, "value": _num(lp, payload[lp.param]),
            "config_id": row["config_id"], "version": row["version"], "source": "registry"}


def _payload(lp: Loop, value) -> str:
    return json.dumps({lp.param: _num(lp, value)}, sort_keys=True)


def ensure_incumbent(db, key: str) -> dict:
    """Register the code default as the incumbent version, once, when a loop has data."""
    from . import league

    lp = loop(key)
    current = active(db, key)
    if current["source"] == "registry":
        return current
    league.register(db, kind=KIND, key=lp.registry_key, payload=_payload(lp, lp.default),
                    why_changed=(f"incumbent {lp.param}={lp.default} recorded from the code "
                                 f"default of {key}: it runs because it was first, before any "
                                 f"measured outcome compared it with anything"),
                    tests_declared=("tests/test_v11_learn_loops.py",),
                    affected_departments=(lp.cell,), incumbent=True)
    return active(db, key)


# ---- decisions and outcomes ------------------------------------------------------------------


def record_decision(db, key: str, subject: str, *, features: dict, action: dict,
                    config_id: int | None, params: dict) -> int | None:
    """Log one runtime decision under the active policy. Idempotent per (loop, subject):
    the first decision about a subject is the one its outcome is attributed to."""
    from sqlalchemy import select

    from ..learn.models import LearnDecision

    loop(key)
    subject = str(subject or "").strip()[:240]
    if not subject:
        return None
    with db.session() as s:
        existing = s.scalar(select(LearnDecision).where(
            LearnDecision.loop == key, LearnDecision.subject == subject))
        if existing is not None:
            return existing.id
        row = LearnDecision(loop=key, subject=subject, features=dict(features),
                            action=dict(action), config_id=config_id, params=dict(params))
        s.add(row)
        s.flush()
        return row.id


def _observe_seo(db, now: datetime) -> int:
    from sqlalchemy import select

    from ..core.models import ListingOutcome
    from ..learn.models import LearnDecision

    done = 0
    with db.session() as s:
        pending = list(s.scalars(select(LearnDecision).where(
            LearnDecision.loop == "seo_lesson_match", LearnDecision.outcome.is_(None))))
        for d in pending:
            since = _aware(d.at).date().isoformat()
            rows = [r for r in s.scalars(select(ListingOutcome).where(
                ListingOutcome.product_slug == d.subject)) if (r.period_start or "") >= since]
            impressions = sum(int(r.impressions or 0) for r in rows)
            if impressions < MIN_IMPRESSIONS:
                continue
            visits = sum(int(r.visits or 0) for r in rows)
            known = [r for r in rows if r.orders is not None]
            k_visits = sum(int(r.visits or 0) for r in known)
            guard = (round(sum(int(r.orders) for r in known) / k_visits, 6)
                     if known and k_visits else None)
            d.outcome = {"value": round(visits / impressions, 6), "guard": guard,
                         "impressions": impressions, "basis": "measured"}
            d.outcome_at = now
            d.outcome_ref = ("listing_outcomes:" + ",".join(str(r.id) for r in rows))[:240]
            done += 1
    return done


def _observe_support(db, now: datetime) -> int:
    from sqlalchemy import select

    from ..core.models import SupportCase
    from ..learn.models import LearnDecision

    done = 0
    with db.session() as s:
        pending = list(s.scalars(select(LearnDecision).where(
            LearnDecision.loop == "support_lesson_match", LearnDecision.outcome.is_(None))))
        for d in pending:
            try:
                case_id = int(d.subject.split(":", 1)[1])
            except (IndexError, ValueError):
                continue
            case = s.get(SupportCase, case_id)
            if case is None or not (case.resolved or case.escalated):
                continue          # undecided is not an outcome
            d.outcome = {"value": 1.0 if (case.resolved and not case.escalated) else 0.0,
                         "guard": 1.0 if case.resolved else 0.0, "basis": "measured"}
            d.outcome_at = now
            d.outcome_ref = f"support_cases:{case.id}"
            done += 1
    return done


def _materialise_patterns(db, now: datetime) -> int:
    """Each pattern version is a subject; its outcome is a defect seen within the window."""
    from sqlalchemy import select

    from ..core.models import Incident, PatternVersion, Product, SupportCase
    from ..learn.models import LearnDecision
    from ..learn.service import topics

    made = 0
    with db.session() as s:
        have = {d.subject: d for d in s.scalars(select(LearnDecision).where(
            LearnDecision.loop == "pattern_defect_watch"))}
        for pv, product in s.execute(select(PatternVersion, Product).join(Product)).all():
            subject = f"pattern_version:{pv.id}"
            d = have.get(subject)
            if d is None:
                try:
                    found = sorted(t for t in topics(pv.cir_json or {}))
                except Exception:  # noqa: BLE001 - unreadable CIR is no feature, not a crash
                    found = []
                d = LearnDecision(loop="pattern_defect_watch", subject=subject,
                                  features={"topics": found, "product_slug": product.slug},
                                  action={}, config_id=None, params={},
                                  at=_aware(pv.created_at) or now)
                s.add(d)
                made += 1
            if d.outcome is not None:
                continue
            released = _aware(pv.created_at) or now
            incidents = [i.id for i in s.scalars(select(Incident).where(
                Incident.product_slug == product.slug)) if _aware(i.at) >= released]
            cases = [c.id for c in s.scalars(select(SupportCase).where(
                SupportCase.product_slug == product.slug,
                SupportCase.specialist == "troubleshooter")) if _aware(c.at) >= released]
            if incidents or cases:
                d.outcome = {"value": 1.0, "basis": "measured"}
                d.outcome_ref = (f"incidents:{incidents}|support_cases:{cases}")[:240]
                d.outcome_at = now
            elif now - released >= timedelta(days=DEFECT_OBSERVATION_DAYS):
                d.outcome = {"value": 0.0, "basis": "measured",
                             "window_days": DEFECT_OBSERVATION_DAYS}
                d.outcome_ref = f"no defect in {DEFECT_OBSERVATION_DAYS}d"
                d.outcome_at = now
    return made


def _materialise_assets(db, now: datetime) -> int:
    from sqlalchemy import select

    from ..core.models import ListingAsset
    from ..learn.models import LearnDecision

    made = 0
    with db.session() as s:
        have = {d.subject for d in s.scalars(select(LearnDecision).where(
            LearnDecision.loop == "visual_gate_precheck"))}
        for a in s.scalars(select(ListingAsset).order_by(ListingAsset.id)):
            subject = f"listing_asset:{a.id}"
            if subject in have:
                continue
            blocked = bool(a.blocked_reasons)
            if not (a.approved or blocked):
                continue          # the gate has not decided this asset yet
            s.add(LearnDecision(loop="visual_gate_precheck", subject=subject,
                                features={"group": f"{a.asset_class}/{a.role}"},
                                action={}, config_id=None, params={},
                                at=_aware(a.created_at) or now,
                                outcome={"value": 1.0 if blocked else 0.0, "basis": "measured"},
                                outcome_at=now, outcome_ref=f"listing_assets:{a.id}"))
            made += 1
    return made


def _materialise_costs(db, now: datetime) -> int:
    from sqlalchemy import select

    from ..core.models import CostEntry
    from ..learn.models import LearnDecision

    by_slug: dict[str, list] = {}
    with db.session() as s:
        for c in s.scalars(select(CostEntry).order_by(CostEntry.at, CostEntry.id)):
            if c.product_slug and float(c.amount_cad or 0.0) > 0:
                by_slug.setdefault(c.product_slug, []).append(
                    (c.id, _aware(c.at), float(c.amount_cad)))
        have = {d.subject: d for d in s.scalars(select(LearnDecision).where(
            LearnDecision.loop == "release_cost_watch"))}
        made = 0
        for slug, entries in by_slug.items():
            subject = f"release_cost:{slug}"
            first = entries[0][1]
            if now - first < timedelta(days=COST_OBSERVATION_DAYS):
                continue          # the release's cost is still accruing
            if subject in have:
                continue
            early = round(sum(a for _i, _t, a in entries[:EARLY_COST_ENTRIES]), 6)
            window = [e for e in entries if e[1] - first <= timedelta(days=COST_OBSERVATION_DAYS)]
            s.add(LearnDecision(loop="release_cost_watch", subject=subject,
                                features={"early_cost_cad": early}, action={},
                                config_id=None, params={}, at=first,
                                outcome={"total_cad": round(sum(a for _i, _t, a in window), 6),
                                         "basis": "measured (actual amount_cad only)"},
                                outcome_at=now,
                                outcome_ref=("cost_entries:" + ",".join(
                                    str(i) for i, _t, _a in window))[:240]))
            made += 1
    return made


OBSERVERS = {"seo_lesson_match": _observe_seo, "support_lesson_match": _observe_support,
             "pattern_defect_watch": _materialise_patterns,
             "visual_gate_precheck": _materialise_assets,
             "release_cost_watch": _materialise_costs}


def observe(db, key: str, *, now: datetime | None = None) -> int:
    return OBSERVERS[loop(key).key](db, now or _now())


# ---- datasets and evaluation -----------------------------------------------------------------


def _decisions(db, key: str, *, ids: list[int] | None = None,
               after: datetime | None = None) -> list[dict]:
    from sqlalchemy import select

    from ..learn.models import LearnDecision

    with db.session() as s:
        q = select(LearnDecision).where(LearnDecision.loop == key)
        if ids is not None:
            q = q.where(LearnDecision.id.in_(ids or [-1]))
        rows = [{"id": d.id, "at": _aware(d.at), "subject": d.subject,
                 "features": dict(d.features or {}), "action": dict(d.action or {}),
                 "config_id": d.config_id, "outcome": d.outcome}
                for d in s.scalars(q)]
    rows.sort(key=lambda r: (r["at"], r["id"]))
    if after is not None:
        rows = [r for r in rows if r["at"] > after]
    return rows


def fingerprint(rows: list[dict]) -> str:
    body = [[r["id"], r["features"], r["action"], r["outcome"]] for r in rows]
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def _split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    cut = len(rows) - max(1, int(round(len(rows) * HOLDOUT_SHARE)))
    return rows[:cut], rows[cut:]


def _mean(values):
    values = [float(v) for v in values if v is not None]
    return round(sum(values) / len(values), 6) if values else None


def _replay(rows: list[dict], value) -> dict:
    """Replay estimator: outcomes of the logged decisions this policy agrees with."""
    matched = [r for r in rows
               if (int(r["features"].get("max_shared") or 0) >= value)
               == bool(r["action"].get("applied"))]
    return {"value": _mean(r["outcome"].get("value") for r in matched), "n": len(matched),
            "guard": _mean(r["outcome"].get("guard") for r in matched)}


def _prior_features(lp: Loop, rows: list[dict], history: list[dict]) -> list[tuple]:
    """(feature, label) per row, each feature from `history` subjects strictly earlier."""
    out = []
    for r in rows:
        prior = [h for h in history if (h["at"], h["id"]) < (r["at"], r["id"])
                 and h["outcome"] is not None]
        if lp.key == "pattern_defect_watch":
            label = float(r["outcome"]["value"])
            rates = []
            for topic in r["features"].get("topics") or []:
                seen = [h for h in prior if topic in (h["features"].get("topics") or [])]
                if len(seen) >= MIN_PRIOR_SUBJECTS:
                    rates.append(sum(float(h["outcome"]["value"]) for h in seen) / len(seen))
            feature = max(rates) if rates else None
        elif lp.key == "visual_gate_precheck":
            label = float(r["outcome"]["value"])
            seen = [h for h in prior if h["features"].get("group") == r["features"].get("group")]
            feature = (sum(float(h["outcome"]["value"]) for h in seen) / len(seen)
                       if len(seen) >= MIN_PRIOR_SUBJECTS else None)
        else:  # release_cost_watch
            totals = [float(h["outcome"]["total_cad"]) for h in prior]
            if len(totals) < MIN_PRIOR_SUBJECTS:
                continue      # no reference to call this release an overspend against
            label = 1.0 if float(r["outcome"]["total_cad"]) > \
                OVERSPEND_FACTOR * statistics.median(totals) else 0.0
            feature = float(r["features"].get("early_cost_cad") or 0.0)
        out.append((feature, label))
    return out


def _predict(lp: Loop, rows: list[dict], history: list[dict], value) -> dict:
    pairs = _prior_features(lp, rows, history)
    tp = sum(1 for f, y in pairs if f is not None and f >= value and y >= 1)
    fp = sum(1 for f, y in pairs if f is not None and f >= value and y < 1)
    fn = sum(1 for f, y in pairs if not (f is not None and f >= value) and y >= 1)
    positives = tp + fn
    f1 = round(2 * tp / (2 * tp + fp + fn), 6) if (2 * tp + fp + fn) else None
    flagged = tp + fp
    return {"value": f1 if positives >= 1 else None, "n": len(pairs), "positives": positives,
            "guard": round(flagged / len(pairs), 6) if pairs else None}


def evaluate(db, key: str, value, *, rows: list[dict] | None = None,
             history: list[dict] | None = None) -> dict:
    """One policy value on the frozen dataset: the shared set and the holdout."""
    lp = loop(key)
    if rows is None:
        rows = [r for r in _decisions(db, key) if r["outcome"] is not None]
    history = rows if history is None else history
    shared, holdout = _split(rows)
    if lp.family == "replay":
        return {"value": _num(lp, value), "shared": _replay(shared, value),
                "holdout": _replay(holdout, value)}
    return {"value": _num(lp, value), "shared": _predict(lp, shared, history, value),
            "holdout": _predict(lp, holdout, history, value)}


def _sufficient(lp: Loop, reading: dict) -> str | None:
    sh, ho = reading["shared"], reading["holdout"]
    if sh["value"] is None or ho["value"] is None:
        return "no measured value on the shared set or the holdout"
    if lp.family == "replay":
        if sh["n"] < MIN_MATCHED or ho["n"] < MIN_HOLDOUT_MATCHED:
            return (f"{sh['n']} shared / {ho['n']} holdout matched decisions; needs "
                    f"{MIN_MATCHED} / {MIN_HOLDOUT_MATCHED}")
    elif sh["positives"] < MIN_POSITIVES:
        return f"{sh['positives']} positive outcomes on the shared set; needs {MIN_POSITIVES}"
    return None


def compare(lp: Loop, incumbent: dict, challenger: dict) -> dict:
    """Does the challenger beat the incumbent without losing the holdout or the guardrail?"""
    blockers = []
    for name, reading in (("incumbent", incumbent), ("challenger", challenger)):
        short = _sufficient(lp, reading)
        if short:
            blockers.append(f"{name}: {short}")
    if blockers:
        return {"promote": False, "blockers": blockers, "gain": None}
    gain = round(challenger["shared"]["value"] - incumbent["shared"]["value"], 6)
    if gain < GAIN_MARGIN:
        blockers.append(f"gain {gain:+.4f} is below the {GAIN_MARGIN} margin")
    if challenger["holdout"]["value"] < incumbent["holdout"]["value"] - HOLDOUT_SLIP:
        blockers.append(f"loses the holdout ({challenger['holdout']['value']} against "
                        f"{incumbent['holdout']['value']})")
    blockers.extend(guardrail_objections(lp, incumbent, challenger))
    return {"promote": not blockers, "blockers": blockers, "gain": gain}


def guardrail_objections(lp: Loop, incumbent: dict, challenger: dict) -> list[str]:
    """F-918: a metric win bought with the guardrail is not a win."""
    out = []
    if lp.family == "predictor":
        load = challenger["shared"]["guard"]
        if load is not None and load > MAX_FLAG_SHARE:
            out.append(f"review load {load} exceeds {MAX_FLAG_SHARE}: flagging everything "
                       f"games recall")
        return out
    ig, cg = incumbent["shared"]["guard"], challenger["shared"]["guard"]
    if ig is not None and cg is not None and cg < ig - GUARDRAIL_SLIP:
        out.append(f"guardrail ({lp.guardrail}) falls from {ig} to {cg}")
    return out


def challenge(lp: Loop, proposal: dict) -> dict:
    """F-919: a specialist from another department reviews the proposal before it enters the
    pipeline. Deterministic: it re-runs the checks a proposer is tempted to wave through."""
    objections = []
    for verdict in invariants.check_payload(proposal["params_to"], tunable=lp.tunable()):
        objections.append(verdict.reason)
    verdict = compare(lp, proposal["incumbent"], proposal["challenger"])
    objections.extend(verdict["blockers"])
    if lp.challenger == proposal.get("proposed_by"):
        objections.append("the challenger is the proposer")
    return {"by": lp.challenger, "upheld": not objections, "objections": objections,
            "checked": ["protected invariants", "sample sufficiency", "margin", "holdout",
                        "guardrail KPI"]}


# ---- memory (F-920) --------------------------------------------------------------------------


def _remember(db, key: str, kind: str, params: dict, statement: str, ref: str,
              delta: float | None = None) -> int:
    from sqlalchemy import select

    from ..learn.models import LearnPolicyLesson

    with db.session() as s:
        if ref:
            existing = s.scalar(select(LearnPolicyLesson).where(
                LearnPolicyLesson.loop == key, LearnPolicyLesson.kind == kind,
                LearnPolicyLesson.evidence_ref == ref[:240]))
            if existing is not None:
                return existing.id
        row = LearnPolicyLesson(loop=key, kind=kind, params=dict(params),
                                statement=statement, evidence_ref=ref[:240],
                                metric_delta=delta)
        s.add(row)
        s.flush()
        return row.id


def lessons(db, key: str | None = None, *, limit: int = 100) -> list[dict]:
    from sqlalchemy import select

    from ..learn.models import LearnPolicyLesson

    with db.session() as s:
        q = select(LearnPolicyLesson).order_by(LearnPolicyLesson.id.desc()).limit(limit)
        if key:
            q = q.where(LearnPolicyLesson.loop == key)
        return [{"id": r.id, "at": _aware(r.at).isoformat(), "loop": r.loop, "kind": r.kind,
                 "params": r.params, "statement": r.statement,
                 "evidence_ref": r.evidence_ref, "metric_delta": r.metric_delta}
                for r in s.scalars(q)]


def remembered_against(db, key: str, params: dict, *, now: datetime) -> dict | None:
    """A persisted lesson that says not to propose these params again (yet)."""
    from sqlalchemy import select

    from ..learn.models import LearnPolicyLesson

    cutoff = now - timedelta(days=LESSON_MEMORY_DAYS)
    with db.session() as s:
        for r in s.scalars(select(LearnPolicyLesson).where(
                LearnPolicyLesson.loop == key,
                LearnPolicyLesson.kind.in_(("rolled_back", "challenged_out")))
                .order_by(LearnPolicyLesson.id.desc())):
            if _aware(r.at) >= cutoff and dict(r.params or {}) == dict(params):
                return {"lesson": r.id, "kind": r.kind, "statement": r.statement}
    return None


# ---- proposal records ------------------------------------------------------------------------


def _audit(db, action: str, detail: dict, artifact: str = "") -> None:
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="learn_improvement", action=action, artifact=artifact or None,
                       detail=json.loads(json.dumps(detail, default=str))))


def _record(db, key: str, state: str, *, proposed_by: str, params_from: dict,
            params_to: dict, evidence: dict, baseline=None, result=None,
            improvement_id=None, config_id=None, replaces=None, dedupe: bool = False) -> int:
    from sqlalchemy import select

    from ..learn.models import LearnProposal

    lp = BY_KEY.get(key)
    with db.session() as s:
        if dedupe:
            fp = evidence.get("fingerprint")
            for r in s.scalars(select(LearnProposal).where(
                    LearnProposal.loop == key, LearnProposal.state == state)):
                if (r.evidence or {}).get("fingerprint") == fp and r.params_to == params_to:
                    return r.id
        row = LearnProposal(loop=key, state=state, proposed_by=proposed_by,
                            params_from=dict(params_from), params_to=dict(params_to),
                            metric=(lp.metric[:80] if lp else ""), baseline=baseline,
                            result=result, improvement_id=improvement_id,
                            config_id=config_id, replaces=replaces,
                            evidence=json.loads(json.dumps(evidence, default=str)),
                            decided_at=None if state in OPEN_STATES else _now())
        s.add(row)
        s.flush()
        return row.id


def _set_state(db, proposal_id: int, state: str, **evidence) -> None:
    from ..learn.models import LearnProposal

    with db.session() as s:
        row = s.get(LearnProposal, proposal_id)
        if row is None:
            return
        row.state = state
        row.decided_at = _now()
        if evidence:
            row.evidence = {**(row.evidence or {}),
                            **json.loads(json.dumps(evidence, default=str))}


def _proposal_for_improvement(db, iid: int):
    from sqlalchemy import select

    from ..learn.models import LearnProposal

    with db.session() as s:
        row = s.scalar(select(LearnProposal).where(LearnProposal.improvement_id == iid))
        return None if row is None else {"id": row.id, "loop": row.loop, "state": row.state}


def refuse(db, key: str, params_to: dict, verdicts: list, *, proposed_by: str) -> dict:
    """Record and audit a proposal the invariant guard refused. Nothing else happens."""
    detail = {"loop": key, "params_to": params_to, "proposed_by": proposed_by,
              "refusals": [v.to_dict() for v in verdicts]}
    pid = _record(db, key, REFUSED, proposed_by=proposed_by, params_from={},
                  params_to=params_to if isinstance(params_to, dict) else {"raw": str(params_to)},
                  evidence={"invariant": [v.to_dict() for v in verdicts]})
    _audit(db, ACTION + ".invariant_refused", {**detail, "proposal": pid}, artifact=key)
    _remember(db, key, "refused", params_to if isinstance(params_to, dict) else {},
              f"proposal {pid} to set {params_to} on {key} was refused by the protected "
              f"invariant guard: {verdicts[0].reason}", f"learn_proposal:{pid}")
    return {"proposal": pid, "state": REFUSED, "refusals": [v.to_dict() for v in verdicts]}


def _open_policy_proposal(db) -> dict | None:
    """The policy-loop proposal in flight, if any. One at a time across all loops."""
    from sqlalchemy import select

    from ..core.models import Improvement
    from ..learn.models import LearnProposal

    with db.session() as s:
        for r in s.scalars(select(LearnProposal).where(LearnProposal.state == PROPOSED)):
            imp = s.get(Improvement, r.improvement_id) if r.improvement_id else None
            if imp is not None and imp.state in ("proposed", "testing"):
                return {"proposal": r.id, "loop": r.loop, "improvement": imp.id}
            if imp is not None and imp.state in ("rejected", "reverted"):
                from ..core.models import ConfigVersion

                challenger = s.get(ConfigVersion, r.config_id) if r.config_id else None
                if challenger is not None and not challenger.incumbent and \
                        challenger.retired_at is None:
                    challenger.retired_at = _now()     # the league stops listing it
                r.state = REJECTED
                r.decided_at = _now()
                r.evidence = {**(r.evidence or {}),
                              "pipeline": {"state": imp.state,
                                           "why": (imp.evidence or {}).get("why")}}
    return None


def _consider(db, lp: Loop, candidate, *, proposed_by: str, now: datetime,
              rows: list[dict], inc: dict, external: bool = False) -> dict:
    """Evaluate one candidate value against the incumbent and propose it, or record why not."""
    from . import cells, league

    params_to = {lp.param: _num(lp, candidate)}
    params_from = {lp.param: inc["value"]}
    fp = fingerprint(rows)
    base_ev = {"fingerprint": fp, "decisions": len(rows), "external": external}

    bad = invariants.check_payload(params_to, tunable=lp.tunable())
    if bad:
        return refuse(db, lp.key, params_to, bad, proposed_by=proposed_by)

    inc_reading = evaluate(db, lp.key, inc["value"], rows=rows)
    ch_reading = evaluate(db, lp.key, candidate, rows=rows)
    verdict = compare(lp, inc_reading, ch_reading)
    ev = {**base_ev, "incumbent": inc_reading, "challenger": ch_reading,
          "verdict": verdict}
    if not verdict["promote"]:
        pid = _record(db, lp.key, NO_GAIN, proposed_by=proposed_by, params_from=params_from,
                      params_to=params_to, evidence=ev, baseline=inc_reading["shared"]["value"],
                      result=ch_reading["shared"]["value"], dedupe=True)
        return {"proposal": pid, "state": NO_GAIN, "blockers": verdict["blockers"]}

    memory = remembered_against(db, lp.key, params_to, now=now)
    if memory:
        pid = _record(db, lp.key, MEMORY_SKIPPED, proposed_by=proposed_by,
                      params_from=params_from, params_to=params_to,
                      evidence={**ev, "memory": memory},
                      baseline=inc_reading["shared"]["value"],
                      result=ch_reading["shared"]["value"], dedupe=True)
        _audit(db, ACTION + ".memory_skipped", {"loop": lp.key, "params_to": params_to,
                                                "lesson": memory, "proposal": pid},
               artifact=lp.key)
        return {"proposal": pid, "state": MEMORY_SKIPPED, "memory": memory}

    contest = challenge(lp, {"params_to": params_to, "incumbent": inc_reading,
                             "challenger": ch_reading, "proposed_by": proposed_by})
    ev["challenge"] = contest
    if not contest["upheld"]:
        pid = _record(db, lp.key, CHALLENGED_OUT, proposed_by=proposed_by,
                      params_from=params_from, params_to=params_to, evidence=ev,
                      baseline=inc_reading["shared"]["value"],
                      result=ch_reading["shared"]["value"])
        _remember(db, lp.key, "challenged_out", params_to,
                  f"{contest['by']} challenged {params_to} on {lp.key} out: "
                  + "; ".join(contest["objections"])[:300], f"learn_proposal:{pid}")
        return {"proposal": pid, "state": CHALLENGED_OUT, "objections": contest["objections"]}

    in_flight = _open_policy_proposal(db)
    if in_flight:
        pid = _record(db, lp.key, HELD, proposed_by=proposed_by, params_from=params_from,
                      params_to=params_to, evidence={**ev, "held_for": in_flight},
                      baseline=inc_reading["shared"]["value"],
                      result=ch_reading["shared"]["value"], dedupe=True)
        return {"proposal": pid, "state": HELD, "held_for": in_flight}

    reg = league.register(
        db, kind=KIND, key=lp.registry_key, payload=_payload(lp, candidate),
        why_changed=(f"challenger to {lp.param}={inc['value']}: {lp.param}={params_to[lp.param]} "
                     f"read {ch_reading['shared']['value']} against "
                     f"{inc_reading['shared']['value']} on {len(rows)} observed decisions"),
        tests_declared=("tests/test_v11_learn_loops.py",), affected_departments=(lp.cell,),
        incumbent=False)
    baseline = inc_reading["shared"]["value"]
    hypothesis = (f"setting {lp.key} {lp.param.replace('_', ' ')} from {inc['value']} to "
                  f"{params_to[lp.param]} should improve the {lp.title.lower()} metric: on "
                  f"{len(rows)} observed decisions the challenger reads "
                  f"{ch_reading['shared']['value']} against {baseline} and it held on the "
                  f"holdout and the guardrail")
    iid = cells.propose(
        db, cell=lp.cell, hypothesis=hypothesis,
        expected_effect=(f"{lp.metric} rises above {baseline} and holds on decisions taken "
                         f"after the promotion"),
        rollback_ref=f"config:{inc['config_id']}", touches=(SURFACE,), proposed_by=proposed_by,
        trial=TRIAL, trial_metric=f"{lp.key}:{lp.param}"[:60], higher_is_better=True,
        baseline=baseline, baseline_ref=f"policy:{lp.key}:{fp[:16]}"[:80],
        change={"loop": lp.key, "config_id": reg["id"], "replaces": inc["config_id"],
                "kind": KIND, "key": lp.registry_key, "params_to": params_to,
                "params_from": params_from, "decision_ids": [r["id"] for r in rows],
                "fingerprint": fp, "challenge": contest})
    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, iid)
        row.evidence = {**(row.evidence or {}), "expected_gain": verdict["gain"]}
    pid = _record(db, lp.key, PROPOSED, proposed_by=proposed_by, params_from=params_from,
                  params_to=params_to, evidence=ev, baseline=baseline,
                  result=ch_reading["shared"]["value"], improvement_id=iid,
                  config_id=reg["id"], replaces=inc["config_id"])
    _audit(db, ACTION + ".proposed", {"loop": lp.key, "proposal": pid, "improvement": iid,
                                      "params_from": params_from, "params_to": params_to,
                                      "baseline": baseline,
                                      "result": ch_reading["shared"]["value"],
                                      "challenge": contest}, artifact=lp.key)
    return {"proposal": pid, "state": PROPOSED, "improvement": iid, "config_id": reg["id"],
            "baseline": baseline, "result": ch_reading["shared"]["value"]}


def _neighbours(lp: Loop, value) -> list:
    out = []
    for sign in (1, -1):
        v = _num(lp, float(value) + sign * lp.step)
        if lp.lo <= v <= lp.hi and v != _num(lp, value):
            out.append(v)
    return out


def _dataset(db, lp: Loop) -> tuple[list[dict], str | None]:
    rows = [r for r in _decisions(db, lp.key) if r["outcome"] is not None]
    if len(rows) < MIN_DECISIONS:
        return rows, (f"{len(rows)} decision(s) with an observed outcome; needs "
                      f"{MIN_DECISIONS} ({lp.outcome_source})")
    return rows, None


def run_loop(db, key: str, *, now: datetime | None = None) -> dict:
    """Observe, evaluate the incumbent's neighbours, and propose the best one, or say why not."""
    now = now or _now()
    lp = loop(key)
    observed = observe(db, key, now=now)
    rows, short = _dataset(db, lp)
    if short:
        return {"loop": key, "reading": "UNMEASURED", "observed": observed, "why": short,
                "decisions_with_outcome": len(rows)}
    inc = ensure_incumbent(db, key)
    results = []
    best = None
    inc_r = evaluate(db, key, inc["value"], rows=rows)
    insufficient = _sufficient(lp, inc_r)
    for candidate in _neighbours(lp, inc["value"]):
        ch_r = evaluate(db, key, candidate, rows=rows)
        v = compare(lp, inc_r, ch_r)
        results.append({"value": candidate, "promote": v["promote"], "gain": v["gain"],
                        "blockers": v["blockers"][:3]})
        if v["promote"] and (best is None or v["gain"] > best[1]):
            best = (candidate, v["gain"])
    outcome = None
    if best is not None:
        outcome = _consider(db, lp, best[0], proposed_by=lp.proposer, now=now, rows=rows,
                            inc=inc)
    elif results:
        top = max(results, key=lambda r: (r["gain"] is not None, r["gain"] or 0))
        outcome = _consider(db, lp, top["value"], proposed_by=lp.proposer, now=now,
                            rows=rows, inc=inc)
    return {"loop": key, "reading": "UNMEASURED" if insufficient else "measured",
            "why": insufficient, "observed": observed,
            "decisions_with_outcome": len(rows), "incumbent": inc,
            "incumbent_reading": inc_r, "candidates": results, "outcome": outcome}


def cycle(db, *, now: datetime | None = None) -> dict:
    """Every loop, once. Isolated: one loop's failure is reported, never another's silence."""
    now = now or _now()
    out = {}
    for lp in LOOPS:
        try:
            out[lp.key] = run_loop(db, lp.key, now=now)
        except Exception as exc:  # noqa: BLE001 - reported per loop, never swallowed silently
            out[lp.key] = {"loop": lp.key, "reading": "ERROR",
                           "why": f"{type(exc).__name__}: {str(exc)[:200]}"}
    _audit(db, ACTION + ".cycle", {k: {kk: v.get(kk) for kk in ("reading", "why", "observed",
                                                              "decisions_with_outcome")}
                                   | {"state": (v.get("outcome") or {}).get("state")}
                                   for k, v in out.items()})
    return {"at": now.isoformat(), "loops": out}


def submit(db, key: str, params_to: dict, *, proposed_by: str,
           now: datetime | None = None) -> dict:
    """A proposal from any agent (or the owner's tooling): guarded first, then evaluated."""
    now = now or _now()
    lp = BY_KEY.get(key)
    if lp is None:
        verdict = invariants.Verdict(False, str(key), "undeclared_surface",
                                     f"{key!r} is not a policy loop; undeclared surfaces are "
                                     f"protected")
        return refuse(db, str(key)[:64], params_to if isinstance(params_to, dict) else {},
                      [verdict], proposed_by=proposed_by)
    bad = invariants.check_payload(params_to, tunable=lp.tunable())
    if bad:
        return refuse(db, key, params_to, bad, proposed_by=proposed_by)
    rows, short = _dataset(db, lp)
    if short:
        pid = _record(db, key, NO_GAIN, proposed_by=proposed_by, params_from={},
                      params_to=params_to, evidence={"why": short, "external": True})
        return {"proposal": pid, "state": NO_GAIN, "why": short}
    inc = ensure_incumbent(db, key)
    return _consider(db, lp, params_to[lp.param], proposed_by=proposed_by, now=now,
                     rows=rows, inc=inc, external=True)


# ---- the sandbox side: trial, execute, monitor, rollback, verify ---------------------------


def _change(db, iid: int) -> dict:
    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, iid)
        if row is None:
            raise LoopRefused(f"no improvement {iid}")
        return {**dict((row.evidence or {}).get("change") or {}),
                "_promoted_at": _aware(row.promoted_at), "_baseline": row.baseline_value,
                "_seen": list((row.evidence or {}).get("monitored_windows") or [])}


def trial(db, iid: int) -> dict:
    """Re-derive the challenger's value from the frozen decision rows named on the proposal."""
    change = _change(db, iid)
    lp = loop(change.get("loop", ""))
    rows = _decisions(db, lp.key, ids=[int(i) for i in change.get("decision_ids") or []])
    if not rows or any(r["outcome"] is None for r in rows):
        return {"ran": False, "trial": TRIAL, "why": "the frozen decision rows are gone"}
    fp = fingerprint(rows)
    params_to, params_from = change["params_to"], change["params_from"]
    inc_r = evaluate(db, lp.key, params_from[lp.param], rows=rows)
    ch_r = evaluate(db, lp.key, params_to[lp.param], rows=rows)
    verdict = compare(lp, inc_r, ch_r)
    blockers = list(verdict["blockers"])
    for v in invariants.check_payload(params_to, tunable=lp.tunable()):
        blockers.append(v.reason)
    return {"ran": True, "trial": TRIAL, "value": ch_r["shared"]["value"],
            "run_ref": f"policy:{lp.key}:{fp[:16]}:c{change['config_id']}",
            "reads": {"decisions": len(rows), "fingerprint": fp,
                      "drifted": fp != change.get("fingerprint")},
            "blockers": blockers,
            "why": (f"{lp.param}={params_to[lp.param]} reads {ch_r['shared']['value']} against "
                    f"{inc_r['shared']['value']} on the frozen {len(rows)} decisions")}


def execute(db, iid: int) -> dict:
    """Make the promoted challenger the registry incumbent -- what the consumer reads next."""
    from . import league

    change = _change(db, iid)
    lp = loop(change["loop"])
    bad = invariants.check_payload(change["params_to"], tunable=lp.tunable())
    if bad:
        refuse(db, lp.key, change["params_to"], bad, proposed_by="executor")
        raise LoopRefused(f"execution refused by the invariant guard: {bad[0].reason}")
    out = league.promote(db, int(change["config_id"]), evidence_ref=f"improvement:{iid}",
                         outcome={"promoted_by": "improve.sandbox", "improvement": iid,
                                  "previous_incumbent": change.get("replaces"),
                                  "promoted_at": _now().isoformat()})
    now_reads = active(db, lp.key)
    if now_reads.get("config_id") != int(change["config_id"]):
        raise LoopRefused(f"promotion did not reach the consumer read: {now_reads}")
    prop = _proposal_for_improvement(db, iid)
    if prop:
        _set_state(db, prop["id"], PROMOTED, executed={"config_id": change["config_id"],
                                                       "active": now_reads})
    _remember(db, lp.key, "promoted", change["params_to"],
              f"{lp.key}: {change['params_from']} -> {change['params_to']} promoted after the "
              f"shadow replay beat the baseline; consumers ({lp.consumer.split(',')[0]}) "
              f"read it from now", f"improvement:{iid}:promoted")
    return {"executed": "registry incumbent", "implements": lp.key, "changes_artifact": False,
            "consumer": lp.consumer[:120], "active_value": now_reads["value"], **out}


def monitor(db, iid: int) -> dict:
    """Measure the promoted policy on decisions taken after the promotion."""
    change = _change(db, iid)
    lp = loop(change["loop"])
    promoted_at = change["_promoted_at"]
    if promoted_at is None:
        return {"judged": False, "why": "not promoted"}
    observe(db, lp.key)
    if lp.family == "replay":
        fresh = [r for r in _decisions(db, lp.key, after=promoted_at)
                 if r["outcome"] is not None and r["config_id"] == int(change["config_id"])]
        if len(fresh) < MIN_FRESH:
            return {"judged": False,
                    "why": f"{len(fresh)} post-promotion decision(s) observed; needs {MIN_FRESH}"}
        observed = _mean(r["outcome"].get("value") for r in fresh)
        replaced = change["_baseline"]
    else:
        history = [r for r in _decisions(db, lp.key) if r["outcome"] is not None]
        fresh = [r for r in history if r["at"] > promoted_at]
        new = _predict(lp, fresh, history, change["params_to"][lp.param])
        old = _predict(lp, fresh, history, change["params_from"][lp.param])
        if new["n"] < MIN_FRESH or new["value"] is None or old["value"] is None:
            return {"judged": False,
                    "why": f"{new['n']} post-promotion subject(s) with a measured F1; needs "
                           f"{MIN_FRESH}"}
        observed, replaced = new["value"], old["value"]
    window = fingerprint(fresh)[:16]
    if window in change["_seen"]:
        return {"judged": False, "why": "already judged against these decisions"}
    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, iid)
        row.evidence = {**(row.evidence or {}),
                        "monitored_windows": change["_seen"] + [window],
                        "monitoring": {"observed": observed, "replaced_reads": replaced,
                                       "decisions": len(fresh), "window": window}}
    worse = replaced is not None and observed < replaced - REGRESSION_MARGIN
    prop = _proposal_for_improvement(db, iid)
    if prop and not worse:
        _remember(db, lp.key, "retained", change["params_to"],
                  f"{lp.key} {change['params_to']} held after promotion: {observed} on "
                  f"{len(fresh)} fresh decisions against {replaced}",
                  f"improvement:{iid}:retained:{window}",
                  delta=round(observed - (replaced or 0.0), 6))
    return {"judged": True, "observed": observed, "replaced_reads": replaced, "worse": worse,
            "decisions": len(fresh),
            "why": (f"{lp.key}: {observed} on {len(fresh)} post-promotion decisions against "
                    f"{replaced}" + (f", worse by more than {REGRESSION_MARGIN}" if worse
                                     else ""))}


def rollback(db, iid: int, *, why: str) -> dict:
    from . import league

    change = _change(db, iid)
    lp = loop(change["loop"])
    out = league.rollback(db, kind=KIND, key=lp.registry_key,
                          to_config_id=int(change["replaces"]), why=why)
    return out


def rollback_verified(db, iid: int) -> dict:
    """The consumer reads the replaced version again -- read back, not assumed."""
    change = _change(db, iid)
    lp = loop(change["loop"])
    reads = active(db, lp.key)
    ok = reads.get("config_id") == int(change.get("replaces") or 0)
    if ok:
        prop = _proposal_for_improvement(db, iid)
        if prop and prop["state"] != ROLLED_BACK:
            _set_state(db, prop["id"], ROLLED_BACK, rollback={"active": reads, "why": "monitor"})
        _remember(db, lp.key, "rolled_back", change["params_to"],
                  f"{lp.key}: {change['params_to']} was rolled back to {change['params_from']} "
                  f"after post-change outcomes regressed; not to be re-proposed for "
                  f"{LESSON_MEMORY_DAYS} days without new evidence", f"improvement:{iid}:rollback")
    return {"verified": ok, "check": "policy_loop.rollback", "active": reads,
            "expected_config_id": change.get("replaces"),
            "why": ("the consumer reads the replaced version" if ok else
                    f"the consumer reads config {reads.get('config_id')}")}


# ---- the consumer-facing reads ---------------------------------------------------------------


def defect_watchlist(db) -> dict:
    """CIR topics whose observed defect rate meets the active threshold (extra review)."""
    lp = BY_KEY["pattern_defect_watch"]
    current = active(db, lp.key)
    rows = [r for r in _decisions(db, lp.key) if r["outcome"] is not None]
    tally: dict[str, list] = {}
    for r in rows:
        for t in r["features"].get("topics") or []:
            tally.setdefault(t, []).append(float(r["outcome"]["value"]))
    watched = {t: round(sum(v) / len(v), 4) for t, v in tally.items()
               if len(v) >= MIN_PRIOR_SUBJECTS and sum(v) / len(v) >= current["value"]}
    return {"threshold": current, "topics": dict(sorted(watched.items())),
            "observed_releases": len(rows), "basis": "measured" if rows else "unknown"}


def requires_extra_review(db, cir: dict) -> dict:
    """Tightening only: whether a CIR touches a watched defect topic. Never relaxes a gate."""
    from ..learn.service import topics

    watch = defect_watchlist(db)
    hit = sorted(set(topics(cir or {})) & set(watch["topics"]))
    return {"extra_review": bool(hit), "topics": hit, "threshold": watch["threshold"]["value"]}


def visual_precheck(db) -> dict:
    """Asset groups whose observed gate block rate meets the active threshold."""
    lp = BY_KEY["visual_gate_precheck"]
    current = active(db, lp.key)
    rows = [r for r in _decisions(db, lp.key) if r["outcome"] is not None]
    tally: dict[str, list] = {}
    for r in rows:
        tally.setdefault(r["features"].get("group") or "?", []).append(
            float(r["outcome"]["value"]))
    groups = {g: round(sum(v) / len(v), 4) for g, v in tally.items()
              if len(v) >= MIN_PRIOR_SUBJECTS and sum(v) / len(v) >= current["value"]}
    return {"threshold": current, "groups": dict(sorted(groups.items())),
            "observed_assets": len(rows), "basis": "measured" if rows else "unknown"}


def cost_watch(db, *, now: datetime | None = None) -> dict:
    """In-flight releases whose early actual cost meets the active review threshold."""
    from sqlalchemy import select

    from ..core.models import CostEntry

    now = now or _now()
    current = active(db, "release_cost_watch")
    by_slug: dict[str, list] = {}
    with db.session() as s:
        for c in s.scalars(select(CostEntry).order_by(CostEntry.at, CostEntry.id)):
            if c.product_slug and float(c.amount_cad or 0.0) > 0:
                by_slug.setdefault(c.product_slug, []).append((_aware(c.at), float(c.amount_cad)))
    flagged = {}
    for slug, entries in by_slug.items():
        if now - entries[0][0] >= timedelta(days=COST_OBSERVATION_DAYS):
            continue
        early = round(sum(a for _t, a in entries[:EARLY_COST_ENTRIES]), 6)
        if early >= current["value"]:
            flagged[slug] = early
    return {"threshold": current, "releases": dict(sorted(flagged.items())),
            "basis": "measured (actual amount_cad)" if by_slug else "unknown"}


def state(db=None) -> dict:
    return {"action": ACTION, "trial": TRIAL, "kind": KIND, "surface": SURFACE,
            "loops": [{"key": lp.key, "title": lp.title, "cell": lp.cell,
                       "family": lp.family, "param": lp.param, "default": lp.default,
                       "bounds": [lp.lo, lp.hi], "metric": lp.metric,
                       "guardrail": lp.guardrail, "proposer": lp.proposer,
                       "challenger": lp.challenger, "consumer": lp.consumer,
                       "consumer_status": lp.consumer_status,
                       "outcome_source": lp.outcome_source} for lp in LOOPS],
            "evidence_floors": {"min_decisions": MIN_DECISIONS, "min_matched": MIN_MATCHED,
                                "holdout_share": HOLDOUT_SHARE, "gain_margin": GAIN_MARGIN,
                                "min_fresh": MIN_FRESH,
                                "regression_margin": REGRESSION_MARGIN},
            "invariants": invariants.describe()}
