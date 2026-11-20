"""What the specialist pods have learned, and what is allowed to change their minds.

Requirement 316. Observations, launches, failures, owner vetoes, conversion data and customer
outcomes all update a versioned learning memory, and challenger agents repeatedly test better
interpretations of the same signals.

The failure this is built against is the one every learning system has: **confidence that
grows with repetition rather than with outcome.** A pod observes the same thing forty times,
the interpretation feels increasingly certain, and nothing has been learned — forty
observations of a shop's Christmas listings is one observation, made forty times. So only an
*outcome* moves a lesson's standing: a launch that sold, a launch that did not, a customer
who complained, an owner who vetoed. Repetition is recorded and changes nothing.

Two consequences worth stating.

**A contradicted lesson is superseded, never deleted.** The useful question next year is not
what the pod believes; it is what it used to believe and what changed its mind. A lesson
overwritten in place answers neither, and deleting the wrong ones leaves a memory that has
only ever been right — which is the shape of a memory that is not learning.

**A challenger wins on outcome or it does not win.** An alternative interpretation is recorded
against the same subject and competes; the one with more supporting outcomes becomes active.
A challenger that is merely newer, or better argued, changes nothing — otherwise the memory
tracks whoever last wrote a paragraph.
"""
from __future__ import annotations

from dataclasses import dataclass

from .pods import MECHANISMS, POD_KEYS, check_expression

# What counts as an outcome. Closed, because an open list accepts "it felt right", and that
# is precisely the evidence that repetition dresses itself as.
OUTCOMES: dict[str, tuple[str, str]] = {
    "launch_sold": ("supports", "a product built on this interpretation sold"),
    "launch_failed": ("contradicts", "a product built on this interpretation did not sell"),
    "conversion_up": ("supports", "measured conversion improved after acting on it"),
    "conversion_down": ("contradicts", "measured conversion fell after acting on it"),
    "customer_complaint": ("contradicts", "a customer said it was wrong"),
    "owner_veto": ("contradicts", "the owner rejected the resulting proposal"),
    "benchmark_confirmed": ("supports", "the benchmark did the thing this predicted"),
    "benchmark_contradicted": ("contradicts", "the benchmark did the opposite"),
}

# Deliberately not an outcome, and named so the refusal can say why.
NON_OUTCOMES: dict[str, str] = {
    "observed_again": ("seeing the same thing again is repetition, not evidence: forty "
                       "observations of one shop's Christmas listings is one observation "
                       "made forty times"),
    "agrees_with_us": "consistency with what we already believe is not evidence",
    "seems_right": "a judgement about a judgement",
}


class MemoryRefused(ValueError):
    """A lesson moved by repetition, or a challenger that won on rhetoric."""


@dataclass
class Standing:
    lesson_id: int
    pod: str
    subject: str
    version: int
    supports: int
    contradicts: int
    active: bool

    @property
    def net(self) -> int:
        return self.supports - self.contradicts

    def to_dict(self) -> dict:
        return {"lesson_id": self.lesson_id, "pod": self.pod, "subject": self.subject,
                "version": self.version, "supports": self.supports,
                "contradicts": self.contradicts, "net": self.net, "active": self.active}


def learn(db, *, pod: str, subject: str, statement: str, mechanism: str,
          origin: str = "observation") -> int:
    """Record an interpretation. It starts with no standing, because nothing has tested it."""
    from sqlalchemy import select

    from ..core.models import PodLesson

    if pod not in POD_KEYS:
        raise MemoryRefused(f"{pod!r} is not a pod: {sorted(POD_KEYS)}")
    if mechanism not in MECHANISMS:
        raise MemoryRefused(
            f"{mechanism!r} is not a mechanism: {sorted(MECHANISMS)}. A lesson about "
            f"something other than a mechanism is a lesson about their product")
    if len(statement.split()) < 6:
        raise MemoryRefused("an interpretation states what it predicts; this is a label")
    check_expression(statement)

    with db.session() as s:
        latest = s.scalars(select(PodLesson).where(
            PodLesson.pod == pod, PodLesson.subject == subject).order_by(
                PodLesson.version.desc())).first()
        version = (latest.version + 1) if latest else 1
        row = PodLesson(pod=pod, subject=subject, version=version,
                        statement=statement.strip(), mechanism=mechanism, origin=origin,
                        active=True)
        s.add(row)
        s.flush()
        return row.id


def outcome(db, lesson_id: int, kind: str, *, evidence_ref: str) -> dict:
    """Move a lesson's standing. Only an outcome does this; repetition is refused."""
    from ..core.models import PodLesson

    if kind in NON_OUTCOMES:
        raise MemoryRefused(
            f"{kind!r} is not an outcome: {NON_OUTCOMES[kind]}. Confidence that grows with "
            f"repetition rather than with outcome is the failure every learning system has "
            f"(#316)")
    if kind not in OUTCOMES:
        raise MemoryRefused(f"{kind!r} is not a recorded outcome: {sorted(OUTCOMES)}")
    if not evidence_ref.strip():
        raise MemoryRefused("an outcome names where it came from, or it is an assertion")

    direction, meaning = OUTCOMES[kind]
    with db.session() as s:
        row = s.get(PodLesson, lesson_id)
        if row is None:
            raise MemoryRefused(f"no lesson {lesson_id}")
        entry = {"kind": kind, "meaning": meaning, "evidence_ref": evidence_ref.strip()}
        if direction == "supports":
            row.supported_by = list(row.supported_by or []) + [entry]
        else:
            row.contradicted_by = list(row.contradicted_by or []) + [entry]
        supports, contradicts = len(row.supported_by or []), len(row.contradicted_by or [])
        pod, subject, version = row.pod, row.subject, row.version

    return {"lesson_id": lesson_id, "pod": pod, "subject": subject, "version": version,
            "kind": kind, "direction": direction,
            "supports": supports, "contradicts": contradicts}


def challenge(db, lesson_id: int, *, statement: str, mechanism: str) -> int:
    """Record an alternative interpretation of the same subject.

    It does not win by being recorded. A challenger that were newer-therefore-better would
    make the memory track whoever last wrote a paragraph.
    """
    from ..core.models import PodLesson

    with db.session() as s:
        incumbent = s.get(PodLesson, lesson_id)
        if incumbent is None:
            raise MemoryRefused(f"no lesson {lesson_id}")
        pod, subject = incumbent.pod, incumbent.subject
    return learn(db, pod=pod, subject=subject, statement=statement, mechanism=mechanism,
                 origin="challenger")


def resolve(db, *, pod: str, subject: str) -> dict:
    """Decide which interpretation of a subject is active, on outcomes alone.

    A tie leaves the incumbent standing: a challenger that has not beaten it has not beaten
    it, and promoting on equal evidence is promoting on novelty.
    """
    from sqlalchemy import select

    from ..core.models import PodLesson

    with db.session() as s:
        rows = list(s.scalars(select(PodLesson).where(
            PodLesson.pod == pod, PodLesson.subject == subject).order_by(PodLesson.version)))
        if not rows:
            return {"resolved": False, "reason": f"no lesson for {pod}/{subject}"}

        standings = [Standing(r.id, r.pod, r.subject, r.version,
                              len(r.supported_by or []), len(r.contradicted_by or []),
                              r.active) for r in rows]
        incumbent = next((s_ for s_ in standings if s_.active), standings[0])
        best = max(standings, key=lambda x: (x.net, -x.version))

        if best.lesson_id != incumbent.lesson_id and best.net > incumbent.net:
            for r in rows:
                if r.id == incumbent.lesson_id:
                    r.active = False
                    r.superseded_by = best.lesson_id
                r.active = (r.id == best.lesson_id)
            winner, changed = best, True
        else:
            winner, changed = incumbent, False

        active_statement = next(r.statement for r in rows if r.id == winner.lesson_id)

    return {
        "resolved": True, "pod": pod, "subject": subject,
        "active_lesson_id": winner.lesson_id, "active_version": winner.version,
        "active_statement": active_statement,
        "changed": changed,
        "candidates": [x.to_dict() for x in standings],
        "note": ("A challenger wins on outcomes or it does not win. A tie leaves the "
                 "incumbent standing, because promoting on equal evidence is promoting on "
                 "novelty (#316)."
                 if not changed else
                 f"version {winner.version} supersedes the incumbent on outcome evidence"),
    }


def report(db, *, pod: str = "") -> dict:
    """What the pods hold, including what they used to hold.

    Superseded lessons are kept and reported: a memory that has only ever been right is a
    memory that is not learning.
    """
    from sqlalchemy import select

    from ..core.models import PodLesson

    with db.session() as s:
        query = select(PodLesson)
        if pod:
            query = query.where(PodLesson.pod == pod)
        rows = list(s.scalars(query))
        out = [{"id": r.id, "pod": r.pod, "subject": r.subject, "version": r.version,
                "statement": r.statement, "mechanism": r.mechanism, "origin": r.origin,
                "active": r.active, "supports": len(r.supported_by or []),
                "contradicts": len(r.contradicted_by or [])} for r in rows]

    untested = [x for x in out if not x["supports"] and not x["contradicts"]]
    return {
        "lessons": len(out),
        "active": sum(1 for x in out if x["active"]),
        "superseded": sum(1 for x in out if not x["active"]),
        "untested": len(untested),
        "challengers": sum(1 for x in out if x["origin"] == "challenger"),
        "all": out,
        "outcomes": {k: v[1] for k, v in OUTCOMES.items()},
        "not_outcomes": NON_OUTCOMES,
        "note": (f"{len(untested)} of {len(out)} interpretations have never met an outcome. "
                 f"Those are hypotheses the pods are carrying, not things they know -- and "
                 f"repetition will not change that (#316)."),
    }
