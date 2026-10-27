"""F-800: a structured curriculum -- tracks from foundations to advanced, seeded as data.

Tracks are not hand-assigned per topic: a stitch's track is its depth on the prerequisite
ladder (`learn.graph_feeds`, derived from the stitch taxonomy), so the curriculum and the
difficulty ladder cannot disagree. Techniques and finishing topics that have no ladder are
placed by an explicit table (`TECHNIQUE_TRACK`), and anything else is `unplaced`, named.

* depth 0-1 -> `foundations` (chain, slip stitch, single crochet)
* depth 2   -> `building` (half double, increases/decreases on sc)
* depth >=3 -> `advanced` (double/treble crochet and what is built on them)

`tracks(db)` places every topic the graph or the Learn queue knows, with each track's
coverage (topics with an approved lesson). Expansion from demand is post-launch (F-800's own
text); this is the seed, measured against what learners already need.
"""
from __future__ import annotations

from sqlalchemy import select

TRACKS = ("foundations", "building", "advanced")
TECHNIQUE_TRACK = {
    "technique:magic_ring": "foundations", "technique:gauge": "foundations",
    "finishing:fasten_off_weave_in_ends": "foundations", "technique:front_loop": "building",
    "technique:back_loop": "building", "technique:colour_change": "building",
    "technique:stitch_holds": "advanced", "technique:gauge_change": "advanced",
    "finishing:stuffing": "building",
}


def track_of(db, topic: str) -> str:
    from . import graph_feeds

    if topic in TECHNIQUE_TRACK:
        return TECHNIQUE_TRACK[topic]
    if topic.startswith("finishing:"):
        return "building"
    if topic.startswith("stitch:"):
        depth = len(graph_feeds.ladder(db, topic))
        return "foundations" if depth <= 1 else "building" if depth == 2 else "advanced"
    return "unplaced"


def tracks(db) -> dict:
    from .models import LearnGap, LearnNode, Lesson
    from .service import eligible

    with db.session() as s:
        topics = {n.key for n in s.scalars(select(LearnNode)) if n.kind in
                  ("stitch", "technique", "finishing")}
        topics |= {g.topic for g in s.scalars(select(LearnGap))}
        approved = set()
        for le in s.scalars(select(Lesson)).all():
            if eligible(le):
                approved.update(le.spec["topics"])
    out = {t: {"topics": [], "covered": 0} for t in (*TRACKS, "unplaced")}
    for topic in sorted(topics):
        tr = track_of(db, topic)
        out[tr]["topics"].append(topic)
        out[tr]["covered"] += topic in approved
    for v in out.values():
        v["coverage"] = (round(v["covered"] / len(v["topics"]), 3) if v["topics"]
                         else "UNMEASURED")
    return {"tracks": out, "order": list(TRACKS)}
