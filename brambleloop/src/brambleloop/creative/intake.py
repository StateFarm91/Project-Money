"""Winner intake: from a tournament winner to an engineering job, with nothing guessed (C-61).

The certification audit of 9434c53 found the original-design pipeline severed at its most
important joint. `creative.tournament` chose a winner, presented it to the pre-engineering
gate with no brief, and stopped: every winner failed "no thumbnail storyboard" (#88) and
"declared no motifs" (#110) by construction, every flagship failed "no WOW mechanism" (#115),
nothing asked the funnel whether the winner had been carried to prototype (#3), and nothing
ever queued `cir.draft`. The creative engine could only ever produce audit rows.

This module is that joint, and every field it produces is **derived by a stated rule from
the concept and the evidence in the database** -- never asked of a model, never a constant:

- the **thumbnail storyboard** (#88) is what the concept says the object is, framed the way
  this department's judged competitor photography frames its hero shots (#278), or the
  catalogue's own hero framing when no photograph has been judged;
- the **motifs** (#110) are the words of the concept that belong to its season's motif
  grammar, so a concept that names nothing from the grammar still fails -- honestly;
- the **WOW mechanism and its grounding** (#115) are read from the premise's own words and
  the construction, and a flagship whose words carry no mechanism still fails;
- the **emotional promise** (#109) is the premise delivering the feeling through a named
  part of the object, and a premise that is listing copy is refused;
- the **half-life** (#290), the **window at the real days to the event** (#112) and the
  **make time per maker skill** (#283) come from the calendar, the lead-time engine and the
  recorded physical tests;
- the **buyer language** (#293) is the six-facet map run against observed listings, with
  every phrase labelled observed or assumed.

Then, in order: the funnel is asked `may_engineer` (#3), the pre-engineering gate is run with
the brief, and only a winner that clears both is queued as `cir.draft`. A winner waiting on a
judgement only a vision model can make (#88's mobile-grid question, the jury's taste) waits
*unpassed*, and `regate_held` re-presents it on cadence the day a judgement is recorded.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

from .concept import GENERIC_TOKENS, Concept

INTAKE_ACTION = "creative.winner_intake"
# The contract a vision judge writes when it has looked at a concept board: the two fields
# `Concept` reserves for "a model that can look at an image" (`thumbnail_reads_small`,
# `craft_impression`) plus the judge's name. Nothing in this module writes it.
JUDGED_ACTION = "concept.judged"

ENGINEERING = "engineering"
WAITING = "waiting"
REFUSED = "refused"
NOT_CARRIED = "not_carried"

# How many held winners one cadence run re-presents, and how far back it looks.
REGATE_LIMIT = 20
REGATE_ROWS = 200

_WORD = re.compile(r"[a-z]+")

# What a buyer calls each form, for the storyboard and the facet map.
FORM_NOUN: dict[str, str] = {
    "flat_panel": "panel", "rectangle_throw": "throw", "round_disc": "round mat",
    "tube": "tube", "cone": "cone", "sphere": "ball", "basket": "basket",
    "fitted_garment": "cardigan", "draped_garment": "shawl", "stocking": "stocking",
    "ornament": "ornament", "bag": "bag", "hat": "hat", "scarf": "scarf",
    "pillow": "pillow", "wall_hanging": "wall hanging", "runner": "runner",
    "coaster": "coaster", "toy": "amigurumi", "wreath": "wreath", "garland": "garland",
    "pouch": "pouch",
}
# A fitted garment's noun is read from the concept's own words when it names one.
_GARMENT_WORDS = ("cardigan", "sweater", "pullover", "jumper", "vest", "top", "tee")

# Words that name a grammar motif without being spelled like it. Singular forms are handled
# by stripping a plural "s"; this table is for the rest.
MOTIF_SYNONYMS: dict[str, str] = {
    "snowflake": "snow", "snowy": "snow", "pine": "tree", "fir": "tree", "evergreen": "tree",
    "spruce": "tree", "deer": "reindeer", "cane": "candy", "peppermint": "candy",
    "ribbon": "bow", "bauble": "ornament", "forest": "woodland", "woods": "woodland",
    "gnome": "woodland", "stars": "star", "starry": "star", "leaves": "leaf",
    "autumn": "leaf", "toadstool": "mushroom", "gourd": "pumpkin", "haunted": "haunted_architecture",
    "mansion": "haunted_architecture", "castle": "haunted_architecture", "flower": "floral",
    "flowers": "floral", "blossom": "floral", "bloom": "floral", "bunny": "rabbit",
    "bunnies": "rabbit", "hare": "rabbit", "chickens": "chick", "garden": "garden_life",
    "seashell": "shell", "lemon": "citrus", "orange": "citrus", "boat": "sailboat",
    "wildflowers": "wildflower", "hedgehogs": "hedgehog", "foxes": "fox",
    "lanterns": "lantern", "candles": "candle", "bells": "bell", "sleighs": "sleigh",
    "wreaths": "wreath", "mittens": "mitten", "stockings": "stocking",
}

# The WOW mechanisms a premise can declare in its own words (#115), first match wins, then
# the construction's own mechanism. Every entry is a physical property of the object.
WOW_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("surprising_transformation", ("transforms", "becomes", "converts", "reversible",
                                   "unfolds", "reveals", "turns")),
    ("modular_reveal", ("modular", "assembles", "assembled", "joins", "panels")),
    ("unusual_but_useful_function", ("pocket", "pockets", "holds", "stores", "hides",
                                     "doubles")),
    ("personalization_architecture", ("name", "initial", "initials", "monogram",
                                      "personalised", "personalized")),
    ("strong_character_system", ("character", "characters", "face", "faces", "creature",
                                 "creatures")),
    ("collection_storytelling", ("collection", "series", "siblings")),
    ("dimensional_construction", ("dimensional", "sculpted", "sculptural", "standing")),
    ("exceptional_motif_composition", ("figures", "procession", "herd", "parade", "scene",
                                       "motif", "motifs")),
    ("striking_texture", ("bobble", "bobbles", "cable", "cables", "cabled", "textured",
                          "relief", "popcorn", "puff")),
    ("premium_silhouette", ("cropped", "silhouette", "sculpted", "balloon", "yoke")),
)
WOW_BY_CONSTRUCTION: dict[str, str] = {
    "modular_panels": "modular_reveal", "motif_join": "modular_reveal",
    "amigurumi_shaping": "dimensional_construction", "cable_panel": "striking_texture",
    "mosaic_overlay": "exceptional_motif_composition",
    "tapestry": "exceptional_motif_composition",
}
# The silhouette qualifier (#108) each WOW mechanism is visible as at thumbnail size.
QUALIFIER_OF_WOW: dict[str, str] = {
    "surprising_transformation": "transformation",
    "exceptional_motif_composition": "motif_composition",
    "striking_texture": "dimensional_texture",
    "dimensional_construction": "dimensional_texture",
    "unusual_but_useful_function": "unusual_function",
    "strong_character_system": "character_system",
    "modular_reveal": "modular_reveal",
}

# Technique words the jury's complexity critic counts (#83): each distinct one beyond the
# construction is one more thing a maker has to know.
TECHNIQUE_WORDS: frozenset[str] = frozenset({
    "bobble", "bobbles", "cable", "cables", "puff", "popcorn", "tapestry", "mosaic",
    "applique", "embroidery", "embroidered", "fringe", "intarsia", "beaded", "felted",
    "colourwork", "colorwork", "surface", "crossed"})

# #283: the maker skills the lead-time engine knows, and which one a skill level's pattern is
# planned for. A beginner pattern is made by beginners, and a beginner needs longer.
MAKER_SKILLS: tuple[str, ...] = ("beginner", "adventurous_beginner", "intermediate",
                                 "experienced")
MAKER_SKILL_OF_LEVEL: dict[str, str] = {
    "beginner_quick_win": "beginner", "intermediate": "intermediate",
    "advanced_heirloom": "experienced",
}

# #278: the judged observation fields a concept brief can learn from. Each is a judgement
# about how an offer is built to sell, never about what a competitor's product depicts.
VISION_FIELDS: tuple[str, ...] = (
    "silhouette_strength", "motif_legibility", "transformation", "characterisation",
    "collection_logic", "surprising_function", "palette_role", "thumbnail_readability",
    "emotional_merchandising", "scale_communication")


class IntakeRefused(ValueError):
    """A winner that cannot be presented to engineering at all."""


def _words(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def _specific(text: str) -> list[str]:
    return [w for w in _words(text) if w not in GENERIC_TOKENS]


def _slugify(text: str, limit: int = 48) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (text or "").lower())).strip("-")[:limit]


def design_slug(concept: Concept) -> str:
    """A stable, unique name for the winning design.

    Tournament keys (`t3-hats-hat-0`) repeat across runs and name a slot, not a design; a
    CIR, a product row and a provenance record need the design itself. The title for a human
    and a digest of everything that makes the idea this idea, so the same concept always
    gets the same slug and a different one never does.
    """
    digest = hashlib.sha1("|".join((
        concept.title, concept.premise, concept.pod, concept.form, concept.construction,
        concept.motif, concept.recipient, concept.occasion, concept.function,
        concept.make_lane)).encode()).hexdigest()[:8]
    return f"{_slugify(concept.title, 40) or 'design'}-{digest}"


# ---------------------------------------------------------------------------
# Evidence readers


def vision_readings(db, pod: str) -> dict:
    """#278: what this department's judged competitor photography shows.

    Read from `gallery_image_observation` rows (recorded only when a model actually looked
    at the image). With none, the state is UNMEASURED and nothing is invented.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing, BenchmarkObservation

    with db.session() as s:
        refs = {(r.benchmark_key, r.listing_ref) for r in s.scalars(
            select(BenchmarkListing).where(BenchmarkListing.pod == pod))}
        rows = [(r.benchmark_key, r.listing_ref, dict(r.detail or {})) for r in s.scalars(
            select(BenchmarkObservation).where(
                BenchmarkObservation.kind == "gallery_image_observation"))]
    observations = [(ref, (d.get("observation") or {})) for key, ref, d in rows
                    if (key, ref) in refs]
    if not observations:
        return {"pod": pod, "judged_images": 0, "listings": 0, "attributes": {},
                "shot_types": {}, "dominant_shot": None,
                "state": ("UNMEASURED: no competitor photograph in this department has been "
                          "judged, so no photographic evidence reaches the brief")}
    shots: dict[str, int] = {}
    attributes: dict[str, list[str]] = {}
    for _ref, obs in observations:
        shot = str(obs.get("shot_type") or "").strip()
        if shot:
            shots[shot] = shots.get(shot, 0) + 1
        for name in VISION_FIELDS:
            value = str(obs.get(name) or "").strip()
            if value and value not in attributes.setdefault(name, []):
                attributes[name].append(value[:80])
    dominant = max(sorted(shots), key=lambda k: shots[k]) if shots else None
    return {"pod": pod, "judged_images": len(observations),
            "listings": len({ref for ref, _ in observations}),
            "attributes": {k: v[:5] for k, v in attributes.items() if v},
            "shot_types": dict(sorted(shots.items(), key=lambda kv: -kv[1])),
            "dominant_shot": dominant,
            "state": f"{len(observations)} judged image(s) in this department"}


def judgement_for(db, key: str) -> dict | None:
    """The vision judgements recorded about this design, or None when nobody has looked.

    Two sources, both written only by a model that looked at an image: the blind search
    grid's verdict on the concept board (#126: a `clear` means it holds its own at grid
    size) and a `concept.judged` row carrying the taste fields and the judge's name. A row
    without a named judge is not a judgement.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from .preengineering import grid_verdict_for

    out: dict = {"sources": []}
    grid = grid_verdict_for(db, key)
    if grid and grid.get("verdict") == "clear":
        out["thumbnail_reads_small"] = True
        out["sources"].append(f"creative.grid_tournament row {grid.get('audit_id')}")
    elif grid and grid.get("below_threshold"):
        out["thumbnail_reads_small"] = False
        out["sources"].append(f"creative.grid_tournament row {grid.get('audit_id')}")
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == JUDGED_ACTION,
                                              AuditLog.artifact == key)
                       .order_by(desc(AuditLog.id)).limit(1))
        detail = dict(row.detail or {}) if row is not None else {}
        row_id = row.id if row is not None else None
    # CB2-D01: a judgement is about one board's bytes. It counts only while the board on
    # file is the board that was judged, by content digest; a re-rendered board, a board
    # whose bytes cannot be identified, or a row that never recorded which bytes it saw is
    # UNKNOWN -- never the old verdict carried onto a picture nobody looked at.
    judged_sha = str(detail.get("board_sha256") or "").strip().lower()
    current_sha = board_digest_for(db, key)
    if detail and (not judged_sha or not current_sha or judged_sha != current_sha):
        detail = {}
    if detail and str(detail.get("judge") or "").strip():
        if isinstance(detail.get("thumbnail_reads_small"), bool) \
                and "thumbnail_reads_small" not in out:
            out["thumbnail_reads_small"] = detail["thumbnail_reads_small"]
        if isinstance(detail.get("craft_impression"), (int, float)):
            out["craft_impression"] = float(detail["craft_impression"])
        out["sources"].append(f"{JUDGED_ACTION} row {row_id} by {detail['judge']}")
    return out if out["sources"] else None


def culture_domain(db, culture_id: int | None) -> str:
    """The trend domain a culture-derived winner came from (#290), or "" for none."""
    if not culture_id:
        return ""
    from sqlalchemy import select

    from ..core.models import CultureConcept, CultureSignal

    with db.session() as s:
        cc = s.get(CultureConcept, int(culture_id))
        if cc is None:
            return ""
        sig = s.scalar(select(CultureSignal).where(CultureSignal.key == cc.signal_key))
        return (sig.domain or "") if sig is not None else ""


# ---------------------------------------------------------------------------
# The brief, one rule per field


def season_of(concept: Concept, event: str = "") -> str | None:
    from ..seasonal.remerchandising import MOTIF_SEASON
    from .preengineering import GRAMMAR_SEASON

    return GRAMMAR_SEASON.get(concept.occasion) or MOTIF_SEASON.get(event) or None


def motifs_for(concept: Concept, season: str | None) -> list[str]:
    """#110: the concept's own words that belong to its season's motif grammar, in order."""
    from .invention import MOTIF_GRAMMAR

    if not season or season not in MOTIF_GRAMMAR:
        return []
    grammar = set(MOTIF_GRAMMAR[season])
    text = " ".join((concept.motif, concept.title, concept.premise)).lower()
    words = _words(text)
    found: list[str] = []
    candidates = []
    for i, w in enumerate(words):
        candidates.append(w)
        if i + 1 < len(words):
            candidates.append(f"{w}_{words[i + 1]}")
    for w in candidates:
        for form in (w, MOTIF_SYNONYMS.get(w, ""), w[:-1] if w.endswith("s") else ""):
            if form and form in grammar and form not in found:
                found.append(form)
                break
    return found


def wow_for(concept: Concept) -> tuple[str | None, str]:
    """#115: the WOW mechanism the concept's own words or construction carry, and its basis."""
    words = set(_words(concept.premise)) | set(_words(concept.title))
    for mechanism, needles in WOW_WORDS:
        hit = sorted(words & set(needles))
        if hit:
            return mechanism, f"the premise names {', '.join(hit)}"
    mechanism = WOW_BY_CONSTRUCTION.get(concept.construction)
    if mechanism:
        return mechanism, f"the {concept.construction.replace('_', ' ')} construction"
    return None, ""


def storyboard_for(concept: Concept, vision: dict | None) -> str:
    """#88: what the square mobile-grid thumbnail shows, derived from the concept.

    Framed the way this department's judged competitor photography frames its hero shots
    when any has been judged (#278); otherwise as the catalogue's own hero product shot.
    """
    noun = noun_for(concept)
    shot = ((vision or {}).get("dominant_shot") or "hero_product_only").replace("_", " ")
    palette = concept.palette_story.strip()
    return (f"{shot} square crop: one {noun} fills the frame, the {concept.motif} reading as "
            f"its focal shape in {palette}, {concept.construction.replace('_', ' ')} "
            f"construction visible; {concept.premise.strip().rstrip('.')}")


def noun_for(concept: Concept) -> str:
    if concept.form == "fitted_garment":
        for w in _words(f"{concept.title} {concept.premise}"):
            if w in _GARMENT_WORDS:
                return w
    return FORM_NOUN.get(concept.form, concept.form.replace("_", " "))


def techniques_for(concept: Concept) -> int:
    words = set(_words(f"{concept.premise} {concept.motif}"))
    return 1 + len(words & TECHNIQUE_WORDS)


def make_time_for(db, concept: Concept, *, event: str, event_date: date | None,
                  today: date) -> dict:
    """#283: make time per maker skill, and the launch dates for the skill it is written for.

    Hours are the lane's nominal hours (the same table `seasonal.cycle` uses) until a CIR's
    own twin replaces them; the interval narrows only with recorded physical tests.
    """
    from ..seasonal.leadtime import compile_launch, effective_make_days
    from ..seasonal.uncertainty import sample_count
    from .preengineering import _LANE_HOURS, skill_level_for_make_lane

    hours = dict(_LANE_HOURS)[concept.make_lane]
    level = skill_level_for_make_lane(concept.make_lane)
    target = MAKER_SKILL_OF_LEVEL.get(level or "", "intermediate")
    samples = sample_count(db)
    by_skill = {skill: {"effective_make_days": effective_make_days(hours, skill)}
                for skill in MAKER_SKILLS}
    out = {"make_hours": hours, "make_hours_basis": "the make lane's nominal hours; the CIR "
           "twin replaces them once a pattern exists", "skill_level": level,
           "planned_for_skill": target, "samples": samples, "by_skill": by_skill,
           "plan": None}
    if event_date is None:
        out["why_no_plan"] = f"{concept.occasion} names no calendar event: no launch deadline"
        return out
    for skill in MAKER_SKILLS:
        plan = compile_launch(event or concept.occasion, event_date, make_hours=hours,
                              skill=skill, samples=samples)
        by_skill[skill].update({"latest_effective_launch":
                                plan.latest_effective_launch.isoformat(),
                                "status": plan.status(today)})
    plan = compile_launch(event or concept.occasion, event_date, make_hours=hours,
                          skill=target, samples=samples)
    action, why = plan.recommendation(today)
    out["plan"] = {"event": event, "event_date": event_date.isoformat(),
                   "skill": target, "status": plan.status(today),
                   "preferred_launch": plan.preferred_launch.isoformat(),
                   "latest_effective_launch": plan.latest_effective_launch.isoformat(),
                   "work_must_start_by": plan.work_must_start_by.isoformat(),
                   "recommendation": action, "because": why}
    return out


def buyer_language(db, concept: Concept, *, event: str, skill_level: str | None) -> dict:
    """#293: the product mapped to buyer facets, and which phrases buyers were seen using."""
    from ..commerce import intent

    facets = {"object": noun_for(concept),
              "technique": ENGINE_TECHNIQUE.get(concept.construction, ""),
              "recipient_or_use": RECIPIENT_USE.get(concept.recipient, ""),
              "season_event": (event or concept.occasion).split(" (")[0].replace("'s", "")
              .replace("_", " ").lower(),
              "skill_feature": "beginner" if skill_level == "beginner_quick_win" else ""}
    try:
        mapped = intent.map_product(**{k: v for k, v in facets.items() if v})
    except intent.IntentRefused as exc:
        return {"mapped": False, "facets": facets, "why": str(exc)[:300]}
    got = intent.strategy(db, facet_map=mapped)
    return {"mapped": True, "facets": mapped,
            "observed": [r["phrase"] for r in got["observed"]],
            "assumed": [r["phrase"] for r in got["assumed"]],
            "observed_share": got["observed_share"], "note": got["note"]}


ENGINE_TECHNIQUE: dict[str, str] = {
    "tapestry": "tapestry", "mosaic_overlay": "mosaic", "cable_panel": "cable",
    "granny_square": "granny square", "corner_to_corner": "c2c",
    "amigurumi_shaping": "amigurumi", "top_down_yoke": "top down",
    "seamless_tube": "seamless",
}
RECIPIENT_USE: dict[str, str] = {
    "self": "women", "partner": "gift", "new_parent": "baby", "child": "kids",
    "teen": "teen", "grandparent": "gift", "host": "hostess gift", "pet_owner": "pet",
    "colleague": "gift", "teacher": "teacher gift", "friend_who_has_everything": "gift",
    "newlyweds": "wedding gift", "student": "gift",
}


def brief_for(db, concept: Concept, *, event: str = "", event_date: date | None = None,
              days_to_event: int | None = None, vision: dict | None = None,
              trend_domain: str = "", today: date | None = None) -> dict:
    """Every brief field the pre-engineering gate reads, each derived by a stated rule."""
    from .family import FamilyRefused, window_fit
    from .invention import InventionRefused
    from .preengineering import (half_life_for, promise_for, skill_level_for_make_lane)

    today = today or date.today()
    season = season_of(concept, event)
    mechanism, wow_basis = wow_for(concept)
    grounding = " ".join(w for w in _specific(concept.premise))
    qualifiers = sorted({QUALIFIER_OF_WOW[m] for m, needles in WOW_WORDS
                         if m in QUALIFIER_OF_WOW
                         and set(_words(concept.premise)) & set(needles)}
                        | ({QUALIFIER_OF_WOW[WOW_BY_CONSTRUCTION[concept.construction]]}
                           if concept.construction in WOW_BY_CONSTRUCTION
                           and WOW_BY_CONSTRUCTION[concept.construction] in QUALIFIER_OF_WOW
                           else set()))
    level = skill_level_for_make_lane(concept.make_lane)
    make_time = make_time_for(db, concept, event=event, event_date=event_date, today=today)
    try:
        promise = promise_for(concept).to_dict()
    except InventionRefused as exc:
        promise = {"refused": str(exc)[:300]}
    brief = {
        "thumbnail_storyboard": storyboard_for(concept, vision),
        "motifs": motifs_for(concept, season),
        "season": season,
        "wow_mechanism": mechanism,
        "wow_grounding": grounding if mechanism else "",
        "silhouette_qualifiers": qualifiers,
        "techniques": techniques_for(concept),
        "trend_domain": trend_domain or "",
    }
    window = {}
    if days_to_event is not None and days_to_event >= 0:
        for skill in MAKER_SKILLS:
            try:
                fit = window_fit(concept, days_to_event=days_to_event, skill=skill,
                                 samples=make_time["samples"], today=today)
                window[skill] = {"verdict": fit["verdict"],
                                 "latest_optimistic_launch": fit["latest_optimistic_launch"]}
            except FamilyRefused as exc:
                window[skill] = {"verdict": "unknown", "why": str(exc)[:200]}
    derivation = {
        "storyboard": ("framed as this department's judged competitor hero shots"
                       if (vision or {}).get("dominant_shot") else
                       "framed as a hero product shot: no competitor photograph in this "
                       "department has been judged"),
        "motifs": f"the concept's words found in the {season} motif grammar" if season
        else "no seasonal grammar applies to this occasion",
        "wow": wow_basis or "no mechanism named by the premise or the construction",
    }
    return {**brief, "skill_level": level, "promise": promise,
            "half_life": half_life_for(concept, brief), "make_time": make_time,
            "days_to_event": days_to_event, "window_by_skill": window,
            "vision": {k: (vision or {}).get(k) for k in ("judged_images", "dominant_shot",
                                                          "state")},
            "buyer_language": buyer_language(db, concept, event=event, skill_level=level),
            "derivation": derivation}


GATE_BRIEF_FIELDS: tuple[str, ...] = (
    "thumbnail_storyboard", "motifs", "season", "wow_mechanism", "wow_grounding",
    "silhouette_qualifiers", "techniques", "trend_domain",
    "benchmarks_consulted", "design_difference_ledger", "source_context")


# ---------------------------------------------------------------------------
# #3: the funnel, asked about this exact run


def tournament_from_rounds(rounds: list[dict]):
    from .funnel import Round, Tournament

    return Tournament(opportunity="recorded run", rounds=[
        Round(stage=r["stage"], entered=int(r.get("entered") or 0),
              survived=list(r.get("survived") or []), killed=dict(r.get("killed") or {}),
              examined=r.get("examined")) for r in rounds or []])


def funnel_verdict(rounds: list[dict] | None, key: str) -> dict:
    """`funnel.may_engineer` on the recorded run: was this concept carried to prototype?"""
    from .funnel import FunnelRefused, may_engineer

    if rounds is None:
        return {"carried": False, "stage_reached": None,
                "why": ("this winner came from an expedition, which is discovery rather than "
                        "the staged funnel; nothing reaches engineering without the funnel "
                        "carrying it to prototype (#3)")}
    run = tournament_from_rounds(rounds)
    try:
        may_engineer(run, key)
    except FunnelRefused as exc:
        return {"carried": False, "stage_reached": run.stage_reached, "why": str(exc)}
    return {"carried": True, "stage_reached": run.stage_reached,
            "why": f"{key} survived the prototype stage of this run"}


# ---------------------------------------------------------------------------
# The intake


def _event_for(concept: Concept, arena, today: date) -> tuple[str, date | None, int | None]:
    from datetime import timedelta

    from .preengineering import _EVENT_OF_OCCASION, _days_to_event
    from .prospecting import EVENT_OCCASION

    if arena is not None and EVENT_OCCASION.get(arena.event) == concept.occasion:
        return arena.event, today + timedelta(days=arena.days_away), arena.days_away
    days = _days_to_event(concept.occasion, today)
    if days is None:
        return "", None, None
    return _EVENT_OF_OCCASION.get(concept.occasion, ""), today + timedelta(days=days), days


def coverage_origin(db, *, event_id, pod: str, product_slug: str,
                    candidate_key: str, job_id=None) -> dict | None:
    """Bind a candidate to the exact mission-produced gap; absent lineage stays unknown."""
    from ..core.models import CoverageGap, MjsMissionEvent

    if not event_id or not candidate_key or not product_slug:
        return None
    with db.session() as s:
        ev = s.get(MjsMissionEvent, event_id)
        if ev is None or ev.pod != pod or not ev.tournament_job_id:
            return None
        if job_id is not None and ev.tournament_job_id != job_id:
            return None
        steps = ev.steps if isinstance(ev.steps, dict) else {}
        coverage_step = steps.get("coverage")
        if not isinstance(coverage_step, dict):
            return None
        recorded = coverage_step.get("origin")
        gap = s.get(CoverageGap, ev.gap_id) if ev.gap_id else None
        if gap is None or gap.pod != pod or gap.benchmark_key != ev.benchmark_key:
            return None
        expected = {"gap_id": gap.id, "benchmark_key": gap.benchmark_key,
                    "coverage_arena": gap.arena, "pod": pod,
                    "event_id": ev.id, "event_fingerprint": ev.fingerprint}
        if not ev.fingerprint or recorded != expected:
            return None
        if gap.product_slug and gap.product_slug != product_slug:
            return None
        return {**expected, "candidate_key": candidate_key,
                "product_slug": product_slug, "mission_arena": ev.arena,
                "tournament_job_id": ev.tournament_job_id}


def brief_coverage_origin(brief) -> dict | None:
    """Malformed persisted provenance is unknown, including during re-presentation."""
    context = brief.get("source_context") if isinstance(brief, dict) else None
    origin = context.get("coverage_origin") if isinstance(context, dict) else None
    return origin if isinstance(origin, dict) else None


def advance_gap(db, pod: str, to: str, *, reason: str, product_slug: str = "",
                origin: dict | None = None, event_id=None, candidate_key: str = "") -> dict:
    """Advance only a validated origin, with identity and mutation in one transaction."""
    from sqlalchemy import select, update, exists, cast, String, JSON, literal
    from ..core.models import CoverageGap, MjsMissionEvent, utcnow
    from ..intel import coverage

    unknown = {"gap": None, "moved": False, "verdict": "UNKNOWN",
               "why": "missing or inconsistent exact coverage origin"}
    if (not isinstance(origin, dict) or not event_id or not candidate_key
            or origin.get("event_id") != event_id
            or origin.get("candidate_key") != candidate_key):
        return unknown
    expected = coverage_origin(db, event_id=origin.get("event_id"), pod=pod,
                              product_slug=product_slug,
                              candidate_key=origin.get("candidate_key", ""))
    if expected is None or origin != expected:
        return unknown
    order = list(coverage.STATES[:6])
    with db.session() as s:
        ev = s.scalar(select(MjsMissionEvent).where(
            MjsMissionEvent.id == origin["event_id"]).with_for_update())
        gap = s.scalar(select(CoverageGap).where(CoverageGap.id == origin["gap_id"])
                       .with_for_update())
        producer_origin = {key: origin[key] for key in (
            "gap_id", "benchmark_key", "coverage_arena", "pod", "event_id",
            "event_fingerprint")}
        # Recheck identity inside the transaction; never overwrite another product's binding.
        if (gap is None or ev is None or ev.gap_id != gap.id
                or ev.fingerprint != origin["event_fingerprint"]
                or ev.pod != pod or ev.benchmark_key != origin["benchmark_key"]
                or ev.arena != origin["mission_arena"]
                or ev.tournament_job_id != origin["tournament_job_id"]
                or not isinstance(ev.steps, dict)
                or not isinstance(ev.steps.get("coverage"), dict)
                or ev.steps["coverage"].get("origin") != producer_origin
                or gap.pod != pod or gap.benchmark_key != origin["benchmark_key"]
                or gap.arena != origin["coverage_arena"]
                or (gap.product_slug and gap.product_slug != product_slug)):
            return unknown
        state = gap.state
        if state not in order or to not in order or order.index(to) <= order.index(state):
            return {"gap": gap.id, "state": state, "moved": False}
        moves = order[order.index(state) + 1:order.index(to) + 1]
        for next_state in moves:
            coverage.check_transition(state, next_state, reason)
            state = next_state
        # Conditional write also protects SQLite, whose FOR UPDATE is a no-op.
        changed = s.execute(update(CoverageGap).where(
            CoverageGap.id == gap.id, CoverageGap.state == gap.state,
            CoverageGap.product_slug == gap.product_slug,
            CoverageGap.pod == pod, CoverageGap.benchmark_key == origin["benchmark_key"],
            CoverageGap.arena == origin["coverage_arena"],
            exists(select(MjsMissionEvent.id).where(
                MjsMissionEvent.id == origin["event_id"],
                MjsMissionEvent.gap_id == origin["gap_id"],
                MjsMissionEvent.pod == pod,
                MjsMissionEvent.benchmark_key == origin["benchmark_key"],
                MjsMissionEvent.arena == origin["mission_arena"],
                MjsMissionEvent.fingerprint == origin["event_fingerprint"],
                MjsMissionEvent.tournament_job_id == origin["tournament_job_id"],
                cast(MjsMissionEvent.steps, String) == cast(literal(ev.steps, type_=JSON), String)))
        ).values(state=state, product_slug=product_slug, reason=reason,
                 updated_at=utcnow()).execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            return unknown
        return {"gap": gap.id, "state": state, "moved": True, "moves": moves}


def _payload(designed: Concept, brief: dict, *, source: str, original_key: str,
             mjs_event_id, pod: str) -> dict:
    return {"slug": designed.key, "title": designed.title, "version": "1.0.0",
            "concept": designed.to_dict(),
            "brief": {k: brief.get(k) for k in GATE_BRIEF_FIELDS},
            "funnel": {"key": original_key, "intake": INTAKE_ACTION},
            "source": source, "pod": pod, "mjs_event_id": mjs_event_id}


def intake(ctx, *, candidate, plan: dict, source: str, arena=None,
           funnel_rounds: list[dict] | None = None, mjs_event_id: int | None = None,
           culture_id: int | None = None, today: date | None = None) -> dict:
    """Take one winner as far toward engineering as the evidence allows, and record why."""
    from . import ideation

    db = ctx.db
    today = today or date.today()
    concept: Concept = candidate.concept
    original_key = concept.key
    slug = design_slug(concept)
    # The run's source belongs in the intake record, not over the original lineage.
    designed = replace(concept, key=slug)
    judged = judgement_for(db, slug)
    if judged:
        designed = replace(designed, **{k: judged[k] for k in ("thumbnail_reads_small",
                                                                "craft_impression")
                                        if k in judged})
    event, event_date, days = _event_for(designed, arena, today)
    brief = brief_for(db, designed, event=event, event_date=event_date, days_to_event=days,
                      vision=plan.get("vision"), trend_domain=culture_domain(db, culture_id),
                      today=today)
    supplied = plan.get("brief") or {}
    if not isinstance(supplied, dict):
        raise ValueError("source brief must be an object; provenance UNKNOWN")
    for field in ("benchmarks_consulted", "design_difference_ledger", "source_context"):
        if field in supplied:
            brief[field] = supplied[field]
    origin = coverage_origin(db, event_id=mjs_event_id, pod=designed.pod,
                             product_slug=slug, candidate_key=original_key,
                             job_id=ctx.job.id)
    context = brief.get("source_context") or {}
    if not isinstance(context, dict):
        origin = None
    elif "coverage_origin" in context and context["coverage_origin"] != origin:
        origin = None
    if isinstance(context, dict):
        brief["source_context"] = {**context, "coverage_origin": origin}
    from .prototype import source_provenance
    lineage_record = source_provenance(designed.key, designed.to_dict(), brief,
                                       ("creative.intake",))
    if lineage_record is not None:
        brief["benchmarks_consulted"] = list(lineage_record.benchmarks_consulted)
    funnel = funnel_verdict(funnel_rounds, original_key)
    gate = ideation.pre_engineering_gate(
        db, SimpleNamespace(concept=designed), ctx=ctx, source=source,
        brief={k: brief.get(k) for k in GATE_BRIEF_FIELDS})
    verdict = gate.get("verdict") or {}
    decision = (REFUSED if verdict.get("decision") == "refused" or gate.get("error") else
                NOT_CARRIED if not funnel["carried"] else
                ENGINEERING if gate.get("cleared_for_engineering") else WAITING)

    # #101: the provenance of the winning design, keyed on the design rather than the run.
    from ..improve import roi

    lesson_ids = tuple((plan.get("lessons") or {}).get("lesson_ids") or ())
    try:
        provenance = roi.design_provenance(db, product_slug=slug, lesson_ids=lesson_ids,
                                           brief=f"winner of {source} ({original_key})")
    except roi.RoiRefused as exc:
        provenance = {"refused": str(exc)[:200]}

    pod = designed.pod
    gap = advance_gap(db, pod, "concepting", origin=origin, product_slug=slug,
                      event_id=mjs_event_id, candidate_key=original_key,
                      reason=f"{source} selected {slug} for this department")
    lesson = response_lesson(db, pod=pod, event=event or designed.occasion,
                             noun=noun_for(designed), slug=slug, mjs_event_id=mjs_event_id)

    payload = _payload(designed, brief, source=source, original_key=original_key,
                       mjs_event_id=mjs_event_id, pod=pod)
    detail = {
        "decision": decision, "source": source, "original_key": original_key,
        "concept": designed.to_dict(), "brief": brief, "funnel": funnel,
        # #111 / #308: a single product is engineered as one; nothing derives a collection
        # from it. Recorded here so the record says what the proposition stage decided.
        "carried_as": getattr(candidate, "carried_as", "") or "",
        "family_verdict": getattr(candidate, "family_verdict", "") or "",
        "funnel_rounds": funnel_rounds or [],
        "gate": {k: verdict.get(k) for k in ("decision", "failed", "unmeasured",
                                              "waiting_on", "reasons")},
        "judgement": judged, "mjs_event_id": mjs_event_id, "culture_id": culture_id,
        "provenance": provenance, "coverage": gap, "pod_lesson": lesson,
        "payload": payload, "job": ctx.job.id,
    }
    ctx.audit(INTAKE_ACTION, artifact=slug, detail=detail)
    job = None
    if decision == ENGINEERING:
        job = ctx.enqueue("crochet_engineer", "cir.draft", payload,
                          idempotency_key=f"draft:{slug}")
        detail["coverage"] = advance_gap(db, pod, "engineering", origin=origin,
                                         event_id=mjs_event_id, candidate_key=original_key,
                                         reason=f"{slug} cleared the funnel and the "
                                                f"pre-engineering gate; cir.draft queued",
                                         product_slug=slug)
    return {"slug": slug, "decision": decision, "funnel": funnel["carried"],
            "gate_call": gate,
            "gate": verdict.get("decision"), "waiting_on": verdict.get("waiting_on"),
            "cir_draft_job": getattr(job, "id", None), "motifs": brief["motifs"],
            "wow_mechanism": brief["wow_mechanism"], "skill_level": brief["skill_level"],
            "days_to_event": days, "coverage": detail["coverage"],
            "why": (funnel["why"] if decision == NOT_CARRIED else
                    "; ".join(verdict.get("reasons") or [])[:400] if decision == REFUSED else
                    f"waiting, unpassed, on {verdict.get('waiting_on')}"
                    if decision == WAITING else "queued for engineering")}


def intake_rows(db, *, slug: str | None = None, mjs_event_id: int | None = None,
                limit: int = REGATE_ROWS) -> list[tuple[int, str, dict]]:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    q = select(AuditLog).where(AuditLog.action == INTAKE_ACTION)
    if slug:
        q = q.where(AuditLog.artifact == slug)
    with db.session() as s:
        rows = [(r.id, r.artifact or "", dict(r.detail or {}))
                for r in s.scalars(q.order_by(desc(AuditLog.id)).limit(limit))]
    if mjs_event_id is not None:
        rows = [r for r in rows if r[2].get("mjs_event_id") == mjs_event_id]
    return rows


def verify_funnel(db, slug: str) -> dict:
    """What `cir.draft` asks before drafting a new creative concept (#3)."""
    rows = intake_rows(db, slug=slug, limit=5)
    if not rows:
        return {"carried": False, "why": (f"{slug} has no winner intake: a concept reaches "
                                          f"engineering only as a tournament winner (#3)")}
    _id, _slug, detail = rows[0]
    got = funnel_verdict(detail.get("funnel_rounds") or None, detail.get("original_key", ""))
    return {**got, "intake_row": _id}


# ---------------------------------------------------------------------------
# The judgement a held winner waits on, produced the day its two inputs exist
#
# A winner waits on `image_vision`: whether its board reads at mobile-grid size (#88) and how
# its craftsmanship reads (#83's taste question). Both are judgements about a picture, so
# both need a picture of the concept -- a board `listing_asset` files for the design, which
# is Product-Only Visual V1 image generation (external) -- and a vision model that has been
# probed as actually working (`gateway.anthropic.vision_usable`, model_provider). Neither is
# invented here: with no board or no working vision model the winner stays WAITING and this
# says which of the two it waits on. The day both exist, the cadence that calls
# `regate_held` asks the judge, records `concept.judged` with the judge's name, and the
# winner is re-presented in the same run.

JUDGE_TASK = "gallery_observation"   # the vision tier the search-grid tournament also uses
JUDGE_MAX_TOKENS = 200
JUDGE_SYSTEM = ("You are judging one crochet concept board for a premium pattern shop. Answer "
                "only about how this board reads as an image. Never describe or compare any "
                "other seller's product.")
JUDGE_PROMPT = (
    "With the seller name, reviews, badges and price removed, would this product idea itself "
    "still create curiosity or desire at mobile-grid thumbnail size? Then rate the apparent "
    "craftsmanship of the object shown from 1.0 (crude) to 5.0 (premium). Answer with exactly "
    "one JSON object and nothing else: "
    '{"thumbnail_reads_small": true or false, "craft_impression": number}')


class JudgeRefused(ValueError):
    """A vision answer that is not a judgement."""


def board_for(db, slug: str) -> str:
    """The concept board on file for this design, or "" when none has been rendered.

    Read from the record `listing_asset` files when a render is made, so a board produced by
    the owned-photography path is found by the design's slug and nothing else has to know
    where images live.
    """
    from ..publish import listing_asset

    for frame in listing_asset.frames_for(db, slug=slug):
        ref = str(frame.get("image_ref") or frame.get("image") or "").strip()
        if ref:
            return ref
    # W4-PIPE2: an engineered candidate's concept board (products.moment_candidates).
    from ..products.moment_candidates import board_record

    record = board_record(db, slug) or {}
    return str(record.get("image_ref") or "").strip()


def _sha256_hex(value) -> str:
    text = str(value or "").strip().lower()
    return text if len(text) == 64 and all(c in "0123456789abcdef" for c in text) else ""


def board_digest_for(db, slug: str) -> str:
    """The SHA-256 of the concept board's bytes on file for this design, or "" (CB2-D01).

    Taken from the digest the artefact store recorded when the render was kept, or from the
    bytes themselves when the reference is a readable local file. A board known only by a
    URL or a path that no longer exists has no identifiable content, and returns "" -- so
    no judgement can be bound to it, which is the fail-closed answer.
    """
    import hashlib
    from pathlib import Path

    from ..publish import listing_asset

    for frame in listing_asset.frames_for(db, slug=slug):
        ref = str(frame.get("image_ref") or "").strip()
        image = frame.get("image")
        if not ref and isinstance(image, str):
            ref = image.strip()
        if not ref:
            continue
        stored = _sha256_hex(image.get("sha256")) if isinstance(image, dict) else ""
        if stored:
            return stored
        try:
            path = Path(ref)
            if path.is_file():
                return hashlib.sha256(path.read_bytes()).hexdigest()
        except (OSError, ValueError):
            pass
        return ""
    # W4-PIPE2: the digest the artefact store recorded for an engineered candidate's board.
    from ..products.moment_candidates import board_record

    return _sha256_hex(((board_record(db, slug) or {}).get("image") or {}).get("sha256"))


def parse_judgement(text: str) -> dict:
    """The judge's answer as the two fields `Concept` reserves for a model with eyes."""
    import json

    body = (text or "").strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise JudgeRefused(f"the judge did not answer with JSON: {body[:100]!r}") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("thumbnail_reads_small"), bool):
        raise JudgeRefused("the judge did not say whether the board reads at grid size")
    craft = parsed.get("craft_impression")
    if isinstance(craft, bool) or not isinstance(craft, (int, float)) or not 1.0 <= craft <= 5.0:
        raise JudgeRefused(f"craft_impression {craft!r} is not a rating from 1.0 to 5.0")
    return {"thumbnail_reads_small": parsed["thumbnail_reads_small"],
            "craft_impression": round(float(craft), 2)}


def judge_held(ctx, *, slug: str, board: str, provider=None) -> dict:
    """Ask the vision judge about one held winner's board, and record what it said.

    Budgeted like every other vision call (reserved before, released with the bill after),
    and refused rather than faked when the model does not answer as a judgement.
    """
    from ..core.resilience import PermanentError, TransientError
    from ..finance import spend_report
    from ..gateway import anthropic as gw

    # CB2-D01: fix which bytes are being judged before spending on the judge. A board with
    # no identifiable content cannot carry a judgement, so it is not sent to one.
    board_sha = board_digest_for(ctx.db, slug)
    if not board_sha:
        return {"judged": False,
                "why": "the board on file has no content digest; a judgement could not be "
                       "bound to the bytes it saw"}
    provider = provider or gw.provider_for(JUDGE_TASK)
    held = None
    try:
        reservation = gw.check_budget(
            ctx.db, model=provider.model,
            input_tokens=len(JUDGE_PROMPT) // 4 + gw.IMAGE_TOKENS_ESTIMATE,
            max_tokens=JUDGE_MAX_TOKENS, agent=ctx.job.agent, purpose=JUDGE_TASK,
            job_id=ctx.job.id)
        held = reservation["reservation_id"]
        response = provider.see(JUDGE_SYSTEM, JUDGE_PROMPT, [board],
                                max_tokens=JUDGE_MAX_TOKENS)
    except gw.BudgetExceeded as exc:
        gw.release_reservation(ctx.db, held)
        return {"judged": False, "why": f"budget: {exc}"[:200], "stopped": True}
    except (PermanentError, TransientError) as exc:
        gw.release_reservation(ctx.db, held)
        return {"judged": False, "why": str(exc)[:200]}
    cost = round(response.input_tokens * provider.cost_per_1k_input_cad / 1000
                 + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
    gw.release_reservation(ctx.db, held, actual_cad=cost)
    if cost > 0:
        spend_report.record(ctx.db, agent=ctx.job.agent, amount_cad=cost, purpose=JUDGE_TASK,
                            provider="anthropic", model=provider.model,
                            department="creative", product_slug=slug, job_id=ctx.job.id,
                            tokens_in=response.input_tokens, tokens_out=response.output_tokens,
                            detail={"what": "concept board judgement", "price_basis": "assumed"})
    try:
        verdict = parse_judgement(response.text)
    except JudgeRefused as exc:
        return {"judged": False, "why": str(exc)[:200], "cost_cad": cost}
    ctx.audit(JUDGED_ACTION, artifact=slug,
              detail={**verdict, "judge": provider.model, "board": board[-120:],
                      "board_sha256": board_sha,
                      "cost_cad": cost, "source": "creative.regate"})
    return {"judged": True, **verdict, "judge": provider.model, "cost_cad": cost}


def regate_held(ctx, *, today: date | None = None, provider=None) -> dict:
    """Re-present winners that waited on a judgement, now that one may exist.

    Only a winner the funnel carried and the gate left *waiting* is eligible: a refusal is a
    refusal, and a winner the funnel did not carry is not re-opened by a judgement. A held
    winner with no judgement is judged here first when its board exists and a vision model
    is usable; otherwise `held` says exactly which input it still waits on.
    """
    from ..gateway import anthropic as gw
    from . import ideation

    latest: dict[str, dict] = {}
    for row_id, slug, detail in intake_rows(ctx.db):
        latest.setdefault(slug, {"id": row_id, **detail})
    presented, queued, held = [], [], []
    vision_ok = gw.vision_usable(ctx.db)
    stopped = False
    for slug, detail in list(latest.items()):
        if len(presented) >= REGATE_LIMIT:
            break
        if detail.get("decision") != WAITING:
            continue
        board = board_for(ctx.db, slug)
        judged = judgement_for(ctx.db, slug)
        if not judged and board and vision_ok and not stopped:
            asked = judge_held(ctx, slug=slug, board=board, provider=provider)
            stopped = bool(asked.get("stopped"))
            judged = judgement_for(ctx.db, slug) if asked.get("judged") else None
        if not judged:
            held.append({"slug": slug, "waiting_on": (
                (["board_image (Product-Only Visual V1 image generation)"] if not board
                 else []) + (["vision_model (no vision probe has succeeded)"]
                             if not vision_ok else [])
                or ["a vision judgement of the board on file"])})
            continue
        known = detail.get("judgement") or {}
        if all(known.get(k) == judged.get(k) for k in ("thumbnail_reads_small",
                                                       "craft_impression")):
            continue
        concept = Concept(**{k: v for k, v in (detail.get("concept") or {}).items()
                             if k in Concept.__dataclass_fields__})
        concept = replace(concept, **{k: judged[k] for k in ("thumbnail_reads_small",
                                                            "craft_impression")
                                      if k in judged})
        brief = {k: (detail.get("brief") or {}).get(k) for k in GATE_BRIEF_FIELDS}
        if board:
            # #126: with a board on file the gate can request the search-grid tournament.
            brief["board_image"] = board
        gate = ideation.pre_engineering_gate(ctx.db, SimpleNamespace(concept=concept),
                                             ctx=ctx, source="creative.regate", brief=brief)
        verdict = gate.get("verdict") or {}
        decision = (REFUSED if verdict.get("decision") == "refused" else
                    ENGINEERING if gate.get("cleared_for_engineering") else WAITING)
        payload = {**(detail.get("payload") or {}), "concept": concept.to_dict()}
        new = {**{k: v for k, v in detail.items() if k != "id"}, "decision": decision,
               "judgement": judged, "payload": payload, "regated_from": detail["id"],
               "gate": {k: verdict.get(k) for k in ("decision", "failed", "unmeasured",
                                                     "waiting_on", "reasons")}}
        ctx.audit(INTAKE_ACTION, artifact=slug, detail=new)
        presented.append({"slug": slug, "decision": decision})
        if decision == ENGINEERING:
            job = ctx.enqueue("crochet_engineer", "cir.draft", payload,
                              idempotency_key=f"draft:{slug}")
            advance_gap(ctx.db, concept.pod, "engineering", product_slug=slug,
                        origin=brief_coverage_origin(brief),
                        event_id=detail.get("mjs_event_id"),
                        candidate_key=detail.get("original_key", ""),
                        reason=f"{slug} cleared the pre-engineering gate on re-presentation")
            queued.append({"slug": slug, "job": getattr(job, "id", None)})
    return {"presented": presented, "queued": queued, "held": held[:REGATE_LIMIT],
            "vision_usable": vision_ok}


# ---------------------------------------------------------------------------
# #316: a Brambleloop response is an interpretation the pod holds, tested by outcomes

RESPONSE_PREFIX = "response:"


def response_subject(event: str) -> str:
    return f"{RESPONSE_PREFIX}{_slugify(event, 40)}"


def response_lesson(db, *, pod: str, event: str, noun: str, slug: str,
                    mjs_event_id: int | None) -> dict:
    """Record the pod's interpretation that its seasonal response will sell, per event.

    It starts with no standing: only launches, conversion, complaints and owner vetoes move
    it (`intel.memory`), which `mission_runtime.response_outcomes` records on cadence.
    """
    from sqlalchemy import select

    from ..core.models import MjsMissionEvent, PodLesson
    from ..intel import memory, pods

    if pod not in pods.POD_KEYS or pod == pods.UNCLASSIFIED:
        return {"learned": False, "why": f"{pod!r} is not a specialist pod"}
    subject = response_subject(event)
    with db.session() as s:
        row = s.scalar(select(PodLesson).where(PodLesson.pod == pod,
                                               PodLesson.subject == subject,
                                               PodLesson.active == True)  # noqa: E712
                       .order_by(PodLesson.id).limit(1))
        lesson_id = row.id if row is not None else None
    learned = False
    if lesson_id is None:
        try:
            lesson_id = memory.learn(
                db, pod=pod, subject=subject,
                statement=(f"Brambleloop responses to {event} demand in the {pod} "
                           f"department sell when they launch by their preferred launch "
                           f"date"),
                mechanism="seasonal_timing", origin="brambleloop_response")
            learned = True
        except (memory.MemoryRefused, pods.MechanismRefused) as exc:
            return {"learned": False, "why": str(exc)[:200]}
    with db.session() as s:
        row = s.get(PodLesson, lesson_id)
        detail = dict(row.detail or {})
        slugs = list(detail.get("slugs") or [])
        if slug not in slugs:
            slugs.append(slug)
        row.detail = {**detail, "slugs": slugs, "polarity": "present", "event": event,
                      "kind": "brambleloop_response"}
        if mjs_event_id:
            ev = s.get(MjsMissionEvent, int(mjs_event_id))
            if ev is not None:
                steps = dict(ev.steps or {})
                mem = dict(steps.get("memory") or {})
                ids = sorted(set(mem.get("lesson_ids") or []) | {lesson_id})
                steps["memory"] = {**mem, "lesson_ids": ids}
                ev.steps = steps
    return {"learned": learned, "lesson_id": lesson_id, "subject": subject}
