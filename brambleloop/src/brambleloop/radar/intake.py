"""Concept intake: an evidence-backed opportunity becomes a radar concept as a ROW, not code.

The gap this closes (W5-CONCEPT, owner P0 revenue workforce). New products could only come
from `radar.opportunity.POOL`, a hand-coded list. `radar.scan` and `radar.score` scored it,
`research.sweep` investigated questions, the family engine reported -- and nothing turned a
research-validated opportunity into a NEW concept, so the factory could not create a product
it had not been edited to know about.

This module is that link, and it is deterministic, CA$0 and makes no model call:

    research task ANSWERED (fact-grade findings, dated sources, a recorded confidence)
        + a structured concept proposal attached to it (`attach_proposal`)
    certified family with proven orders and no declared next member (Winner Amplification)
        -> `radar_concepts` row (proposed)
        -> validation: evidence, construction the draft path compiles, closed concept
           vocabulary, children's product_creation pre-check, originality / dedupe /
           anti-copy against POOL, the database concepts, the catalogue, certified products
           and the observed competitor listings
        -> approved (audited, radar.score enqueued) or refused (audited, with reasons)

Everything downstream is the existing chain: `radar.scan` / `select_portfolio` score POOL plus
the approved rows with the same `score_concept`, and `radar.score` applies the same steering,
the same #38 evidence discount, the same lesson nudge and the same pre-engineering gate
before it enqueues `cir.draft` (`draft:<slug>`).

What this module never does:

* invent evidence. A proposal with no recorded evidence, evidence that does not resolve to
  the research task's own findings and dated sources, an unanswered or expired task, or a
  task that recorded no confidence is refused;
* accept a construction the radar draft path cannot compile honestly. `cir.draft` drafts a
  radar concept with `runtime.pipeline.concept_to_cir`: a flat_rows panel worked over the
  category's stitch repeat. Anything else -- worked in the round, mosaic overlay, cables,
  tapestry, granny squares, shaping -- would be compiled as an object it is not, so it is
  refused here with an "unsupported construction" reason instead of failing downstream;
* set a taste judgement. `thumbnail_reads_small` / `craft_impression` are stripped from
  proposals; only the vision judge's record (`creative.intake.judgement_for`) supplies them,
  and with `image_vision` CLOSED the pre-engineering gate leaves the concept WAITING;
* copy a competitor. A proposal indistinguishable from an observed listing, or whose title
  is a competitor's title, is refused (CLAUDE.md non-negotiable).
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from .opportunity import (
    PREMIUM_PRICE_CEILING_CAD, POOL, ConceptSeed, score_concept,
)

JOB_TYPE = "radar.concept_intake"
PROPOSED_ACTION = "concept.intake_proposed"
APPROVED_ACTION = "concept.intake_approved"
REFUSED_ACTION = "concept.intake_refused"
HANDOFF_ACTION = "concept.intake_handoff"

PROPOSED, APPROVED, REFUSED, SUPERSEDED = "proposed", "approved", "refused", "superseded"
# F1 (review 933bf74): an approval whose evidence went stale, expired or became unresolved.
WITHDRAWN = "withdrawn"
WITHDRAWN_ACTION = "concept.intake_withdrawn"
# Retention (ops.retention calls `prune`): decided, non-approved rows older than this go,
# except the newest row per (source_ref, slug), which carries the idempotency fingerprint.
RETENTION_DAYS = 90
SOURCE_RESEARCH, SOURCE_FAMILY = "research", "family"

# Bounded per run: an intake that evaluates without limit is a worker that never finishes.
MAX_EVALUATIONS_PER_RUN = 10
# A family proposes at most this many coordinated variations per run.
MAX_FAMILY_VARIATIONS = 2

# Evidence quality below which an opportunity is not strong enough to become a concept.
MIN_EVIDENCE_QUALITY = 0.40

# The research confidence vocabulary as it is recorded on answered tasks. "unknown" (or
# nothing) is not a confidence: an answer that could not say how sure it is cannot carry a
# product.
CONFIDENCE_WEIGHT: dict[str, float] = {
    "high": 0.90, "medium": 0.65, "moderate": 0.65, "low": 0.35,
}

# ---- what `cir.draft` can actually compile for a radar concept --------------------------

SUPPORTED_CONSTRUCTIONS: tuple[str, ...] = ("flat_rows",)
"""The radar draft path (`runtime.pipeline.concept_to_cir`) emits one construction: a flat
panel worked in rows over the category's repeat. Only a concept built that way is drafted as
what it says it is."""

# Category -> the creative forms a flat rows panel honestly IS. Every category here has a row
# in `runtime.pipeline._GEOMETRY` (asserted by the tests), so `concept_geometry` gives it a
# repeat that divides its width rather than the default.
SUPPORTED_FORMS: dict[str, tuple[str, ...]] = {
    "blanket": ("rectangle_throw",),
    "baby": ("rectangle_throw",),
    "runner": ("runner",),
    "placemat": ("flat_panel",),
    "coaster": ("coaster", "flat_panel"),
    "pillow": ("pillow",),
    "wall_decor": ("wall_hanging",),
    "pet": ("flat_panel", "rectangle_throw"),
    "scarf": ("scarf",),
}

# Categories with a template row that are still refused, and why: the template would draft
# them as a flat striped panel, which is not the product the category names (B-059, B-080).
UNSUPPORTED_CATEGORY_WHY: dict[str, str] = {
    "mosaic_blanket": "overlay mosaic needs a charted overlay; the template drafts plain "
                      "sc/dc stripes, which is not mosaic",
    "graphghan": "a graphghan is a charted picture; the template drafts plain single crochet",
    "basket": "a basket is worked in the round with a base; the template drafts a flat side "
              "panel (B-059)",
    "seasonal_decor": "seasonal decor is garlands, shapes and ornaments; the template drafts "
                      "a rectangle",
    "ornament": "an ornament is a closed or shaped piece; the template drafts a rectangle",
    "flower": "a flower motif is worked in rounds; the template drafts a rectangle",
}

# Why each non-flat construction is refused on this path (the creative prototype path routes
# several of them through `creative.prospecting.ENGINE_ROUTE`; the radar template does not).
CONSTRUCTION_WHY: dict[str, str] = {
    "in_the_round": "needs joined rounds and increases; the radar template works flat rows",
    "seamless_tube": "needs joined rounds; the radar template works flat rows",
    "amigurumi_shaping": "needs spiral rounds and shaping; the radar template works flat rows",
    "top_down_yoke": "needs a graded garment design; the radar template works flat rows",
    "bottom_up": "needs a graded garment design; the radar template works flat rows",
    "mosaic_overlay": "needs an overlay chart; the radar template drafts plain stripes",
    "tapestry": "needs a colourwork chart; the radar template drafts plain stripes",
    "cable_panel": "needs post-stitch crossings; the radar template has none (B-080)",
    "granny_square": "needs motifs worked in rounds and joined; the radar template works "
                     "one flat panel",
    "motif_join": "needs motifs and a join; the radar template works one flat panel",
    "modular_panels": "needs several shaped panels and assembly; the template works one",
    "corner_to_corner": "needs diagonal tile increases and decreases; the template works "
                        "straight rows",
    "side_to_side": "needs a lengthwise foundation the template does not author",
}

# Variation vocabulary for family proposals: what each supported category is, for a buyer.
_NOUN: dict[str, str] = {
    "blanket": "Throw", "baby": "Baby Blanket", "runner": "Table Runner",
    "placemat": "Placemat Pair", "coaster": "Coaster Set", "pillow": "Cushion Cover",
    "wall_decor": "Wall Hanging", "pet": "Pet Mat", "scarf": "Scarf",
}
_FUNCTION: dict[str, str] = {
    "blanket": "covers a sofa in the family's pattern",
    "baby": "wraps a new baby in the family's pattern",
    "runner": "dresses the table to match the set",
    "placemat": "lays a matching place at the table",
    "coaster": "protects a table under mugs in the matching pattern",
    "pillow": "fronts a cushion that matches the set",
    "wall_decor": "hangs the family's motif on a wall",
    "pet": "gives a pet a matching bed mat",
    "scarf": "carries the family's pattern outdoors",
}
_WHAT: dict[str, str] = {
    "blanket": "a sofa throw", "baby": "a pram-sized blanket", "runner": "a table runner",
    "placemat": "a pair of placemats", "coaster": "a set of coasters",
    "pillow": "a cushion front", "wall_decor": "a hung panel", "pet": "a pet mat",
    "scarf": "a wrapped scarf",
}
_OCCASION_OF_SEASON: dict[str, str] = {
    "Christmas": "christmas", "Halloween": "halloween", "Thanksgiving (CA)": "thanksgiving",
    "Valentine's": "valentines", "Easter": "easter", "Mother's Day": "mothers_day",
}

# Fields a proposal may carry. Anything else is dropped before fingerprinting.
_SEED_FIELDS = ("slug", "title", "category", "price_cad", "maker_hours", "design_hours",
                "rationale", "season", "family", "evergreen", "bundle_ready")
_CONCEPT_FIELDS = ("premise", "pod", "form", "construction", "motif", "palette_story",
                   "recipient", "occasion", "feeling", "function")
_JUDGED_FIELDS = ("thumbnail_reads_small", "craft_impression")
# F3 (review 933bf74): brief fields that are JUDGED values -- a strength score and its judge,
# benchmark scores, a grid board. Only their own producers (the jury, the grid record) may
# supply them; a proposal that carries one is carrying a judgement nobody made.
_JUDGED_BRIEF_FIELDS = ("strength_score", "strength_score_source", "benchmark_scores",
                        "board_image")
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_WORD = re.compile(r"[a-z]+")


class RadarConcept(Base):
    """One proposed radar concept and what intake decided about it. Append-mostly: a changed
    proposal is a new row; the earlier approved row of the same slug becomes `superseded`."""

    __tablename__ = "radar_concepts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                         default=lambda: datetime.now(timezone.utc), index=True)
    slug: Mapped[str] = mapped_column(String(80), index=True)
    state: Mapped[str] = mapped_column(String(12), default=PROPOSED, index=True)
    source: Mapped[str] = mapped_column(String(20), index=True)
    source_ref: Mapped[str] = mapped_column(String(120), index=True)
    # sha256 of the normalised proposal + its evidence: the idempotency key. An unchanged
    # opportunity has the same fingerprint and is never evaluated twice.
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    seed: Mapped[dict] = mapped_column(JSON, default=dict)
    concept: Mapped[dict] = mapped_column(JSON, default=dict)
    brief: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    quality: Mapped[float] = mapped_column(Float, default=0.0)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")


def _ensure(db) -> None:
    RadarConcept.__table__.create(bind=db.engine, checkfirst=True)


def _aware(v):
    return None if v is None else (v if v.tzinfo else v.replace(tzinfo=timezone.utc))


def _norm(text: str) -> str:
    return " ".join(_WORD.findall(str(text or "").lower()))


def _specific_tokens(text: str) -> set[str]:
    from ..creative.concept import GENERIC_TOKENS

    return {w for w in _WORD.findall(str(text or "").lower())
            if w not in GENERIC_TOKENS and len(w) > 2}


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def fingerprint(source_ref: str, proposal: dict, evidence: dict) -> str:
    body = {"source_ref": source_ref, "proposal": proposal,
            "evidence": [{k: i.get(k) for k in ("ref", "kind", "date", "claim_class")}
                         for i in evidence.get("items") or []],
            # F1: the recorded facts, never the day-dependent quality -- freshness decay must
            # not mint a new row every day. A re-answered task (new answer date) is new input;
            # an approval whose evidence decays is WITHDRAWN by `withdraw_unsupported`.
            "answered": evidence.get("answered")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def _clean(proposal: dict) -> dict:
    """The proposal fields intake reads, normalised. Judged taste fields are dropped: only a
    model that looked at an image may set them, and a proposal is not that."""
    p = dict(proposal or {})
    concept = {k: v for k, v in dict(p.get("concept") or {}).items()
               if k in _CONCEPT_FIELDS}
    from ..creative.preengineering import BRIEF_FIELDS

    brief = {k: v for k, v in dict(p.get("brief") or {}).items()
             if k in BRIEF_FIELDS and k not in _JUDGED_BRIEF_FIELDS}
    out = {k: p.get(k) for k in _SEED_FIELDS if p.get(k) is not None}
    if isinstance(out.get("maker_hours"), (list, tuple)):
        out["maker_hours"] = [float(x) for x in out["maker_hours"]]
    out["concept"] = concept
    out["brief"] = brief
    out["evidence"] = [str(r) for r in p.get("evidence") or [] if str(r).strip()]
    return out


# ---- evidence ------------------------------------------------------------------------------


def research_evidence(db, task_id: int, refs, *, today: date) -> dict:
    """The recorded evidence a proposal cites on its research task, dated and graded.

    Returns {"ok", "items", "quality", "uncertainty", "reasons", ...}. Each cited ref must be
    one of the task's own findings (F..) or sources (S..); a finding is dated by the sources
    it rests on (internal evidence by the task's answer date). Quality is the task's recorded
    confidence x the fact-grade share of what is cited x freshness against the domain's own
    freshness window (F-433) -- a number computed from the record, never typed.
    """
    from ..intel import research

    research._ensure(db)
    refs = [str(r) for r in refs or () if str(r).strip()]
    with db.session() as s:
        row = s.get(research.ResearchTask, int(task_id))
        if row is None:
            return {"ok": False, "reasons": [f"no research task {task_id}"], "items": [],
                    "quality": 0.0}
        state, domain = row.state, row.domain
        confidence = str(row.confidence or "").strip().lower()
        expires = _aware(row.expires_on)
        answered = _aware(row.answered_at)
        findings = {f["ref"]: f for f in row.findings or []}
        sources = {x["ref"]: x for x in row.sources or []}
        internal = {x.get("ref") for x in row.internal_evidence or []}
        conclusion = (row.detail or {}).get("conclusion") or {}
    reasons: list[str] = []
    if state != research.ANSWERED:
        reasons.append(f"research task {task_id} is {state}, not answered: an open question "
                       f"is not an approved opportunity")
    if conclusion.get("status") == "unresolved":
        reasons.append(f"research task {task_id} concluded unresolved")
    # The moment evidence is judged at: the start of `today`, or the real time when `today`
    # is today -- so an expiry earlier today is already an expiry (F1, review 933bf74).
    now = max(datetime(today.year, today.month, today.day, tzinfo=timezone.utc),
              datetime.now(timezone.utc) if today >= datetime.now(timezone.utc).date()
              else datetime.min.replace(tzinfo=timezone.utc))
    if expires is not None and expires <= now:
        reasons.append(f"research task {task_id} expired on {expires.date().isoformat()} "
                       f"(F-433): stale evidence is not current evidence")
    if not refs:
        reasons.append("the proposal cites no evidence: a concept without recorded evidence "
                       "is refused")
    weight = CONFIDENCE_WEIGHT.get(confidence)
    if weight is None:
        reasons.append(f"research task {task_id} recorded no usable confidence "
                       f"({confidence or 'none'!r})")

    def _source_date(ref: str) -> str | None:
        if ref in sources:
            return sources[ref].get("read_on")
        if ref in internal and answered is not None:
            return answered.date().isoformat()
        return None

    items: list[dict] = []
    for ref in refs:
        if ref in findings:
            f = findings[ref]
            dates = [d for d in (_source_date(r) for r in f.get("rests_on") or []) if d]
            item = {"ref": ref, "kind": "finding", "claim_class": f.get("claim_class"),
                    "statement": str(f.get("statement") or "")[:300],
                    "rests_on": list(f.get("rests_on") or []),
                    "date": min(dates) if dates else None}
        elif ref in sources:
            src = sources[ref]
            item = {"ref": ref, "kind": "source", "retrieval": src.get("retrieval"),
                    "source": str(src.get("source") or "")[:120],
                    "citation": str(src.get("citation") or "")[:240],
                    "claim_class": ("fact" if src.get("retrieval") in research.FACT_GRADE
                                    else "source_claim"),
                    "date": src.get("read_on")}
        else:
            reasons.append(f"evidence ref {ref!r} is not a finding or source of research "
                           f"task {task_id}: evidence must be recorded, not asserted")
            continue
        if not item["date"]:
            reasons.append(f"evidence {ref!r} carries no source date")
        items.append(item)
    if items and not any(i["claim_class"] == "fact" for i in items):
        reasons.append("no cited evidence is fact-grade (a fact finding, or a source this "
                       "system read in full); claims and inferences alone cannot carry a "
                       "product")
    dated = [date.fromisoformat(i["date"][:10]) for i in items if i.get("date")]
    try:
        fresh_days, _why = research.freshness_for(domain)
    except research.ResearchRefused:
        fresh_days = None
    age = (today - min(dated)).days if dated else None
    if fresh_days is None or age is None:
        freshness = 1.0 if age is not None else 0.0
    elif age <= fresh_days:
        freshness = 1.0
    else:
        freshness = max(0.0, 1.0 - (age - fresh_days) / float(fresh_days))
    grade = (sum(1 for i in items if i["claim_class"] == "fact") / len(items)) if items else 0.0
    quality = round((weight or 0.0) * grade * freshness, 3)
    if not reasons and quality < MIN_EVIDENCE_QUALITY:
        reasons.append(f"evidence quality {quality} is below {MIN_EVIDENCE_QUALITY} "
                       f"(confidence {confidence}, fact share {grade:.2f}, freshness "
                       f"{freshness:.2f})")
    return {"ok": not reasons, "reasons": reasons, "items": items, "quality": quality,
            "uncertainty": round(1.0 - quality, 3), "confidence": confidence,
            "fact_share": round(grade, 3), "freshness": round(freshness, 3),
            "oldest_evidence_days": age, "fresh_for_days": fresh_days,
            "task": int(task_id), "domain": domain,
            "answered": answered.isoformat() if answered is not None else None}


def attach_proposal(db, task_id: int, proposal: dict) -> dict:
    """Attach a structured concept proposal to a research task (the creative answer to the
    question the task researched). Shape only; every judgement is made by `run`. One proposal
    per slug per task: re-attaching a slug replaces it, which changes its fingerprint and so
    re-evaluates it once."""
    from sqlalchemy.orm.attributes import flag_modified

    from ..intel import research

    research._ensure(db)
    slug = str((proposal or {}).get("slug") or "").strip()
    if not slug:
        raise ValueError("a concept proposal names its slug")
    with db.session() as s:
        row = s.get(research.ResearchTask, int(task_id))
        if row is None:
            raise ValueError(f"no research task {task_id}")
        d = dict(row.detail or {})
        kept = [p for p in d.get("concept_proposals") or [] if p.get("slug") != slug]
        d["concept_proposals"] = kept + [dict(proposal)]
        row.detail = d
        flag_modified(row, "detail")
    return {"task": int(task_id), "slug": slug, "proposals": len(kept) + 1}


# ---- the approved pool ---------------------------------------------------------------------


def _seed_from(row: RadarConcept) -> ConceptSeed:
    s = dict(row.seed or {})
    return ConceptSeed(
        slug=row.slug, title=s["title"], category=s["category"], risk_class=s["risk_class"],
        price_cad=float(s["price_cad"]), maker_hours=tuple(s["maker_hours"]),
        design_hours=float(s["design_hours"]), whitespace=float(s["whitespace"]),
        rationale=s["rationale"], season=s.get("season"), family=s.get("family"),
        evergreen=bool(s.get("evergreen")), bundle_ready=bool(s.get("bundle_ready")),
        is_bundle=False, origin=f"radar.intake:{row.source_ref}")


def approved_rows(db) -> list[RadarConcept]:
    _ensure(db)
    pool = {s.slug for s in POOL}
    with db.session() as s:
        rows = list(s.scalars(select(RadarConcept).where(RadarConcept.state == APPROVED)
                              .order_by(RadarConcept.id)))
        s.expunge_all()
    unsupported = _unsupported_research(db, rows)
    seen, out = set(), []
    for r in rows:
        if r.slug in pool or r.slug in seen or r.id in unsupported:
            continue
        seen.add(r.slug)
        out.append(r)
    return out


def _unsupported_research(db, rows) -> set[int]:
    """F1: ids of approved research rows whose task is no longer an approved opportunity --
    not ANSWERED, concluded unresolved, or past `expires_on` -- read from the task row at the
    moment of use, so a stale approval is out of the pool even before `run` withdraws it."""
    from ..intel import research

    refs = {r.id: r.source_ref for r in rows if r.source == SOURCE_RESEARCH}
    if not refs:
        return set()
    research._ensure(db)
    ids = {int(v.split(":", 1)[1]) for v in refs.values()}
    now = datetime.now(timezone.utc)
    with db.session() as s:
        tasks = {t.id: t for t in s.scalars(select(research.ResearchTask)
                                            .where(research.ResearchTask.id.in_(ids)))}
        ok = set()
        for tid, t in tasks.items():
            expires = _aware(t.expires_on)
            concl = (t.detail or {}).get("conclusion") or {}
            if (t.state == research.ANSWERED and concl.get("status") != "unresolved"
                    and (expires is None or expires > now)):
                ok.add(tid)
    return {rid for rid, ref in refs.items() if int(ref.split(":", 1)[1]) not in ok}


def has_rows(db, slug: str) -> bool:
    """True when intake has ever recorded a row for `slug` (any state)."""
    if db is None or not slug:
        return False
    _ensure(db)
    with db.session() as s:
        return s.scalar(select(RadarConcept.id).where(RadarConcept.slug == slug)
                        .limit(1)) is not None


def latest_state(db, slug: str) -> str | None:
    _ensure(db)
    with db.session() as s:
        return s.scalar(select(RadarConcept.state).where(RadarConcept.slug == slug)
                        .order_by(RadarConcept.id.desc()).limit(1))


def approved_seeds(db) -> list[ConceptSeed]:
    """The approved database concepts as `ConceptSeed`s, in approval order."""
    return [_seed_from(r) for r in approved_rows(db)]


def pool_with_intake(db) -> list[ConceptSeed]:
    """POOL plus the approved database concepts. With no approved row this IS `POOL`."""
    if db is None:
        return list(POOL)
    return list(POOL) + approved_seeds(db)


def approved_concept(db, slug: str) -> dict | None:
    """The approved row for `slug` as {seed, concept, brief, source_ref}, or None."""
    if db is None or not slug:
        return None
    for r in approved_rows(db):
        if r.slug == slug:
            return {"seed": _seed_from(r), "concept": dict(r.concept or {}),
                    "brief": dict(r.brief or {}), "source_ref": r.source_ref, "id": r.id}
    return None


def seed_for(db, slug: str) -> ConceptSeed | None:
    """POOL first (unchanged behaviour), then an approved database concept."""
    seed = next((s for s in POOL if s.slug == slug), None)
    if seed is not None or db is None:
        return seed
    got = approved_concept(db, slug)
    return got["seed"] if got else None


def gate_inputs(db, slug: str, inputs: dict) -> dict:
    """The job inputs the pre-engineering gate and `cir.draft` read for an intake concept:
    the stored concept and brief at top level (read from the database, never the job), and
    the vision judge's recorded taste fields when one exists. A POOL slug is returned as is."""
    got = approved_concept(db, slug)
    if got is None:
        return dict(inputs)
    from ..creative import intake as creative_intake

    from ..creative.preengineering import BRIEF_FIELDS

    # F2 (review 933bf74): everything the gate judges comes from the database row or the
    # vision judge's record. The job's own concept, brief, taste and strength fields are
    # dropped, whoever enqueued it.
    drop = set(_JUDGED_FIELDS) | set(_CONCEPT_FIELDS) | set(BRIEF_FIELDS) | {
        "concept", "brief", "key", "make_lane", "provenance"}
    out = {k: v for k, v in dict(inputs).items() if k not in drop}
    out.update({k: v for k, v in got["brief"].items() if k not in _JUDGED_BRIEF_FIELDS})
    out.update({**got["concept"], "key": slug, "title": got["seed"].title,
                "provenance": f"radar.intake:{got['source_ref']}"})
    judged = creative_intake.judgement_for(db, slug) or {}
    for k in _JUDGED_FIELDS:
        if k in judged:
            out[k] = judged[k]
    return out


# ---- validation ------------------------------------------------------------------------------


def construction_verdict(category: str, form: str, construction: str) -> list[str]:
    """Reasons the radar draft path cannot compile this, or [] when it can."""
    reasons = []
    if construction not in SUPPORTED_CONSTRUCTIONS:
        why = CONSTRUCTION_WHY.get(construction, "no template drafts it")
        reasons.append(f"unsupported construction {construction!r}: {why}. Supported on the "
                       f"radar draft path: {list(SUPPORTED_CONSTRUCTIONS)}")
    if category not in SUPPORTED_FORMS:
        why = UNSUPPORTED_CATEGORY_WHY.get(
            category, "no `concept_geometry` template row exists for it")
        reasons.append(f"unsupported construction for category {category!r}: {why}. "
                       f"Supported categories: {sorted(SUPPORTED_FORMS)}")
    elif form not in SUPPORTED_FORMS[category]:
        reasons.append(f"unsupported construction: form {form!r} is not what a flat rows "
                       f"{category} panel is (allowed {list(SUPPORTED_FORMS[category])})")
    return reasons


def _children_reasons(db, p: dict, concept: dict) -> list[str]:
    """The children's-products policy pre-check at product_creation (Etsy Children and Baby
    Products, effective 2026-06-02): the prohibition covers PATTERNS for prohibited items, so
    the refusal belongs before a CIR is written -- here."""
    from ..creative.children import is_children
    from ..gates.platform_policy import unreviewed_changes
    from ..intel.childrens import prohibited_subject

    text = " ".join(str(x) for x in (p.get("title"), p.get("rationale"),
                                    *(concept.get(k) for k in _CONCEPT_FIELDS)) if x)
    reasons = []
    banned = prohibited_subject(text)
    if banned is not None:
        reasons.append(f"children's policy (product_creation): {banned.slug} is prohibited -- "
                       f"{banned.why[:200]}")
    child = is_children(category=str(p.get("category") or ""),
                        audience=str(concept.get("recipient") or ""),
                        title=str(p.get("title") or "")) or concept.get("recipient") in (
                            "child", "new_parent")
    if child:
        changed = [c for c in unreviewed_changes(db) if c["source"] == "children_and_baby"]
        if changed:
            reasons.append("children's policy (product_creation): the Children and Baby "
                           "Products policy changed materially and the change is unreviewed "
                           f"(snapshot {changed[0]['snapshot_id']}); children's concepts are "
                           f"blocked until it is reviewed (#39)")
    return reasons


def _originality_reasons(db, p: dict, built, source_ref: str) -> tuple[list[str], float, dict]:
    """Dedupe and anti-copy. Returns (reasons, nearest distance, detail)."""
    from ..creative import preengineering
    from ..creative.audit import briefed_catalogue_concepts
    from ..creative.concept import Concept, ConceptRefused, nearest
    from ..creative.prospecting import MIN_NOVELTY, _matches_a_listing, benchmark_comparables

    slug, title, category = p["slug"], p["title"], p["category"]
    reasons: list[str] = []
    detail: dict = {}
    if any(s.slug == slug for s in POOL):
        reasons.append(f"duplicate: {slug!r} is a radar POOL concept")
    else:
        shadow = next((s.slug for s in POOL if slug.startswith(s.slug + "-")), None)
        if shadow:
            # F5: a slug a POOL slug prefixes is read as that POOL product's size variant by
            # slug-prefix readers; it would be priced and listed as something it is not.
            reasons.append(f"duplicate: {slug!r} extends POOL slug {shadow!r} and would be "
                           f"read as its variant")
    est = preengineering.established(db, slug)
    if est:
        reasons.append(f"duplicate: {slug!r} is {est}")
    others = [r for r in approved_rows(db) if r.source_ref != source_ref or r.slug != slug]
    if any(r.slug == slug for r in others):
        reasons.append(f"duplicate: {slug!r} is already an approved database concept")
    t_norm = _norm(title)
    t_tok = _specific_tokens(title)
    for s in POOL:
        if _norm(s.title) == t_norm:
            reasons.append(f"duplicate: title {title!r} is POOL concept {s.slug!r}")
        elif s.category == category and _jaccard(t_tok, _specific_tokens(s.title)) >= 0.5:
            reasons.append(f"duplicate: {title!r} restates POOL concept {s.slug!r} "
                           f"({s.title!r}) in the same category")
    for r in others:
        if _norm((r.seed or {}).get("title")) == t_norm:
            reasons.append(f"duplicate: title {title!r} is database concept {r.slug!r}")
    # Structural distance: the same definition of "the same idea" the pre-engineering gate
    # and the tournament use (B-295), against the briefed catalogue and the approved rows.
    catalogue = [c for c in briefed_catalogue_concepts()[0] if c.key != slug]
    for r in others:
        try:
            catalogue.append(Concept(**{**r.concept, "key": r.slug,
                                        "title": (r.seed or {}).get("title", r.slug),
                                        "make_lane": (r.seed or {}).get("make_lane", "SHORT")}))
        except (ConceptRefused, TypeError):
            continue
    near, gap = nearest(built, catalogue)
    detail.update(nearest=near.key if near else None, distance=gap, min_novelty=MIN_NOVELTY)
    if near is not None and gap < MIN_NOVELTY:
        reasons.append(f"duplicate: {gap} from {near.key!r}, below the novelty floor "
                       f"{MIN_NOVELTY} -- a near-clone or recolour of an existing concept")
    # Anti-copy: never arrive as a competitor's listing, never wear its title.
    cards = benchmark_comparables(db, pod=built.pod)
    twin = _matches_a_listing(built, cards) if cards else ""
    detail["benchmark_cards"] = len(cards)
    if twin:
        reasons.append(f"copy: indistinguishable from observed competitor listing {twin} on "
                       f"everything either side states")
    from ..core.models import BenchmarkListing

    with db.session() as s:
        titles = [(ref, t) for ref, t in s.execute(
            select(BenchmarkListing.listing_ref, BenchmarkListing.title)).all()]
    for ref, t in titles:
        if t_tok and _jaccard(t_tok, _specific_tokens(t)) >= 0.8:
            reasons.append(f"copy: title {title!r} is competitor listing {ref}'s title")
            break
    # Certified products the catalogue does not know by slug.
    from ..core.models import PatternVersion, Product

    with db.session() as s:
        certified = [(sl, (cj or {}).get("title", "")) for sl, cj in s.execute(
            select(Product.slug, PatternVersion.cir_json)
            .join(PatternVersion, PatternVersion.product_id == Product.id)
            .where(PatternVersion.certified.is_(True))).all()]
    for sl, t in certified:
        if _norm(t) == t_norm and sl != slug:
            reasons.append(f"duplicate: title {title!r} is certified product {sl!r}")
            break
    return reasons, gap, detail


def validate(db, proposal: dict, evidence: dict, *, source_ref: str) -> dict:
    """Every check, in a fixed order, never short-circuited past the shape check, so a
    refusal names all of its reasons. Returns {"ok", "reasons", "seed", "concept", "brief"}."""
    from ..creative.concept import Concept, ConceptRefused
    from ..creative.preengineering import make_lane_for_hours
    from ..intel.pods import POD_KEYS
    from .market import SEASONAL_EVENTS

    p = _clean(proposal)
    reasons: list[str] = []
    missing = [k for k in ("slug", "title", "category", "price_cad", "maker_hours",
                           "design_hours", "rationale") if p.get(k) in (None, "", [])]
    missing += [f"concept.{k}" for k in _CONCEPT_FIELDS if not str(p["concept"].get(k)
                                                                    or "").strip()]
    if missing:
        return {"ok": False, "reasons": [f"the proposal is not a concept yet: missing "
                                         f"{missing}"] + list(evidence.get("reasons") or []),
                "seed": None, "concept": p["concept"], "brief": p["brief"]}
    slug = str(p["slug"])
    if not _SLUG.match(slug) or len(slug) > 60:
        reasons.append(f"slug {slug!r} is not a lowercase hyphenated slug of at most 60 chars")
    try:
        price = float(p["price_cad"])
        hours = tuple(float(x) for x in p["maker_hours"])
        design = float(p["design_hours"])
        assert len(hours) == 2
    except (TypeError, ValueError, AssertionError):
        price, hours, design = 0.0, (0.0, 0.0), 0.0
        reasons.append("price_cad, maker_hours (fast, slow) and design_hours must be numbers")
    if not 0 < price <= PREMIUM_PRICE_CEILING_CAD * 1.5:
        reasons.append(f"price CA${price} is outside (0, {PREMIUM_PRICE_CEILING_CAD * 1.5}]")
    if not (0 < hours[0] <= hours[1]) or design <= 0:
        reasons.append("maker_hours must be 0 < fast <= slow and design_hours positive")
    if len(str(p["rationale"]).split()) < 12:
        reasons.append("the rationale must say, in a sentence of at least 12 words, why "
                       "this opportunity is real")
    season = p.get("season")
    if season and season not in {e.name for e in SEASONAL_EVENTS}:
        reasons.append(f"season {season!r} is not a known seasonal event")
    # Evidence (never fabricated): whatever the source module recorded about it.
    reasons += list(evidence.get("reasons") or [])
    c = p["concept"]
    reasons += construction_verdict(p["category"], str(c.get("form")),
                                    str(c.get("construction")))
    if c.get("pod") not in POD_KEYS:
        reasons.append(f"pod {c.get('pod')!r} is not a pod key")
    make_lane = make_lane_for_hours(hours) if hours[1] > 0 else "QUICK"
    built = None
    try:
        built = Concept(key=slug, title=str(p["title"]), premise=str(c["premise"]),
                        pod=str(c["pod"]), form=str(c["form"]),
                        construction=str(c["construction"]), motif=str(c["motif"]),
                        palette_story=str(c["palette_story"]), recipient=str(c["recipient"]),
                        occasion=str(c["occasion"]), feeling=str(c["feeling"]),
                        function=str(c["function"]), make_lane=make_lane,
                        provenance=f"radar.intake:{source_ref}")
    except ConceptRefused as exc:
        reasons.append(f"concept vocabulary: {exc}")
    reasons += _children_reasons(db, p, c)
    gap, originality = 0.0, {}
    if built is not None:
        more, gap, originality = _originality_reasons(db, p, built, source_ref)
        reasons += more
    seed = None
    if not reasons:
        seed = {"title": str(p["title"]), "category": p["category"],
                # Derived, not typed: a flat rows panel is the Class A geometry the compiler
                # proves end to end; whitespace is the measured distance to the nearest
                # existing idea; the make lane is read from the maker hours.
                "risk_class": "A", "price_cad": price, "maker_hours": list(hours),
                "design_hours": design, "whitespace": round(min(1.0, gap), 3),
                "rationale": str(p["rationale"]), "season": season or None,
                "family": p.get("family"), "evergreen": bool(p.get("evergreen"))
                if season is None else False,
                "bundle_ready": bool(p.get("bundle_ready")), "make_lane": make_lane}
    return {"ok": not reasons, "reasons": reasons, "seed": seed,
            "concept": {**c, "make_lane": make_lane}, "brief": p["brief"],
            "originality": originality, "clean": p}


# ---- sources of proposals -----------------------------------------------------------------


def research_candidates(db, *, today: date) -> list[dict]:
    """Every concept proposal attached to a research task, with that task's evidence."""
    from ..intel import research

    research._ensure(db)
    with db.session() as s:
        rows = [(r.id, list((r.detail or {}).get("concept_proposals") or []), r.trigger)
                for r in s.scalars(select(research.ResearchTask)
                                   .order_by(research.ResearchTask.id))
                if (r.detail or {}).get("concept_proposals")]
    out = []
    for tid, proposals, trigger in rows:
        for prop in proposals:
            ev = research_evidence(db, tid, (prop or {}).get("evidence") or (), today=today)
            out.append({"source": SOURCE_RESEARCH, "source_ref": f"research_task:{tid}",
                        "proposal": dict(prop or {}), "evidence": ev, "trigger": trigger})
    return out


def _median(xs: list[float], default: float) -> float:
    xs = sorted(xs)
    if not xs:
        return default
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def family_evidence(db, family: dict, *, today: date) -> dict:
    """Winner Amplification evidence: the family's measured orders and certified members,
    dated. Quality grows with the order count and decays when the last order is old."""
    from sqlalchemy import func

    from ..core.models import Order
    from ..creative.family_engine import AMPLIFY_MIN_ORDERS

    slugs = [m["slug"] for m in family.get("members") or []]
    with db.session() as s:
        n, first, last = s.execute(
            select(func.count(Order.id), func.min(Order.at), func.max(Order.at))
            .where(Order.product_slug.in_(slugs), Order.refunded.is_(False))).one()
    n = int(n or 0)
    reasons = []
    if n < AMPLIFY_MIN_ORDERS:
        reasons.append(f"family {family.get('family')!r} has {n} measured order(s), below the "
                       f"amplification floor {AMPLIFY_MIN_ORDERS}: no proven demand to amplify")
    items = [{"ref": f"orders:{family.get('family')}", "kind": "orders", "orders": n,
              "claim_class": "fact",
              "date": _aware(first).date().isoformat() if first else None,
              "last": _aware(last).date().isoformat() if last else None}]
    items += [{"ref": f"certified:{m['slug']}@{m['version']}", "kind": "certified_member",
               "claim_class": "fact", "orders": m.get("orders", 0), "date": None}
              for m in family.get("members") or []]
    age = (today - _aware(last).date()).days if last else None
    freshness = 0.0 if age is None else (1.0 if age <= 90 else max(0.0, 1 - (age - 90) / 90))
    quality = round(min(1.0, 0.5 + 0.5 * min(1.0, n / 20.0)) * freshness, 3) if n else 0.0
    if not reasons and quality < MIN_EVIDENCE_QUALITY:
        reasons.append(f"family evidence quality {quality} is below {MIN_EVIDENCE_QUALITY} "
                       f"(last order {age} days ago)")
    return {"ok": not reasons, "reasons": reasons, "items": items, "quality": quality,
            "uncertainty": round(1.0 - quality, 3), "orders": n}


def _decided_slugs(db, source_ref: str) -> set[str]:
    _ensure(db)
    with db.session() as s:
        return set(s.scalars(select(RadarConcept.slug).where(
            RadarConcept.source_ref == source_ref,
            RadarConcept.state.in_((APPROVED, REFUSED, SUPERSEDED)))))


def family_candidates(db, *, today: date) -> list[dict]:
    """Coordinated variations for every certified family whose orders prove demand and
    which has no declared next member left (the family engine's `needs_original_design`).
    Deterministic: the categories the family does not yet hold, in table order, in a
    construction the draft path compiles. The same validation as any other proposal."""
    from ..creative.family_engine import family_report
    from ..intel import pods

    rep = family_report(db)
    by_slug = {s.slug: s for s in POOL}
    intake_rows = approved_rows(db)
    out = []
    for f in rep.get("families") or []:
        if not isinstance(f.get("amplification"), dict) or f.get("next_members"):
            continue
        key = f["family"]
        members = sorted(f.get("members") or [], key=lambda m: (-m["orders"], m["slug"]))
        if not members:
            continue
        winner = members[0]["slug"]
        parent = next((s for s in POOL if s.family == key and not s.is_bundle), None)
        held = {s.category for s in POOL if s.family == key} | {
            (r.seed or {}).get("category") for r in intake_rows
            if (r.seed or {}).get("family") == key}
        # A variation intake already decided (approved or refused) is not re-proposed: a
        # refused one would otherwise hold a slot every run and the family would never move.
        decided = _decided_slugs(db, f"family:{key}")
        ev = family_evidence(db, f, today=today)
        name = key.replace("-", " ").title()
        motif = key.replace("-", " ")
        made = 0
        for category in SUPPORTED_FORMS:
            if made >= MAX_FAMILY_VARIATIONS:
                break
            if category in held or f"{key}-{category.replace('_', '-')}" in decided:
                continue
            peers = [s for s in POOL if s.category == category and not s.is_bundle]
            title = f"{name} {_NOUN[category]}"
            season = parent.season if parent else None
            winner_title = (by_slug.get(winner).title if by_slug.get(winner)
                            else winner.replace("-", " "))
            proposal = {
                "slug": f"{key}-{category.replace('_', '-')}", "title": title,
                "category": category,
                "price_cad": round(_median([s.price_cad for s in peers], 6.5), 2),
                "maker_hours": [_median([s.maker_hours[0] for s in peers], 2.0),
                                _median([s.maker_hours[1] for s in peers], 6.0)],
                "design_hours": _median([s.design_hours for s in peers], 8.0),
                "season": season, "family": key, "evergreen": season is None,
                "bundle_ready": True,
                "rationale": (f"Winner Amplification: family {key} has {ev.get('orders', 0)} "
                              f"measured orders across {len(members)} certified member(s) and "
                              f"no declared next member, so a {_NOUN[category].lower()} "
                              f"extends the set in a construction the draft path compiles"),
                "concept": {
                    "premise": (f"The {motif} motif from {winner_title} carried onto "
                                f"{_WHAT[category]} so an owner of one piece can complete "
                                f"the matching set"),
                    "pod": pods.route(f"{title} {category.replace('_', ' ')}"),
                    "form": SUPPORTED_FORMS[category][0], "construction": "flat_rows",
                    "motif": motif, "palette_story": f"the {motif} family palette",
                    "recipient": "self",
                    "occasion": _OCCASION_OF_SEASON.get(season or "", "everyday"),
                    "feeling": "cosy", "function": _FUNCTION[category]},
                "brief": {"silhouette_qualifiers": ["motif_composition"],
                          "thumbnail_storyboard": (f"{_WHAT[category]} carrying the {motif} "
                                                   f"motif beside the {winner_title}")},
                "evidence": [i["ref"] for i in ev["items"]],
            }
            out.append({"source": SOURCE_FAMILY, "source_ref": f"family:{key}",
                        "proposal": proposal, "evidence": ev, "trigger": f"family:{key}"})
            made += 1
    return out


# ---- the run -----------------------------------------------------------------------------


def _existing(db, fp: str) -> RadarConcept | None:
    with db.session() as s:
        row = s.scalar(select(RadarConcept).where(RadarConcept.fingerprint == fp))
        if row is not None:
            s.expunge(row)
        return row


def evaluate(db, candidate: dict, *, audit, enqueue, today: date) -> dict:
    """Propose, validate and decide one candidate. Idempotent on its fingerprint."""
    _ensure(db)
    ev = candidate["evidence"]
    clean = _clean(candidate["proposal"])
    fp = fingerprint(candidate["source_ref"], clean, ev)
    prior = _existing(db, fp)
    if prior is not None:
        return {"slug": prior.slug, "state": prior.state, "unchanged": True, "id": prior.id}
    slug = str(clean.get("slug") or "unnamed")[:80]
    with db.session() as s:
        row = RadarConcept(slug=slug, state=PROPOSED, source=candidate["source"],
                           source_ref=candidate["source_ref"], fingerprint=fp,
                           evidence=list(ev.get("items") or []),
                           quality=float(ev.get("quality") or 0.0),
                           detail={"proposal": clean, "trigger": candidate.get("trigger"),
                                   "evidence": {k: v for k, v in ev.items() if k != "items"}})
        s.add(row)
        s.flush()
        row_id = row.id
    audit(PROPOSED_ACTION, artifact=slug, detail={
        "row": row_id, "source": candidate["source"], "source_ref": candidate["source_ref"],
        "evidence_refs": [i.get("ref") for i in ev.get("items") or []],
        "quality": ev.get("quality")})
    verdict = validate(db, candidate["proposal"], ev, source_ref=candidate["source_ref"])
    now = datetime.now(timezone.utc)
    withdrawn_ids: list[int] = []
    with db.session() as s:
        row = s.get(RadarConcept, row_id)
        row.reasons = list(verdict["reasons"])
        row.concept = dict(verdict["concept"] or {})
        row.brief = dict(verdict["brief"] or {})
        row.decided_at = now
        row.detail = {**(row.detail or {}), "originality": verdict.get("originality")}
        if verdict["ok"]:
            row.seed = verdict["seed"]
            row.state = APPROVED
            # A changed proposal for the same slug from the same source replaces the old one.
            for old in s.scalars(select(RadarConcept).where(
                    RadarConcept.slug == slug, RadarConcept.state == APPROVED,
                    RadarConcept.source_ref == candidate["source_ref"],
                    RadarConcept.id != row_id)):
                old.state = SUPERSEDED
        else:
            row.state = REFUSED
            # F1: a changed proposal for an approved (source_ref, slug) that is now refused
            # takes the earlier approval with it -- the newest decision is the standing one.
            for old in s.scalars(select(RadarConcept).where(
                    RadarConcept.slug == slug, RadarConcept.state == APPROVED,
                    RadarConcept.source_ref == candidate["source_ref"],
                    RadarConcept.id != row_id)):
                old.state = WITHDRAWN
                old.reasons = list(old.reasons or []) + [
                    f"withdrawn: its revised proposal (row {row_id}) was refused"]
                withdrawn_ids.append(old.id)
    for old_id in withdrawn_ids:
        audit(WITHDRAWN_ACTION, artifact=slug, detail={
            "row": old_id, "source_ref": candidate["source_ref"],
            "reasons": [f"revised proposal row {row_id} was refused"]})
    if not verdict["ok"]:
        audit(REFUSED_ACTION, artifact=slug, detail={
            "row": row_id, "source_ref": candidate["source_ref"],
            "reasons": verdict["reasons"][:10], "quality": ev.get("quality")})
        return {"slug": slug, "state": REFUSED, "reasons": verdict["reasons"], "id": row_id}
    audit(APPROVED_ACTION, artifact=slug, detail={
        "row": row_id, "source_ref": candidate["source_ref"], "quality": ev.get("quality"),
        "uncertainty": ev.get("uncertainty"), "whitespace": verdict["seed"]["whitespace"],
        "category": verdict["seed"]["category"], "make_lane": verdict["seed"]["make_lane"],
        "originality": verdict.get("originality")})
    # The successor job: the ordinary per-slug radar.score, keyed like radar.scan so a
    # concept the scan already queued today is not queued twice.
    seed = approved_concept(db, slug)["seed"]
    payload = score_concept(seed, today).to_dict()
    payload["intake"] = {"row": row_id, "source_ref": candidate["source_ref"]}
    job = enqueue("market_radar", "radar.score", payload,
                  idempotency_key=f"score:{slug}:{today.isoformat()}")
    audit(HANDOFF_ACTION, artifact=slug, detail={
        "row": row_id, "job_type": "radar.score",
        "job_id": getattr(job, "id", None), "already_queued": job is None})
    return {"slug": slug, "state": APPROVED, "id": row_id,
            "score_job": getattr(job, "id", None)}


def rescore_judged(db, *, audit, enqueue, today: date) -> list[str]:
    """An approved concept that waited at the pre-engineering gate for a taste judgement is
    re-scored once the vision judge's verdict is on record, so it reaches `cir.draft` with no
    session in the loop. Keyed `score:<slug>:<date>` (shared with radar.scan): at most once a
    day, and never for a concept whose `draft:<slug>` already exists. No judgement, no job."""
    from ..core.models import Job
    from ..creative import intake as creative_intake

    out = []
    for row in approved_rows(db):
        with db.session() as s:
            drafted = s.scalar(select(Job.id).where(
                Job.idempotency_key == f"draft:{row.slug}").limit(1))
        if drafted is not None or not creative_intake.judgement_for(db, row.slug):
            continue
        payload = score_concept(_seed_from(row), today).to_dict()
        payload["intake"] = {"row": row.id, "source_ref": row.source_ref,
                             "reason": "vision judgement recorded"}
        job = enqueue("market_radar", "radar.score", payload,
                      idempotency_key=f"score:{row.slug}:{today.isoformat()}")
        if job is not None:
            audit(HANDOFF_ACTION, artifact=row.slug, detail={
                "row": row.id, "job_type": "radar.score", "job_id": job.id,
                "reason": "re-scored: a vision judgement is now on record"})
            out.append(row.slug)
    return out


def withdraw_unsupported(db, *, audit, today: date) -> list[dict]:
    """F1: an approval stands only while its evidence does. Each approved row is re-checked
    against its source as of `today`; one that no longer passes (stale, expired, unresolved,
    an unproven family) is WITHDRAWN -- out of the pool -- and audited with the reasons."""
    _ensure(db)
    with db.session() as s:
        rows = list(s.scalars(select(RadarConcept).where(RadarConcept.state == APPROVED)
                              .order_by(RadarConcept.id)))
        s.expunge_all()
    report = None
    out = []
    for row in rows:
        refs = ((row.detail or {}).get("proposal") or {}).get("evidence") or []
        if row.source == SOURCE_RESEARCH:
            ev = research_evidence(db, int(row.source_ref.split(":", 1)[1]), refs, today=today)
        else:
            if report is None:
                from ..creative.family_engine import family_report

                report = {f["family"]: f for f in family_report(db).get("families") or []}
            fam = report.get(row.source_ref.split(":", 1)[1])
            ev = (family_evidence(db, fam, today=today) if fam is not None else
                  {"ok": False, "reasons": [f"{row.source_ref} is no longer a certified "
                                            f"family"]})
            if fam is not None and not isinstance(fam.get("amplification"), dict):
                ev = {**ev, "ok": False, "reasons": list(ev.get("reasons") or []) + [
                    f"{row.source_ref} no longer has proven demand to amplify"]}
        if ev.get("ok"):
            continue
        with db.session() as s:
            r = s.get(RadarConcept, row.id)
            r.state = WITHDRAWN
            r.decided_at = datetime.now(timezone.utc)
            r.reasons = list(r.reasons or []) + [f"withdrawn {today.isoformat()}: {x}"
                                                 for x in ev.get("reasons") or []][:10]
        audit(WITHDRAWN_ACTION, artifact=row.slug, detail={
            "row": row.id, "source_ref": row.source_ref,
            "reasons": list(ev.get("reasons") or [])[:5], "as_of": today.isoformat()})
        out.append({"slug": row.slug, "reasons": list(ev.get("reasons") or [])[:3]})
    return out


def _current_fingerprints(db, *, today: date) -> set[str]:
    """The fingerprints today's candidates produce (what `evaluate` would look up)."""
    cands = research_candidates(db, today=today) + family_candidates(db, today=today)
    return {fingerprint(c["source_ref"], _clean(c["proposal"]), c["evidence"]) for c in cands}


def prune(db, *, now: datetime | None = None, dry_run: bool = False) -> dict:
    """Retention for `radar_concepts` (called by `ops.retention`). Approved rows are never
    pruned. Refused, superseded and withdrawn rows older than RETENTION_DAYS go, except the
    newest row of each (source_ref, slug): its fingerprint is what keeps an unchanged refused
    proposal from being re-evaluated."""
    _ensure(db)
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RETENTION_DAYS)
    with db.session() as s:
        rows = list(s.execute(select(RadarConcept.id, RadarConcept.source_ref,
                                     RadarConcept.slug, RadarConcept.state, RadarConcept.at,
                                     RadarConcept.fingerprint)
                              .order_by(RadarConcept.id)).all())
    newest: dict[tuple, int] = {}
    for rid, ref, slug, _st, _at, _fp in rows:
        newest[(ref, slug)] = rid
    # G2 (review bb680ec): a row holding the fingerprint a CURRENT candidate would produce is
    # what keeps that unchanged proposal from being re-evaluated, whether or not it is the
    # newest row of its slug -- so it is never pruned.
    current = _current_fingerprints(db, today=now.date())
    deletable = [rid for rid, ref, slug, st, at, fp in rows
                 if st in (REFUSED, SUPERSEDED, WITHDRAWN) and newest[(ref, slug)] != rid
                 and fp not in current and at is not None and _aware(at) < cutoff]
    if not dry_run and deletable:
        with db.session() as s:
            for rid in deletable:
                row = s.get(RadarConcept, rid)
                if row is not None:
                    s.delete(row)
    return {"rows": len(rows), "deletable": len(deletable),
            "removed": 0 if dry_run else len(deletable), "retention_days": RETENTION_DAYS}


def run(db, *, audit, enqueue, today: date | None = None) -> dict:
    """One intake pass: research proposals, then family variations. Bounded, idempotent."""
    _ensure(db)
    today = today or datetime.now(timezone.utc).date()
    withdrawn = withdraw_unsupported(db, audit=audit, today=today)
    candidates = research_candidates(db, today=today) + family_candidates(db, today=today)
    decided, unchanged = [], 0
    for cand in candidates:
        if len(decided) >= MAX_EVALUATIONS_PER_RUN:
            break
        out = evaluate(db, cand, audit=audit, enqueue=enqueue, today=today)
        if out.get("unchanged"):
            unchanged += 1
            continue
        decided.append(out)
    rescored = rescore_judged(db, audit=audit, enqueue=enqueue, today=today)
    return {"candidates": len(candidates), "unchanged": unchanged,
            "rescored": rescored, "withdrawn": withdrawn,
            "approved": [d["slug"] for d in decided if d["state"] == APPROVED],
            "refused": [{"slug": d["slug"], "reasons": d.get("reasons", [])[:3]}
                        for d in decided if d["state"] == REFUSED],
            "work_done": len(decided) + len(rescored) + len(withdrawn), "network_calls": 0, "spend_cad": 0.0,
            "as_of": today.isoformat()}
