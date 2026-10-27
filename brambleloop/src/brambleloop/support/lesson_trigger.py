"""Support-to-lesson trigger (F-802) -- W4-C14.

"Cluster customer questions, refunds, support tickets, failed validations and review complaints.
Repeated confusion automatically proposes a tutorial/FAQ/diagram/video/pattern clarification
experiment."

Signals are `{kind, ref, reporter, product_slug, row, text}` with `kind` one of `KINDS`;
`signals_from_cases` reads `SupportCase` rows as questions/tickets. Each signal is classified
into the failure modes of `project_tips` (fixed patterns, no model) and clustered by
(mode, product). A cluster is *repeated confusion* at `MIN_REPORTERS` distinct reporters -- a
failed validation is its own reporter, since the compiler is not a customer.

A repeated cluster proposes one experiment:

* the format is fixed per mode (`FORMAT_FOR_MODE`): a tension problem is a diagram and a
  tutorial, a stitch-count problem an FAQ, and so on;
* when `MIN_SAME_ROW` of the cluster name the same row of the same product, it is a *pattern
  clarification* instead: the confusion has an address, and the fix belongs in the pattern
  (through a new validated version -- support cannot amend one);
* an approved lesson (`learn.models.Lesson`, its canonical `spec.topics`) already covering the
  topic `failure:<mode>` makes it a revision of that lesson at its revision hash; otherwise a
  new lesson.

The experiment states its hypothesis, metric (repeat contacts on this mode per 100 orders),
baseline (the cluster's count over the window) and stopping rule before it starts. The
durable record is the Learn department's own queue: one `LearnGap` per topic, its evidence the
signal refs (no customer text), and its state set exactly as `learn.service.scan` sets it, so
the next scan agrees with this one.
"""
from __future__ import annotations

from . import project_tips as P

KINDS = ("question", "ticket", "refund", "failed_validation", "review_complaint")
MIN_REPORTERS = 3
MIN_SAME_ROW = 2
WINDOW_DAYS = 30
FORMAT_FOR_MODE = {
    "tension": ("diagram", "tutorial"),
    "markers": ("diagram",),
    "joins": ("video",),
    "symmetry": ("diagram",),
    "stitch_counts": ("faq",),
    "sizing": ("tutorial", "faq"),
    "seaming": ("video", "diagram"),
    "finishing": ("tutorial",),
}


def topic_for(mode: str) -> str:
    return f"failure:{mode}"


def signals_from_cases(db) -> list[dict]:
    return [{**f, "kind": "ticket" if f["source"] == "support" else f["source"]}
            for f in P.failures_from_cases(db)]


def _approved_covering(db) -> dict[str, dict]:
    from sqlalchemy import select

    from ..learn.models import Lesson
    from ..learn.service import eligible

    out = {}
    with db.session() as s:
        for lesson in s.scalars(select(Lesson).order_by(Lesson.slug)):
            if eligible(lesson):
                for t in (lesson.spec or {}).get("topics", []):
                    out.setdefault(t, {"slug": lesson.slug, "revision": lesson.revision})
    return out


def cluster(signals) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for sig in signals:
        if sig.get("kind") not in KINDS:
            continue
        for mode in P.classify(sig.get("text", "")):
            c = out.setdefault((mode, sig.get("product_slug") or "*"),
                               {"refs": [], "reporters": set(), "kinds": {}, "rows": {}})
            c["refs"].append(sig.get("ref"))
            who = (f"validation:{sig.get('ref')}" if sig["kind"] == "failed_validation"
                   else sig.get("reporter") or sig.get("ref"))
            c["reporters"].add(who)
            c["kinds"][sig["kind"]] = c["kinds"].get(sig["kind"], 0) + 1
            if sig.get("row") is not None:
                c["rows"].setdefault(int(sig["row"]), set()).add(who)
    return out


def propose(db, signals, *, orders: int | None = None) -> dict:
    """Cluster, propose an experiment for each repeated cluster, and queue its Learn gap."""
    from ..learn.models import LearnGap

    covering = _approved_covering(db)
    proposals, watching = [], []
    for (mode, slug), c in sorted(cluster(signals).items()):
        n = len(c["reporters"])
        summary = {"mode": mode, "product_slug": None if slug == "*" else slug,
                   "distinct_reporters": n, "by_kind": dict(sorted(c["kinds"].items())),
                   "refs": sorted(r for r in c["refs"] if r)}
        if n < MIN_REPORTERS:
            watching.append({**summary, "state": "WATCHING",
                             "why": f"{n} of {MIN_REPORTERS} distinct reporters"})
            continue
        hot = sorted(((row, len(w)) for row, w in c["rows"].items() if len(w) >= MIN_SAME_ROW),
                     key=lambda rw: (-rw[1], rw[0]))
        topic = topic_for(mode)
        lesson = covering.get(topic)
        if hot and slug != "*":
            kind, formats = "pattern_clarification", ("pattern_clarification",)
            target = {"product_slug": slug, "row": hot[0][0],
                      "route": "defect incident -> CIR fix -> re-validated version"}
        elif lesson:
            kind, formats = "revise_lesson", FORMAT_FOR_MODE[mode]
            target = dict(lesson)
        else:
            kind, formats = "new_lesson", FORMAT_FOR_MODE[mode]
            target = {"topic": topic}
        baseline = (round(len(c["refs"]) * 100 / orders, 2) if orders else None)
        proposals.append({
            **summary, "state": "PROPOSED", "experiment": kind, "formats": list(formats),
            "target": target,
            "hypothesis": f"{'/'.join(formats)} on {mode.replace('_', ' ')} reduces repeat "
                          f"contacts about it",
            "metric": "contacts on this mode per 100 orders",
            "baseline": baseline if baseline is not None else "UNMEASURED",
            "baseline_why": (None if baseline is not None else
                             "no order count supplied, so the rate is UNMEASURED, not 0"),
            "stop_rule": f"{WINDOW_DAYS} days after release, or {MIN_REPORTERS} new contacts "
                         f"on the mode, whichever first",
        })
        with db.session() as s:
            gap = s.get(LearnGap, topic)
            if gap is None:
                gap = LearnGap(topic=topic, state="QUEUED", owner="learn", evidence=[])
                s.add(gap)
            ev = {"support_cluster": summary["product_slug"] or "*", "mode": mode,
                  "refs": summary["refs"], "distinct_reporters": n}
            if ev not in (gap.evidence or []):
                gap.evidence = [*(gap.evidence or []), ev]
            gap.state = "COVERED" if lesson else "QUEUED"
    return {"proposals": proposals, "watching": watching,
            "rule": f"repeated confusion = {MIN_REPORTERS}+ distinct reporters on one mode"}
