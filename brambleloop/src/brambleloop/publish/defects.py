"""Visual defects as named classes, and the recurrence that means the fixture is wrong.

Requirement 68. Track clipping, confusing dimensions, misleading visualisation, weak hero,
unreadable chart and redundant frames as named defect classes. Every production-discovered
visual defect gets a regression fixture, just like a compiler defect. Asset-system quality
should improve monotonically rather than rediscovering the same layout failures.

`gates.regression` already does this for the compiler: a defect becomes a fixture, the fixture
runs forever, and the defect cannot come back unnoticed. Visual defects never got the same
treatment, and the reason is worth naming -- a compiler defect is a wrong number and a layout
defect is a look, so it feels like a matter of taste and taste does not get a fixture. But
`publish.layout_qa` measures rendered pixels, which means these *are* reproducible, and
anything reproducible can be fixtured.

Two rules carry the requirement.

**A defect with no reproduction cannot get a fixture, and one without a fixture will recur.**
So a recorded defect names the artefact that reproduces it, and `record` refuses one that
does not. This is the honest constraint rather than a bureaucratic one: a defect somebody
described but nobody can reproduce is a memory, and memories do not prevent anything.

**A recurrence after a fixture exists is a worse finding than a first occurrence, and a
different one.** The first time is a bug in the renderer. The second time, with a fixture
supposedly covering it, is a bug in the fixture -- it is testing something adjacent to what
actually broke. Reporting both as "clipping, again" loses the distinction, and the
distinction is the whole of "improve monotonically": monotonic improvement is not a hope, it
is the claim that the count of classes with a passing fixture never goes down.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

# The six the requirement names. Closed, because a defect taxonomy that grows a class
# whenever something does not fit stops being able to say whether anything improved.
CLIPPING = "clipping"
CONFUSING_DIMENSIONS = "confusing_dimensions"
MISLEADING_VISUALISATION = "misleading_visualisation"
WEAK_HERO = "weak_hero"
UNREADABLE_CHART = "unreadable_chart"
REDUNDANT_FRAMES = "redundant_frames"

CLASSES: dict[str, str] = {
    CLIPPING: "text or a chart crossing the frame edge or a reserved region",
    CONFUSING_DIMENSIONS: "a measurement a buyer cannot place, or two that disagree",
    MISLEADING_VISUALISATION: "an image that implies something the pattern does not support",
    WEAK_HERO: "a first frame that documents rather than sells",
    UNREADABLE_CHART: "a chart whose type or symbols cannot be read at delivered size",
    REDUNDANT_FRAMES: "frames doing the same commercial job as each other",
}

# Which checker finds each class, so a class with no detector is visible rather than implied.
DETECTED_BY: dict[str, str] = {
    CLIPPING: "publish.layout_qa, on rendered pixels",
    CONFUSING_DIMENSIONS: "publish.dimensions, against the canonical geometry",
    MISLEADING_VISUALISATION: "gates.asset_truth, against the twin",
    WEAK_HERO: "publish.eligibility, on the hero's job and purpose",
    UNREADABLE_CHART: "publish.layout_qa, on the minimum text band at mobile scale",
    REDUNDANT_FRAMES: "publish.eligibility, on job collision",
}

FIRST = "first_occurrence"
RECURRENCE = "recurrence_after_fixture"


class DefectRefused(ValueError):
    """A defect nobody can reproduce, or a class nobody named."""


@dataclass(frozen=True)
class VisualDefect:
    """One defect found in production, with the thing that reproduces it."""

    defect_class: str
    product_slug: str
    reproduces_with: str
    found_on: str
    note: str = ""
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.defect_class not in CLASSES:
            raise DefectRefused(
                f"{self.defect_class!r} is not a visual defect class: {sorted(CLASSES)}. A "
                f"taxonomy that grows a class whenever something does not fit stops being "
                f"able to say whether anything improved")
        if not self.reproduces_with.strip():
            raise DefectRefused(
                f"{self.defect_class} on {self.product_slug}: name the artefact that "
                f"reproduces it. A defect nobody can reproduce cannot get a fixture, and a "
                f"defect without a fixture will happen again -- it is a memory, and memories "
                f"do not prevent anything")

    def to_dict(self) -> dict:
        return {"class": self.defect_class, "means": CLASSES[self.defect_class],
                "detected_by": DETECTED_BY[self.defect_class],
                "product_slug": self.product_slug,
                "reproduces_with": self.reproduces_with, "found_on": self.found_on,
                "note": self.note, "at": self.at.isoformat()}


def classify(defect: VisualDefect, *, fixtured_classes: set[str]) -> dict:
    """Whether this is a new defect or a fixture that does not cover what it claims to."""
    if defect.defect_class in fixtured_classes:
        return {
            "kind": RECURRENCE, "class": defect.defect_class,
            "why": (f"{defect.defect_class} has a fixture and happened anyway. The first "
                    f"occurrence was a bug in the renderer; this one is a bug in the "
                    f"fixture -- it is testing something adjacent to what actually broke, "
                    f"and adding a second fixture for the same class without finding out "
                    f"why leaves both wrong"),
            "action": "widen the existing fixture rather than adding a second one",
        }
    return {
        "kind": FIRST, "class": defect.defect_class,
        "why": f"first recorded {defect.defect_class}, and it is reproducible",
        "action": "capture a regression fixture from the reproduction",
    }


def coverage(fixtured_classes: set[str]) -> dict:
    """Which classes are fixtured and which are only named."""
    unknown = sorted(fixtured_classes - set(CLASSES))
    if unknown:
        raise DefectRefused(f"{unknown} are not defect classes: {sorted(CLASSES)}")
    covered = sorted(fixtured_classes & set(CLASSES))
    uncovered = sorted(set(CLASSES) - fixtured_classes)
    return {
        "classes": len(CLASSES), "fixtured": len(covered),
        "covered": covered, "uncovered": uncovered,
        "detectors": {k: DETECTED_BY[k] for k in uncovered},
        "why": (f"{len(uncovered)} classes have a detector and no fixture. A detector finds "
                f"a defect once; a fixture stops it coming back, and only the second is what "
                f"'improve monotonically' means"
                if uncovered else "every named class has a fixture behind it"),
    }


def monotonic(history: list[dict]) -> dict:
    """Whether asset quality actually improved, which is a claim about a count not going down.

    Each entry is {"at": str, "fixtured": [class, ...]}. Monotonic improvement is not a hope
    about defect counts falling -- production finds what production finds -- it is the
    narrower and checkable claim that the set of classes with a passing fixture never shrinks.
    """
    if len(history) < 2:
        return {"readable": False,
                "why": (f"{len(history)} reading(s). Monotonic is a claim about a sequence, "
                        f"and one point is not one")}
    points = [{"at": h.get("at", ""), "fixtured": sorted(set(h.get("fixtured", [])))}
              for h in history]
    regressions = []
    for before, after in zip(points, points[1:]):
        lost = sorted(set(before["fixtured"]) - set(after["fixtured"]))
        if lost:
            regressions.append({"between": [before["at"], after["at"]], "lost": lost})
    return {
        "readable": True, "points": points,
        "monotonic": not regressions,
        "regressions": regressions,
        "fixtured_now": points[-1]["fixtured"],
        "why": ("the set of fixtured classes never shrank" if not regressions else
                f"{len(regressions)} point(s) where a class lost its fixture. A fixture that "
                f"stops running is a defect that is free to return, and nothing announces it"),
    }


def state() -> dict:
    """The six classes, their detectors, and what monotonic actually claims."""
    return {
        "requirement": 68,
        "classes": dict(CLASSES),
        "detected_by": dict(DETECTED_BY),
        "refuses": [
            "a defect class the taxonomy does not name",
            "a defect with no artefact that reproduces it",
            "a monotonic verdict from a single reading",
        ],
        "note": ("a compiler defect is a wrong number and a layout defect is a look, which "
                 "is why these never got fixtures -- it feels like taste. But layout_qa "
                 "measures rendered pixels, so they are reproducible, and anything "
                 "reproducible can be fixtured"),
        "recurrence_rule": (
            "a recurrence after a fixture is a bug in the fixture, not a second bug in the "
            "renderer. Reporting both as the same thing loses the distinction that makes "
            "the difference between widening a fixture and adding a broken second one"),
    }


# ---- #68 in the runtime: production findings become fixtures ------------------------

FIXTURE_ACTION = "creative.defect_fixture"

# The codes the release chain's own checkers emit, onto the six classes. Matched as whole
# codes inside the problem string. Longest first so a specific code wins over its prefix.
CODE_CLASS: tuple[tuple[str, str], ...] = (
    ("FRAME_EDGE_CLIPPING", CLIPPING),
    ("FRAME_CROP_LOSS", CLIPPING),
    ("CLAIM_SIZE_LABEL_UNSUPPORTED", CONFUSING_DIMENSIONS),
    ("CLAIM_SIZE_UNSUPPORTED", CONFUSING_DIMENSIONS),
    ("CLAIM_SIZE_UNVERIFIABLE", CONFUSING_DIMENSIONS),
    ("LISTING_HERO_IS_A_CONCEPT", MISLEADING_VISUALISATION),
    ("ASSET_CONCEPT_AS_HERO", MISLEADING_VISUALISATION),
    ("ASSET_UNDISCLOSED_CONCEPT", MISLEADING_VISUALISATION),
    ("ASSET_MOTIF_ABSENT", MISLEADING_VISUALISATION),
    ("ASSET_COLOR_ABSENT", MISLEADING_VISUALISATION),
    ("ASSET_COMPONENT_ABSENT", MISLEADING_VISUALISATION),
    ("ASSET_CLASS_MISMATCH", MISLEADING_VISUALISATION),
    ("LISTING_HERO_IS_AN_INFOGRAPHIC", WEAK_HERO),
    ("LISTING_HERO_FABRIC_FLAT", WEAK_HERO),
    ("FRAME_DIES_AT_THUMBNAIL", WEAK_HERO),
    ("FRAME_FLAT", WEAK_HERO),
    ("THUMB_LOW_CONTRAST", WEAK_HERO),
    ("THUMB_SUBJECT_TOO_SMALL", WEAK_HERO),
    ("THUMB_NO_BREATHING_ROOM", WEAK_HERO),
    ("THUMB_TEXT_ILLEGIBLE", UNREADABLE_CHART),
    ("FRAME_TEXT_TOO_SMALL", UNREADABLE_CHART),
    ("LISTING_CHART_COLOR_ONLY", UNREADABLE_CHART),
    ("LISTING_NO_FONT", UNREADABLE_CHART),
    ("LISTING_REDUNDANT_FRAME", REDUNDANT_FRAMES),
)


def class_of(problem: str) -> tuple[str, str] | None:
    """(code, class) for a checker's problem string, or None when it is not a visual defect.

    None is an answer: a missing frame or a wrong image count is a structural problem, not
    one of the six looks this taxonomy names, and forcing it into one would grow the
    taxonomy by the back door.
    """
    text = str(problem or "")
    for code, defect_class in CODE_CLASS:
        if re.search(rf"(?<![A-Z_]){code}(?![A-Z_])", text):
            return code, defect_class
    return None


def fixtures(db) -> list[dict]:
    """Every fixture captured from production, oldest first."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        return [dict(r.detail or {}, audit_id=int(r.id), at=r.at.isoformat() if r.at else "")
                for r in s.scalars(select(AuditLog).where(AuditLog.action == FIXTURE_ACTION)
                                   .order_by(AuditLog.id))]


def fixtured_classes(db) -> set[str]:
    return {f["class"] for f in fixtures(db) if f.get("kind") == FIRST}


def capture(db, problems: list[str], *, slug: str, version: str, reproduces_with: str,
            found_on: str = "assets.build", actor: str = "publishing",
            job_id: int | None = None) -> dict:
    """Turn a release's visual problems into regression fixtures, classified on the way.

    One fixture per (class, code) per build. A first occurrence captures the reproduction
    as the fixture; a recurrence in a class that already has one is recorded as a bug in the
    existing fixture, with the action to widen it, rather than as a second fixture.
    """
    from ..core.models import AuditLog

    already = fixtured_classes(db)
    written, unclassified, seen = [], [], set()
    for problem in problems:
        hit = class_of(problem)
        if hit is None:
            unclassified.append(str(problem)[:200])
            continue
        code, defect_class = hit
        if (defect_class, code) in seen:
            continue
        seen.add((defect_class, code))
        defect = VisualDefect(defect_class=defect_class, product_slug=slug,
                              reproduces_with=reproduces_with, found_on=found_on,
                              note=f"{code}: {str(problem)[:300]}")
        verdict = classify(defect, fixtured_classes=already)
        detail = {**defect.to_dict(), "kind": verdict["kind"], "action": verdict["action"],
                  "why": verdict["why"], "code": code, "version": version,
                  "fixture": {"reproduces_with": reproduces_with, "code": code,
                              "expect_absent": code}}
        with db.session() as s:
            row = AuditLog(actor=actor, action=FIXTURE_ACTION, artifact=f"{slug}@{version}",
                           job_id=job_id, detail=detail)
            s.add(row)
            s.flush()
            detail["audit_id"] = int(row.id)
        if verdict["kind"] == FIRST:
            already = already | {defect_class}
        written.append(detail)
    after = fixtured_classes(db)
    return {"fixtures": written, "unclassified": unclassified,
            "coverage": coverage(after),
            "first": [w["class"] for w in written if w["kind"] == FIRST],
            "recurrences": [w["class"] for w in written if w["kind"] == RECURRENCE]}


def history(db) -> dict:
    """`monotonic` over the fixture record: the fixtured set after each capture."""
    points, running = [], set()
    for f in fixtures(db):
        if f.get("kind") == FIRST:
            running = running | {f["class"]}
        points.append({"at": f.get("at", ""), "fixtured": sorted(running)})
    return monotonic(points)


def replay(db, problems_now: list[str], *, slug: str) -> dict:
    """Run this product's fixtures against a fresh build's problems.

    A fixture fails when the code it captured is present again for the same product; that
    is the regression it exists to catch.
    """
    present = {c for c, _ in (class_of(p) or ("", "") for p in problems_now) if c}
    mine = [f for f in fixtures(db) if f.get("product_slug") == slug]
    failed = [f for f in mine if f.get("code") in present]
    return {"fixtures": len(mine), "failed": [{"class": f["class"], "code": f["code"],
                                               "audit_id": f["audit_id"]} for f in failed],
            "passed": len(mine) - len(failed)}
