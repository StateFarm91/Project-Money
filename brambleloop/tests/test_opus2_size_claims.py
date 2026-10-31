"""OPUS2-P0: size-claim truth (owner report 2026-10-27, permanent regression).

"Nesting Baskets, three sizes" was advertised at CA$6.50 and the PDF downloaded from it was
`market-basket-medium@1.2.0`, one basket. Each size is its own CIR and release, so a listing
or PDF that promises more sizes than its release delivers must refuse at publication.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_size_claims.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")
_ART = tempfile.mkdtemp(prefix="opus2_size_art_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = _ART

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Job, JobStatus, Listing, PatternVersion, Product  # noqa: E402
from brambleloop.gates import size_claims as Z  # noqa: E402
from brambleloop.products import launch0 as l0  # noqa: E402
from brambleloop.publish.pdf import build_pattern_pdf  # noqa: E402


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='opus2_size_')}/s.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _release(db, cir, *, title=None, description="", tags=(), pdf=True):
    from brambleloop.core.artifacts import ArtifactStore

    with db.session() as s:
        p = Product(slug=cir.slug, title=cir.title, status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=cir.version, cir_json=cir.to_dict(),
                             certified=True, release_hash="r" * 64,
                             certificate={"granted": True}))
        if title is not None:
            s.add(Listing(product_slug=cir.slug, version=cir.version, title=title,
                          description=description, tags=list(tags), state="draft",
                          release_hash="r" * 64))
    if pdf:
        doc = build_pattern_pdf(cir)
        stored = ArtifactStore(_ART).put(f"{cir.slug}/{cir.version}/US.pdf", doc.pdf_bytes,
                                         "application/pdf")
        with db.session() as s:
            s.add(Job(agent="publishing", job_type="assets.build", status=JobStatus.DONE,
                      inputs={"slug": cir.slug, "version": cir.version},
                      outputs={"pdf_sha256": stored.sha256,
                               "pdf_sha256_by_terminology": {"US": stored.sha256}}))


def test_the_parser_reads_promises_not_incidental_words():
    fail = ["Nesting Baskets, three sizes", "Crochet basket pattern in 3 sizes",
            "small, medium and large baskets", "Sizes S/M/L", "multiple sizes included",
            "two different sizes"]
    ok = ["Hexagonal Bread Basket", "Hexagon Coaster Set (4)", "set of 6 ornaments",
          "One size. Finished size 20 x 16 cm.", "1 size",
          "The medium basket. The small and large are sold separately.",
          "This listing is the medium basket; the small and large are separate listings.",
          "Measure your gauge swatch: 10 cm square."]
    assert fail and ok
    for t in fail:
        assert Z.check_texts({"listing": t})["state"] == Z.FAIL, t
    for t in ok:
        assert Z.check_texts({"listing": t})["state"] == Z.PASS, t
    v = Z.check_texts({"listing title": "Nesting Baskets, three sizes"})
    assert v["claimed"] == 3 and "3 sizes" in v["reasons"][0]
    assert "listing title" in v["reasons"][0]
    assert Z.check_texts({"x": "nesting baskets"})["reasons"][0].count("several")


def test_the_reported_basket_defect_refuses_at_its_release():
    """The owner's case: a single basket release whose listing says three sizes."""
    db = _db()
    medium = l0.cir_for("basket_medium")
    assert (medium.slug, medium.version) == ("market-basket-medium", "1.2.0")
    _release(db, medium, title="Nesting Baskets, three sizes",
             description="Three hexagon baskets that nest.")
    v = Z.for_release(db, slug=medium.slug, version=medium.version)
    assert v["state"] == Z.FAIL and v["delivered"] == 1 and v["claimed"] == 3
    assert any("listing title" in r for r in v["reasons"])
    assert v["pdf"].startswith("customer PDF"), v["pdf"]
    # The medium PDF itself makes no size promise: the defect is the listing, not the pattern.
    assert "customer PDF" not in v["claims"]


def test_an_honest_single_size_listing_passes_with_its_pdf_read():
    db = _db()
    small = l0.cir_for("basket_small")
    _release(db, small, title="Hexagonal Bread Basket",
             description="One hexagonal basket, 16.0 cm across the points. The larger "
                         "baskets are separate listings.", tags=("bread basket", "hexagon"))
    v = Z.for_release(db, slug=small.slug, version=small.version)
    assert v["state"] == Z.PASS and v["reasons"] == [], v
    assert v["pdf"].startswith("customer PDF")


def test_tags_are_read_too():
    db = _db()
    small = l0.cir_for("basket_small")
    _release(db, small, title="Hexagonal Bread Basket", tags=("nesting baskets",))
    v = Z.for_release(db, slug=small.slug, version=small.version)
    assert v["state"] == Z.FAIL and "listing tags" in v["reasons"][0]


def test_no_listing_is_unknown_without_a_reason_and_an_unread_pdf_is_reported():
    db = _db()
    small = l0.cir_for("basket_small")
    _release(db, small, title=None, pdf=False)
    v = Z.for_release(db, slug=small.slug, version=small.version)
    assert v["state"] == Z.UNKNOWN and v["reasons"] == []
    db = _db()
    _release(db, small, title="Hexagonal Bread Basket", pdf=False)
    v = Z.for_release(db, slug=small.slug, version=small.version)
    # Review OPUS2A F1.4: an unread customer PDF refuses; it is never passed on the listing.
    assert v["state"] == Z.FAIL and v["pdf"].startswith("no completed assets.build")
    assert any("was not read" in r for r in v["reasons"])


def test_a_graded_release_size_chart_is_reference_but_its_listing_may_not_promise_sizes():
    from brambleloop.products import garments as G

    d = next(iter(G.DESIGNS.values()))()
    sizes = d.sourced_sizes()
    cir = d.build(sizes[len(sizes) // 2])
    assert cir.grading is not None and len(cir.grading.sizes) > 1
    db = _db()
    _release(db, cir, title=cir.title, description="A drop-shoulder pullover.")
    v = Z.for_release(db, slug=cir.slug, version=cir.version)
    # The PDF prints "size XL of 9" and "any of the 9 sizes in the size chart": reference.
    assert v["state"] == Z.PASS, v["reasons"]
    assert v["graded"] == {"size": cir.grading.size, "family": len(cir.grading.sizes)}
    db = _db()
    _release(db, cir, title=f"{cir.title}, {len(cir.grading.sizes)} sizes")
    v = Z.for_release(db, slug=cir.slug, version=cir.version)
    assert v["state"] == Z.FAIL


def test_the_publish_gate_refuses_a_release_whose_listing_overpromises_sizes():
    from brambleloop.publish import release_gates

    db = _db()
    medium = l0.cir_for("basket_medium")
    _release(db, medium, title="Nesting Baskets, three sizes")
    g = release_gates.for_publish(db, slug=medium.slug, version=medium.version,
                                  store_root=_ART, read_only=True)
    assert g["blocks_release"] is True
    assert any(r.startswith("size-claim truth") for r in g["reasons"]), g["reasons"][:5]
    db = _db()
    _release(db, medium, title="Hexagonal Storage Basket")
    g = release_gates.for_publish(db, slug=medium.slug, version=medium.version,
                                  store_root=_ART, read_only=True)
    assert not any(r.startswith("size-claim truth") for r in g["reasons"])


def test_launched_candidates_never_promise_more_sizes_than_one_release_delivers():
    """The static half. On a base where the three-size nursery family is still launched it is
    the one finding; once W-LISTING's D-W4-OWNER-BASKET-IDENTITY change lands it is held for
    verification and there are none."""
    found = Z.launch0_findings()
    if "nursery-nesting-baskets" in l0.LAUNCH0_SLUGS:
        assert [f["candidate"] for f in found] == ["nursery-nesting-baskets"], found
        assert found[0]["variants"] == 3 and found[0]["claimed"] == 3
    else:
        assert found == [], found


# Independent review OPUS2A (54766c9e), F1.1-F1.3: every probe row, pinned.
REVIEW_MUST_FAIL = (
    "Three sizes, yarn not included.", "Three sizes\u2014yarn not included",
    "3 sizes included (pattern sold separately for hats)",
    "three sizes, each size is its own pattern", "three-size set", "set of 3 baskets",
    "a set of three baskets", "trio of baskets", "3 basket sizes",
    "three different basket sizes", "small, medium, large", "small/medium/large",
    "small \u00b7 medium \u00b7 large", "S, M, L", "sizes: S M L", "sizes S to XL", "XS-3XL",
    "Diameters 20 cm, 25 cm and 30 cm",
    "Nesting baskets in three sizes, yarn not included.",
)
REVIEW_MUST_PASS = (
    "If your gauge is tight, try a hook one or two sizes larger.",
    "Works in all sizes of yarn", "Fits a 1 m/s fan", "a set of four coasters",
    "A pair of placemats", "Other sizes sold separately.",
    "16.0 cm across the points, 13.9 cm across the flats and about 9 cm tall",
    "Finished size: 20 cm wide and 15 cm tall", "Worsted weight yarn, 5.0 mm hook (US H-8)",
)


def test_review_opus2a_probe_rows_are_each_judged_as_the_review_expects():
    assert REVIEW_MUST_FAIL and REVIEW_MUST_PASS
    for t in REVIEW_MUST_FAIL:
        assert Z.check_texts({"listing description": t})["state"] == Z.FAIL, t
    for t in REVIEW_MUST_PASS:
        assert Z.check_texts({"listing description": t})["state"] == Z.PASS, t


def test_a_generic_disclaimer_never_hides_a_size_claim_in_the_same_sentence():
    for tail in ("yarn not included", "hook sold separately", "pattern available separately"):
        t = f"Nesting baskets in three sizes, {tail}."
        v = Z.check_texts({"listing description": t})
        assert v["state"] == Z.FAIL and v["claimed"] == 3, t


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
