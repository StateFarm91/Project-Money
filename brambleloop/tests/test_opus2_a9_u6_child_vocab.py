"""Review U6: the A1 parts the A9 listing package depends on (F3, N6, N10).

F3 HIGH: an infant-only product noun ("Pacifier Clip", "Teething Ring", "12M Hat") was not a
child-audience word, so a listing package's copy could name a baby product with no
children's decision. `assemble` and `eligibility.name_truth` read the same
`launch0.child_words_in_listing`, so the vocabulary is the package's safety boundary.

N6 / N10 MED: an unreadable construction and an unmeasurable sewn-on piece must hold (they
are UNKNOWN), and before this file no test failed if either returned [] instead.
"""
from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import test_a1r_child_safety_core as harness
from brambleloop.gates import small_parts
from brambleloop.products import inventory, launch0
from brambleloop.publish import eligibility, pdf

# The reviewer's probe P2: each returned () before this fix.
INFANT_TITLES = ("Pacifier Clip", "Teething Ring", "Rattle", "Bib", "Binky Leash",
                 "Stroller Blanket", "Toy", "Plushie", "Doll", "12M Hat", "0-3m Bonnet",
                 "Soother Holder", "Teether Ring", "Booties Set")
NOT_A_CHILD_CLAIM = ("Market Basket", "Cat Toy Mouse", "Dog Toys Set",
                     "Uses 200m of worsted yarn", "Plant hanger, 6 mm cord, 12 mm ring",
                     "Everyday Storage Basket")


def _adult():
    cir = inventory._engineered("market-basket-small")
    assert launch0.childrens_decision_for(cir)[0] == launch0.NOT_FOR_CHILDREN
    return cir


def test_f3_infant_product_nouns_are_child_audience_words():
    for title in INFANT_TITLES:
        assert launch0.child_words_in(title), title
        assert launch0.child_words_in_listing({"title": "Basket", "tags": [title]}), title
        assert launch0.child_words_in_listing(
            {"title": "Basket", "description": f"A {title.lower()}.", "tags": []}), title


def test_f3_pet_toys_and_yarn_lengths_are_not_child_claims():
    for text in NOT_A_CHILD_CLAIM:
        assert launch0.child_words_in(text) == (), (text, launch0.child_words_in(text))
    # A pet qualifier covers only its own toy: a second, unqualified toy still holds.
    assert "toy" in launch0.child_words_in("Cat toy and a toy for the nursery")


def test_f3_an_adult_design_retitled_with_an_infant_noun_is_held():
    adult = _adult()
    for title in INFANT_TITLES:
        changed = dataclasses.replace(adult, title=title)
        assert launch0.childrens_decision_for(changed)[0] == launch0.UNDECIDED, title
        assert harness._refused(changed), title


def test_f3_listing_copy_with_an_infant_noun_is_undecided_and_not_publishable():
    adult = _adult()
    for title in INFANT_TITLES:
        listing = {"title": title, "description": "plain", "tags": []}
        assert launch0.childrens_decision_for(adult, listing=listing)[0] == launch0.UNDECIDED
        reasons = eligibility.name_truth(adult, listing)
        assert any("child audience" in r for r in reasons), (title, reasons)
    for text in NOT_A_CHILD_CLAIM:
        listing = {"title": text, "description": "plain", "tags": []}
        assert launch0.childrens_decision_for(adult, listing=listing)[0] \
            == launch0.NOT_FOR_CHILDREN, text


def test_f3_listing_package_blocks_infant_copy_through_the_worker():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.models import Listing, PatternVersion, Product
    from brambleloop.gates.certificate import GAUGE_STANDARD
    from brambleloop.publish import listing_package
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import listing_package_ops  # noqa: F401
    from brambleloop.runtime.worker import Worker

    with tempfile.TemporaryDirectory() as directory:
        old_dir = os.environ.get("BRAMBLELOOP_ARTIFACT_DIR")
        os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = directory + "/artifacts"
        try:
            url = f"sqlite:///{directory}/listing.sqlite"
            db = Database(url, scratch=True)
            db.create_all()
            Registry(db).seed_defaults()
            cir = _adult()
            with db.session() as s:
                product = Product(slug=cir.slug, title=cir.title, status="certified")
                s.add(product)
                s.flush()
                s.add(PatternVersion(product_id=product.id, version=cir.version,
                                     certified=True, cir_json=cir.to_dict(),
                                     release_hash="a" * 64,
                                     certificate={"granted": True,
                                                  "gauge_standard": GAUGE_STANDARD}))
                s.add(Listing(product_slug=cir.slug, version=cir.version, state="draft",
                              title="Pacifier Clip Basket", description="A plain basket",
                              tags=["teether"], price_cad=5, release_hash="a" * 64))
            JobQueue(db).enqueue("listing", "listing.package", {},
                                 idempotency_key="opus2:a9u6:f3")
            assert Worker(db, "a9u6-f3", job_types=["listing.package"]).run_once()
            package = listing_package.latest(db, cir.slug, cir.version)
            assert package and package["state"] == listing_package.BLOCKED, package
            assert package["identity"]["childrens_decision"][0] == launch0.UNDECIDED, package
            assert any(b["source"] == "childrens_decision" for b in package["blockers"]), \
                package["blockers"]
            assert package["publishes"] is False
        finally:
            if old_dir is None:
                os.environ.pop("BRAMBLELOOP_ARTIFACT_DIR", None)
            else:
                os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = old_dir


class _Unreadable:
    """A construction field that is present but cannot be read."""

    def __bool__(self):
        return True

    def __iter__(self):
        raise RuntimeError("construction cannot be read")


def test_n6_an_unreadable_construction_is_a_stuffed_form_and_is_held():
    adult = _adult()
    bad = dataclasses.replace(adult)
    # The CIR constructor validates components, so the unreadable field is set afterwards:
    # this is a stored CIR whose construction cannot be read back.
    object.__setattr__(bad, "components", _Unreadable())
    reasons = launch0.stuffed_form_reasons(bad)
    assert reasons and "unreadable" in reasons[0] and "UNKNOWN" in reasons[0], reasons
    assert launch0.closed_stuffed_form(bad) is True
    # The adult basket's written exemption does not cover a construction nobody can read.
    assert launch0.childrens_decision_for(bad)[0] == launch0.UNDECIDED
    assert harness._refused(bad)


def test_n10_unmeasurable_sewn_on_pieces_block_an_assigned_product():
    adult = _adult()
    with patch.object(small_parts, "separable_pieces",
                      side_effect=RuntimeError("geometry cannot be read")):
        blocks = small_parts.blocking(adult)
        assert blocks and small_parts.UNKNOWN in blocks[0] and "unmeasurable" in blocks[0], \
            blocks
        try:
            pdf._refuse_an_undecided_childrens_title(adult, ("toys", "under_3"))
        except pdf.ChildrensDecisionRequired as exc:
            assert exc.reason == "small_parts", exc.reason
        else:
            raise AssertionError("an unmeasurable assigned product cleared the PDF gate")


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
