"""Reading a department's lesson inbox where its decisions are made (#97, #101, #147).

`improve.bus` routed every lesson to the cells its subject concerns, and `bus.acted_on` -- the
record that a receiving department changed something because of one -- had no runtime caller:
only the creativity brief ever read an inbox. So Market Radar, Pattern Engineering, Listings
and Support were told things and never listened, and `compounding()` read zero forever.

This is the listening half, deliberately small. A consumer hands over the text its decision is
about (a concept, a listing's candidate queries, a customer's question); the lessons in its
inbox whose statements share content words with that text are the ones that apply; the
consumer changes its decision with them and records exactly that through `bus.acted_on`, with
the words it acted on. A lesson that applies to nothing the department is deciding stays
unacted, which is the honest reading.
"""
from __future__ import annotations

import re

from . import bus

_WORD = re.compile(r"[a-z][a-z\-]{2,}")
# Words that appear in lessons about everything and so tie a lesson to nothing.
_STOP: frozenset[str] = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "have", "has", "was", "were", "are",
    "not", "but", "its", "our", "their", "they", "them", "than", "then", "into", "onto",
    "which", "when", "what", "who", "whom", "will", "would", "should", "could", "been",
    "being", "more", "most", "less", "each", "every", "any", "all", "one", "two", "three",
    "pattern", "patterns", "product", "products", "crochet", "brambleloop", "customer",
    "customers", "listing", "listings", "lesson", "lessons", "department", "requirement",
    "teardown", "benchmark", "binds", "prevent", "exceed", "clarify", "higher", "lower",
    "score", "scores", "scored", "because", "about", "there", "here", "also", "only",
    "must", "make", "made", "does", "doing", "done", "rather", "other", "same", "again",
})

# Subjects whose lessons raise what they match, and subjects whose lessons lower it: a
# construction customers prefer is a reason to pursue, a creative death is a reason not to.
FAVOURS: frozenset[str] = frozenset({"construction_preference", "cultural_territory",
                                     "cultural_timing", "seasonal_timing", "search_language",
                                     "pricing_response",
                                     # OPUS2-P0: measured own-listing demand (improve.
                                     # commercial_lessons) raises the concepts it names.
                                     "commercial_demand"})
DISFAVOURS: frozenset[str] = frozenset({"creative_rejection", "defect",
                                        # OPUS2-P0: measured own-listing underperformance.
                                        "commercial_underperformance"})


def words(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or "").lower()) if w not in _STOP}


def policy(db, cell: str, call_site_min_shared: int) -> dict:
    """The match threshold this cell uses now (v1.1 lane B, directive §4).

    For a cell with a measured policy loop (`policy_loops.LOOP_FOR_CELL`) the registry
    incumbent decides once one is recorded -- the call-site value is the code default the
    loop's first version was registered from. A cell with no loop keeps its call-site value.
    """
    from . import policy_loops

    key = policy_loops.LOOP_FOR_CELL.get(cell)
    if key is None:
        return {"loop": None, "value": call_site_min_shared, "config_id": None,
                "source": "call_site"}
    current = policy_loops.active(db, key)
    if current["source"] != "registry":
        return {**current, "value": call_site_min_shared, "source": "call_site"}
    return current


def matching(db, cell: str, text: str, *, min_shared: int = 2,
             subjects: frozenset[str] | None = None,
             subject: str | None = None) -> list[dict]:
    """Lessons routed to (or published by) this cell that apply to `text`.

    `subject` names what the decision is about (a product slug, `support_case:<id>`). When
    given, and the cell has a policy loop, the decision is logged with the feature it was
    taken on, so its outcome can later be attributed and the threshold evaluated (§4).
    """
    current = policy(db, cell, min_shared)
    threshold = int(current["value"])
    want = words(text)
    out = []
    best = 0
    candidates = 0
    for lesson in bus.inbox(db, cell, unacted_only=False, include_own=False):
        if subjects is not None and lesson["subject"] not in subjects:
            continue
        shared = sorted(words(lesson["statement"]) & want)
        candidates += 1
        best = max(best, len(shared))
        if len(shared) >= threshold:
            out.append({**lesson, "shared": shared,
                        "direction": (1 if lesson["subject"] in FAVOURS else
                                      -1 if lesson["subject"] in DISFAVOURS else 0)})
    if subject and current.get("loop"):
        from . import policy_loops

        policy_loops.record_decision(
            db, current["loop"], subject,
            features={"max_shared": best, "candidates": candidates},
            action={"applied": bool(out), "lessons": [int(x["id"]) for x in out]},
            config_id=current.get("config_id"), params={"min_shared": threshold})
    return out


def act(db, cell: str, lessons: list[dict], *, how: str) -> list[int]:
    """Record that this cell changed a decision because of these lessons."""
    acted = []
    for lesson in lessons:
        try:
            bus.acted_on(db, int(lesson["id"]), cell,
                         how=f"{how} (shared: {', '.join(lesson.get('shared', [])[:6])})"[:300])
            acted.append(int(lesson["id"]))
        except bus.LessonRefused:
            continue
    return acted


def score_adjustment(lessons: list[dict], *, step: float = 0.02, cap: float = 0.06) -> float:
    """A bounded nudge from the lessons that apply: favoured up, disfavoured down."""
    total = sum(step * lesson["direction"] for lesson in lessons)
    return round(max(-cap, min(cap, total)), 4)


# --- P0-LEARNING-TO-DESIGN (A6): the design-side consumer --------------------------------
#
# Pattern Engineering's inbox used to move only queue priority (`radar.score`). Here a lesson
# can change a later *draft* -- but never by its words. A lesson's statement is free text, and
# free text never becomes geometry (Master Plan s2). A lesson changes a design only through
# one of the declared, deterministic drafting parameters below, and only once a reviewer
# independent of the lesson's origin has approved exactly that parameter and value for it.
# Everything else `matching` returns is reported as unapproved and changes nothing. The
# compiler and certificate still decide every draft a lesson shaped.

DESIGN_CELL = "pattern_engineering"
# The drafting code's own exposed choices. `yarn_weight` is the concept's declared yarn, from
# which the gauge is derived (`creative.prototype.gauge_for`), never typed; `hold_construction`
# names a fallback construction family a lesson says failed testing, and holds the draft.
DESIGN_YARN_WEIGHTS: frozenset[str] = frozenset({"sport", "dk", "worsted", "aran", "bulky",
                                                  "chunky"})
# The fallback drafter's construction families (`creative.fallback_constructions`) and the
# creative concept vocabulary (`creative.concept.CONSTRUCTIONS`), the two places a draft's
# construction is decided. Listed rather than imported so this module stays import-light;
# tests/test_w5_a6_learning_to_design.py asserts it equals the union of the two.
DESIGN_CONSTRUCTIONS: frozenset[str] = frozenset({
    "flat_panel", "vessel", "panel_pair", "tote", "cosy", "triangle", "stocking", "tapestry",
    "pouch",
    "flat_rows", "in_the_round", "motif_join", "top_down_yoke", "bottom_up", "side_to_side",
    "modular_panels", "amigurumi_shaping", "mosaic_overlay", "cable_panel", "granny_square",
    "corner_to_corner", "seamless_tube"})
# `construction` (A6 acceptance): the construction a `construction_preference` lesson says
# makers or buyers prefer. It is a value of the creative concept vocabulary, and it changes a
# draft only where that construction can physically build the concept's form
# (`creative.family.FORM_CONSTRUCTIONS`), the engine has a route for it, and the concept's own
# words do not name the construction it already has (a "Granny Square Pillow" stays granny).
PREFERABLE_CONSTRUCTIONS: frozenset[str] = frozenset({
    "flat_rows", "in_the_round", "motif_join", "top_down_yoke", "bottom_up", "side_to_side",
    "modular_panels", "amigurumi_shaping", "tapestry", "mosaic_overlay", "cable_panel",
    "granny_square", "corner_to_corner", "seamless_tube"})
DESIGN_PARAMETERS: dict[str, frozenset[str]] = {"yarn_weight": DESIGN_YARN_WEIGHTS,
                                                "hold_construction": DESIGN_CONSTRUCTIONS,
                                                "construction": PREFERABLE_CONSTRUCTIONS}
# Which lesson subjects may carry which parameter: a preference is not a defect report.
PARAMETER_SUBJECTS: dict[str, frozenset[str]] = {
    "construction": frozenset({"construction_preference"}),
}
DESIGN_APPROVED = "lesson.design_approved"
# The durable record that Pattern Engineering changed a design because of a lesson (the A6
# acceptance's `lesson.acted_on` row), beside the lesson's own `acted_on_by` entry.
DESIGN_APPLIED = "lesson.acted_on"


class DesignApprovalRefused(ValueError):
    """An approval that is not independent, or names no declared parameter."""


def _design_approvers() -> frozenset[str]:
    from . import roles

    return frozenset({"owner"} | {k for k, r in roles.BY_KEY.items()
                                  if roles.JUDGE in r.powers})


def approve_for_design(db, lesson_id: int, *, parameter: str, value: str,
                       approved_by: str, why: str) -> dict:
    """Approve one lesson to change one declared drafting parameter to one value.

    The approver is the owner or a judging role, never the lesson's origin and never the
    consuming cell itself. Idempotent per (lesson, parameter, value).
    """
    from sqlalchemy import select

    from ..core.models import AuditLog, Lesson
    from . import governance

    who = governance.normalise_actor(approved_by)
    if who not in _design_approvers():
        raise DesignApprovalRefused(
            f"{approved_by!r} may not approve design learning: the owner or a judging role "
            f"({sorted(_design_approvers())}) decides")
    if parameter not in DESIGN_PARAMETERS or value not in DESIGN_PARAMETERS[parameter]:
        raise DesignApprovalRefused(
            f"{parameter}={value!r} is not a declared drafting parameter "
            f"({ {k: sorted(v) for k, v in DESIGN_PARAMETERS.items()} })")
    if len(str(why or "").split()) < 4:
        raise DesignApprovalRefused("an approval says why the lesson justifies this change")
    with db.session() as s:
        row = s.get(Lesson, int(lesson_id))
        if row is None:
            raise DesignApprovalRefused(f"no lesson {lesson_id}")
        if row.superseded_by is not None or row.withdrawn_at is not None:
            raise DesignApprovalRefused(f"lesson {lesson_id} is superseded or withdrawn")
        if DESIGN_CELL not in (row.routed_to or []):
            raise DesignApprovalRefused(f"lesson {lesson_id} was not routed to {DESIGN_CELL}")
        allowed = PARAMETER_SUBJECTS.get(parameter)
        if allowed is not None and row.subject not in allowed:
            raise DesignApprovalRefused(
                f"a {row.subject!r} lesson may not set {parameter}: only {sorted(allowed)}")
        if who in (governance.normalise_actor(row.origin_cell), DESIGN_CELL):
            raise DesignApprovalRefused(
                f"{who} may not approve lesson {lesson_id}: the origin of a lesson, or the "
                f"cell that would apply it, is not an independent reviewer")
        artifact = f"lessons:{int(lesson_id)}"
        for prior in s.scalars(select(AuditLog).where(AuditLog.action == DESIGN_APPROVED,
                                                      AuditLog.artifact == artifact)):
            d = prior.detail or {}
            if d.get("parameter") == parameter and d.get("value") == value:
                return {"lesson": int(lesson_id), "approval_id": prior.id, "recorded": False}
        rec = AuditLog(actor=who[:64], action=DESIGN_APPROVED, artifact=artifact,
                       detail={"parameter": parameter, "value": value, "why": why[:400]})
        s.add(rec)
        s.flush()
        return {"lesson": int(lesson_id), "approval_id": rec.id, "recorded": True}


def _design_approval(db, lesson_id: int) -> dict | None:
    """The latest valid design approval on file for this lesson, or None."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(
                AuditLog.action == DESIGN_APPROVED,
                AuditLog.artifact == f"lessons:{int(lesson_id)}").order_by(desc(AuditLog.id))):
            d = dict(row.detail or {})
            if (d.get("parameter") in DESIGN_PARAMETERS
                    and d.get("value") in DESIGN_PARAMETERS[d["parameter"]]
                    and row.actor in _design_approvers()
                    and _subject_may_set(db, lesson_id, d["parameter"])):
                return {"approval_id": row.id, "approved_by": row.actor,
                        "parameter": d["parameter"], "value": d["value"]}
    return None


def _subject_may_set(db, lesson_id: int, parameter: str) -> bool:
    allowed = PARAMETER_SUBJECTS.get(parameter)
    if allowed is None:
        return True
    from ..core.models import Lesson

    with db.session() as s:
        row = s.get(Lesson, int(lesson_id))
        return row is not None and row.subject in allowed


def design_directives(db, text: str, *, constructions: tuple[str, ...] = ()) -> dict:
    """What APPROVED Pattern Engineering learning says about the design `text` describes.

    Reads `matching(db, "pattern_engineering", text)`; each match applies only with an
    independent approval naming a declared parameter. Deterministic: a hold for one of
    `constructions` wins; conflicting yarn approvals cancel each other (applied: none).
    """
    hold, yarn, prefer, unapproved, conflicts = [], [], [], [], []
    for lesson in sorted(matching(db, DESIGN_CELL, text), key=lambda l: int(l["id"])):
        approval = _design_approval(db, int(lesson["id"]))
        if approval is None:
            unapproved.append(int(lesson["id"]))
            continue
        item = {**lesson, "approval": approval}
        if approval["parameter"] == "hold_construction":
            if approval["value"] in constructions:
                hold.append(item)
        elif approval["parameter"] == "yarn_weight":
            yarn.append(item)
        elif approval["parameter"] == "construction":
            prefer.append(item)
    if len({l["approval"]["value"] for l in yarn}) > 1:
        conflicts += [int(l["id"]) for l in yarn]
        yarn = []
    if len({l["approval"]["value"] for l in prefer}) > 1:
        conflicts += [int(l["id"]) for l in prefer]
        prefer = []
    return {"hold": hold, "yarn_weight": (yarn[0]["approval"]["value"] if yarn else None),
            "yarn_lessons": yarn,
            "construction": (prefer[0]["approval"]["value"] if prefer else None),
            "construction_lessons": prefer,
            "unapproved": unapproved, "conflicts": conflicts}


def record_application(db, lessons: list[dict], *, subject: str, change: dict,
                       how: str) -> list[int]:
    """`act` plus one durable record per (lesson, product, change), however often re-run."""
    import json

    from sqlalchemy import select

    from ..core.models import AuditLog

    key = json.dumps(change, sort_keys=True, default=str)
    recorded = []
    for lesson in lessons:
        artifact = f"lessons:{int(lesson['id'])}"
        with db.session() as s:
            exists = any(
                (r.detail or {}).get("subject") == subject
                and (r.detail or {}).get("change_key") == key
                for r in s.scalars(select(AuditLog).where(AuditLog.action == DESIGN_APPLIED,
                                                          AuditLog.artifact == artifact)))
            if exists:
                continue
            s.add(AuditLog(actor=DESIGN_CELL, action=DESIGN_APPLIED, artifact=artifact,
                           detail={"subject": subject, "change": change, "change_key": key,
                                   "approval_id": (lesson.get("approval") or {})
                                   .get("approval_id"),
                                   "outcome": "unmeasured until the release is certified "
                                              "and sold"}))
        recorded.append(int(lesson["id"]))
    if recorded:
        act(db, DESIGN_CELL, [l for l in lessons if int(l["id"]) in recorded],
            how=f"{how} [{subject}]")
    return recorded
