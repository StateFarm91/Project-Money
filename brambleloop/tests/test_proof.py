"""#8: what this company may honestly claim about a pattern, and what it may not.

The requirement's own sentence is "marketing must distinguish proof levels honestly". These
tests are about the three ways that distinction gets blurred: a rung that leapfrogs, a phrase
that claims more than the evidence, and a photograph nobody asked permission for.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    PatternVersion, PhysicalTest, Product, utcnow,
)
from brambleloop.quality import proof as P  # noqa: E402


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/proof.sqlite")
    db.create_all()
    return db


def _certified(db, slug="lantern-throw", *, stages=("compile", "twin", "write", "reverse"),
               granted=True):
    with db.session() as s:
        product = Product(slug=slug, title="Lantern Throw")
        s.add(product)
        s.flush()
        s.add(PatternVersion(product_id=product.id, version="1.0.0", cir_json={},
                             certified=granted,
                             certificate={"granted": granted, "stages_run": list(stages)}))
    return slug


def test_proof_accumulates_and_does_not_leapfrog():
    """A customer photograph before anybody made the thing licenses nothing new.

    Reporting the highest rung reached *in isolation* is how a listing ends up claiming a
    test nobody ran. The claim level is the highest contiguous rung, and the rung that ran
    ahead is reported rather than averaged away -- it is real, and it is not a test.
    """
    ahead = P.reached({"deterministic_validation": True, "customer_project": True})
    assert ahead["claim_level"] == 1, ahead
    assert ahead["ahead_of_the_ladder"] == ["customer_project"]
    assert "leapfrogs" in ahead["why"]
    assert "customers have made this" not in ahead["licenses"]

    contiguous = P.reached({"deterministic_validation": True,
                            "independent_reverse_compilation": True})
    assert contiguous["claim_level"] == 2
    assert "independently verified" in contiguous["licenses"]


def test_nothing_established_is_level_zero_and_says_so():
    """A pattern that has not compiled proves nothing, and the honest word for that is nothing."""
    nothing = P.reached({})
    assert nothing["level"] == 0
    assert nothing["rung"] == ""
    assert nothing["licenses"] == []
    assert "has not been compiled" in nothing["does_not_prove"]


def test_language_is_checked_against_the_level_not_against_intention():
    """"Maker tested" on a pattern nobody has made is the same sentence either way.

    This is the only place the difference between meaning it and reaching for it stops
    mattering, which is what makes it a control rather than a good habit.
    """
    at_two = {"deterministic_validation": True, "independent_reverse_compilation": True}
    refused = P.check_claim("Maker tested and independently verified", at_two)
    phrases = {r["phrase"] for r in refused}
    assert "maker tested" in phrases, refused
    assert "independently verified" not in phrases, "a licensed phrase was refused"
    assert all(r["needs_level"] > r["have_level"] for r in refused)
    assert "a recorded sample assessment" in refused[0]["why"]

    # And the same text at the level that earns it passes.
    at_three = {**at_two, "physical_tester_example": True}
    assert P.check_claim("Maker tested and independently verified", at_three) == []


def test_every_rung_states_what_it_does_not_prove():
    """The honest half of a proof ladder, and the half that gets left out.

    "The counts add up" and "a human can follow it" are different claims, and a ladder that
    only says what each rung establishes invites the reader to round it up.
    """
    for rung in P.LADDER:
        assert rung.does_not_prove.strip(), rung.key
        assert rung.checked_by.strip(), rung.key
        assert rung.licenses, rung.key
    # Every licensed phrase belongs to exactly one rung, or the level it needs is ambiguous.
    phrases = [p for r in P.LADDER for p in r.licenses]
    assert len(phrases) == len(set(phrases)), phrases


def test_a_rung_is_a_query_and_not_a_field():
    """No parameter sets a rung. Each one counts something in the database."""
    db = _db()
    slug = _certified(db)
    at_two = P.report(db, slug)
    assert at_two["level"] == 2, at_two["states"]
    assert at_two["states"]["physical_tester_example"] is False

    with db.session() as s:
        s.add(PhysicalTest(product_slug=slug, version="1.0.0", tester_ref="t1",
                           completed_at=utcnow(), passed=True))
    assert P.report(db, slug)["level"] == 3


def test_a_sample_that_failed_is_evidence_and_is_not_a_proof_point():
    """Rung three says the thing came out. A sample that disagreed is the opposite.

    It is also the most valuable result a sample can produce, which is why it is stored --
    but storing it and counting it as proof are different things.
    """
    db = _db()
    slug = _certified(db)
    with db.session() as s:
        s.add(PhysicalTest(product_slug=slug, version="1.0.0", tester_ref="t1",
                           completed_at=utcnow(), passed=False))
    report = P.report(db, slug)
    assert report["states"]["physical_tester_example"] is False, report["states"]
    assert report["level"] == 2


def test_an_ungranted_certificate_establishes_nothing():
    """A certificate is granted only when no stage errored. An ungranted one is a refusal."""
    db = _db()
    slug = _certified(db, granted=False)
    report = P.report(db, slug)
    assert report["level"] == 0, report["states"]


def test_the_upper_rungs_are_present_and_false_rather_than_absent():
    """A missing key and an unreached rung look identical to a caller and are not.

    These two wait on orders -- the executor's `customers` gate -- and a listing has to say
    "not established", which is what False means here.
    """
    db = _db()
    report = P.report(db, _certified(db))
    assert report["states"]["customer_project"] is False
    assert report["states"]["repeat_purchase"] is False
    assert set(report["not_reachable_yet"]) == {"customer_project", "repeat_purchase"}


def test_a_testers_photograph_without_a_recorded_permission_cannot_be_published():
    """"With appropriate permission" means recorded, not remembered.

    A reference rather than a boolean, because somebody has to be able to go and look. This
    is the one asset class where getting it wrong is a wrong done to a named person.
    """
    from brambleloop.gates.asset_truth import Asset, AssetClass, Provenance, check_asset
    from brambleloop.publish import substitution  # noqa: F401 - import parity with the gate

    from test_accessibility import _twin, _two_colour

    cir = _two_colour()
    _result, twin = _twin(cir)

    unconsented = Asset(
        asset_id="tester-1", asset_class=AssetClass.PHYSICAL_PRODUCT_PHOTO,
        provenance=Provenance(source="tester", created_by="publishing"))
    codes = {f.code for f in check_asset(unconsented, cir, twin)}
    assert "ASSET_CONSENT_MISSING" in codes, codes

    consented = Asset(
        asset_id="tester-2", asset_class=AssetClass.PHYSICAL_PRODUCT_PHOTO,
        provenance=Provenance(source="tester", created_by="publishing",
                              consent_ref="consent/2026-09-20/tester-1"))
    assert "ASSET_CONSENT_MISSING" not in {
        f.code for f in check_asset(consented, cir, twin)}

    # Our own camera work needs no permission record, and demanding one would be noise.
    ours = Asset(asset_id="ours", asset_class=AssetClass.PHYSICAL_PRODUCT_PHOTO,
                 provenance=Provenance(source="camera", created_by="publishing"))
    assert "ASSET_CONSENT_MISSING" not in {f.code for f in check_asset(ours, cir, twin)}


def test_consent_required_says_why_rather_than_returning_a_boolean():
    assert P.consent_required("camera", None)["publishable"] is True
    refused = P.consent_required("customer", "")
    assert refused["publishable"] is False
    assert "not implied consent" in refused["why"]
    assert P.consent_required("customer", "consent/123")["publishable"] is True


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
