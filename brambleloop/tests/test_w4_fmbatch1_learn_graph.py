"""F-807 prerequisite ladder from the stitch taxonomy; F-803 search phrases reach the Learn
queue; F-830 solved support questions become reusable FAQ nodes. Idempotent."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1lg_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/l.db"

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Keyword, SupportCase  # noqa: E402
from brambleloop.learn import graph_feeds as G, service  # noqa: E402
from brambleloop.learn.models import LearnEdge, LearnGap, LearnNode  # noqa: E402

db = Database(os.environ["BRAMBLELOOP_DATABASE_URL"])
db.create_all()


def _count(model):
    with db.session() as s:
        return s.query(model).count()


def test_f807_prerequisite_ladder_and_help_expansion():
    n = G.seed_prerequisites(db)
    assert n > 10
    edges = _count(LearnEdge)
    G.seed_prerequisites(db)
    assert _count(LearnEdge) == edges, "idempotent"
    assert G.ladder(db, "stitch:dc_inc") == ["stitch:ch", "stitch:sc", "stitch:hdc", "stitch:dc"]
    assert "stitch:dc" in service.expand_topics(db, {"stitch:dc_inc"})
    assert G.ladder(db, "stitch:ch") == []


def test_f803_search_phrase_queues_a_lesson_gap_in_either_terminology():
    with db.session() as s:
        s.add(Keyword(phrase="half treble crochet blanket pattern"))     # UK name of hdc
        s.add(Keyword(phrase="cozy throw for winter"))                    # names no stitch
    out = G.search_demand(db)
    assert out["search_sources"] == 1
    with db.session() as s:
        gap = s.get(LearnGap, "stitch:hdc")
        assert gap.state == "QUEUED" and gap.evidence[-1]["phrase"].startswith("half treble")
        assert s.get(LearnNode, "search:1").kind == "search"
    with db.session() as s:
        s.add(Keyword(phrase="double crochet hat"))                    # US dc or UK sc
    G.search_demand(db)
    with db.session() as s:
        for topic in ("stitch:dc", "stitch:sc"):
            assert s.get(LearnGap, topic).evidence[-1]["ambiguous_us_uk"] is True, topic


def test_f830_solved_questions_become_reusable_faq_nodes():
    with db.session() as s:
        s.add(SupportCase(customer_ref="a", product_slug="hex", question="q", resolved=True,
                          specialist="sizing"))
        s.add(SupportCase(customer_ref="b", product_slug="pebble", question="q", resolved=True,
                          specialist="sizing"))
        s.add(SupportCase(customer_ref="c", product_slug="hex", question="q", resolved=False,
                          specialist="sizing"))
    out = G.solved_questions(db)
    assert out == {"faq_nodes": 1, "solved": 2}
    with db.session() as s:
        node = s.get(LearnNode, "faq:sizing")
        assert node.detail["products"] == ["hex", "pebble"]
        assert node.detail["reusable_across_products"] is True
    assert service.graph(db, "faq:sizing")["counts"]["edges"] == 2


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
