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
    "kitchen_bath": {"category": "coaster", "form": "coaster", "recipient": "host",
                     "occasion": "housewarming", "feeling": "bold",
                     "function": "protects a table surface under a hot mug",
                     "motif": "offset row stripes", "palette": "two contrasting house colours"},
    "home_decor": {"category": "pillow", "form": "pillow", "recipient": "self",
                   "occasion": "spring_refresh", "feeling": "serene",
                   "function": "softens and brightens a reading chair",
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


def proposal_for(gap_id: int, pod: str, task_id: int, corroborated: int, facts: dict,
                 band: dict) -> dict:
    """The proposal, built from our own vocabulary only."""
    from .intake import _WHAT

    spec = POD_CONCEPTS[pod]
    category = spec["category"]
    what = _WHAT.get(category, category)
    arena = pod.replace("_", " ")
    slug = f"{category}-{pod.replace('_', '-')}-gap-{int(gap_id)}"[:60].rstrip("-")
    return {
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

        if state == "covered":
            skip("the arena is already covered")
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
        proposal = proposal_for(gid, pod, int(task_id), corroborated, facts, band)
        intake.attach_proposal(db, int(task_id), proposal)
        written.append({"gap": gid, "pod": pod, "task": int(task_id),
                        "slug": proposal["slug"], "evidence": proposal["evidence"]})
    with db.session() as s:
        for w in written:
            s.add(AuditLog(actor="market_radar", action=ACTION,
                           artifact=f"research_task:{w['task']}",
                           detail={**w, "written_at": now.isoformat()}))
    return {"written": written, "skipped": skipped}
