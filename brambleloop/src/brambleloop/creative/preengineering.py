"""The pre-engineering gate: one deterministic sequence between an idea and a CIR.

Requirements 83, 87, 88, 108, 110, 115, 125 and 126 (engineering half), with 114 measured on
the wave. Each of those modules existed, was tested, and was called by nothing on the path
that actually sends work to engineering: `radar.score` enqueued `cir.draft` on an opportunity
score alone, which is precisely "engineered because it filled a keyword/category slot" (#83).

This module is the one place that path now has to pass through. It runs every check, in a
fixed order, and never short-circuits, so a refusal names *all* of its reasons rather than the
first one somebody happened to hit:

    premise_thumbnail (#88) -> jury (#83) -> novelty (#87) -> silhouette (#108)
        -> motif_grammar (#110) -> wow (#115) -> top_decile (#125) -> grid_tournament (#126)

Three outcomes, and the difference between the last two is the honest part:

* ``passed`` -- every applicable check ran and passed. Only this is engineered.
* ``refused`` -- a check failed on something deterministic. The idea is returned to creative
  development with the reasons and an autopsy (#127), never engineered.
* ``waiting`` -- nothing failed, but a check needs a judgement nobody can supply today (the
  vision jury, a top-decile concept score, the grid's judges; all need `model_provider` /
  `image_vision`, which read CLOSED). The concept is **not** engineered. Unmeasured is never
  passing, and a gate that let "nobody has looked" through would be the formality #83 forbids.

What is *not* a new concept: a design that already exists in the catalogue (a hand-engineered
product or a generated catalogue design) or a product already certified. Re-drafting those is a
rebuild -- `chain.rebuild` re-derives a stale CIR for a design that was already chosen -- and
blocking it would stop the company maintaining what it sells without making a single new idea
better. That exemption is a closed list read from the code and the database, never from a
job's inputs, so a caller cannot talk its way into it.
"""
from __future__ import annotations

import re
from datetime import date

from .concept import GENERIC_TOKENS, Concept, ConceptRefused

GATE_ACTION = "concept.gate"
RETURNED_ACTION = "concept.returned_to_ideation"

PASSED, REFUSED, WAITING, EXEMPT = "passed", "refused", "waiting", "exempt"
PASS, FAIL, UNMEASURED, NOT_APPLICABLE = "pass", "fail", "unmeasured", "not_applicable"

CHECKS: tuple[str, ...] = ("premise_thumbnail", "jury", "novelty", "silhouette",
                           "motif_grammar", "wow", "top_decile", "grid_tournament",
                           "emotional_promise", "half_life", "redesign")

# Which requirement each check is the runtime form of.
REQUIREMENT: dict[str, int] = {
    "premise_thumbnail": 88, "jury": 83, "novelty": 87, "silhouette": 108,
    "motif_grammar": 110, "wow": 115, "top_decile": 125, "grid_tournament": 126,
    "emotional_promise": 109, "half_life": 290,
    # Master v1.0 ids from here on; the numbers above are the v1.4.3 plan's.
    "redesign": "F-791",
}

# #126: "before CIR engineering for *expensive* concepts". Expensive is the make lane, which
# is the engineering and making time the concept commits to.
EXPENSIVE_MAKE_LANES: tuple[str, ...] = ("LONG", "FLAGSHIP")

# A thumbnail storyboard says what a 170-pixel square shows. Fewer specific words than this
# and it is a title, not a storyboard.
STORYBOARD_MIN_WORDS = 6

# Which motif grammar (#110) an occasion draws on. An occasion absent here has no seasonal
# grammar, and the check does not apply to it rather than being passed.
GRAMMAR_SEASON: dict[str, str] = {
    "christmas": "christmas", "thanksgiving": "fall", "halloween": "halloween",
    "easter": "spring", "spring_refresh": "spring", "summer_travel": "summer",
}

# The calendar event an occasion belongs to, for the jury's shopping-window critic.
_EVENT_OF_OCCASION: dict[str, str] = {
    "christmas": "Christmas", "halloween": "Halloween", "thanksgiving": "Thanksgiving (CA)",
    "valentines": "Valentine's", "easter": "Easter", "mothers_day": "Mother's Day",
}

# The fields a concept brief may carry beside the Concept itself.
BRIEF_FIELDS: tuple[str, ...] = (
    "thumbnail_storyboard", "silhouette_qualifiers", "motifs", "wow_mechanism",
    "wow_grounding", "strength_score", "strength_score_source", "benchmark_scores",
    "board_image", "techniques", "season", "trend_domain",
    # F-794: a competitor-informed concept names the benchmarks it learned from and carries
    # its design-difference ledger (a list of `gates.originality.LedgerEntry` dicts).
    "benchmarks_consulted", "design_difference_ledger",
)

_CONCEPT_FIELDS: tuple[str, ...] = (
    "key", "title", "premise", "pod", "form", "construction", "motif", "palette_story",
    "recipient", "occasion", "feeling", "function", "make_lane")

_WORD = re.compile(r"[a-z]+")


def _specific(text: str) -> list[str]:
    return [w for w in _WORD.findall((text or "").lower()) if w not in GENERIC_TOKENS]


# ---------------------------------------------------------------------------
# What is a new concept


def established(db, slug: str) -> str | None:
    """Why `slug` is not a new concept, or None when it is one.

    A closed list read from the code and the database: the hand-engineered designs, the
    generated catalogue, and anything already certified. Job inputs cannot add to it.
    """
    if not slug:
        return None
    from ..products.builder import CATALOGUE
    from ..runtime.pipeline import ENGINEERED

    if slug in ENGINEERED:
        return "an engineered catalogue design: re-drafting it is a rebuild, not a new concept"
    from ..products.launch0 import LEGACY_DUPLICATES

    # PT-11: a retired concept slug whose design is a Launch-0 variant is not a new concept
    # either; `cir.draft` routes it to the Launch-0 slugs instead of drafting it.
    if slug in LEGACY_DUPLICATES:
        return ("a retired alias of an engineered Launch-0 design: re-drafting it routes to "
                f"{', '.join(LEGACY_DUPLICATES[slug]['superseded_by'])}, not a new concept")
    if any(design.slug == slug for design in CATALOGUE.values()):
        return "a generated catalogue design: re-drafting it is a rebuild, not a new concept"
    if db is not None:
        from sqlalchemy import select

        from ..core.models import PatternVersion, Product

        with db.session() as s:
            certified = s.scalar(
                select(PatternVersion.id).join(Product, Product.id == PatternVersion.product_id)
                .where(Product.slug == slug, PatternVersion.certified.is_(True)).limit(1))
        if certified is not None:
            return "already certified: a re-draft of a certified product is a rebuild"
    return None


def concept_from(data) -> tuple[Concept | None, dict, str]:
    """(concept, brief, problem). The problem is non-empty when no Concept could be built."""
    if isinstance(data, Concept):
        return data, {}, ""
    data = dict(data or {})
    raw = dict(data.get("concept") if isinstance(data.get("concept"), dict) else data)
    raw.setdefault("key", raw.get("slug"))
    brief = {k: v for k, v in {**data, **(data.get("brief") or {}), **raw}.items()
             if k in BRIEF_FIELDS}
    missing = [f for f in _CONCEPT_FIELDS if not str(raw.get(f) or "").strip()]
    if missing:
        return None, brief, (
            f"{raw.get('key') or raw.get('slug') or 'this idea'} is not a concept yet: it has "
            f"no {missing}. A radar slot names a category and a price; #83 forbids "
            f"engineering something because it fills a slot, and #88 requires a one-sentence "
            f"visual premise and a thumbnail storyboard before any CIR work")
    try:
        concept = Concept(
            key=str(raw["key"]), title=str(raw["title"]), premise=str(raw["premise"]),
            pod=str(raw["pod"]), form=str(raw["form"]), construction=str(raw["construction"]),
            motif=str(raw["motif"]), palette_story=str(raw["palette_story"]),
            recipient=str(raw["recipient"]), occasion=str(raw["occasion"]),
            feeling=str(raw["feeling"]), function=str(raw["function"]),
            make_lane=str(raw["make_lane"]), provenance=str(raw.get("provenance") or "internal"),
            thumbnail_reads_small=raw.get("thumbnail_reads_small"),
            craft_impression=raw.get("craft_impression"))
    except ConceptRefused as exc:
        return None, brief, str(exc)
    return concept, brief, ""


# ---------------------------------------------------------------------------
# The checks. Each returns {"status", "reasons", "detail"}.


def _result(status: str, reasons: list[str] | None = None, **detail) -> dict:
    return {"status": status, "reasons": list(reasons or []), "detail": detail}


def _premise_thumbnail(concept: Concept, brief: dict) -> dict:
    """#88: a one-sentence visual premise (enforced by Concept) and a thumbnail storyboard."""
    storyboard = str(brief.get("thumbnail_storyboard") or "").strip()
    words = _specific(storyboard)
    if len(words) < STORYBOARD_MIN_WORDS:
        return _result(FAIL, [
            f"no thumbnail storyboard: {len(words)} specific word(s) describing what the "
            f"mobile-grid thumbnail shows, below {STORYBOARD_MIN_WORDS}. #88 requires one "
            f"before CIR work"], premise=concept.premise, storyboard=storyboard)
    if concept.thumbnail_reads_small is False:
        return _result(FAIL, ["judged not to read at mobile-grid size"],
                       premise=concept.premise, storyboard=storyboard)
    if concept.thumbnail_reads_small is None:
        return _result(UNMEASURED, [
            "whether the idea still creates curiosity at mobile-grid size with seller, "
            "price, reviews and badges removed is a judgement only a vision model can make, "
            "and none has made it"], premise=concept.premise, storyboard=storyboard,
            needs="image_vision")
    return _result(PASS, premise=concept.premise, storyboard=storyboard)


def _days_to_event(occasion: str, today: date) -> int | None:
    from ..radar.market import SEASONAL_EVENTS

    name = _EVENT_OF_OCCASION.get(occasion)
    event = next((e for e in SEASONAL_EVENTS if e.name == name), None)
    if event is None:
        return None
    when = event.event_date
    while when < today:
        when = when.replace(year=when.year + 1)
    return (when - today).days


def _jury(concept: Concept, brief: dict, catalogue: list, today: date) -> dict:
    """#83: every critic, then the taste questions only eyes can answer."""
    from .jury import APPROVED, REJECTED, Context, judge

    techniques = brief.get("techniques")
    ctx = Context(catalogue=catalogue, techniques=int(techniques) if techniques else 1,
                  days_to_event=_days_to_event(concept.occasion, today))
    verdict = judge(concept, ctx)
    detail = {"decision": verdict.decision, "findings": [f.to_dict() for f in verdict.findings],
              "unjudged": list(verdict.unjudged), "techniques_declared": bool(techniques)}
    if verdict.decision == REJECTED:
        return _result(FAIL, [f"{f.critic}: {f.problem}" for f in verdict.findings], **detail)
    if verdict.decision == APPROVED:
        return _result(PASS, **detail)
    return _result(UNMEASURED, [
        f"structurally clean and unjudged on {verdict.unjudged}: the jury's best verdict "
        f"without a vision model is needs_taste, which is not approval"],
        needs="image_vision", **detail)


def _novelty(db, concept: Concept, catalogue: list, benchmark: list | None) -> dict:
    """#87: distance from our own catalogue and from observed competitor concepts."""
    from .concept import nearest
    from .prospecting import MIN_NOVELTY, _matches_a_listing, benchmark_comparables

    cards = benchmark if benchmark is not None else (
        benchmark_comparables(db) if db is not None else [])
    near, gap = nearest(concept, catalogue)
    twin = _matches_a_listing(concept, cards) if cards else ""
    detail = {"nearest_own": near.key if near else None, "distance_own": gap,
              "min_novelty": MIN_NOVELTY, "benchmark_cards": len(cards),
              "benchmark_twin": twin or None,
              "comparable_in_catalogue": any(c.pod == concept.pod for c in catalogue)}
    reasons = []
    if near is not None and gap < MIN_NOVELTY:
        reasons.append(f"{gap} from our own {near.key!r}, below the novelty floor "
                       f"{MIN_NOVELTY}: a near-clone or recolour of something we already sell")
    if twin:
        reasons.append(f"indistinguishable from observed listing {twin} on everything either "
                       f"side states. The arena is allowed; arriving as their listing is not")
    if reasons:
        return _result(FAIL, reasons, **detail)
    if not cards:
        return _result(UNMEASURED, [
            "no observed competitor concept is on file to compare against, so the anti-clone "
            "half of #87 has not been measured -- which is not the same as passing it"],
            needs="benchmark_observation", **detail)
    return _result(PASS, **detail)


def _silhouette(concept: Concept, brief: dict) -> dict:
    """#108, with the premise read with the title's words removed."""
    from .invention import InventionRefused, silhouette

    try:
        out = silhouette(form=concept.form, premise=concept.premise, title=concept.title,
                         qualifiers=tuple(brief.get("silhouette_qualifiers") or ()))
    except InventionRefused as exc:
        return _result(FAIL, [str(exc)])
    return _result(PASS if out["passes"] else FAIL, out["problems"], **out)


def _motif_grammar(concept: Concept, brief: dict) -> dict:
    """#110: a seasonal concept declares motifs from its season's grammar, not only clichés."""
    from .invention import InventionRefused, motifs

    season = GRAMMAR_SEASON.get(concept.occasion) or (brief.get("season") or None)
    if not season:
        return _result(NOT_APPLICABLE, season=None, occasion=concept.occasion)
    chosen = tuple(brief.get("motifs") or ())
    if not chosen:
        return _result(FAIL, [
            f"a {season} concept has declared no motifs from the {season} grammar, so "
            f"nothing shows it recombines rather than reaching for the category's default"],
            season=season)
    try:
        out = motifs(season, chosen)
    except InventionRefused as exc:
        return _result(FAIL, [str(exc)], season=season)
    if out["all_saturated"]:
        return _result(FAIL, [out["note"]], **out)
    return _result(PASS, **out)


def _wow(concept: Concept, brief: dict) -> dict:
    """#115: every flagship declares a grounded WOW mechanism."""
    from .invention import FLAGSHIP, InventionRefused, wow

    if concept.make_lane != FLAGSHIP:
        return _result(NOT_APPLICABLE, make_lane=concept.make_lane)
    try:
        out = wow(concept.make_lane, brief.get("wow_mechanism"),
                  str(brief.get("wow_grounding") or ""))
    except InventionRefused as exc:
        return _result(FAIL, [str(exc)])
    return _result(PASS if out.ok else FAIL, out.problems, **out.to_dict())


def _top_decile(concept: Concept, brief: dict, db=None) -> dict:
    """#125: a flagship is scored against the category's top decile, not its mean.

    C-60: when the brief carries no judged score and no benchmark scores, both are produced
    by `creative.strength` -- the same deterministic card rubric applied to the concept and
    to every observed listing in its pod -- so the check measures rather than waits. A brief
    that does carry a score keeps it, and still needs its judge named.
    """
    from .invention import FLAGSHIP
    from .standard import aspiration

    if concept.make_lane != FLAGSHIP:
        return _result(NOT_APPLICABLE, make_lane=concept.make_lane)
    scores = [float(s) for s in (brief.get("benchmark_scores") or [])]
    score = brief.get("strength_score")
    source = str(brief.get("strength_score_source") or "").strip()
    if db is not None and score is None and not scores:
        from . import strength

        scores = strength.benchmark_scores(db, concept.pod)
        mine = strength.concept_score(db, concept)
        score, source = mine["score"], (mine["source"] if mine["score"] is not None else "")
    aim = aspiration(scores)
    reasons = []
    if score is None or not source:
        reasons.append(
            "no judged concept-strength score with a named judge: scoring a concept's "
            "strength needs the model jury (model_provider), and a score with no judge is "
            "not a measurement")
    if not aim["measurable"]:
        reasons.append(aim["reason"])
    if reasons:
        return _result(UNMEASURED, reasons, aspiration=aim, needs="model_provider")
    score = float(score)
    detail = {"score": score, "score_source": source, "top_decile": aim["top_decile"],
              "category_mean": aim["category_mean"], "sample": aim["sample"]}
    if score < aim["top_decile"]:
        return _result(FAIL, [
            f"scored {score} against a category top decile of {aim['top_decile']}: parity "
            f"with the category is the floor, and a flagship aims at the top decile (#125)"],
            **detail)
    return _result(PASS, **detail)


def grid_verdict_for(db, ref: str) -> dict | None:
    """The newest recorded search-grid verdict for a concept or product, if any (#126)."""
    if db is None or not ref:
        return None
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        for row in s.scalars(select(AuditLog)
                             .where(AuditLog.action == "creative.grid_tournament")
                             .order_by(desc(AuditLog.id)).limit(20)):
            found = ((row.detail or {}).get("concepts") or {}).get(ref)
            if found:
                return dict(found, audit_id=row.id)
    return None


def release_grid_verdict(db, slug: str) -> dict:
    """#126's release half for one product: the verdict of the grid its pod was judged in.

    `cleared` is True only for a recorded `clear`. No run, a refused grid or an unjudged one
    all read as not cleared, with the reason -- a threshold cleared by default is the brand
    favouritism the requirement forbids.
    """
    if db is None or not slug:
        return {"slug": slug, "cleared": False, "verdict": None, "why": "no database"}
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        for row in s.scalars(select(AuditLog)
                             .where(AuditLog.action == "creative.grid_tournament")
                             .order_by(desc(AuditLog.id)).limit(20)):
            found = ((row.detail or {}).get("products") or {}).get(slug)
            if found:
                return {"slug": slug, "cleared": found.get("verdict") == "clear",
                        "verdict": found.get("verdict"), "pod": found.get("pod"),
                        "why": found.get("why"), "audit_id": row.id}
    return {"slug": slug, "cleared": False, "verdict": None,
            "why": "the search-grid tournament has never recorded a verdict for this product"}


def _grid(db, concept: Concept, brief: dict) -> dict:
    """#126: an expensive concept clears the blind search grid before engineering."""
    if concept.make_lane not in EXPENSIVE_MAKE_LANES:
        return _result(NOT_APPLICABLE, make_lane=concept.make_lane)
    found = grid_verdict_for(db, concept.key)
    board = str(brief.get("board_image") or "").strip()
    if found and found.get("verdict") == "clear":
        return _result(PASS, **found)
    if found and found.get("below_threshold"):
        return _result(FAIL, [f"the blind search grid ranked it below the threshold on "
                              f"{found['below_threshold']}"], **found)
    reasons = [("the blind search grid has not judged this concept: "
                + (found.get("why") or found.get("verdict") or "") if found else
                "the blind search grid has not judged this concept")]
    if not board:
        reasons.append("no concept board image exists to place in the grid; rendering one "
                       "needs image_generation")
    return _result(UNMEASURED, reasons, board_image=board or None, recorded=found,
                   needs="image_vision", request_grid=bool(board) and not found)


# #109: the emotional promise, executed in the object. Which part of the object carries the
# feeling is read from the premise's own words, first match wins; a premise naming none of
# them delivers it through what it depicts. The table is the rule, stated.
EXECUTION_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("texture", ("bobble", "bobbles", "cable", "cables", "cabled", "ribbed", "rib",
                 "textured", "texture", "relief", "puff", "popcorn", "pile", "waffle",
                 "bumps", "loops")),
    ("colour_relationship", ("stripe", "stripes", "striped", "band", "bands", "banding",
                             "colourwork", "colorwork", "contrast", "ombre", "gradient",
                             "blocked", "blocking")),
    ("scale", ("oversized", "giant", "tiny", "miniature", "mini", "huge", "chunky")),
    ("finish", ("edging", "edge", "trim", "button", "buttons", "border", "fringe", "tassel",
                "tassels", "pompom", "picot", "scallop", "scalloped")),
    ("structure", ("fold", "folds", "folded", "pocket", "pockets", "pleat", "yoke", "panel",
                   "panels", "unfold", "unfolds", "opens", "nest", "nests", "stack",
                   "stacks", "reversible", "transforms", "converts", "hood", "cuff",
                   "collar", "cropped", "silhouette", "shaped")),
)


def execution_of(concept: Concept) -> str:
    """Which part of the object delivers the feeling, read from the premise (#109)."""
    words = _WORD.findall((concept.premise or "").lower())
    motif_words = set(_specific(concept.motif))
    for word in words:
        if word in motif_words:
            return "motif"
        for execution, needles in EXECUTION_WORDS:
            if word in needles:
                return execution
    return "motif"


def promise_for(concept: Concept):
    """The concept's emotional promise and the physical thing that delivers it (#109).

    Raises `InventionRefused` when the premise is listing copy rather than an object -- the
    failure the requirement names ("cosy" achieved by writing *cosy*).
    """
    from .invention import promise

    return promise(concept.feeling, execution_of(concept), concept.premise)


def _emotional_promise(concept: Concept, brief: dict) -> dict:
    """#109: the promise must be visible in the object, not added as listing copy."""
    from .invention import InventionRefused

    try:
        made = promise_for(concept)
    except InventionRefused as exc:
        return _result(FAIL, [str(exc)], feeling=concept.feeling)
    return _result(PASS, **made.to_dict())


# #290: the occasions that are calendar events. A concept for one of these is a recurring
# seasonal product; anything else is evergreen unless it was translated from a trend, in
# which case the trend's own domain decides (a film moment is not a recurring season).
SEASONAL_OCCASIONS: frozenset[str] = frozenset({
    "christmas", "halloween", "easter", "valentines", "thanksgiving", "mothers_day",
    "fathers_day", "back_to_school", "graduation"})


def half_life_for(concept: Concept, brief: dict) -> dict:
    """The half-life class of this concept, with its basis (#290)."""
    from ..seasonal.fastlane import FastLaneRefused, classify_half_life

    domain = str(brief.get("trend_domain") or "").strip()
    try:
        if domain:
            return classify_half_life(domain=domain)
        if concept.occasion in SEASONAL_OCCASIONS:
            return classify_half_life(domain="", season=concept.occasion)
        return classify_half_life(domain="", evergreen=True)
    except FastLaneRefused as exc:
        return {"half_life": None, "basis": f"unclassified trend domain {domain!r}",
                "why": str(exc)}


def _half_life(concept: Concept, brief: dict) -> dict:
    """#290: no flagship engineering on a trend likely to expire before a maker finishes."""
    from ..seasonal.calendar import CalendarRefused, check_half_life

    got = half_life_for(concept, brief)
    if got.get("half_life") is None:
        return _result(FAIL, [got.get("why") or "an unclassified trend gets whatever effort "
                              "somebody felt like spending"], **got)
    try:
        check_half_life(got["half_life"], concept.make_lane)
    except CalendarRefused as exc:
        return _result(FAIL, [str(exc)], make_lane=concept.make_lane, **got)
    return _result(PASS, make_lane=concept.make_lane, **got)


def benchmarks_consulted(concept: Concept, brief: dict) -> list[str]:
    """Which benchmarks informed this concept, from the brief and the concept's lineage."""
    named = [str(b) for b in (brief.get("benchmarks_consulted") or []) if str(b).strip()]
    lineage = str(getattr(concept, "provenance", "") or "")
    if lineage.startswith("benchmark:") and lineage[len("benchmark:"):].strip():
        named.append(lineage[len("benchmark:"):].strip())
    return list(dict.fromkeys(named))


def _redesign(db, concept: Concept, brief: dict) -> dict:
    """F-791/F-794: a competitor-informed concept enters engineering only with a ledger that
    documents original design decisions materially distinguishing it from every benchmark
    consulted. A concept that consulted none is not competitor-informed and the check does
    not apply -- which is recorded, not passed."""
    from ..gates import originality

    consulted = benchmarks_consulted(concept, brief)
    if not consulted:
        return _result(NOT_APPLICABLE, ["no benchmark consulted"])
    entries = list(brief.get("design_difference_ledger") or [])
    source = "brief"
    if not entries and db is not None:
        entries = originality.ledger_from_db(db, concept.key)
        source = "database"
    if not entries:
        return _result(FAIL, [
            f"consulted {consulted} with no design-difference ledger: record what was "
            f"learned, what changed, why it is better and what was designed independently"],
            consulted=consulted)
    verdict = originality.redesign_verdict(entries, consulted)
    ledger = [e.to_dict() if isinstance(e, originality.LedgerEntry) else dict(e)
              for e in entries]
    return _result(PASS if verdict["passed"] else FAIL, verdict["reasons"][:6],
                   consulted=consulted, ledger=ledger, ledger_source=source,
                   per_benchmark=verdict["per_benchmark"])


# ---------------------------------------------------------------------------
# The gate


def gate_concept(db, concept, *, brief: dict | None = None, catalogue: list | None = None,
                 benchmark: list | None = None, today: date | None = None) -> dict:
    """Run the whole pre-engineering sequence on one concept. Deterministic; spends nothing.

    `concept` is a `Concept`, or a dict of Concept fields (optionally under "concept") plus
    brief fields (`BRIEF_FIELDS`, top level or under "brief"). Returns a verdict whose
    `engineer` is True only when every applicable check ran and passed.
    """
    today = today or date.today()
    built, found_brief, problem = concept_from(concept)
    brief = {**found_brief, **(brief or {})}
    key = (built.key if built else
           str((concept or {}).get("key") or (concept or {}).get("slug") or "")
           if isinstance(concept, dict) else "")
    checks: dict[str, dict] = {}
    if built is None:
        checks["premise_thumbnail"] = _result(FAIL, [problem])
        for name in CHECKS[1:]:
            checks[name] = _result(NOT_APPLICABLE, ["no concept to judge"])
    else:
        if catalogue is None:
            from .audit import briefed_catalogue_concepts

            # W4-CREATIVE: compare against the catalogue as the design process specifies it
            # (briefed where a valid brief exists), not the bare builder output whose every
            # product reads self/everyday/no-function.
            catalogue = [c for c in briefed_catalogue_concepts()[0] if c.key != built.key]
        checks["premise_thumbnail"] = _premise_thumbnail(built, brief)
        checks["jury"] = _jury(built, brief, catalogue, today)
        checks["novelty"] = _novelty(db, built, catalogue, benchmark)
        checks["silhouette"] = _silhouette(built, brief)
        checks["motif_grammar"] = _motif_grammar(built, brief)
        checks["wow"] = _wow(built, brief)
        checks["top_decile"] = _top_decile(built, brief, db)
        checks["grid_tournament"] = _grid(db, built, brief)
        checks["emotional_promise"] = _emotional_promise(built, brief)
        checks["half_life"] = _half_life(built, brief)
        checks["redesign"] = _redesign(db, built, brief)
        grid = checks["grid_tournament"]
        # C-60 (#126): an expensive concept with no board gets one -- rendered from its own
        # prototype's digital twin, deterministically -- so the grid can be requested.
        if (db is not None and grid["status"] == UNMEASURED
                and not grid["detail"].get("board_image")
                and not grid["detail"].get("recorded")):
            from .board import make_board

            board = make_board(db, built)
            if board.get("board_image"):
                brief = {**brief, "board_image": board["board_image"]}
                checks["grid_tournament"] = _grid(db, built, brief)
                checks["grid_tournament"]["detail"]["board"] = board
            else:
                grid["detail"]["board"] = board

    failed = [n for n in CHECKS if checks[n]["status"] == FAIL]
    unmeasured = [n for n in CHECKS if checks[n]["status"] == UNMEASURED]
    decision = REFUSED if failed else WAITING if unmeasured else PASSED
    reasons = [f"#{REQUIREMENT[n]} {n}: {r}" for n in failed for r in checks[n]["reasons"]]
    waiting_on = sorted({checks[n]["detail"].get("needs") for n in unmeasured} - {None})
    return {
        "concept": key,
        "decision": decision,
        "engineer": decision == PASSED,
        "failed": failed,
        "unmeasured": unmeasured,
        "reasons": reasons,
        "waiting_on": waiting_on,
        "checks": checks,
        "make_lane": built.make_lane if built else None,
        "pod": built.pod if built else None,
        "title": built.title if built else None,
        "skill_level": skill_level_for_make_lane(built.make_lane) if built else None,
        "consequence": (
            "engineered" if decision == PASSED else
            "not engineered: returned to creative development with these reasons"
            if decision == REFUSED else
            f"not engineered: waits, unpassed, until {waiting_on or unmeasured} can be "
            f"measured. Unmeasured is never passing"),
        "as_of": today.isoformat(),
    }


def _autopsy_reason(failed: list[str]) -> str:
    if "silhouette" in failed:
        return "silhouette"
    if failed == ["top_decile"]:
        return "floor"
    return "jury"


def record(ctx, verdict: dict, *, source: str) -> dict:
    """Write the verdict, and route a refused idea back to creative development.

    Every verdict is an audit row. A refusal also writes an autopsy (#127) -- which is what
    `standard.autopsy_patterns` reads when ideation asks what keeps dying -- and a
    `concept.returned_to_ideation` row carrying the reasons to fix. A waiting concept with a
    board image requests its grid tournament (#126) as a queued creative job.
    """
    key = verdict.get("concept") or ""
    summary = {k: verdict[k] for k in ("decision", "engineer", "failed", "unmeasured",
                                       "reasons", "waiting_on", "consequence", "make_lane",
                                       "skill_level", "as_of")}
    summary["source"] = source
    summary["checks"] = {n: {"status": c["status"], "reasons": c["reasons"][:3]}
                         for n, c in verdict["checks"].items()}
    ctx.audit(f"{GATE_ACTION}_{verdict['decision']}", artifact=key, detail=summary)
    effects: dict = {"audited": f"{GATE_ACTION}_{verdict['decision']}"}

    # F-794: a ledger that came with the brief is made durable, with the redesign gate's
    # reading of it, whatever the decision -- a refused ledger is the record of why.
    redesign = verdict["checks"].get("redesign", {}).get("detail", {})
    if redesign.get("ledger_source") == "brief" and redesign.get("ledger") and key:
        from ..gates import originality

        originality.record_ledger(ctx.db, key, redesign["ledger"])
        ctx.audit(originality.LEDGER_ACTION, artifact=key,
                  detail={"benchmarks": redesign.get("consulted"),
                          "passed": verdict["checks"]["redesign"]["status"] == PASS})
        effects["ledger_recorded"] = True

    if verdict["decision"] == REFUSED:
        from .standard import autopsy

        detail = "; ".join(verdict["reasons"])[:600] or "refused before engineering"
        if len(detail.split()) < 5:
            detail = f"refused before engineering by the gate: {detail}"
        effects["autopsy_id"] = autopsy(
            ctx.db, concept_key=key or "unnamed", cohort=f"pre-engineering:{source}",
            reason=_autopsy_reason(verdict["failed"]), detail=detail)
        ctx.audit(RETURNED_ACTION, artifact=key, detail={
            "source": source, "failed": verdict["failed"], "reasons": verdict["reasons"],
            "to": "creative development", "engineered": False})
        effects["returned_to_ideation"] = True

    grid = verdict["checks"].get("grid_tournament", {})
    if grid.get("detail", {}).get("request_grid"):
        from ..intel.pods import POD_KEYS, route

        pod = verdict.get("pod") or ""
        pod = pod if pod in POD_KEYS else route(verdict.get("title") or "")
        job = ctx.enqueue("creative_director", "creative.grid_tournament", {
            "concepts": [{"key": key, "board_image": grid["detail"]["board_image"],
                          "pod": pod}]},
            idempotency_key=f"grid:concept:{key}:{grid['detail']['board_image'][-32:]}")
        effects["grid_requested"] = job is not None
    return effects


# ---------------------------------------------------------------------------
# #114: skill level, and the wave it segments

# Nominal customer make hours per make lane, the same figures `seasonal.cycle` uses to chain
# a launch back from an event.
_LANE_HOURS: tuple[tuple[str, float], ...] = (
    ("QUICK", 3.0), ("SHORT", 8.0), ("MEDIUM", 20.0), ("LONG", 45.0), ("FLAGSHIP", 90.0))

_SKILL_OF_LANE: dict[str, str] = {
    "QUICK": "beginner_quick_win", "SHORT": "beginner_quick_win",
    "MEDIUM": "intermediate", "LONG": "advanced_heirloom", "FLAGSHIP": "advanced_heirloom",
}


def make_lane_for_hours(maker_hours: tuple[float, float]) -> str:
    """The make lane whose nominal hours are nearest the midpoint of a (fast, slow) range."""
    mid = (float(maker_hours[0]) + float(maker_hours[1])) / 2.0
    return min(_LANE_HOURS, key=lambda lane: abs(lane[1] - mid))[0]


def skill_level_for_make_lane(make_lane: str) -> str | None:
    """Skill level read from the commitment a make asks for. Deliberately coarse and stated:
    make time is the only measured proxy this company has for skill today."""
    return _SKILL_OF_LANE.get(make_lane)


def wave_skill_portfolio(seeds: list) -> dict:
    """#114 over a wave of radar seeds: the whole wave and each season within it."""
    from .universe import skill_portfolio

    rows = [(s.slug, s.season or "evergreen",
             skill_level_for_make_lane(make_lane_for_hours(s.maker_hours)))
            for s in seeds if not getattr(s, "is_bundle", False)]
    whole = skill_portfolio([level for _, _, level in rows])
    by_season = {}
    for season in sorted({season for _, season, _ in rows}):
        levels = [level for _, s, level in rows if s == season]
        if len(levels) >= 3:
            by_season[season] = skill_portfolio(levels)
    return {"wave": whole, "by_season": by_season,
            "levels": {slug: level for slug, _, level in rows},
            "basis": "make lane from the maker-hours midpoint; skill level from make lane"}


def missing_skill_levels(portfolio: dict) -> list[str]:
    return [g["level"] for g in portfolio.get("gaps") or [] if "want_at_least" in g]
