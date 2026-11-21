"""WS2 R5: validated watchlist gaps + answered research become concept proposals (CA$0).

`radar.intake` judges concept proposals attached to answered research tasks, but nothing in
production ever attached one (`attach_proposal` had no caller), so intake had no automatic
input. This module is that caller. It is deterministic, makes no model call, reads no
network, and never reads a competitor's listing content: the only inputs are

* a coverage gap the watchlist comparison VALIDATED (benchmark key `watchlist`, arena
  `watchlist:<pod>`, corroborated by two or more watchlist shops) that carries the
  `research_task_id` of the question it opened (`intel.watchlist._research_question`);
* that research task, ANSWERED, with a usable confidence, unexpired, not concluded
  `unresolved`, and holding at least one fact-grade finding;
* our own catalogue: the closed concept vocabulary (`creative.concept`), the categories the
  radar draft path compiles (`radar.intake.SUPPORTED_FORMS`, construction `flat_rows`), and
  the price / hour bands of our own POOL concepts in that category.

The proposal is written in our words from that vocabulary: no title, description, tag or
image of any listing is read or copied. It cites the task's own fact-grade findings and the
sources they rest on, so `intake.research_evidence` resolves every reference. Every judgement
-- evidence quality and freshness, construction, vocabulary, children's policy, originality,
dedupe and anti-copy -- stays with `radar.intake.run`, which approves or refuses it.

One proposal per research task: a task that already carries a proposal is left alone, so a
proposal the owner or another writer attached is never overwritten.

Review H1 (eng/r5-research-2): a proposal is written only when the task's evidence clears
concept intake's own floor (`intake.research_evidence`, the same function intake judges
with), and an earlier proposal for the gap blocks a new one only while it is pending or
approved, or -- if refused -- only until the evidence quality rises above what it was refused
on. Each proposal is stamped on its task with its evidence digest and quality.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from statistics import median

ACTION = "radar.proposal_written"
SKIPPED = "radar.proposal_skipped"
WATCHLIST_KEY = "watchlist"

# Watchlist pod -> what our flat-rows radar draft path can honestly make for it. A pod with
# no entry has no supported category (garments, hats, amigurumi, stockings, ornaments, bags,
# collections, education, seasonal gifts): it is skipped with that reason, never forced.
POD_CONCEPTS: dict[str, dict] = {
    "blankets": {"category": "blanket", "form": "rectangle_throw", "recipient": "self",
                 "occasion": "winter_nesting", "feeling": "serene",
                 "function": "keeps a sofa sitter warm through an evening",
                 "motif": "wide tonal bands", "palette": "three tones from the house palette"},
    # CERTFIX-2: a placemat pair, not a coaster. Since ENG-FAMILIES (2ed3294, reviewed SHIP)
    # intake routes every concept through `construction_families.route`, and no verified
    # engine drafts a coaster from flat rows (a coaster needs a disc worked in joined rounds,
    # `fallback_constructions.NEEDS`). A coaster here was a concept intake must refuse, so the
    # kitchen arena could never reach an approved concept. A placemat is a flat_panel pair
    # with its own end-to-end proof (`construction_families.PAIR_PROOFS`), and its
    # `flat_panel` form is still generic, so #108 still judges it on its qualifiers.
    "kitchen_bath": {"category": "placemat", "form": "flat_panel", "recipient": "host",
                     "occasion": "housewarming", "feeling": "bold",
                     "function": "lays a place at the table for a shared meal",
                     "motif": "offset row stripes", "palette": "two contrasting house colours"},
    # Review H1: `housewarming`, not `spring_refresh` -- plain bands draw nothing from the
    # spring motif grammar (#110), so a seasonal occasion was a claim the concept could not
    # carry; and "everyday, for oneself" names no buying moment (#83 jury). A new home does.
    "home_decor": {"category": "pillow", "form": "pillow", "recipient": "self",
                   "occasion": "housewarming", "feeling": "serene",
                   "function": "softens and brightens a reading chair in a new home",
                   "motif": "stacked horizontal bands",
                   "palette": "a light and a deep house colour"},
}


def _now(now=None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def bands(category: str) -> dict | None:
    """Price and hours for a category, from our own POOL concepts in it (medians). None when
    we have no concept of that category to take a band from."""
    from .opportunity import POOL

    seeds = [s for s in POOL if s.category == category]
    if not seeds:
        return None
    return {"price_cad": round(median(s.price_cad for s in seeds), 2),
            "maker_hours": [round(median(s.maker_hours[0] for s in seeds), 1),
                            round(median(s.maker_hours[1] for s in seeds), 1)],
            "design_hours": round(median(s.design_hours for s in seeds), 1),
            "from_pool": sorted(s.slug for s in seeds)}


# Review 6954809399 (M1): which coverage-gap states may receive a proposal, derived from the
# real lifecycle (`intel.coverage.STATES`) rather than a state that does not exist. Only an
# uncovered gap is open for a new concept; every other state is in progress, done, or
# declined, and says so. `_check_states` refuses a lifecycle this table does not cover.
def _gap_state_skip() -> dict[str, str | None]:
    from ..intel import coverage as C

    table = {
        C.UNCOVERED: None,
        C.CONCEPTING: "the gap is already being concepted",
        C.ENGINEERING: "the gap is already in engineering",
        C.CERTIFIED: "the gap already has a certified product",
        C.LAUNCHED: "the gap is already launched",
        C.VALIDATED_WINNER: "the gap is already a validated winner",
        C.NOT_PURSUING: "the owner or system decided not to pursue this gap",
    }
    missing = set(C.STATES) - set(table)
    if missing:
        raise RuntimeError(f"proposal_writer has no rule for gap state(s) {sorted(missing)}")
    return table


_GAP_STATE_SKIP = _gap_state_skip()


def gap_tasks(db, gap_id: int) -> list:
    """Every research task opened for this gap (its trigger, and the `#after:` re-openings)."""
    from sqlalchemy import select

    from ..intel import research

    research._ensure(db)
    prefix = f"watchlist_gap:{gap_id}"
    with db.session() as s:
        rows = [t for t in s.scalars(select(research.ResearchTask).where(
                    research.ResearchTask.trigger.like(prefix + "%"))
                    .order_by(research.ResearchTask.id))
                if str(t.trigger or "") == prefix
                or str(t.trigger or "").startswith(prefix + "#")]
        s.expunge_all()
        return rows


def prior_proposals(db, gap_id: int) -> list[dict]:
    """Review H1 (eng/r5-research-2): every proposal written for this gap, with the evidence
    it was written on (digest, quality) and what concept intake decided (None = not judged
    yet). Keyed on the evidence, not just the gap, so a refusal is not forever."""
    from sqlalchemy import select

    from . import intake

    out = []
    for t in gap_tasks(db, gap_id):
        d = dict(t.detail or {})
        stamps = d.get("proposal_evidence") or {}
        for p in d.get("concept_proposals") or []:
            slug = str(p.get("slug") or "")
            intake._ensure(db)
            with db.session() as s:
                row = s.scalar(select(intake.RadarConcept).where(
                    intake.RadarConcept.source_ref == f"research_task:{t.id}",
                    intake.RadarConcept.slug == slug).order_by(intake.RadarConcept.id.desc())
                    .limit(1))
                decided = (row.state, float(row.quality or 0.0)) if row is not None else None
                reasons = [str(r) for r in (row.reasons or [])][:3] if row is not None else []
            stamp = stamps.get(slug) or {}
            out.append({"task": t.id, "slug": slug, "digest": stamp.get("digest"),
                        "quality": (float(stamp["quality"]) if "quality" in stamp else
                                    decided[1] if decided else 0.0),
                        "state": decided[0] if decided else None,
                        "reasons": reasons})
    return out


def evidence_digest(ev: dict) -> str:
    """What the proposal's evidence says, independent of which task holds it or the day it
    is judged: the confidence and the cited statements and dates."""
    import hashlib
    import json

    body = {"confidence": ev.get("confidence"),
            "items": sorted([str(i.get("claim_class")), str(i.get("statement") or
                                                            i.get("citation") or ""),
                             str(i.get("date"))] for i in ev.get("items") or [])}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:24]


def _blocked_by_prior(priors: list[dict], digest: str, quality: float) -> str | None:
    """Why an earlier proposal for this gap blocks a new one, or None. A proposal intake has
    not judged yet, or approved (its support is renewed daily while the evidence holds,
    review H3), blocks. A refused one blocks only the same evidence or evidence no stronger
    than it was refused on. A withdrawn one (its evidence went stale or unsupported) blocks
    only the same evidence: fresh, durable evidence -- a new digest -- makes the gap
    re-eligible; the old evidence never resurrects it. A superseded one was replaced by a
    newer decision on the same task, which is judged instead."""
    from . import intake

    for p in priors:
        if p["state"] in (None, intake.PROPOSED, intake.APPROVED):
            return (f"an earlier proposal for this gap ({p['slug']} on research task "
                    f"{p['task']}) is {p['state'] or 'awaiting concept intake'}")
    for p in priors:
        if p["state"] == intake.WITHDRAWN and p["digest"] == digest:
            return ("the same evidence was already proposed for this gap and withdrawn as "
                    "no longer supported")
    refused = [p for p in priors if p["state"] == intake.REFUSED]
    if any(p["digest"] == digest for p in refused):
        return "the same evidence was already proposed for this gap and refused"
    best = max((p["quality"] for p in refused), default=None)
    if best is not None and quality <= best:
        return (f"the evidence quality {quality} has not risen above the {best} an earlier "
                f"proposal for this gap was refused on")
    return None


def _task_facts(db, task_id: int, today: date) -> tuple[dict | None, str | None]:
    """The task's citable facts, or why it cannot carry a proposal."""
    from ..intel import research
    from .intake import CONFIDENCE_WEIGHT

    research._ensure(db)
    with db.session() as s:
        t = s.get(research.ResearchTask, int(task_id))
        if t is None:
            return None, f"research task {task_id} does not exist"
        state, conf = t.state, str(t.confidence or "").strip().lower()
        expires = _aware(t.expires_on)
        findings = list(t.findings or [])
        detail = dict(t.detail or {})
    if state != research.ANSWERED:
        return None, f"research task {task_id} is {state}, not answered"
    if (detail.get("conclusion") or {}).get("status") == "unresolved":
        return None, f"research task {task_id} concluded unresolved"
    if conf not in CONFIDENCE_WEIGHT:
        return None, f"research task {task_id} recorded no usable confidence"
    if expires is not None and expires.date() <= today:
        return None, f"research task {task_id} expired on {expires.date().isoformat()}"
    if detail.get("concept_proposals"):
        return None, f"research task {task_id} already carries a proposal"
    facts = [f for f in findings if f.get("claim_class") == "fact" and f.get("ref")]
    if not facts:
        return None, f"research task {task_id} holds no fact-grade finding"
    refs = [f["ref"] for f in facts]
    for f in facts:
        refs += [r for r in f.get("rests_on") or [] if r not in refs]
    return {"refs": refs, "confidence": conf, "facts": len(facts)}, None


def _stamp(db, task_id: int, slug: str, digest: str, quality: float) -> None:
    from sqlalchemy.orm.attributes import flag_modified

    from ..intel import research

    with db.session() as s:
        t = s.get(research.ResearchTask, int(task_id))
        d = dict(t.detail or {})
        d["proposal_evidence"] = {**(d.get("proposal_evidence") or {}),
                                  slug: {"digest": digest, "quality": quality}}
        t.detail = d
        flag_modified(t, "detail")


# Review H1 (main, eng/research-flow): the brief is DERIVED from the concept's own fields by
# the repository's own rules, never typed. `creative.intake.qualifiers_for` reads the #108
# silhouette qualifiers off the premise words and the construction; a plain flat-rows stripe
# carries none, and a concept in a generic form (`creative.invention.GENERIC_FORMS`) with
# none is refused by #108 at the gate -- the refusal is the honest outcome, recorded in the
# lineage, and is never relabelled away here.
BRIEF_DERIVED_FROM = {
    "thumbnail_storyboard": ("category", "concept.motif", "concept.palette_story"),
    "silhouette_qualifiers": ("concept.premise", "concept.construction"),
}
QUALIFIER_RULE = "creative.intake.qualifiers_for"


def creative_concept(slug: str, title: str, concept: dict):
    """The proposal's concept as the creative `Concept` the gate reads (the same fields
    `radar.intake.validate` builds it from)."""
    from ..creative.concept import Concept

    return Concept(key=slug, title=title, premise=str(concept["premise"]),
                   pod=str(concept["pod"]), form=str(concept["form"]),
                   construction=str(concept["construction"]), motif=str(concept["motif"]),
                   palette_story=str(concept["palette_story"]),
                   recipient=str(concept["recipient"]), occasion=str(concept["occasion"]),
                   feeling=str(concept["feeling"]), function=str(concept["function"]),
                   make_lane="SHORT", provenance="radar.proposal_writer")


def brief_for(slug: str, title: str, category: str, concept: dict) -> dict:
    """The gate brief, derived from the concept's own fields: the #88 storyboard from its
    category, motif and palette; the #108 qualifiers by `creative.intake.qualifiers_for`.
    An empty qualifier list is a true answer, not a gap to fill."""
    from ..creative.intake import qualifiers_for
    from .intake import _WHAT

    what = _WHAT.get(category, category)
    return {"thumbnail_storyboard": (f"{what} laid flat from above showing its "
                                     f"{concept['motif']} in {concept['palette_story']}"),
            "silhouette_qualifiers": qualifiers_for(creative_concept(slug, title, concept))}


def silhouette_precheck(slug: str, title: str, concept: dict, brief: dict) -> dict:
    """#108 exactly as the pre-engineering gate runs it (`preengineering._silhouette`), on
    the derived brief. Recorded on the proposal so a refusal is visible before scoring."""
    from ..creative.preengineering import FAIL, _silhouette

    out = _silhouette(creative_concept(slug, title, concept), brief)
    return {"passes": out["status"] != FAIL, "reasons": list(out.get("reasons") or [])[:2],
            "qualifiers": list(brief.get("silhouette_qualifiers") or []),
            "generic_form": bool((out.get("detail") or {}).get("generic_form"))}


def proposal_for(gap_id: int, pod: str, task_id: int, corroborated: int, facts: dict,
                 band: dict) -> dict:
    """The proposal, built from our own vocabulary only."""
    from .intake import _WHAT

    spec = POD_CONCEPTS[pod]
    category = spec["category"]
    what = _WHAT.get(category, category)
    arena = pod.replace("_", " ")
    slug = f"{category}-{pod.replace('_', '-')}-gap-{int(gap_id)}"[:60].rstrip("-")
    out = {
        "slug": slug,
        "title": f"Worked-row {what.split(' ', 1)[-1]} for the {arena} arena",
        "category": category,
        "price_cad": band["price_cad"], "maker_hours": list(band["maker_hours"]),
        "design_hours": band["design_hours"],
        "rationale": (f"The watchlist comparison validated the {arena} arena across "
                      f"{corroborated} of the owner's watchlist shops, and research task "
                      f"{task_id} answered that the demand is durable with "
                      f"{facts['confidence']} confidence on {facts['facts']} fact-grade "
                      f"finding(s)."),
        "evergreen": True, "bundle_ready": False,
        "concept": {
            "premise": (f"{what[0].upper()}{what[1:]} worked in plain rows with "
                        f"{spec['motif']}, made for the {arena} arena"),
            "pod": pod, "form": spec["form"], "construction": "flat_rows",
            "motif": spec["motif"], "palette_story": spec["palette"],
            "recipient": spec["recipient"], "occasion": spec["occasion"],
            "feeling": spec["feeling"], "function": spec["function"]},
        "evidence": list(facts["refs"]),
    }
    # ENG-RESEARCH (review H1): the gate's deterministic inputs (#88 storyboard, #108
    # qualifiers) DERIVED from the concept above, with their provenance. A concept that
    # honestly carries no qualifier in a generic form is refused by #108 -- the precheck
    # records that before scoring, and the gate refuses it again on its own.
    brief = brief_for(slug, out["title"], category, out["concept"])
    out["brief"] = brief
    out["brief_provenance"] = {k: {"derived_from": list(v)}
                               for k, v in BRIEF_DERIVED_FROM.items()}
    out["brief_provenance"]["silhouette_qualifiers"]["rule"] = QUALIFIER_RULE
    out["silhouette_precheck"] = silhouette_precheck(slug, out["title"], out["concept"],
                                                     brief)
    return out


def write(db, *, today: date | None = None, now: datetime | None = None) -> dict:
    """Attach one proposal to each eligible research task behind a validated watchlist gap.
    Returns {"written": [...], "skipped": [...]}; both are audited."""
    from sqlalchemy import select

    from ..core.models import AuditLog, CoverageGap
    from . import intake

    now = _now(now)
    today = today or now.date()
    with db.session() as s:
        gaps = [(g.id, g.pod, g.state, dict(g.evidence or {})) for g in s.scalars(
            select(CoverageGap).where(CoverageGap.benchmark_key == WATCHLIST_KEY)
            .order_by(CoverageGap.id))]
    written, skipped = [], []
    for gid, pod, state, ev in gaps:
        task_id = ev.get("research_task_id")
        corroborated = len(ev.get("corroborated_by") or [])

        def skip(why):
            skipped.append({"gap": gid, "pod": pod, "task": task_id, "why": why})

        why_not = _GAP_STATE_SKIP.get(state, f"unknown gap state {state!r}")
        if why_not:
            skip(why_not)
            continue
        if not task_id:
            skip("no research question was opened for this gap")
            continue
        if corroborated < 2:
            skip("the arena is not corroborated by two watchlist shops")
            continue
        if pod not in POD_CONCEPTS:
            skip(f"pod {pod!r} has no category the flat-rows radar draft path compiles")
            continue
        band = bands(POD_CONCEPTS[pod]["category"])
        if band is None:
            skip(f"no POOL concept of category {POD_CONCEPTS[pod]['category']!r} to take a "
                 f"price band from")
            continue
        facts, why = _task_facts(db, int(task_id), today)
        if facts is None:
            skip(why)
            continue
        # Review H1 (eng/r5-research-2): judge the evidence exactly as concept intake will,
        # and propose only what clears intake's own floor. A proposal refused for thin
        # evidence used to block the gap for good; now none is written until it would pass.
        ev = intake.research_evidence(db, int(task_id), facts["refs"], today=today)
        if not ev.get("ok"):
            skip("the answer does not clear concept intake's evidence floor yet: "
                 + "; ".join(ev.get("reasons") or [])[:300])
            continue
        digest = evidence_digest(ev)
        blocked = _blocked_by_prior(prior_proposals(db, gid), digest, float(ev["quality"]))
        if blocked:
            skip(blocked)
            continue
        proposal = proposal_for(gid, pod, int(task_id), corroborated, facts, band)
        intake.attach_proposal(db, int(task_id), proposal)
        _stamp(db, int(task_id), proposal["slug"], digest, float(ev["quality"]))
        written.append({"gap": gid, "pod": pod, "task": int(task_id),
                        "slug": proposal["slug"], "evidence": proposal["evidence"],
                        "silhouette": proposal["silhouette_precheck"],
                        "evidence_digest": digest, "quality": ev["quality"]})
    with db.session() as s:
        for w in written:
            s.add(AuditLog(actor="market_radar", action=ACTION,
                           artifact=f"research_task:{w['task']}",
                           detail={**w, "written_at": now.isoformat()}))
    return {"written": written, "skipped": skipped}
