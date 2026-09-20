"""A certificate for the listing, and the thing that invalidates it without being told.

Requirement 70. `gates.certificate` certifies the pattern -- that the document is what the
compiler says. This certifies the listing -- that what a buyer sees was checked, against which
geometry, under which policy. Two objects because they go stale for different reasons: a
listing's size card can be quoting geometry that has since changed while the pattern's own
certificate stays perfectly valid.

The load-bearing word in the requirement is *invalidates*. A revocation step is a step
somebody forgets, and the forgetting is silent -- the listing goes on carrying a certificate
that was true about a version nobody sells any more. So validity is recomputed from the
current inputs rather than read from a flag.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.publish import eligibility as E  # noqa: E402
from brambleloop.publish import listing_set as L  # noqa: E402

GEOMETRY = {"blanket_width_cm": 90.0, "blanket_length_cm": 122.0}
CLAIMS = {"finished_size": "90 x 122 cm", "difficulty": "intermediate"}


def _frame(**kw) -> L.CertifiedFrame:
    args = dict(position=1, asset_id="hero", sha256="a" * 64, job=E.DESIRE,
                purpose=E.CONVERSION_CREATIVE, medium="AI_LIFESTYLE_CONCEPT",
                measurement_sources=())
    args.update(kw)
    return L.CertifiedFrame(**args)


def _cert(**kw) -> L.ListingCertificate:
    args = dict(slug="autumn-throw", version="1",
                frames=[_frame(),
                        _frame(position=3, asset_id="size", sha256="b" * 64, job=E.SCALE,
                               purpose=E.CUSTOMER_INFORMATION, medium="INFOGRAPHIC",
                               measurement_sources=("blanket-w", "blanket-l"))],
                gate_results={g: E.PASSED for g in E.GATES},
                geometry=GEOMETRY, claims=CLAIMS, policy_version="v3",
                disclosures=("ai_assisted",))
    args.update(kw)
    return L.certify(**args)


# ---- what it records ------------------------------------------------------


def test_the_certificate_records_everything_the_requirement_names():
    out = _cert().to_dict()
    for key in ("frames", "frame_order", "gate_results", "measurement_sources",
                "disclosures", "policy_version"):
        assert key in out, key
    assert out["frames"][0]["sha256"] == "a" * 64
    assert out["measurement_sources"] == ["blanket-l", "blanket-w"]


def test_the_frame_order_is_recorded_by_position():
    cert = _cert()
    assert cert.frame_order == ("hero", "size")


def test_a_frame_with_no_asset_hash_is_refused():
    try:
        _frame(sha256="abc")
    except L.ListingSetRefused as e:
        assert "told from the one that is live" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a certificate approved a file it could not identify")


def test_two_frames_claiming_one_position_is_refused():
    try:
        _cert(frames=[_frame(), _frame(asset_id="other", sha256="c" * 64)])
    except L.ListingSetRefused as e:
        assert "same position" in str(e)
    else:  # pragma: no cover
        raise AssertionError("two frames took one position")


def test_a_frame_job_the_vocabulary_does_not_have_is_refused():
    try:
        _frame(job="VIBES")
    except L.ListingSetRefused as e:
        assert "is not a frame job" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an invented job was certified")


# ---- it records what was checked, not that checking happened --------------


def test_a_gate_that_never_ran_cannot_be_certified_around():
    partial = {g: E.PASSED for g in E.GATES if g != E.COMMERCIAL_QA}
    try:
        _cert(gate_results=partial)
    except L.ListingSetRefused as e:
        assert "never ran" in str(e)
        assert "not that checking happened" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a certificate papered over an unrun gate")


def test_a_failing_gate_cannot_be_certified():
    results = {g: E.PASSED for g in E.GATES}
    results[E.DATA_TRUTH] = E.FAILED
    try:
        _cert(gate_results=results)
    except L.ListingSetRefused as e:
        assert "failing gates" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a failing set was certified")


def test_a_gate_nobody_has_heard_of_is_refused():
    results = {g: E.PASSED for g in E.GATES}
    results["VIBE_CHECK"] = E.PASSED
    try:
        _cert(gate_results=results)
    except L.ListingSetRefused as e:
        assert "are not promotion gates" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an invented gate was recorded as passing")


def test_an_empty_set_is_refused():
    try:
        _cert(frames=[])
    except L.ListingSetRefused as e:
        assert "is not a set" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an empty listing set was certified")


def test_a_certificate_with_no_geometry_could_never_be_invalidated():
    try:
        _cert(geometry={})
    except L.ListingSetRefused as e:
        assert "the one thing it is for" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a certificate was issued that nothing could invalidate")


# ---- invalidated by its inputs, not by being revoked ----------------------


def test_an_unchanged_product_keeps_its_certificate():
    out = L.still_valid(_cert(), geometry=GEOMETRY, claims=CLAIMS, policy_version="v3")
    assert out["valid"] is True
    assert out["invalidated_by"] == []


def test_a_geometry_change_invalidates_without_anybody_revoking_it():
    changed = dict(GEOMETRY, blanket_width_cm=95.0)
    out = L.still_valid(_cert(), geometry=changed, claims=CLAIMS)
    assert out["valid"] is False
    assert out["invalidated_by"] == [L.GEOMETRY_CHANGED]
    assert "a step somebody forgets" in out["recomputed"]


def test_a_geometry_change_affects_the_frames_that_quote_measurements():
    changed = dict(GEOMETRY, blanket_width_cm=95.0)
    out = L.still_valid(_cert(), geometry=changed, claims=CLAIMS)
    assert out["affected_assets"] == ["size"], "the hero quotes no measurement"


def test_a_claims_change_affects_the_whole_set_rather_than_the_number_frames():
    out = L.still_valid(_cert(), geometry=GEOMETRY,
                        claims=dict(CLAIMS, difficulty="beginner"))
    assert out["invalidated_by"] == [L.CLAIMS_CHANGED]
    assert sorted(out["affected_assets"]) == ["hero", "size"]
    assert "not confined to the frames that show numbers" in out["why"]


def test_a_policy_change_invalidates_too():
    out = L.still_valid(_cert(), geometry=GEOMETRY, claims=CLAIMS, policy_version="v4")
    assert L.POLICY_CHANGED in out["invalidated_by"]


def test_policy_is_only_checked_when_a_version_is_supplied():
    out = L.still_valid(_cert(), geometry=GEOMETRY, claims=CLAIMS)
    assert L.POLICY_CHANGED not in out["invalidated_by"]


def test_validity_is_recomputed_rather_than_stored():
    cert = _cert()
    assert not hasattr(cert, "valid")
    assert not hasattr(cert, "revoked")


def test_state_says_why_this_is_not_the_release_certificate():
    out = L.state()
    assert out["requirement"] == 70
    assert "gates.certificate certifies the pattern" in out["distinct_from"]
    assert "never read from a flag" in out["note"]


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
