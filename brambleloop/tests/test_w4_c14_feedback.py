"""W4-C14: customer feedback into lessons and content economics (F-766, F-769, F-802,
F-820, F-825). Fixture cases only; no network, CA$0."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import SupportCase  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.products.builder import CATALOGUE, build  # noqa: E402


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


# ---- F-766 -----------------------------------------------------------------------------------

def test_f766_failures_become_placed_tips_checked_against_the_compiler():
    from brambleloop.support import project_tips as P

    cir = build(CATALOGUE["cloudline-baby-blanket"])
    comp = cir.components[0].name
    db = _db()
    with db.session() as s:
        for ref, q in (("buyer-a", "I ended up with 3 extra stitches at row 12, count is off"),
                       ("buyer-b", "row 12 my stitch count is wrong, missing a stitch"),
                       ("buyer-c", "my blanket is curling, too tight at row 4"),
                       ("buyer-d", "lovely pattern thank you")):
            s.add(SupportCase(customer_ref=ref, product_slug=cir.slug, version=cir.version,
                              question=q))
    failures = P.failures_from_cases(db)
    failures.append({"source": "test", "ref": "tester:7", "product_slug": cir.slug,
                     "component": None, "row": 9999, "text": "the join drifts at row 9999"})
    failures.append({"source": "test", "ref": "tester:8", "product_slug": cir.slug,
                     "component": None, "row": None, "text": "seaming the edges was unclear"})
    out = P.tips(failures, cir=cir)

    counts = compile_cir(cir).counts(comp)
    tip = next(t for t in out["proposed"] if t["mode"] == "stitch_counts")
    assert tip["row"] == 12 and tip["placement"] == "row 12"
    assert f"{counts[11]} stitches" in tip["tip"] and tip["checked_against_compiler"]
    assert len(tip["tip"]) <= P.MAX_TIP_CHARS and tip["state"] == "PROPOSED"
    assert tip["evidence"]["distinct_customers"] == 2
    # No customer text or reference in a tip: case ids only.
    assert "buyer-a" not in str(out) and "extra stitches" not in str(out)
    # One customer is that customer's trouble, not a tip.
    assert any(b["mode"] == "tension" and b["row"] == 4 for b in out["below_evidence"])
    # A tester failure is enough evidence, but a row the pattern does not have is refused.
    assert any(r["mode"] == "joins" and r["row"] == 9999 for r in out["refused"])
    # Evidence with no row is real, but not "at the exact point".
    assert any(u["mode"] == "seaming" for u in out["needs_placement"])
    assert len(out["unclassified"]) == 1
    assert set(P.classify("tension markers join symmetry stitch count size seam blocking")) \
        == set(P.MODES)


# ---- F-769 -----------------------------------------------------------------------------------

def test_f769_gallery_corroborates_but_never_overrides_or_replaces_testing():
    from brambleloop.support import gallery_evidence as G

    imgs = [{"ref": "studio-1", "source": "studio", "version": "1.0", "plausible": True},
            {"ref": "tester-1", "source": "tester", "version": "1.0", "plausible": True},
            {"ref": "old-1", "source": "customer", "version": "0.9", "plausible": False}]
    ok = G.weigh(product_truth="PASS", physical_test="NOT_RUN", images=imgs, version="1.0")
    assert ok["gallery"]["state"] == "CORROBORATES" and ok["gallery"]["other_version"] == ["old-1"]
    assert ok["confidence"] == G.TRUTH_WEIGHT + G.GALLERY_WEIGHT_CAP
    # The gallery never stands in for the physical test.
    assert ok["physical_test_outstanding"] and not ok["physical_test_satisfied"]

    failed = G.weigh(product_truth="FAIL", physical_test="PASS", images=imgs, version="1.0")
    assert failed["verdict"] == "FAIL" and failed["confidence"] == 0.0

    unknown = G.weigh(product_truth=None, physical_test=None, images=imgs, version="1.0")
    assert unknown["verdict"] == "UNKNOWN" and unknown["confidence"] is None

    bad = imgs + [{"ref": "cust-2", "source": "customer", "version": "1.0", "plausible": False}]
    contra = G.weigh(product_truth="PASS", physical_test="PASS", images=bad, version="1.0")
    assert contra["gallery"]["state"] == "CONTRADICTS" and contra["review_required"]
    assert contra["verdict"] == "PASS"            # the review decides, not the picture

    one_source = [imgs[0], {**imgs[0], "ref": "studio-2"}]
    assert G.gallery_support(one_source, version="1.0")["state"] == "INSUFFICIENT"


# ---- F-802 -----------------------------------------------------------------------------------

def _approve_tension_lesson(db):
    from brambleloop.learn import service as LS

    spec = {"author": "pattern-engineering", "learner_problem": "keep an even tension",
            "topics": ["failure:tension"], "terminology": "US",
            "assumptions": {"hook_mm": 4, "yarn_weight": "worsted"},
            "assets": [{"rights": "brambleloop_original", "source": "canonical-demo",
                        "sha256": "a" * 64}],
            "steps": [{"stitch": "sc", "repeat": 2, "consumes": 2, "produces": 2,
                       "term": "sc", "instruction": "Work one sc in each of next two sts."}]}
    rev = LS.save_lesson(db, "even-tension", spec)
    LS.review_lesson(db, "even-tension", rev, "independent-qa",
                     dict.fromkeys(LS.DIMENSIONS, "PASS"), "fixture-review:test-only")
    assert LS.approved_lesson(db, "even-tension") is not None
    return rev


def test_f802_repeated_confusion_proposes_an_experiment_and_queues_learn():
    from brambleloop.learn.models import LearnGap
    from brambleloop.support import lesson_trigger as T

    db = _db()
    sig = [
        # stitch counts: three people, two of them at row 12 of one product -> clarification
        {"kind": "question", "ref": "q1", "reporter": "a", "product_slug": "p1", "row": 12,
         "text": "my stitch count is off"},
        {"kind": "refund", "ref": "r1", "reporter": "b", "product_slug": "p1", "row": 12,
         "text": "refund please, extra stitches every time"},
        {"kind": "failed_validation", "ref": "v1", "product_slug": "p1", "row": 3,
         "text": "stitch count mismatch: count is wrong at row 3"},
        # tension: three people across reviews and tickets, no shared row -> lesson revision
        {"kind": "review_complaint", "ref": "rv1", "reporter": "c", "product_slug": "p2",
         "text": "came out too tight"},
        {"kind": "ticket", "ref": "t1", "reporter": "d", "product_slug": "p2",
         "text": "the edge is curling"},
        {"kind": "ticket", "ref": "t2", "reporter": "e", "product_slug": "p2",
         "text": "fabric is wavy and loose"},
        # sizing: one person repeating themselves is not repeated confusion
        {"kind": "ticket", "ref": "t3", "reporter": "f", "product_slug": "p3",
         "text": "it is too big"},
        {"kind": "ticket", "ref": "t4", "reporter": "f", "product_slug": "p3",
         "text": "still too big"},
    ]
    out = T.propose(db, sig)
    by_mode = {p["mode"]: p for p in out["proposals"]}
    assert set(by_mode) == {"stitch_counts", "tension"}
    sc = by_mode["stitch_counts"]
    assert sc["experiment"] == "pattern_clarification" and sc["target"]["row"] == 12
    assert sc["distinct_reporters"] == 3 and sc["baseline"] == "UNMEASURED"
    assert by_mode["tension"]["experiment"] == "new_lesson"
    assert by_mode["tension"]["formats"] == ["diagram", "tutorial"]
    assert any(w["mode"] == "sizing" for w in out["watching"])
    with db.session() as s:
        gap = s.get(LearnGap, "failure:tension")
        assert gap.state == "QUEUED" and gap.evidence[0]["refs"] == ["rv1", "t1", "t2"]
        assert "too tight" not in str(gap.evidence)

    # An approved lesson on the topic turns the proposal into a revision of that lesson.
    rev = _approve_tension_lesson(db)
    again = {p["mode"]: p for p in T.propose(db, sig, orders=200)["proposals"]}
    assert again["tension"]["experiment"] == "revise_lesson"
    assert again["tension"]["target"] == {"slug": "even-tension", "revision": rev}
    assert again["tension"]["baseline"] == 1.5
    with db.session() as s:
        gap = s.get(LearnGap, "failure:tension")
        assert gap.state == "COVERED" and len(gap.evidence) == 1   # same evidence, once


# ---- F-820 -----------------------------------------------------------------------------------

def test_f820_community_signals_reach_the_ledger_with_privacy_and_rights():
    from sqlalchemy import select

    from brambleloop.core.models import Lesson
    from brambleloop.support import community as C

    db = _db()
    yes = {"learning": True, "reuse": False}
    sig = [
        {"kind": "project_photo", "ref": "ph1", "reporter": "ann@example.com",
         "product_slug": "p1", "outcome": "failure", "text": "seams pulled apart",
         "consent": {"learning": True, "reuse": True}, "photo_ref": "img://ph1"},
        {"kind": "project_photo", "ref": "ph2", "reporter": "bob", "product_slug": "p1",
         "outcome": "failure", "text": "the seaming gaps", "consent": yes,
         "photo_ref": "img://ph2"},
        {"kind": "community_post", "ref": "cp1", "reporter": "cat", "product_slug": "p1",
         "outcome": "failure", "text": "whipstitch seams show"},
        {"kind": "support", "ref": "s1", "reporter": "dan", "product_slug": "p1",
         "outcome": "failure", "text": "my seam came undone", "consent": {}},
        {"kind": "review", "ref": "rv1", "reporter": "eve", "product_slug": "p1",
         "outcome": "success", "text": "border and blocking came out great"},
    ]
    out = C.intake(db, sig)
    assert out["admitted"] == 4 and out["declined_no_consent"] == 1
    pub = out["published"]
    assert len(pub) == 1 and pub[0]["mode"] == "seaming" and pub[0]["contributors"] == 3
    assert pub[0]["reusable_photos"] == ["img://ph1"]          # ph2 had no reuse consent
    assert pub[0]["subject"] == "instruction_clarity"
    with db.session() as s:
        lessons = list(s.scalars(select(Lesson)))
        assert len(lessons) == 1 and "learn" in lessons[0].routed_to
        text = lessons[0].statement
    assert "3 community members struggle with seaming" in text
    for private in ("ann@example.com", "pulled apart", "img://ph2", "undone"):
        assert private not in str(out) and private not in text
    assert any(b["outcome"] == "success" for b in out["below_threshold"])
    C.intake(db, sig)                                          # idempotent on the aggregate
    with db.session() as s:
        assert len(list(s.scalars(select(Lesson)))) == 1


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
