"""Continuous teaching improvement (F-829) -- W4-C11.

"Every lesson participates in OBSERVE -> HYPOTHESIS -> EXPERIMENT -> MEASURE -> VALIDATE ->
PROMOTE/REJECT. Improve explanations, visuals, sequencing and formats while preserving the
underlying technical truth."

One loop per attempt, durable as a Learn graph node (`learn_nodes`, kind `teaching`, key
`teaching:<lesson>:<n>`; editor-only like the rest of the graph). Each stage can only follow
its predecessor, and each records what it was given:

* OBSERVE -- an observation with its evidence ref, against the lesson's current revision;
* HYPOTHESIS -- what changes (one of `CHANGES`), the metric, the expected direction;
* EXPERIMENT -- the variant spec. It must pass `service.validate_spec` and keep the technical
  truth (`truth`): terminology, hook/yarn assumptions, topics and every step's stitch, repeat,
  consumes and produces -- in order, except a `sequencing` change, which may reorder steps but
  not alter one. Its words may not introduce a number or stitch the lesson does not state
  (`formats.drift`);
* MEASURE -- baseline and result over `n` learners; below `MIN_SAMPLE` it stays UNMEASURED and
  the loop waits;
* VALIDATE -- passes when the lift reaches `MIN_LIFT` and the lesson has not changed revision
  since the experiment began (a result measured against an old lesson says nothing about the
  new one); otherwise REJECT;
* PROMOTE saves the variant through `service.save_lesson`: a new revision in DRAFT whose
  reviews are reset. Approval is never inherited by a promotion.
"""
from __future__ import annotations

CHANGES = ("explanation", "visual", "sequencing", "format")
ORDER = ("OBSERVE", "HYPOTHESIS", "EXPERIMENT", "MEASURE", "VALIDATE")
MIN_SAMPLE = 30
MIN_LIFT = 0.05


class TeachingRefused(ValueError):
    pass


def truth(spec: dict, *, ordered: bool = True):
    steps = [(s.get("stitch"), s.get("repeat"), s.get("consumes"), s.get("produces"),
              s.get("loop", "both")) for s in spec.get("steps") or []]
    return (spec.get("terminology"), tuple(sorted((spec.get("assumptions") or {}).items())),
            tuple(sorted(spec.get("topics") or [])),
            tuple(steps) if ordered else tuple(sorted(steps, key=repr)))


def _get(db, key):
    from .models import LearnNode

    with db.session() as s:
        n = s.get(LearnNode, key)
        if n is None or n.kind != "teaching":
            raise TeachingRefused(f"no teaching loop {key!r}")
        return dict(n.detail)


def _put(db, key, detail):
    from .models import LearnNode

    with db.session() as s:
        s.merge(LearnNode(key=key, kind="teaching", detail=detail))


def _advance(db, key, stage, **fields):
    d = _get(db, key)
    want = ORDER[ORDER.index(stage) - 1]
    if d["stage"] != want:
        raise TeachingRefused(f"{stage} follows {want}; the loop is at {d['stage']}")
    d.update(fields)
    d["stage"] = stage
    d["history"] = [*d["history"], stage]
    _put(db, key, d)
    return d


def _lesson(db, slug):
    from .models import Lesson

    with db.session() as s:
        row = s.get(Lesson, slug)
        if row is None:
            raise TeachingRefused(f"no lesson {slug!r}")
        return dict(row.spec), row.revision


def observe(db, slug: str, *, observation: str, evidence_ref: str) -> str:
    from sqlalchemy import select

    from .models import LearnNode

    if not observation or not evidence_ref:
        raise TeachingRefused("an observation needs its words and its evidence ref")
    _spec, revision = _lesson(db, slug)
    with db.session() as s:
        n = len(list(s.scalars(select(LearnNode.key).where(
            LearnNode.key.like(f"teaching:{slug}:%")))))
    key = f"teaching:{slug}:{n + 1}"
    _put(db, key, {"slug": slug, "stage": "OBSERVE", "history": ["OBSERVE"],
                   "observation": observation, "evidence_ref": evidence_ref,
                   "lesson_revision": revision})
    return key


def hypothesise(db, key, *, change: str, hypothesis: str, metric: str) -> dict:
    if change not in CHANGES:
        raise TeachingRefused(f"change must be one of {CHANGES}")
    return _advance(db, key, "HYPOTHESIS", change=change, hypothesis=hypothesis,
                    metric=metric)


def experiment(db, key, *, variant: dict) -> dict:
    from . import formats as F
    from .service import digest, validate_spec

    d = _get(db, key)
    spec, revision = _lesson(db, d["slug"])
    errs = validate_spec(variant)
    if errs:
        raise TeachingRefused("variant fails validation: " + "; ".join(errs))
    ordered = d.get("change") != "sequencing"
    if truth(variant, ordered=ordered) != truth(spec, ordered=ordered):
        raise TeachingRefused("the variant changes the technical truth of the lesson")
    words = " ".join(str(s.get("instruction") or "") for s in variant["steps"])
    drift = F.drift(spec, words + " " + str(variant.get("learner_problem") or ""))
    if drift:
        raise TeachingRefused(f"the variant states what the lesson does not: {drift}")
    return _advance(db, key, "EXPERIMENT", variant=variant, variant_revision=digest(variant),
                    experiment_lesson_revision=revision)


def measure(db, key, *, baseline: float | None, result: float | None, n: int | None) -> dict:
    if baseline is None or result is None or n is None or n < MIN_SAMPLE:
        d = _get(db, key)
        return {**d, "measurement": "UNMEASURED",
                "why": f"{n or 0} of {MIN_SAMPLE} learners measured"}
    return _advance(db, key, "MEASURE", baseline=baseline, result=result, n=n)


def validate(db, key) -> dict:
    d = _get(db, key)
    _spec, revision = _lesson(db, d["slug"])
    if d["stage"] != "MEASURE":
        raise TeachingRefused(f"VALIDATE follows MEASURE; the loop is at {d['stage']}")
    lift = (d["result"] - d["baseline"]) / d["baseline"] if d["baseline"] else None
    stale = revision != d["experiment_lesson_revision"]
    ok = lift is not None and lift >= MIN_LIFT and not stale
    d = _advance(db, key, "VALIDATE", lift=None if lift is None else round(lift, 4),
                 validated=ok, why=("the lesson changed revision during the experiment"
                                    if stale else f"lift {lift}" if lift is not None
                                    else "no baseline"))
    if not ok:
        return _close(db, key, "REJECT")
    return d


def _close(db, key, outcome):
    d = _get(db, key)
    d["stage"] = outcome
    d["history"] = [*d["history"], outcome]
    _put(db, key, d)
    return d


def promote(db, key) -> dict:
    from .service import save_lesson

    d = _get(db, key)
    if d["stage"] != "VALIDATE" or not d.get("validated"):
        raise TeachingRefused("only a validated experiment is promoted")
    revision = save_lesson(db, d["slug"], d["variant"])
    d = _close(db, key, "PROMOTE")
    d["promoted_revision"] = revision
    _put(db, key, d)
    return {**d, "lesson_state": "DRAFT",
            "why": "promoted as a new revision; it is reviewed again before it is approved"}
