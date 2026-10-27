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


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
