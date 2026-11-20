"""ENG-RESEARCH: the research loop, made traceable from observation to engineering.

The loop already runs on the existing jobs; this module only READS it and records what it
concluded, so a scan is never the end of the story:

    observe        intel.watchlist_scan / mjs.scan (official Etsy Open API v3)
    identify       intel.watchlist_compare -> a validated arena -> a `watchlist` coverage gap
    validate       the gap's research task, answered from fresh, durable observations
    propose        radar.proposal_writer: an ORIGINAL proposal in our own vocabulary
    score/approve  radar.concept_intake (intake.run) -> radar.score -> the pre-engineering gate
    engineering    cir.draft (`draft:<slug>`), enqueued by radar.score when the gate passes

`lineage` follows every watchlist gap through those stages from the rows the stages
themselves write (coverage gap, research task, radar concept, job rows). `conclude` stores
one dated conclusion per day (`intel.research_conclusion`): either the opportunities and the
stage each reached -- and, if held, exactly what holds it -- or an explicit "no qualifying
opportunity" with the evidence for that. It is called by `radar.concept_intake` after the
writer and intake ran, so every cycle ends in a recorded outcome.

Competitor content never enters: aliases, our pod labels, our own slugs and our own reasons
only (`_assert_no_content`, the watchlist's L-3 rule). Read-only apart from the one reading.
CA$0, no network, no model call.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

CONCLUSION_READING = "intel.research_conclusion"
NO_QUALIFYING = "no_qualifying_opportunity"
OPPORTUNITIES = "opportunities"
CONCLUSION_FAILED = "conclusion_failed"

# The stages, in loop order. A gap's stage is the furthest one its own rows prove.
STAGES = ("validated", "researching", "proposed", "intake_refused", "approved", "scored",
          "gate_refused", "gate_waiting", "engineering")
_RANK = {s: i for i, s in enumerate(STAGES)}
# A gap at or past `approved` is a qualifying opportunity: research-backed, original, and
# accepted by intake for scoring.
QUALIFYING_FROM = "approved"


def _now(now=None) -> datetime:
    return now or datetime.now(timezone.utc)


def _iso(v):
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return v


def _jobs_for_slug(db, slug: str) -> tuple[dict | None, dict | None]:
    """(newest radar.score of this concept, its cir.draft) from the job rows."""
    from sqlalchemy import desc, select

    from ..core.models import Job

    with db.session() as s:
        score = s.scalar(select(Job).where(Job.job_type == "radar.score",
                                           Job.idempotency_key.like(f"score:{slug}:%"))
                         .order_by(desc(Job.id)).limit(1))
        draft = s.scalar(select(Job).where(Job.idempotency_key == f"draft:{slug}").limit(1))

        def row(j):
            if j is None:
                return None
            out = dict(j.outputs or {})
            gate = out.get("gate") if isinstance(out.get("gate"), dict) else {}
            return {"job_id": j.id, "job_type": j.job_type,
                    "status": getattr(j.status, "value", str(j.status)),
                    "promoted": out.get("promoted"),
                    "gate": gate.get("decision") or (
                        "exempt" if out.get("gate_exempt") else None),
                    "waiting_on": list(gate.get("waiting_on") or []),
                    "failed": list(gate.get("failed") or []),
                    # Review H1: our own #108 rule text only (never a novelty reason, which
                    # can quote what a concept was measured against).
                    "silhouette_reasons": [r for r in gate.get("reasons") or []
                                           if str(r).startswith("#108 ")][:2],
                    "at": _iso(j.finished_at or j.created_at)}
        return row(score), row(draft)


def _proposal_stage(p: dict, score: dict | None, draft: dict | None) -> str:
    from ..radar import intake

    if draft is not None:
        return "engineering"
    if score is not None and score["status"] == "done":
        if score["gate"] == "refused":
            return "gate_refused"
        if score["gate"] == "waiting":
            return "gate_waiting"
        return "scored"
    if p.get("state") == intake.APPROVED or score is not None:
        return "approved"
    if p.get("state") == intake.REFUSED:
        # Refused by concept intake itself (for example, no verified construction engine can
        # make it): a terminal hold, never shown as still awaiting judgement.
        return "intake_refused"
    return "proposed"


def _precheck(db, task_id, slug: str) -> dict | None:
    """The #108 precheck the proposal writer recorded on this proposal, or None."""
    from . import research

    with db.session() as s:
        t = s.get(research.ResearchTask, int(task_id))
        props = list((t.detail or {}).get("concept_proposals") or []) if t else []
    got = next((p.get("silhouette_precheck") for p in props if p.get("slug") == slug), None)
    return dict(got) if isinstance(got, dict) else None


def lineage(db, *, now: datetime | None = None) -> list[dict]:
    """Every watchlist gap, the furthest stage its own rows prove, and why it stopped there."""
    from sqlalchemy import select

    from ..core.models import CoverageGap
    from ..radar import proposal_writer
    from . import research

    research._ensure(db)
    with db.session() as s:
        gaps = [(g.id, g.pod, g.state, dict(g.evidence or {}))
                for g in s.scalars(select(CoverageGap).where(
                    CoverageGap.benchmark_key == proposal_writer.WATCHLIST_KEY)
                    .order_by(CoverageGap.id))]
    out = []
    for gid, pod, state, ev in gaps:
        task_id = ev.get("research_task_id")
        task_state = None
        if task_id:
            with db.session() as s:
                t = s.get(research.ResearchTask, int(task_id))
                task_state = t.state if t is not None else None
        proposals = []
        for p in proposal_writer.prior_proposals(db, gid):
            score, draft = _jobs_for_slug(db, p["slug"])
            proposals.append({"slug": p["slug"], "task": p["task"],
                              "intake_state": p.get("state"),
                              "intake_reasons": list(p.get("reasons") or []),
                              "stage": _proposal_stage(p, score, draft),
                              "silhouette": _precheck(db, p["task"], p["slug"]),
                              "score_job": score, "engineering_job": draft})
        stage = "researching" if task_id else "validated"
        for p in proposals:
            if _RANK[p["stage"]] > _RANK[stage]:
                stage = p["stage"]
        if stage == "researching" and task_state != research.ANSWERED:
            held = f"research task {task_id} is {task_state or 'missing'}"
        elif stage in ("validated", "researching"):
            held = "no proposal yet (the writer's reason is in the cycle's skip list)"
        elif stage == "gate_waiting":
            waits = sorted({w for p in proposals for w in
                            ((p["score_job"] or {}).get("waiting_on") or [])})
            held = f"the pre-engineering gate waits on {waits}; unmeasured is never passing"
        elif stage == "gate_refused":
            failed = sorted({w for p in proposals for w in
                             ((p["score_job"] or {}).get("failed") or [])})
            why108 = next((r for p in proposals for r in
                           ((p["score_job"] or {}).get("silhouette_reasons") or [])), None)
            held = (f"the pre-engineering gate refused it ({failed}); returned to development"
                    + (f". {why108[:240]}" if why108 else ""))
        elif stage == "intake_refused":
            why = next((r for p in proposals for r in (p.get("intake_reasons") or [])), "")
            held = "concept intake refused it" + (f": {why[:240]}" if why else "")
            bad = next((p["silhouette"] for p in proposals
                        if p["silhouette"] and not p["silhouette"].get("passes")), None)
            if bad:
                held += (f"; held by #108: it honestly carries no silhouette qualifier "
                         f"({(bad.get('reasons') or [''])[0][:200]})")
        elif stage in ("proposed", "approved"):
            held = ("awaiting concept intake's judgement" if stage == "proposed"
                    else "approved; radar.score not yet run")
            # Review H1: a concept whose derived brief fails #108 is named as held by it now,
            # before scoring -- the gate will refuse it, and nothing relabels it to pass.
            bad = next((p["silhouette"] for p in proposals
                        if p["silhouette"] and not p["silhouette"].get("passes")), None)
            if bad:
                held += (f"; held by #108: it honestly carries no silhouette qualifier "
                         f"({(bad.get('reasons') or [''])[0][:200]})")
        else:
            held = None
        held_by_108 = stage == "gate_refused" and any(
            "silhouette" in ((p["score_job"] or {}).get("failed") or []) for p in proposals) \
            or (stage in ("proposed", "intake_refused", "approved")
                and "held by #108" in (held or ""))
        out.append({"gap": gid, "pod": pod, "gap_state": state,
                    "corroborated_by": list(ev.get("corroborated_by") or []),
                    "validated_at": ev.get("validated_at"),
                    "research_task": task_id, "research_state": task_state,
                    "proposals": proposals, "stage": stage,
                    # A refused gap, or one #108 holds, is not a qualifying opportunity.
                    "qualifying": (_RANK[stage] >= _RANK[QUALIFYING_FROM]
                                   and stage != "gate_refused" and not held_by_108),
                    "held_by_108": held_by_108,
                    "held_because": held})
    return out


def per_alias(rows: list[dict]) -> dict[str, dict]:
    """Downstream counts per corroborating shop alias: findings (validated gaps), concepts
    created from them and products that entered engineering."""
    out: dict[str, dict] = {}
    for r in rows:
        for alias in r["corroborated_by"]:
            e = out.setdefault(alias, {"findings": 0, "concepts": [], "engineering": []})
            e["findings"] += 1
            for p in r["proposals"]:
                if p["intake_state"] is not None:
                    e["concepts"].append(p["slug"])
                if p["stage"] == "engineering":
                    e["engineering"].append(p["slug"])
    return out


def _assert_no_content(payload: dict) -> None:
    from .watchlist import WATCHLIST

    text = json.dumps(payload, default=str).lower()
    for m in WATCHLIST:
        if m.shop_name.lower() in text or m.key.lower() in text:
            raise ValueError("the research conclusion carries a shop name or key; aliases only")


def conclude(db, *, now: datetime | None = None, written: list | None = None,
             skipped: list | None = None, intake_out: dict | None = None) -> dict:
    """Record the cycle's outcome: the opportunities and where each stands, or an explicit
    "no qualifying opportunity" with its evidence. One reading per UTC day (replaced)."""
    from ..runtime.etsy_ops import latest_reading, store_reading
    from .watchlist import COMPARE_READING

    now = _now(now)
    rows = lineage(db, now=now)
    comparison = latest_reading(db, COMPARE_READING) or {}
    qualifying = [r for r in rows if r["qualifying"]]
    evidence = {
        "comparison_at": comparison.get("at"),
        "shops_compared": len(comparison.get("shops") or []),
        # A shop is fresh in the comparison when any of its figures is graded MEASURED
        # (graded STALE or UNKNOWN otherwise, by the comparison's own rule).
        "shops_fresh": sum(1 for sh in comparison.get("shops") or []
                           if any((f or {}).get("grade") == "MEASURED"
                                  for f in (sh.get("figures") or {}).values())),
        "validated_arenas": [a.get("pod") for a in comparison.get("validated_arenas") or []],
        "unknown_arenas": [{"pod": a.get("pod"), "why": a.get("why")}
                           for a in comparison.get("unknown_arenas") or []],
        "gaps": [{k: r[k] for k in ("gap", "pod", "stage", "held_because")} for r in rows],
        "writer_skipped": [{"gap": x.get("gap"), "pod": x.get("pod"), "why": x.get("why")}
                           for x in (skipped or [])],
        "proposals_written": [w.get("slug") for w in (written or [])],
        "intake": {k: (intake_out or {}).get(k) for k in ("approved", "refused",
                                                          "candidates")},
    }
    if qualifying:
        outcome = OPPORTUNITIES
        why = (f"{len(qualifying)} qualifying opportunit(y/ies); "
               f"{sum(1 for r in qualifying if r['stage'] == 'engineering')} in engineering")
    else:
        outcome = NO_QUALIFYING
        if not comparison:
            why = "no watchlist comparison has been recorded, so nothing could be validated"
        elif not rows:
            why = ("the comparison validated no arena: no pod is occupied by two or more "
                   "freshly observed watchlist shops that we do not already cover")
        else:
            why = ("no validated arena has an approved concept yet: "
                   + "; ".join(f"{r['pod']}: {r['held_because']}" for r in rows)[:600])
    payload = {"at": now.isoformat(), "outcome": outcome, "why": why,
               "qualifying": [{k: r[k] for k in ("gap", "pod", "stage", "held_because")}
                              | {"slugs": [p["slug"] for p in r["proposals"]]}
                              for r in qualifying],
               "evidence": evidence, "copies_competitor_content": False}
    _assert_no_content(payload)
    store_reading(db, CONCLUSION_READING, payload, now=now)
    return payload


def latest_conclusion(db) -> dict | None:
    from ..runtime.etsy_ops import latest_reading

    return latest_reading(db, CONCLUSION_READING)


# ---- the source registry -------------------------------------------------------------------
#
# Every research source the repository documents, with the agent and job that collect it.
# The cadence is read from `runtime.worker.CADENCES` (never restated here), so the registry
# cannot claim a schedule the scheduler does not have. A source with no collector is kept as
# MISSING -- visible, never silently dropped (D-W4-OWNER-SEEDSHOPS: "do not silently drop").
# research/final_build/w6/research_sources.md is the prose form of this table.

SCHEDULED, DISABLED, BLOCKED, MISSING = "scheduled", "disabled", "blocked", "missing"
ETSY_CREDENTIAL = "etsy_credential"     # ETSY_API_KEY + ETSY_SHARED_SECRET, proven by etsy.probe
FETCH_ENV = "BRAMBLELOOP_RESEARCH_FETCH"
API = "official Etsy Open API v3 (intel.etsy_public.PublicReader)"


def _src(id, label, agent, job_type, method, *, gate=None, kind="shop", note=""):
    return {"id": id, "label": label, "agent": agent, "job_type": job_type,
            "method": method, "gate": gate, "kind": kind, "note": note}


def sources() -> tuple[dict, ...]:
    """The registry. Watchlist shops come from `intel.watchlist.WATCHLIST` itself (aliases in
    every reading; the id is the member key, which the owner's directive names)."""
    from .watchlist import ANCHOR, WATCHLIST

    shops = []
    for m in WATCHLIST:
        if m.role == ANCHOR:
            shops.append(_src(m.key, f"watchlist {m.role}", "market_radar", "mjs.scan",
                              API + ": findShops, shop listings, images; adaptive interval",
                              gate=ETSY_CREDENTIAL,
                              note="reviews weekly through mjs.reviews"))
        else:
            shops.append(_src(m.key, f"watchlist {m.role}", "market_radar",
                              "intel.watchlist_scan",
                              API + ": findShops, shop listings, getReviewsByShop (weekly)",
                              gate=ETSY_CREDENTIAL,
                              note="an unreachable shop is recorded not_accessible with its "
                                   "dated alternative evidence; monitoring is kept"))
    return tuple(shops) + (
        _src("watchlist_compare", "watchlist comparison -> validated arenas", "market_radar",
             "intel.watchlist_compare", "stored official-API rows; no network", kind="analysis"),
        _src("mjs_reviews", "anchor review themes", "market_radar", "mjs.reviews",
             API + ": getReviewsByShop", gate=ETSY_CREDENTIAL, kind="shop_aux"),
        _src("second_market", "second-market benchmark shops (CA, UK)", "market_radar",
             "intel.panel_discovery",
             "candidates chosen from dated search-index snippets, joined only after "
             + API + " resolves the shop and getShop states the market",
             gate=ETSY_CREDENTIAL, kind="panel",
             note="alternates are recorded only, never registered"),
        _src("category_leaders", "category-leader panel (top of the API search index)",
             "market_radar", "intel.panel_discovery", API + ": listings/active + getShop",
             gate=ETSY_CREDENTIAL, kind="panel"),
        _src("benchmark_refresh", "benchmark refresh (panel, SERP, purchased library)",
             "market_radar", "intel.benchmark_refresh", "stored rows; raises owner purchase "
             "asks only", kind="analysis"),
        _src("benchmark_health", "benchmark URL health", "market_radar",
             "intel.benchmark_health", "rendered page when a browser worker is configured, "
             "otherwise " + API + " findShops", gate=ETSY_CREDENTIAL, kind="shop_aux"),
        _src("serp_capture", "search results laboratory (pod + seasonal queries)",
             "market_radar", "intel.serp_capture", API + ": findAllListingsActive sort_on=score",
             gate=ETSY_CREDENTIAL, kind="search"),
        _src("culture_sweep", "culture radar: Wikimedia pageviews (standing topics, top "
             "articles, colours, children's series) + Etsy first-seen demand",
             "market_radar", "culture.sweep",
             "Wikimedia REST pageviews API (keyless, public) + stored listing rows",
             kind="trend"),
        _src("gallery_analysis", "competitor gallery judgement", "market_radar",
             "intel.gallery_analysis", "stored API gallery URLs judged by the vision model "
             "inside market_radar's ceiling", gate="image_vision", kind="analysis"),
        _src("competitor_snapshot", "competitor aggregate snapshot", "market_radar",
             "radar.competitor_snapshot", "stored rows; aggregates only", kind="analysis"),
        _src("scan_evidence", "daily per-shop scan evidence", "market_radar",
             "intel.scan_evidence", "stored rows", kind="analysis"),
        # ENG-BENCHBUY (review main-integ #2): the daily benchmark shopping list is a research
        # job over stored scan rows (CA$0, no network); nothing is bought by it.
        _src("benchmark_shopping", "benchmark shopping list (per-shop picks, owner buys)",
             "market_radar", "intel.benchmark_shopping", "stored rows; owner card only",
             kind="analysis"),
        _src("market_radar", "Market Radar signal review (POOL + intake concepts, arbitrage)",
             "market_radar", "radar.scan", "stored rows; no network", kind="analysis"),
        _src("concept_intake", "concept intake (proposal writer -> intake -> radar.score)",
             "market_radar", "radar.concept_intake", "stored rows; no network",
             kind="analysis"),
        # ENG-CONCEPTS-100: the evidence-backed concept pool (scan rows -> original concepts).
        _src("concept_pool", "concept pool (scan evidence -> original concepts -> intake)",
             "market_radar", "radar.concept_pool", "stored rows; no network", kind="analysis"),
        _src("research_sweep", "Research Agent sweep", "research_agent", "research.sweep",
             "stored rows; enqueues research.investigate", kind="analysis"),
        _src("research_fetch", "allow-listed public reference fetch (gov, Wikipedia, "
             "Etsy help)", "learn", "learn.scan", "HTTPS GET to an allow-list of hosts",
             gate="env:" + FETCH_ENV, kind="reference",
             note="off unless the deployment sets BRAMBLELOOP_RESEARCH_FETCH=1"),
        _src("marketplace_insights", "Etsy Marketplace Insights", "owner", None,
             "owner-recorded readings (POST /api/insights/snapshot); Etsy has no API for "
             "them", gate="owner_readings", kind="owner"),
        _src("external_trends", "external trend platforms (Google Trends, Pinterest "
             "Trends, social)", "market_radar", None,
             "none: no official API is wired; never scraped", kind="trend",
             note="spec/05 'external traffic/content ecosystems'; master v1.1 'external "
                  "research'. Wikimedia pageviews is the only trend feed"),
        # Review M2: the off-Etsy competitor channels Master Plan MP1.2-s4 asks for. Each is
        # UNAVAILABLE (FOUR_SHOP_COMPARISON.md: "Off-Etsy channels (websites, YouTube,
        # Pinterest) have no compliant collector") and kept visible as a limitation.
        _src("competitor_websites", "competitors' own websites (MP1.2-s4)", "market_radar",
             None, "none: no compliant collector; pages are never scraped", kind="offsite",
             note="UNAVAILABLE: no allow-listed, terms-compliant fetch exists for a "
                  "competitor's site; research_fetch is limited to gov, Wikipedia and Etsy "
                  "help"),
        _src("youtube", "competitors' YouTube channels (MP1.2-s4)", "market_radar", None,
             "none: the YouTube Data API is not wired and no key is provisioned",
             kind="offsite",
             note="UNAVAILABLE: needs a YouTube Data API key (owner action) and a collector"),
        _src("pinterest", "competitors' Pinterest boards (MP1.2-s4)", "market_radar", None,
             "none: the Pinterest API needs an approved app and owner OAuth; never scraped",
             kind="offsite",
             note="UNAVAILABLE: needs Pinterest API app approval and owner OAuth"),
    )


def cadences() -> dict[str, int]:
    from ..runtime.worker import CADENCES

    out: dict[str, int] = {}
    for _name, _agent, job_type, period in CADENCES:
        out.setdefault(job_type, period)
    return out


def status_of(src: dict, *, env=None, credential: str | None = None,
              vision_ok: bool | None = None, cad=None) -> tuple[str, str]:
    """(scheduled | disabled | blocked | missing, why). Never OK on an assumption: a gate
    whose state is not known reads as the gate, named."""
    import os

    env = os.environ if env is None else env
    cad = cadences() if cad is None else cad
    if not src["job_type"]:
        if src["gate"] == "owner_readings":
            return BLOCKED, "no collector exists by design: the owner records the readings"
        if src.get("kind") == "offsite":
            return MISSING, ("UNAVAILABLE: no compliant collector exists; kept visible as a "
                             "limitation (" + src["note"].split(": ", 1)[-1] + ")")
        return MISSING, "no collector and no cadence exist; kept visible as a limitation"
    if src["job_type"] not in cad:
        return MISSING, f"job {src['job_type']} has no cadence in runtime.worker.CADENCES"
    gate = src["gate"]
    if gate and gate.startswith("env:"):
        var = gate[4:]
        if str(env.get(var) or "").strip() != "1":
            return DISABLED, f"{var} is not set to 1 in this deployment"
    if gate == ETSY_CREDENTIAL and credential not in (None, "OK"):
        return BLOCKED, f"the Etsy read credential reads {credential}; jobs no-op until " \
                        f"etsy.probe succeeds"
    if gate == "image_vision" and vision_ok is not True:
        # Review LOW: an unreadable vision state is not a usable one.
        return BLOCKED, ("no usable vision model (image_vision closed)" if vision_ok is False
                         else "the image_vision gate's state could not be read; unknown is "
                              "not usable")
    return SCHEDULED, f"every {cad[src['job_type']] // 3600} h via {src['job_type']}"


# ---- per-source evidence for Mission Control (read-only) -----------------------------------

FAILURE_WINDOW_DAYS = 7


def _job_facts(db, job_types: set[str], now: datetime) -> dict[str, dict]:
    """Per job type: newest attempt, newest success, failures in the window. One query each."""
    from datetime import timedelta

    from sqlalchemy import func, select

    from ..core.models import Job, JobStatus

    out: dict[str, dict] = {jt: {"last_attempt": None, "last_success": None,
                                 "failures_7d": 0, "last_failure_class": None}
                            for jt in job_types}
    since = now - timedelta(days=FAILURE_WINDOW_DAYS)
    with db.session() as s:
        for jt, status, at in s.execute(
                select(Job.job_type, Job.status,
                       func.max(func.coalesce(Job.finished_at, Job.created_at)))
                .where(Job.job_type.in_(job_types)).group_by(Job.job_type, Job.status)):
            e = out[jt]
            at = _iso(at)
            if e["last_attempt"] is None or (at and at > e["last_attempt"]):
                e["last_attempt"] = at
            if status == JobStatus.DONE:
                e["last_success"] = at
        for jt, n in s.execute(
                select(Job.job_type, func.count(Job.id))
                .where(Job.job_type.in_(job_types),
                       Job.status.in_((JobStatus.FAILED, JobStatus.DEAD)),
                       Job.created_at >= since).group_by(Job.job_type)):
            out[jt]["failures_7d"] = int(n)
    return out


def health_of(row: dict) -> str:
    """Review M1: the per-row pill, derived. OK only for a scheduled source that has
    succeeded, is not failing and is not stale. Never succeeded -> UNKNOWN; failing -> DEGRADED;
    not scheduled -> UNKNOWN (missing) or DEGRADED (disabled / blocked)."""
    if row.get("status") != SCHEDULED:
        return "UNKNOWN" if row.get("status") == MISSING else "DEGRADED"
    failing = (row.get("consecutive_failures") or 0) > 0 if "consecutive_failures" in row \
        else (row.get("failures_7d") or 0) > 0
    if failing:
        return "DEGRADED"
    if not row.get("last_success"):
        return "UNKNOWN"
    if row.get("stale"):
        return "STALE"
    return "OK"


def _tables_exist(db) -> bool:
    from sqlalchemy import inspect

    from ..radar.intake import RadarConcept
    from . import research

    insp = inspect(db.engine)
    return insp.has_table(RadarConcept.__tablename__) and \
        insp.has_table(research.ResearchTask.__tablename__)


def evidence(db, *, now: datetime | None = None, env=None) -> dict:
    """One row per registered source: responsible agent and method, status and why, last
    attempt / success / source timestamp, listings observed and changes, freshness and next
    scan, failures and backoff, and downstream findings -> concepts -> engineering. Shops are
    named by alias. Writes nothing (the board's rule): lineage is read only when its tables
    already exist."""
    from ..gateway import providers as gw
    from ..ops import production_evidence as PE
    from ..ops import scheduler_readback as SR
    from ..runtime.intel_ops import benchmark_alias
    from .watchlist import BY_KEY, _state

    now = _now(now)
    cad = cadences()
    scans = PE.competitor_scans(db, now=now)
    by_alias = {r.get("alias"): r for r in scans.get("shops") or []}
    credential = scans.get("credential")
    try:
        vision_ok = bool(gw.vision_usable(db))
    except Exception:  # noqa: BLE001 - unknown is not usable
        vision_ok = None
    sched = {c["job_type"]: c for c in SR.scheduler_block(db, now=now)["cadences"]}
    reg = sources()
    facts = _job_facts(db, {s["job_type"] for s in reg if s["job_type"]}, now)
    tables = _tables_exist(db)
    rows = lineage(db, now=now) if tables else []
    downstream = per_alias(rows)
    out = []
    for src in reg:
        status, why = status_of(src, env=env, credential=credential, vision_ok=vision_ok,
                                cad=cad)
        jt = src["job_type"]
        f = facts.get(jt) or {}
        c = sched.get(jt) or {}
        row = {"id": src["id"], "kind": src["kind"], "label": src["label"],
               "agent": src["agent"], "job_type": jt, "method": src["method"], "note": src["note"],
               "status": status, "why": why,
               "cadence_hours": round(cad[jt] / 3600, 2) if jt in cad else None,
               "last_attempt": f.get("last_attempt"), "last_success": f.get("last_success"),
               "failures_7d": f.get("failures_7d"),
               "next_scan": c.get("next_window_at"),
               "skipped_because": c.get("skipped_because")}
        if src["id"] in BY_KEY:
            alias = benchmark_alias(src["id"])
            sh = by_alias.get(alias) or {}
            st = _state(db, src["id"])
            # Review LOW: with no lineage tables the downstream is UNKNOWN (None), not 0.
            d = (downstream.get(alias) or {"findings": 0, "concepts": [], "engineering": []}) \
                if tables else {"findings": None, "concepts": None, "engineering": None}
            row.update(
                id=alias, label=f"{src['label']} (owner order {sh.get('owner_order')})",
                last_attempt=sh.get("last_attempted"), last_success=sh.get("last_successful"),
                source_timestamp=sh.get("etsy_source_timestamp"),
                listings_observed=sh.get("listings_seen_last_scan"),
                listings_live=sh.get("listings_live"),
                changes_discovered=st.get("changes") if st.get("state") == "ok" else None,
                stale=sh.get("stale"), next_scan=sh.get("next_due") or row["next_scan"],
                consecutive_failures=sh.get("consecutive_failures"),
                failure_class=sh.get("failure_class"),
                backoff_until=sh.get("backoff_until"),
                not_attempted_because=sh.get("not_attempted_because"),
                findings=d["findings"],
                concepts=None if d["concepts"] is None else sorted(set(d["concepts"])),
                engineering=None if d["engineering"] is None else sorted(set(d["engineering"])))
        row["health"] = health_of(row)
        out.append(row)
    concl = latest_conclusion(db) or {}
    payload = {
        "as_of": now.isoformat(), "credential": credential, "sources": out,
        "counts": {k: sum(1 for r in out if r["status"] == k)
                   for k in (SCHEDULED, DISABLED, BLOCKED, MISSING)},
        "loop": {"opportunities": len(rows),
                 "qualifying": sum(1 for r in rows if r["qualifying"]),
                 "in_engineering": sum(1 for r in rows if r["stage"] == "engineering"),
                 "stages": [{k: r[k] for k in ("gap", "pod", "stage", "held_because",
                                               "corroborated_by")}
                            | {"concepts": [p["slug"] for p in r["proposals"]],
                               "engineering": [p["slug"] for p in r["proposals"]
                                               if p["stage"] == "engineering"]}
                            for r in rows]},
        "conclusion": {k: concl.get(k) for k in ("at", "outcome", "why")} if concl else None,
    }
    _assert_no_content(payload)
    return payload
