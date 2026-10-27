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


# ---- F-823 -----------------------------------------------------------------------------------

def _swatch_cir(stitch="sc", rows=3, width=6, hook=4.0, weight="worsted"):
    return {"slug": "swatch", "title": "Practice swatch", "version": "1",
            "construction": "flat_rows",
            "gauge": {"stitches_per_10cm": 18, "rows_per_10cm": 20, "stitch_type": stitch,
                      "hook_mm": hook},
            "materials": [{"name": "practice yarn", "yarn_weight": weight}],
            "components": [{"name": "swatch", "construction": "flat_rows", "foundation": width,
                            "rows": [{"index": i, "ops": [{"stitch": stitch, "count": width}],
                                      "declared_count": width, "turning_chain": 1}
                                     for i in range(1, rows + 1)]}]}


def test_f823_foundational_lessons_are_checked_against_beginner_mistakes():
    from brambleloop.learn import beginner_sim as B

    db = _db()
    sc_step = {"stitch": "sc", "repeat": 2, "consumes": 2, "produces": 2, "term": "sc",
               "instruction": "Work one sc under both loops of each of next two sts."}
    guarded = {**_spec(topics=("technique:gauge", "stitch:sc"), problem="single crochet"),
               "steps": [{**sc_step, "instruction": sc_step["instruction"] +
                          " Keep the chain flat, not twisted."}],
               "swatch": {"cir": _swatch_cir()}}
    assert LS.validate_spec(guarded) == [], LS.validate_spec(guarded)
    _approve(db, "sc-basics", guarded)
    ok = B.check(db, "sc-basics")
    assert ok["foundational"] and ok["verdict"] == "PASS", ok
    m = ok["mistakes"]
    assert m["wrong_stitch_count"]["state"] == "DETECTED"         # compiler disagrees
    assert m["skipped_turning_chain"]["state"] == "DETECTED"      # written rows change
    assert m["missed_gauge"]["state"] == "DETECTED"               # twin width moves
    assert m["reversed_rs_ws"]["state"] == "NOT_APPLICABLE"

    # The same lesson without its swatch, loop or chain warning leaves mistakes unguarded.
    bare = {**_spec(topics=("technique:gauge",), problem="single crochet"),
            "steps": [{**sc_step, "instruction": "Work one sc in each of next two sts."}]}
    _approve(db, "sc-bare", bare)
    bad = B.check(db, "sc-bare")
    assert bad["verdict"] == "FAIL"
    assert {"wrong_loop", "wrong_stitch_count", "missed_gauge"} <= set(bad["unguarded"])

    from brambleloop.learn import graph_feeds
    graph_feeds.seed_prerequisites(db)            # fpdc -> dc -> hdc -> sc -> ch: advanced
    _approve(db, "dc-only", _spec(topics=("stitch:fpdc",), problem="front post dc"))
    assert B.check(db, "dc-only")["verdict"] == "NOT_REQUIRED"


# ---- F-829 -----------------------------------------------------------------------------------

def test_f829_teaching_improves_through_the_loop_without_changing_technical_truth():
    from brambleloop.learn import teaching_loop as L
    from brambleloop.learn.models import Lesson

    db = _db()
    spec = _spec()
    rev = _approve(db, "sc-dc", spec)
    key = L.observe(db, "sc-dc", observation="learners stall at step 2",
                    evidence_ref="support-cluster:fixture")
    try:
        L.experiment(db, key, variant=spec)
        raise AssertionError("EXPERIMENT ran before HYPOTHESIS")
    except L.TeachingRefused:
        pass
    L.hypothesise(db, key, change="explanation", hypothesis="name the turning chain first",
                  metric="step-2 completion")
    wrong = copy.deepcopy(spec)
    wrong["steps"][1]["repeat"] = 4
    wrong["steps"][1]["consumes"] = wrong["steps"][1]["produces"] = 4
    for bad, needle in ((wrong, "technical truth"),):
        try:
            L.experiment(db, key, variant=bad)
            raise AssertionError("a variant that changes the truth was accepted")
        except L.TeachingRefused as exc:
            assert needle in str(exc)
    drifted = copy.deepcopy(spec)
    drifted["steps"][1]["instruction"] = "Chain 5, then work one dc in each of next three sts."
    try:
        L.experiment(db, key, variant=drifted)
        raise AssertionError("a variant stating a new number was accepted")
    except L.TeachingRefused as exc:
        assert "number 5" in str(exc)
    better = copy.deepcopy(spec)
    better["steps"][1]["instruction"] = ("First chain 3 for the turning chain, then work one "
                                         "dc in each of next three sts.")
    L.experiment(db, key, variant=better)
    assert L.measure(db, key, baseline=0.5, result=0.7, n=10)["measurement"] == "UNMEASURED"
    L.measure(db, key, baseline=0.5, result=0.6, n=40)
    assert L.validate(db, key)["stage"] == "VALIDATE"
    out = L.promote(db, key)
    assert out["history"] == ["OBSERVE", "HYPOTHESIS", "EXPERIMENT", "MEASURE", "VALIDATE",
                              "PROMOTE"]
    with db.session() as s:
        row = s.get(Lesson, "sc-dc")
        assert row.revision == out["promoted_revision"] != rev and row.reviews == []

    # A loop whose lesson changed revision mid-experiment is rejected, not promoted.
    k2 = L.observe(db, "sc-dc", observation="o", evidence_ref="e")
    L.hypothesise(db, k2, change="sequencing", hypothesis="dc first", metric="m")
    swapped = copy.deepcopy(better)
    swapped["steps"].reverse()
    L.experiment(db, k2, variant=swapped)                      # reorder is allowed here
    L.measure(db, k2, baseline=0.5, result=0.9, n=40)
    LS.save_lesson(db, "sc-dc", {**better, "learner_problem": "work sc and dc"})
    assert L.validate(db, k2)["stage"] == "REJECT"


# ---- F-771 / F-811 ---------------------------------------------------------------------------

def _free(**kw):
    base = {"key": "article:granny-square", "topics": ["stitch:dc"],
            "features": ["technique_steps"],
            "steps": ["Chain 4 and join.", "Work 3 dc into the ring.", "Fasten off."],
            "cta": [{"text": "The full blanket pattern is in the shop.", "position": 4}]}
    return {**base, **kw}


def test_f771_free_and_paid_are_differentiated_not_duplicated():
    from brambleloop.learn import ladder as D

    paid = {"slug": "granny-blanket", "topics": ["stitch:dc"],
            "features": ["full_pattern", "all_sizes", "chart", "printable_pdf"]}
    ok = D.rung(_free(), paid)
    assert ok["state"] == "LADDER"
    assert ok["paid_only"] == ["all_sizes", "chart", "full_pattern", "printable_pdf"]
    dup = D.rung(_free(features=["technique_steps", "full_pattern", "chart", "all_sizes"]),
                 paid)
    assert dup["state"] == "DUPLICATE" and dup["paid_only"] == ["printable_pdf"]


def test_f811_the_ladder_is_relevant_and_the_free_piece_stays_useful():
    from brambleloop.learn import ladder as D

    paid = {"slug": "granny-blanket", "topics": ["stitch:dc"],
            "features": ["full_pattern", "chart"]}
    assert D.rung(_free(), {**paid, "topics": ["stitch:tr"]})["state"] == "NOT_RELEVANT"
    teaser = D.rung(_free(steps=["Chain 4 and join.",
                                 "Buy the full pattern to finish the rest of the square."]), paid)
    assert teaser["state"] == "DECEPTIVE" and "defers" in teaser["problems"][0]
    early = D.rung(_free(cta=[{"text": "Shop now", "position": 1}]), paid)
    assert early["state"] == "DECEPTIVE" and "interrupts" in early["problems"][0]
    assert D.rung(_free(steps=[]), paid)["state"] == "DECEPTIVE"


# ---- F-772 -----------------------------------------------------------------------------------

def test_f772_one_canonical_record_fans_out_and_drift_is_found():
    from brambleloop.core.models import PatternVersion, Product
    from brambleloop.learn import distribution as M

    db = _db()
    with db.session() as s:
        p = Product(slug="granny-blanket", title="Granny Blanket", status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0", cir_json={}, certified=True,
                             release_hash="r1"))
        s.add(PatternVersion(product_id=p.id, version="1.1", cir_json={}, certified=True,
                             release_hash="r2"))
        s.add(PatternVersion(product_id=p.id, version="2.0-draft", cir_json={},
                             certified=False))
    rec = M.canonical(db, "granny-blanket", price_cad=9.5, files={"US.pdf": "b" * 64},
                      claims=["US and UK terms", "digital pattern"])
    assert rec["version"] == "1.1" and rec["release_hash"] == "r2"   # newest certified only
    out = M.fan_out(rec)
    assert all(c["state"] == "CLOSED" and not c["sent"] for c in out["channels"].values())
    assert {c["payload"]["price_cad"] for c in out["channels"].values()} == {9.5}
    same = {k: rec[k] for k in M.FIELDS}
    sync = M.sync(rec, {"etsy": same, "own_site": {**same, "price_cad": 8.0,
                                                   "files": {"US.pdf": "c" * 64}}})
    assert sync["channels"]["etsy"]["state"] == "IN_SYNC"
    pend = sync["channels"]["own_site"]
    assert pend["state"] == "UPDATE_PENDING"
    assert {d["field"] for d in pend["differences"]} == {"price_cad", "files"}
    assert sync["channels"]["email_store"]["state"] == "UNKNOWN"
    try:
        M.canonical(db, "granny-blanket", price_cad=9.5, files={"US.pdf": "short"}, claims=[])
        raise AssertionError("a file without its digest was accepted")
    except M.RecordRefused:
        pass


# ---- F-810 -----------------------------------------------------------------------------------

def test_f810_lead_magnets_carry_goal_provenance_version_and_attribution():
    from datetime import date

    from brambleloop.learn import lead_magnets as G

    db = _db()
    magnet = {"slug": "gauge-checklist", "kind": "checklist", "version": "1",
              "title": "Gauge checklist",
              "goal": {"signups": 4, "by": "2026-12-31"},
              "provenance": {"rights": "brambleloop_original", "sha256": "d" * 64,
                             "sources": ["learn:gauge"]}}
    for missing in ("goal", "provenance", "version"):
        try:
            G.register(db, {k: v for k, v in magnet.items() if k != missing})
            raise AssertionError(f"registered without {missing}")
        except G.MagnetRefused:
            pass
    G.register(db, magnet)
    try:
        G.register(db, {**magnet, "title": "rewritten"})
        raise AssertionError("an existing version was rewritten")
    except G.MagnetRefused:
        pass
    assert G.attribute(db, "gauge-checklist", "1")["state"] == "UNMEASURED"
    sign = [{"subscriber": "s1", "consent": True, "purchases": [9.5]},
            {"subscriber": "s2", "consent": True, "purchases": []},
            {"subscriber": "s3", "consent": False, "purchases": [12.0]}]
    a = G.attribute(db, "gauge-checklist", "1", signups=sign, today=date(2026, 11, 1))
    assert a["state"] == "IN_PROGRESS" and a["signups"] == 2 and a["progress"] == 0.5
    assert a["excluded_without_consent"] == 1 and a["attributed_revenue_cad"] == 9.5
    assert a["buyer_share"] == 0.5
    late = G.attribute(db, "gauge-checklist", "1", signups=sign, today=date(2027, 1, 2))
    assert late["state"] == "MISSED"


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
