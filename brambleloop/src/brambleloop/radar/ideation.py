"""Research to concept: an uncovered arena becomes a concept proposal from recorded evidence.

A4(a), P0-RESEARCH-TO-CONCEPT. Before this, nothing in production created a concept beyond
the 34 POOL concepts: `radar.score`'s coverage handoff reported a gap no concept answers as
`without_a_pool_concept` and stopped, and `radar.intake.attach_proposal` had test callers only.

The chain this module adds, all deterministic, CA$0, no model call, no network:

    radar.scan (6 h cadence, and plan.cycle daily)
      -> radar.score coverage handoff (no slug)
         -> a gap no POOL/intake concept answers  -> `open_briefs`: ONE research task per gap
            (trigger `ideation_gap:<gap id>`), carrying the ideation brief {gap, pod, arena},
            and a `research.investigate` job for it
      -> research.investigate  -> `investigate`: the RECORDED market observations for the
         gap's pod (dated `benchmark_listings` rows: counts, shops, prices) become a fact-grade
         source and finding with a recorded confidence, the task is answered, and a flat_rows
         concept proposal is attached (`radar.intake.attach_proposal`)
      -> radar.concept_intake  -> validation (evidence, construction, vocabulary, children's
         pre-check, originality/anti-copy) -> approved -> radar.score -> pre-engineering gate
         -> cir.draft (`draft:<slug>`, provenance `radar.intake:research_task:<id>`)

What it never does:

* invent evidence. Too few observed listings, too few shops, no price, or no object a flat
  rows panel honestly is: a NAMED outcome (`insufficient_evidence` / `no_supported_object`)
  is recorded on the gap and no proposal is written;
* copy a competitor. The title is the pod's object noun plus a descriptor from the house
  vocabulary below; a descriptor whose title equals or overlaps any observed listing title is
  skipped, and when every descriptor collides the outcome is `title_overlaps_competitor`,
  with no proposal. Competitor rows are read as counts and prices only (demand
  intelligence); no competitor title, description or image reaches the proposal;
* bypass a gate. The proposal is a proposal: intake, the pre-engineering gate, the
  children's pre-check and `cir.draft`'s construction rules decide it exactly as they decide
  any other concept.

Continuation (A4(a) part 4): at most MAX_IN_FLIGHT gaps are being ideated at once. A gap's
ideation completes when its concept is drafted, refused, held at the pre-engineering gate,
or ended with a named outcome; the next coverage handoff (the radar.scan cadence) then opens
the next eligible gap. No new scheduler.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

TRIGGER_PREFIX = "ideation_gap:"
DECISION_PREFIX = "radar.ideation:gap:"
# Competitor positioning is a quarter-scale thing (learning domain freshness 90 days): the
# market census an ideation answer rests on is dated against that window.
DOMAIN = "competitor_positioning"

BRIEF_OPENED = "ideation.brief_opened"
WAITING = "ideation.waiting"
PROPOSED = "ideation.proposed"
INSUFFICIENT = "ideation.insufficient_evidence"
NO_OBJECT = "ideation.no_supported_object"
TITLE_REFUSED = "ideation.title_overlaps_competitor"
COMPLETED = "ideation.completed"

# Named outcomes recorded on the gap.
OUT_PROPOSED = "proposed"
OUT_INSUFFICIENT = "insufficient_evidence"
OUT_NO_OBJECT = "no_supported_object"
OUT_TITLE = "title_overlaps_competitor"
NAMED_ENDS = (OUT_INSUFFICIENT, OUT_NO_OBJECT, OUT_TITLE)

# How many gaps are ideated at once. One: the next gap opens when this one has an outcome,
# so the queue advances product by product instead of opening every gap on day one.
MAX_IN_FLIGHT = 1
# A brief with no outcome after this long no longer holds the slot (it is recorded stalled).
STALL_DAYS = 14

# The evidence floor. Below it there is no observed market to build a concept on.
MIN_LISTINGS = 3
MIN_SHOPS = 2
HIGH_LISTINGS = 8
HIGH_SHOPS = 3
OBSERVATION_WINDOW_DAYS = 90


@dataclass(frozen=True)
class PodObject:
    """An object a pod sells that the radar flat_rows draft path honestly makes."""

    key: str
    keywords: tuple[str, ...]        # pod keywords that name this object in a listing title
    noun: str                        # the buyer-facing noun our title uses
    category: str                    # the radar category whose template drafts it
    form: str
    what: str
    function: str
    maker_hours: tuple[float, float]  # ESTIMATED make time (fast, slow), stated, not measured
    design_hours: float


# Only objects that ARE one flat panel worked in rows. The placemat template drafts a flat
# panel (`runtime.pipeline._GEOMETRY['placemat']`); `creative.prototype` describes the same
# flat_panel form as "a dishcloth or potholder". Coasters are not here: the fallback refuses
# the coaster category (it needs a disc worked in rounds).
POD_OBJECTS: dict[str, tuple[PodObject, ...]] = {
    "kitchen_bath": (
        PodObject("dishcloth", ("dishcloth", "dish cloth", "washcloth", "wash cloth",
                                "facecloth", "face cloth"),
                  "Dishcloth", "placemat", "flat_panel", "a square dishcloth",
                  "wipes dishes and counters at the sink", (1.0, 2.5), 3.0),
        PodObject("hot_pad", ("potholder", "pot holder", "hot pad", "trivet"),
                  "Hot Pad", "placemat", "flat_panel", "a flat hot pad",
                  "rests a hot pot on the table without marking it", (1.5, 3.0), 3.0),
    ),
}

# The house descriptor vocabulary: Brambleloop's own words, never read from a competitor.
# (descriptor, motif, palette story, feeling)
HOUSE_DESCRIPTORS: tuple[tuple[str, str, str, str], ...] = (
    ("Tideline Stripe", "tideline stripes", "sea glass green and oat", "serene"),
    ("Oat Furrow", "furrowed oat rows", "oat and loam brown", "rugged"),
    ("Harbour Band", "harbour bands", "harbour blue and cream", "serene"),
    ("Kiln Brick", "kiln brick courses", "kiln red and clay", "rugged"),
    ("Linen Ridge", "linen ridges", "flax and chalk", "quietly_luxurious"),
    ("Orchard Row", "orchard rows", "apple green and cream", "cosy"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v):
    return None if v is None else (v if v.tzinfo else v.replace(tzinfo=timezone.utc))


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


# ---- the gap record ------------------------------------------------------------------------


def _gap_record(db, gap_id: int) -> dict | None:
    from ..core.models import CoverageGap

    with db.session() as s:
        row = s.get(CoverageGap, int(gap_id))
        if row is None:
            return None
        return {"id": row.id, "pod": row.pod, "arena": row.arena, "state": row.state,
                "benchmark_key": row.benchmark_key,
                "ideation": dict((row.evidence or {}).get("ideation") or {})}


def _record(db, gap_id: int, **fields) -> dict:
    """Merge fields into the gap's `evidence.ideation` record (durable, per gap)."""
    from sqlalchemy.orm.attributes import flag_modified

    from ..core.models import CoverageGap

    with db.session() as s:
        row = s.get(CoverageGap, int(gap_id))
        ev = dict(row.evidence or {})
        rec = dict(ev.get("ideation") or {})
        rec.update(fields)
        rec["updated_at"] = _now().isoformat()
        ev["ideation"] = rec
        row.evidence = ev
        flag_modified(row, "evidence")
        return rec


def brief_of(db, task_id: int) -> dict | None:
    """The ideation brief a research task carries, or None for any other task."""
    from ..intel import research

    research._ensure(db)
    with db.session() as s:
        row = s.get(research.ResearchTask, int(task_id))
        if row is None:
            return None
        brief = (row.detail or {}).get("ideation_brief")
        return dict(brief) if isinstance(brief, dict) else None


# ---- 1. the coverage handoff opens one brief per gap ---------------------------------------


def status(db, rec: dict, *, now: datetime | None = None) -> tuple[str, str]:
    """(in_flight | done, outcome) for a gap's ideation record, read from the records the
    downstream steps write: the intake row, the radar.scored audit and the draft job."""
    from ..core.models import AuditLog, Job, JobStatus
    from . import intake

    now = now or _now()
    if not rec.get("task"):
        return "none", ""
    outcome = rec.get("outcome")
    if outcome in NAMED_ENDS:
        return "done", outcome
    opened = _aware(datetime.fromisoformat(rec["opened_at"])) if rec.get("opened_at") else now
    stalled = (now - opened) > timedelta(days=STALL_DAYS)
    if outcome != OUT_PROPOSED or not rec.get("slug"):
        return ("done", "stalled") if stalled else ("in_flight", "awaiting investigation")
    slug = rec["slug"]
    state = intake.latest_state(db, slug)
    if state in (intake.REFUSED, intake.WITHDRAWN):
        return "done", f"intake_{state}"
    if state != intake.APPROVED:
        return ("done", "stalled") if stalled else ("in_flight", "awaiting intake")
    with db.session() as s:
        draft = s.scalar(select(Job).where(Job.idempotency_key == f"draft:{slug}").limit(1))
        dstatus = draft.status if draft is not None else None
        drafted = bool((draft.outputs or {}).get("drafted")) if draft is not None else None
        scored = s.scalar(select(AuditLog).where(AuditLog.action == "radar.scored",
                                                 AuditLog.artifact == slug)
                          .order_by(AuditLog.id.desc()).limit(1))
        promoted = bool((scored.detail or {}).get("promoted")) if scored is not None else None
    if dstatus is not None:
        if dstatus in (JobStatus.DONE, JobStatus.DEAD, JobStatus.CANCELLED):
            return "done", ("drafted" if drafted else "draft_refused")
        return ("done", "stalled") if stalled else ("in_flight", "draft queued")
    if promoted is False:
        return "done", "held_at_pre_engineering_gate"
    return ("done", "stalled") if stalled else ("in_flight", "awaiting radar.score")


def open_briefs(ctx, unanswered: list[dict], *, today: date) -> dict:
    """The unanswered branch of the coverage handoff. Idempotent per gap: a gap that already
    has a brief is never given a second one; at most MAX_IN_FLIGHT are in flight."""
    from ..core.models import CoverageGap
    from ..intel import research

    db = ctx.db
    research._ensure(db)
    now = _now()
    # Every open gap's record, answered or not: a gap whose own concept now answers it may
    # still be in flight (drafting), and it holds the slot until it has an outcome.
    with db.session() as s:
        rows = [(g.id, dict((g.evidence or {}).get("ideation") or {}))
                for g in s.scalars(select(CoverageGap).order_by(CoverageGap.id))]
    in_flight, completed = [], []
    for gid, rec in rows:
        if not rec.get("task"):
            continue
        st, outcome = status(db, rec, now=now)
        if st == "in_flight":
            in_flight.append(gid)
        elif st == "done" and rec.get("completed") != outcome:
            _record(db, gid, completed=outcome)
            ctx.audit(COMPLETED, artifact=f"coverage_gap:{gid}",
                      detail={"gap": gid, "outcome": outcome, "slug": rec.get("slug"),
                              "task": rec.get("task")})
            completed.append({"gap": gid, "outcome": outcome})
    opened, already, waiting = [], [], []
    for gap in unanswered:
        rec = (_gap_record(db, gap["gap"]) or {}).get("ideation") or {}
        if rec.get("task"):
            already.append(gap["gap"])
            continue
        if len(in_flight) >= MAX_IN_FLIGHT:
            waiting.append(gap["gap"])
            continue
        brief = {"gap": gap["gap"], "pod": gap["pod"], "arena": gap["arena"]}
        try:
            got = research.open_question(
                db, question=(f"What does the observed market sell in the {gap['pod']} arena "
                              f"(gap {gap['gap']}), at what prices, and which object could "
                              f"Brambleloop make for it?"),
                trigger=f"{TRIGGER_PREFIX}{gap['gap']}",
                decision_ref=f"{DECISION_PREFIX}{gap['gap']}", domain=DOMAIN,
                query_terms=[gap["pod"]],
                evidence_needed=("dated benchmark listing counts, shops and prices in this "
                                 "pod, recorded by the market scans"),
                stop_condition=("a fact-grade census of the pod's observed listings answers "
                                "it, or it is recorded as insufficient evidence"),
                if_unresolved=("leave the gap uncovered with the named outcome; the next "
                               "watchlist scan adds observations and research.sweep "
                               "re-investigates"))
        except research.ResearchRefused as exc:
            ctx.audit(WAITING, artifact=f"coverage_gap:{gap['gap']}",
                      detail={"gap": gap["gap"], "why": f"research refused: {exc}"[:300]})
            continue
        tid = int(got["task"])
        with db.session() as s:
            from sqlalchemy.orm.attributes import flag_modified

            row = s.get(research.ResearchTask, tid)
            d = dict(row.detail or {})
            d["ideation_brief"] = brief
            row.detail = d
            flag_modified(row, "detail")
        _record(db, gap["gap"], task=tid, opened_at=now.isoformat(), brief=brief,
                outcome=None, slug=None)
        ctx.enqueue("research_agent", "research.investigate", {"task_id": tid},
                    idempotency_key=f"ideation:investigate:{tid}")
        ctx.audit(BRIEF_OPENED, artifact=f"research_task:{tid}",
                  detail={**brief, "task": tid, "as_of": today.isoformat()})
        opened.append({"gap": gap["gap"], "task": tid})
        in_flight.append(gap["gap"])
    if waiting:
        ctx.audit(WAITING, detail={"waiting": waiting[:50], "in_flight": in_flight,
                                   "max_in_flight": MAX_IN_FLIGHT,
                                   "why": "the next gap opens when the one in flight has "
                                          "an outcome"})
    return {"opened": opened, "already": already, "waiting": waiting,
            "in_flight": in_flight, "completed": completed}


# ---- 2. the research step answers a brief from recorded observations ------------------------


def observe(db, pod: str, *, today: date) -> dict:
    """The recorded market census for a pod: dated listing counts, shops, prices, and which
    flat_rows object the observed titles name most. Reads counts and prices, never content."""
    from ..core.models import BenchmarkListing
    from ..intel import pods

    since = datetime(today.year, today.month, today.day, tzinfo=timezone.utc) - timedelta(
        days=OBSERVATION_WINDOW_DAYS)
    with db.session() as s:
        rows = [(r.benchmark_key, r.listing_ref, r.title or "", r.pod or "",
                 float(r.price_cad or 0.0), _aware(r.last_seen) or _aware(r.first_seen))
                for r in s.scalars(select(BenchmarkListing))]
    listings = [r for r in rows
                if (r[3] == pod or (not r[3] and pods.route(r[2]) == pod))
                and r[5] is not None and r[5] >= since]
    objects = POD_OBJECTS.get(pod, ())
    counts = []
    for obj in objects:
        n = sum(1 for r in listings
                if any(re.search(rf"\b{re.escape(k)}s?\b", r[2].lower()) for k in obj.keywords))
        counts.append((n, obj))
    best = max(counts, key=lambda c: c[0]) if counts else (0, None)
    obj = best[1] if best[0] > 0 else None
    mine = [r for r in listings if obj is not None and any(
        re.search(rf"\b{re.escape(k)}s?\b", r[2].lower()) for k in obj.keywords)]
    priced = sorted(r[4] for r in (mine or listings) if r[4] > 0)
    shops = {r[0] for r in listings}
    dates = sorted(r[5].date() for r in listings)
    reasons = []
    if not objects:
        reasons.append(f"pod {pod!r} has no object the radar flat_rows draft path makes")
    if len(listings) < MIN_LISTINGS:
        reasons.append(f"{len(listings)} observed listing(s) in the last "
                       f"{OBSERVATION_WINDOW_DAYS} days, below {MIN_LISTINGS}")
    if len(shops) < MIN_SHOPS:
        reasons.append(f"{len(shops)} observed shop(s), below {MIN_SHOPS}")
    if listings and not priced:
        reasons.append("no observed listing carries a price")
    if objects and listings and obj is None:
        reasons.append("no observed title names an object a flat rows panel is")
    confidence = ("high" if len(listings) >= HIGH_LISTINGS and len(shops) >= HIGH_SHOPS
                  else "medium")
    return {"ok": not reasons, "reasons": reasons, "pod": pod, "listings": len(listings),
            "shops": len(shops), "object": obj, "object_listings": len(mine),
            "price_median_cad": round(statistics.median(priced), 2) if priced else None,
            "price_min_cad": priced[0] if priced else None,
            "price_max_cad": priced[-1] if priced else None,
            "oldest": dates[0].isoformat() if dates else None,
            "newest": dates[-1].isoformat() if dates else None,
            "confidence": confidence if not reasons else "none",
            "no_object": not objects}


def observed_titles(db) -> list[tuple[str, str]]:
    from ..core.models import BenchmarkListing

    with db.session() as s:
        return [(ref, t or "") for ref, t in s.execute(
            select(BenchmarkListing.listing_ref, BenchmarkListing.title)).all()]


def originality_reasons(title: str, descriptor: str, titles) -> list[str]:
    """Why a title is a competitor's, or [] when it is ours. Equal, overlapping (half or
    more of its specific words), or carrying our descriptor phrase are all refusals."""
    from .intake import _jaccard, _norm, _specific_tokens

    t_norm, t_tok, d_norm = _norm(title), _specific_tokens(title), _norm(descriptor)
    out = []
    for ref, other in titles:
        o_norm = _norm(other)
        if o_norm == t_norm:
            out.append(f"title {title!r} equals observed listing {ref}'s title")
        elif t_tok and _jaccard(t_tok, _specific_tokens(other)) >= 0.5:
            out.append(f"title {title!r} overlaps observed listing {ref}'s title")
        elif d_norm and f" {d_norm} " in f" {o_norm} ":
            out.append(f"descriptor {descriptor!r} appears in observed listing {ref}'s title")
    return out


def _taken_titles(db) -> set[str]:
    from .intake import _norm, approved_rows
    from .opportunity import POOL

    return {_norm(s.title) for s in POOL} | {
        _norm((r.seed or {}).get("title")) for r in approved_rows(db)}


def build_proposal(db, gap_id: int, obs: dict, *, finding: str, source: str) -> dict:
    """The flat_rows concept proposal, or {"refused": [...]} when no title is ours."""
    from .intake import _norm
    from .opportunity import PREMIUM_PRICE_CEILING_CAD, POOL

    obj: PodObject = obs["object"]
    titles = observed_titles(db)
    taken = _taken_titles(db)
    pool_slugs = {s.slug for s in POOL}
    refusals = []
    pick = None
    n = len(HOUSE_DESCRIPTORS)
    for i in range(n):
        desc = HOUSE_DESCRIPTORS[(int(gap_id) + i) % n]
        title = f"{desc[0]} {obj.noun}"
        slug = _slugify(title)
        why = originality_reasons(title, desc[0], titles)
        if _norm(title) in taken or slug in pool_slugs or any(
                slug.startswith(p + "-") for p in pool_slugs):
            why.append(f"title {title!r} is already a POOL or approved concept")
        if why:
            refusals.extend(why[:2])
            continue
        pick = (desc, title, slug)
        break
    if pick is None:
        return {"refused": refusals}
    (descriptor, motif, palette, feeling), title, slug = pick
    price = round(min(float(obs["price_median_cad"]), PREMIUM_PRICE_CEILING_CAD * 1.5), 2)
    return {
        "slug": slug, "title": title, "category": obj.category, "price_cad": price,
        "maker_hours": list(obj.maker_hours), "design_hours": obj.design_hours,
        "evergreen": True,
        "rationale": (f"Coverage gap {gap_id}: {obs['listings']} listings across "
                      f"{obs['shops']} observed shops sell in the {obs['pod']} arena "
                      f"(observed {obs['oldest']} to {obs['newest']}, median price "
                      f"CA${obs['price_median_cad']}), {obs['object_listings']} of them "
                      f"{obj.noun.lower()}s, and no Brambleloop concept answers it"),
        "concept": {
            "premise": (f"{obj.what.capitalize()} worked flat in rows of {motif} in "
                        f"{palette}"),
            "pod": obs["pod"], "form": obj.form, "construction": "flat_rows",
            "motif": motif, "palette_story": palette, "recipient": "self",
            "occasion": "everyday", "feeling": feeling, "function": obj.function},
        "brief": {"thumbnail_storyboard": (f"{obj.what} laid flat showing its {motif} in "
                                           f"{palette}"),
                  "silhouette_qualifiers": ["motif_composition"]},
        "evidence": [finding, source],
    }


def _task_state(db, task_id: int) -> dict:
    from ..intel import research

    with db.session() as s:
        row = s.get(research.ResearchTask, int(task_id))
        return {"state": row.state, "detail": dict(row.detail or {}),
                "proposals": list((row.detail or {}).get("concept_proposals") or [])}


def investigate(ctx, task_id: int, *, today: date | None = None) -> dict:
    """Answer one ideation brief from the recorded observations and attach the proposal.

    Idempotent: a re-delivered job on an answered task with its proposal attached does
    nothing; a task answered whose proposal was not yet attached (a crash between the two)
    attaches it from the refs it recorded; refs already recorded on an open task are reused.
    """
    from ..intel import research
    from . import intake

    db = ctx.db
    today = today or _now().date()
    brief = brief_of(db, task_id) or {}
    gap_id = int(brief.get("gap") or 0)
    t = _task_state(db, task_id)
    refs = dict(t["detail"].get("ideation_refs") or {})
    if t["state"] == research.ANSWERED and t["proposals"]:
        return {"task": task_id, "ran": False, "why": "already answered and proposed",
                "work_done": 0}
    if t["state"] not in (research.OPEN, research.ANSWERED):
        return {"task": task_id, "ran": False, "why": f"task is {t['state']}", "work_done": 0}
    obs = observe(db, str(brief.get("pod") or ""), today=today)
    if not obs["ok"] and not (t["state"] == research.ANSWERED and refs):
        outcome = OUT_NO_OBJECT if obs["no_object"] else OUT_INSUFFICIENT
        action = NO_OBJECT if obs["no_object"] else INSUFFICIENT
        _record(db, gap_id, outcome=outcome, why=obs["reasons"][:5], slug=None)
        ctx.audit(action, artifact=f"research_task:{task_id}", detail={
            "gap": gap_id, "pod": obs["pod"], "reasons": obs["reasons"][:5],
            "listings": obs["listings"], "shops": obs["shops"]})
        return {"task": task_id, "ran": True, "proposed": False, "outcome": outcome,
                "reasons": obs["reasons"], "work_done": 1}
    if t["state"] == research.OPEN:
        if not refs:
            src = research.add_source(
                db, task_id, source="benchmark_listings census (recorded market scans)",
                citation=(f"db:benchmark_listings?pod={obs['pod']}&from={obs['oldest']}"
                          f"&to={obs['newest']}&listings={obs['listings']}"),
                retrieval="internal", read_on=date.fromisoformat(obs["oldest"]))
            sref = f"S{src}"
            fref = research.add_finding(
                db, task_id, claim_class="fact", rests_on=[sref], confidence=obs["confidence"],
                statement=(f"{obs['listings']} listings in the {obs['pod']} arena observed "
                           f"across {obs['shops']} benchmark shops between {obs['oldest']} "
                           f"and {obs['newest']}; priced listings median "
                           f"CA${obs['price_median_cad']} (CA${obs['price_min_cad']}-"
                           f"CA${obs['price_max_cad']}); {obs['object_listings']} name a "
                           f"{obs['object'].noun.lower()}"))
            refs = {"finding": fref, "source": sref}
            with db.session() as s:
                from sqlalchemy.orm.attributes import flag_modified

                row = s.get(research.ResearchTask, int(task_id))
                d = dict(row.detail or {})
                d["ideation_refs"] = refs
                row.detail = d
                flag_modified(row, "detail")
        research.answer(
            db, task_id, outcome=(f"{obs['pod']}: {obs['listings']} observed listings, "
                                  f"{obs['shops']} shops, median CA${obs['price_median_cad']}"),
            confidence=obs["confidence"],
            effect={"kind": "constraint_established",
                    "statement": (f"the {obs['pod']} arena has observed demand: "
                                  f"{obs['listings']} dated listings across {obs['shops']} "
                                  f"shops")},
            conclusion={"alternatives": [], "constraints": [
                f"observed listings {obs['listings']} >= {MIN_LISTINGS} across "
                f"{obs['shops']} >= {MIN_SHOPS} shops"],
                "unresolved": [], "next_test": {},
                "applicability": {"pod": obs["pod"], "gap": gap_id}})
    if obs["object"] is None:
        # Answered earlier and the observations have since gone: nothing to propose today.
        _record(db, gap_id, outcome=OUT_INSUFFICIENT, why=obs["reasons"][:5], slug=None)
        return {"task": task_id, "ran": True, "proposed": False, "outcome": OUT_INSUFFICIENT,
                "reasons": obs["reasons"], "work_done": 1}
    proposal = build_proposal(db, gap_id, obs, finding=refs["finding"], source=refs["source"])
    if "refused" in proposal:
        _record(db, gap_id, outcome=OUT_TITLE, why=proposal["refused"][:5], slug=None)
        ctx.audit(TITLE_REFUSED, artifact=f"research_task:{task_id}",
                  detail={"gap": gap_id, "reasons": proposal["refused"][:6]})
        return {"task": task_id, "ran": True, "proposed": False, "outcome": OUT_TITLE,
                "reasons": proposal["refused"], "work_done": 1}
    intake.attach_proposal(db, task_id, proposal)
    _record(db, gap_id, outcome=OUT_PROPOSED, slug=proposal["slug"], why=[])
    ctx.audit(PROPOSED, artifact=proposal["slug"], detail={
        "gap": gap_id, "task": task_id, "title": proposal["title"],
        "evidence": proposal["evidence"], "confidence": obs["confidence"],
        "listings": obs["listings"], "shops": obs["shops"],
        "price_cad": proposal["price_cad"]})
    # The intake runs on its own 6 h cadence; queue one pass now so the concept is judged
    # without waiting for the window. Keyed per task: a re-delivery queues nothing new.
    ctx.enqueue("market_radar", intake.JOB_TYPE, {"source": f"research_task:{task_id}"},
                idempotency_key=f"intake:ideation:{task_id}")
    return {"task": task_id, "ran": True, "proposed": True, "slug": proposal["slug"],
            "title": proposal["title"], "outcome": OUT_PROPOSED, "work_done": 1}
