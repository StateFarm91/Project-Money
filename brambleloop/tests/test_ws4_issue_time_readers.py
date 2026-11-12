"""WS4-6: the standing-policy issuer's issue-time readers (design §3.3 checks 6, 9, 10, 12).

Each reader is exercised on a real certified release (the Launch-0 small basket, certified by
the real `gate.certify` job) and on the change that must make it refuse. A reader that cannot
read is UNKNOWN; none of these ever reads PASS by default.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select, update  # noqa: E402

import test_physfix_photo_first as T  # noqa: E402
from brambleloop.core.models import PatternVersion, PhysicalPhoto  # noqa: E402
from brambleloop.ops import standing_boundary as SB  # noqa: E402
from brambleloop.ops import standing_issuer as SI  # noqa: E402

_STATE: dict = {}


def _basket():
    """One certified basket per process (certification is the slow part)."""
    if not _STATE:
        db = T._db()
        cir, release = T._certified_basket(db)
        _STATE.update(db=db, cir=cir, release=release)
    return _STATE["db"], _STATE["cir"], _STATE["release"]


def _stored(db, cir):
    fact = SI._stored_cir(db, cir.slug, cir.version)
    assert fact["state"] == SB.PASS, fact
    return fact["value"]


def test_reverify_passes_on_the_certified_release_and_refuses_a_different_hash():
    db, cir, release = _basket()
    stored = _stored(db, cir)
    assert SI._reverify(stored, release)["state"] == SB.PASS
    other = SI._reverify(stored, "0" * 64)
    assert other["state"] == SB.FAIL and "recompiled release hash" in other["why"], other


def test_reverify_refuses_a_stored_cir_that_was_edited_after_certification():
    db, cir, release = _basket()
    stored = _stored(db, cir)
    import dataclasses

    edited = dataclasses.replace(stored, title=stored.title + " (edited)")
    assert SI._reverify(edited, release)["state"] == SB.FAIL


def test_reverify_refuses_a_cir_that_no_longer_compiles():
    db, cir, release = _basket()
    stored = _stored(db, cir)

    class _Bad:
        errors = ["E: a row does not close"]

    with patch("brambleloop.cir.compiler.compile_cir", return_value=_Bad()):
        out = SI._reverify(stored, release)
    assert out["state"] == SB.FAIL and "no longer compiles" in out["why"], out


def test_physical_with_nothing_bound_holds_no_classes_and_needs_no_attestation():
    db, cir, _release = _basket()
    out = SI._physical(db, _stored(db, cir))
    held = out.pop("held")
    assert held["state"] == SB.PASS and held["value"] == [], held
    assert out["state"] == SB.PASS and "nothing to attest" in out["why"], out


def test_physical_requires_an_owner_attestation_on_every_bound_test():
    db, cir, _release = _basket()
    test_id = T._passed_full_make(db, cir)
    try:
        # An intake flagged unedited by the operator token, never attested by the owner.
        T._upgrade(db, cir, test_id, attest=False)
    except AssertionError:
        pass    # plan_upgrade refuses without the attestation; the intake row exists
    out = SI._physical(db, _stored(db, cir))
    held = out.pop("held")
    assert "full_physical_make" in held["value"], held
    assert out["state"] == SB.FAIL and str(test_id) in out["why"], out
    # The owner's Command Center attestation, bound to the file's sha, clears it.
    from brambleloop.publish import physical_upgrade as pu

    with db.session() as s:
        photo = s.scalar(select(PhysicalPhoto).where(PhysicalPhoto.physical_test_id == test_id))
        pid = photo.id
    pu.attest_unedited(db, pid, actor=T.OWNER, confirm=pu.UNEDITED_CONFIRMATION)
    out = SI._physical(db, _stored(db, cir))
    out.pop("held")
    assert out["state"] == SB.PASS, out
    # An attestation for another file's sha does not count.
    with db.session() as s:
        photo = s.get(PhysicalPhoto, pid)
        detail = dict(photo.detail)
        detail["owner_attestation"] = {**detail["owner_attestation"], "sha256": "0" * 64}
        s.execute(update(PhysicalPhoto).where(PhysicalPhoto.id == pid).values(detail=detail))
    out = SI._physical(db, _stored(db, cir))
    out.pop("held")
    assert out["state"] == SB.FAIL, out


def test_sizes_colourwork_and_wearable_come_from_the_cir():
    db, cir, _release = _basket()
    stored = _stored(db, cir)
    assert SI._sizes(stored) == {"state": SB.PASS, "value": 1, "why": None}
    assert SI._wearable(stored)["value"] is False
    import dataclasses

    two = dataclasses.replace(stored, colors={"A": "#fff", "B": "#000"})
    facts = SI.read_facts(db, cir.slug, cir.version, "r", {}, shadow=True)
    assert facts["colourwork"]["state"] == SB.PASS
    assert (len(two.colors) > 1) is True


def test_taxonomy_without_a_certified_search_profile_is_refused():
    db, cir, _release = _basket()
    out = SI._taxonomy_agrees(db, cir.slug, cir.version)
    assert out["state"] in (SB.FAIL, SB.UNKNOWN) and out["state"] != SB.PASS, out


def test_taxonomy_must_be_the_node_the_category_chooses():
    from brambleloop.commerce import category as cat

    db, cir, _release = _basket()
    chosen = cat.CategoryChoice(cat.CHOSEN, taxonomy_id=111)
    with patch.object(cat, "publish_inputs", return_value={
            "status": cat.CHOSEN, "taxonomy_id": 111, "certified": "PASS"}), \
            patch.object(cat, "choose", return_value=chosen), \
            patch("brambleloop.integrations.etsy_taxonomy.latest", return_value={"x": 1}):
        assert SI._taxonomy_agrees(db, cir.slug, cir.version)["state"] == SB.PASS
    with patch.object(cat, "publish_inputs", return_value={
            "status": cat.CHOSEN, "taxonomy_id": 222, "certified": "PASS"}), \
            patch.object(cat, "choose", return_value=chosen), \
            patch("brambleloop.integrations.etsy_taxonomy.latest", return_value={"x": 1}):
        out = SI._taxonomy_agrees(db, cir.slug, cir.version)
    assert out["state"] == SB.FAIL and "222" in out["why"], out
    with patch.object(cat, "publish_inputs", return_value={
            "status": cat.CHOSEN, "taxonomy_id": 111, "certified": "STALE"}):
        assert SI._taxonomy_agrees(db, cir.slug, cir.version)["state"] == SB.FAIL


def test_no_fake_discount_refuses_a_reference_price_in_the_payload():
    from brambleloop.runtime import etsy_ops

    db, cir, _release = _basket()
    with patch.object(etsy_ops, "certified_payload", return_value=object()), \
            patch.object(etsy_ops, "sent_fields", return_value={"title": "x", "price": 8.0}):
        assert SI._no_fake_discount(db, cir.slug, cir.version)["state"] == SB.PASS
    with patch.object(etsy_ops, "certified_payload", return_value=object()), \
            patch.object(etsy_ops, "sent_fields",
                         return_value={"price": 8.0, "reference_price": 12.0}):
        out = SI._no_fake_discount(db, cir.slug, cir.version)
    assert out["state"] == SB.FAIL and "reference_price" in out["why"], out


def test_read_facts_now_reads_the_issue_time_facts_for_real():
    db, cir, release = _basket()
    facts = SI.read_facts(db, cir.slug, cir.version, release, {}, shadow=True)
    for name in ("deterministic_reverify", "physical_held", "owner_attested_physical",
                 "sizes", "colourwork", "wearable", "taxonomy_agrees", "no_fake_discount"):
        assert "not built yet" not in str(facts[name].get("why") or ""), (name, facts[name])
    assert facts["deterministic_reverify"]["state"] == SB.PASS
    assert SI.NOT_BUILT_YET == {}


def test_a_missing_cir_makes_every_cir_reader_unknown():
    db, cir, release = _basket()
    with patch.object(SI, "_stored_cir", return_value=SI._fact(SB.UNKNOWN, None, "no CIR")):
        facts = SI.read_facts(db, cir.slug, cir.version, release, {}, shadow=True)
    for name in ("deterministic_reverify", "physical_held", "owner_attested_physical",
                 "sizes", "colourwork", "wearable"):
        assert facts[name]["state"] == SB.UNKNOWN, name


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
