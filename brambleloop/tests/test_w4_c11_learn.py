"""W4-C11: education and content (F-804, F-809, F-813, F-816, F-817, F-818, F-823, F-829,
F-771, F-772, F-810, F-811). Fixture lessons and products only; no network, CA$0."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.learn import service as LS  # noqa: E402
from brambleloop.products.builder import CATALOGUE, build  # noqa: E402


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _spec(topics=("stitch:sc", "stitch:dc"), problem="work single and double crochet"):
    return {"author": "pattern-engineering", "learner_problem": problem,
            "topics": list(topics), "terminology": "US",
            "assumptions": {"hook_mm": 4, "yarn_weight": "worsted"},
            "assets": [{"rights": "brambleloop_original", "source": "canonical-demo",
                        "sha256": "a" * 64}],
            "steps": [{"stitch": "sc", "repeat": 2, "consumes": 2, "produces": 2,
                       "term": "sc", "instruction": "Work one sc in each of next two sts."},
                      {"stitch": "dc", "repeat": 3, "consumes": 3, "produces": 3,
                       "term": "dc",
                       "instruction": "Chain 3, then work one dc in each of next three sts."}]}


def _approve(db, slug, spec):
    rev = LS.save_lesson(db, slug, spec)
    LS.review_lesson(db, slug, rev, "independent-qa", dict.fromkeys(LS.DIMENSIONS, "PASS"),
                     "fixture-review:test-only")
    assert LS.approved_lesson(db, slug) is not None
    return rev


# ---- F-804 -----------------------------------------------------------------------------------

def test_f804_one_spec_renders_every_format_without_drift():
    from brambleloop.learn import formats as F

    db = _db()
    spec = _spec()
    rev = _approve(db, "sc-dc", spec)
    out = F.render_all(db, "sc-dc", pattern_topics={"stitch:dc"})
    assert set(out["formats"]) == set(F.FORMATS)
    assert all(r["revision"] == rev for r in out["formats"].values())
    assert "Chain 3" in out["formats"]["article"]["body"]
    assert "3 double crochet from 3" in out["formats"]["faq"]["body"]
    help_ = out["formats"]["pattern_help"]["body"]
    assert "three sts" in help_ and "two sts" not in help_          # only the pattern's stitch

    # Drift is caught: a number the spec never states, and a stitch it does not teach.
    assert F.drift(spec, "Work 5 dc") == ["number 5 is not in the specification"]
    assert F.drift(spec, "then a treble crochet") == [
        "stitch 'treble crochet' is not taught by the specification"]
    assert F.drift(spec, "single crochet, double crochet, chain 3") == []
    assert F.drift({**spec, "steps": spec["steps"][:1]}, "half double crochet") == [
        "stitch 'half double crochet' is not taught by the specification"]

    # A draft is not rendered for the public, and an edited spec is a new revision.
    LS.save_lesson(db, "draft", _spec(problem="draft lesson"))
    try:
        F.render_all(db, "draft")
        raise AssertionError("a draft rendered")
    except PermissionError:
        pass
    assert F.render_all(db, "draft", allow_draft=True)["approved"] is False


# ---- F-809 -----------------------------------------------------------------------------------

def test_f809_gauge_calculators_agree_with_product_truth():
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.learn import gauge as G

    sw = G.measure_swatch(stitches=18, rows=20, width_cm=10, height_cm=12.5)
    assert sw == {**sw, "stitches_per_10cm": 18.0, "rows_per_10cm": 16.0}
    assert G.hook_advice(target_sts=16, measured_sts=18, hook_mm=4.0)["hook_mm"] == 4.5
    assert G.hook_advice(target_sts=16, measured_sts=14, hook_mm=4.0)["action"] == "go_down"
    assert G.hook_advice(target_sts=16, measured_sts=16.2, hook_mm=4.0)["action"] == "keep"
    assert G.consistency([16, 16.1, 15.9])["state"] == "CONSISTENT"
    assert G.consistency([14, 16, 18])["state"] == "INCONSISTENT"
    assert G.consistency([16])["state"] == "UNMEASURED"
    assert G.blocking(unblocked_sts=16, blocked_sts=15)["measure_blocked"]

    cir = build(CATALOGUE["cloudline-baby-blanket"])
    twin = build_twin(cir, compile_cir(cir))
    same = G.fit(cir, stitches_per_10cm=cir.gauge.stitches_per_10cm,
                 rows_per_10cm=cir.gauge.rows_per_10cm)
    assert same["width"]["pattern_cm"] == round(twin.width_cm, 1)        # the stated size
    assert same["width"]["difference_cm"] == 0
    looser = G.fit(cir, stitches_per_10cm=cir.gauge.stitches_per_10cm * 0.9,
                   rows_per_10cm=cir.gauge.rows_per_10cm)
    assert looser["width"]["difference_pct"] > 0.1                     # fewer sts: wider

    weight = next(m.yarn_weight for m in cir.materials if m.yarn_weight)
    sub = G.substitute(cir, metres_per_skein=200, yarn_weight=weight)
    metres = sum(twin.yarn_metres_by_color.values()) * (1 + twin.yardage_tolerance)
    assert sub["skeins"] * 200 >= metres > (sub["skeins"] - 1) * 200
    try:
        G.substitute(cir, metres_per_skein=200, yarn_weight="lace-not-this")
        raise AssertionError("cross-weight substitution allowed")
    except G.GaugeRefused:
        pass


# ---- F-813 -----------------------------------------------------------------------------------

def test_f813_partial_videos_say_so_and_the_written_pattern_stands_alone():
    from brambleloop.learn import video_contract as V

    product = {"slug": "p", "version": "1.2", "sizes": ["S", "M", "L"], "promises_video": False}
    full = {"ref": "v0", "sizes": ["S", "M", "L"], "version": "1.2"}
    part = {"ref": "v1", "sizes": ["M"], "version": "1.1"}
    assert V.scope_statement(product, full) is None
    stmt = V.scope_statement(product, part)
    assert stmt == ("This video shows size M only from version 1.1 of the pattern; the "
                    "current pattern is version 1.2.")
    assert V.check_statement(product, part, stmt) == []
    bad = V.check_statement(product, part, "A full video walkthrough!")
    assert len(bad) == 3
    assert V.standalone("Rnd 5: see the video for the rest.", product)["standalone"] is False
    assert V.standalone("Rnd 5: 2 sc in each st (12).", product)["standalone"] is True
    assert V.standalone("Watch the video.", {**product, "promises_video": True})["standalone"]


# ---- F-816 -----------------------------------------------------------------------------------

def test_f816_links_follow_prerequisites_and_relevance_not_keywords():
    from brambleloop.learn import graph_feeds, linking as K

    db = _db()
    graph_feeds.seed_prerequisites(db)
    pages = [
        {"key": "lesson:sc", "kind": "lesson", "title": "Single crochet", "intent": "learn",
         "topics": ["stitch:sc"]},
        {"key": "lesson:dc-inc", "kind": "lesson", "title": "Double crochet increase",
         "intent": "learn", "topics": ["stitch:dc_inc"]},
        {"key": "lesson:dc", "kind": "lesson", "title": "Double crochet", "intent": "learn",
         "topics": ["stitch:dc"]},
        {"key": "pattern:blanket", "kind": "pattern", "intent": "make",
         "title": "Easy Double Crochet Blanket", "topics": ["stitch:sc"]},
        {"key": "support:curl", "kind": "support", "title": "Why is my edge curling",
         "intent": "troubleshoot", "topics": ["stitch:sc"]},
    ]
    links = K.propose(pages, db=db)["links"]
    # dc_inc needs dc (a recorded prerequisite edge), so the dc lesson is linked first.
    assert links["lesson:dc-inc"][0] == {"target": "lesson:dc", "anchor": "Double crochet",
                                         "reason": "prerequisite", "via": ["stitch:dc"],
                                         "state": "PROPOSED"}
    # The blanket says "Double Crochet" in its title but uses sc: it links sc, not dc.
    assert [lk["target"] for lk in links["pattern:blanket"]] == ["lesson:sc"]
    assert links["pattern:blanket"][0]["reason"] == "technique_used"
    assert [lk["target"] for lk in links["support:curl"]] == ["lesson:sc"]
    assert links["support:curl"][0]["reason"] == "answers"
    assert {"target": "pattern:blanket"}.items() <= links["lesson:sc"][0].items()
    assert all(len(v) <= K.MAX_LINKS for v in links.values())

    assert K.evaluate(impressions=100, clicks=50)["state"] == "UNMEASURED"
    assert K.evaluate(impressions=None, clicks=None)["ctr"] is None
    assert K.evaluate(impressions=400, clicks=8)["state"] == "KEEP"
    assert K.evaluate(impressions=400, clicks=1)["state"] == "DROP"


# ---- F-817 -----------------------------------------------------------------------------------

def test_f817_search_briefs_are_independent_and_cannot_distort_truth():
    from brambleloop.core.models import Keyword
    from brambleloop.learn import graph_feeds, seo as S

    db = _db()
    _approve(db, "sc-dc", _spec())
    _approve(db, "fix-curl", _spec(topics=("stitch:sc",),
                                   problem="fix a curling edge on single crochet"))
    with db.session() as s:
        cols = Keyword.__table__.columns.keys()
        s.add(Keyword(**{k: v for k, v in {"phrase": "how to double crochet for beginners",
                                            "intent": "learn"}.items() if k in cols}))
    graph_feeds.search_demand(db)
    b = S.brief(db, "sc-dc")
    assert b["state"] == "READY" and b["intent"] == "how_to"
    assert b["title"] == "How to work single and double crochet"
    assert len(b["title"]) <= S.TITLE_MAX and len(b["meta_description"]) <= S.META_MAX
    assert b["schema"]["@type"] == "HowTo" and len(b["schema"]["step"]) == 2
    assert "how to double crochet for beginners" in b["faq_opportunities"]
    fix = S.brief(db, "fix-curl")
    assert fix["intent"] == "troubleshoot" and fix["schema"]["@type"] == "FAQPage"
    assert fix["update_every_days"] < b["update_every_days"]

    # Optimisation may not claim what the lesson cannot evidence.
    _approve(db, "best", _spec(problem="the easiest way to work single and double crochet"))
    bad = S.brief(db, "best")
    assert bad["state"] == "REFUSED" and "unearned claim" in bad["problems"][0]


# ---- F-818 -----------------------------------------------------------------------------------

def test_f818_lessons_are_monitored_and_updates_are_versioned_and_regression_checked():
    from brambleloop.core.models import Product
    from brambleloop.learn import freshness as R
    from brambleloop.learn.models import LearnGap, Lesson

    db = _db()
    spec = {**_spec(), "products": ["gone", "live"]}
    rev = _approve(db, "sc-dc", spec)
    with db.session() as s:
        s.add(Product(slug="live", title="Live", status="certified"))
        s.add(LearnGap(topic="stitch:sc", state="COVERED",
                       evidence=[{"support_case_id": 4, "product_slug": "live"}]))
        s.add(LearnGap(topic="stitch:ch", state="QUEUED",
                       evidence=[{"support_case_id": 5, "product_slug": "live"}]))
    from brambleloop.learn import service
    service.link_topics(db, "stitch:dc", "stitch:ch", "prerequisite", {"rule": "fixture"})

    out = R.monitor(db, links={"sc-dc": [{"target": "lesson:nope"}]}, media={"a" * 64})
    kinds = {f["kind"] for f in out["lessons"]["sc-dc"]["findings"]}
    assert kinds == {"stale_link", "obsolete_product", "new_evidence", "support_gap"}
    assert out["lessons"]["sc-dc"]["state"] == "STALE"
    unknown = R.monitor(db)["lessons"]["sc-dc"]["findings"]
    assert any(f["kind"] == "broken_media" and f.get("state") == "UNKNOWN" for f in unknown)
    assert any(f["kind"] == "broken_media" and f.get("sha256") for f in
               R.monitor(db, media=set())["lessons"]["sc-dc"]["findings"])

    # Terminology drift in a saved spec is found (the taxonomy is the authority).
    with db.session() as s:
        row = s.get(Lesson, "sc-dc")
        bad = copy.deepcopy(row.spec)
        bad["steps"][0]["term"] = "dc"
        row.spec = bad
    assert any(f["kind"] == "terminology" for f in
               R.monitor(db, media={"a" * 64})["lessons"]["sc-dc"]["findings"])

    # An update that still names a missing product is refused; a clean one is a new
    # revision whose reviews reset.
    try:
        R.update(db, "sc-dc", spec, media={"a" * 64})
        raise AssertionError("an update carrying an obsolete product was saved")
    except R.UpdateRefused:
        pass
    fixed = {**_spec(), "products": ["live"]}
    up = R.update(db, "sc-dc", fixed, media={"a" * 64})
    assert up["revision"] != rev and up["state"] == "DRAFT"
    with db.session() as s:
        assert s.get(Lesson, "sc-dc").reviews == []


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
