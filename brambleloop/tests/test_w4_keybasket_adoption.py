"""W4-KEYBASKET: what adopting the Housewarming Key Basket (0.1.0 -> 1.0.0) would mean.

`products.moment_candidates` keeps a candidate at 0.x until an owner-governed adoption. The
adoption is prepared, not made: `ADOPTED_RELEASE` is empty; `PROPOSED_ADOPTION` names 1.0.0.
These tests pin what the owner would be deciding: the pattern content is unchanged, only the
release identity moves (new fingerprint, new release hash, so re-certification through the
normal chain), and the product's own demand is UNKNOWN.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_keybasket_adoption.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.products import launch0 as l0  # noqa: E402
from brambleloop.products import moment_candidates as mc  # noqa: E402

SLUG = "housewarming-key-basket"
FAILS = 0


def check(name, fn):
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as e:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {e!r}")


def test_no_adoption_has_been_made_and_one_is_proposed():
    assert mc.ADOPTED_RELEASE == {}
    assert mc.PROPOSED_ADOPTION == {SLUG: "1.0.0"}
    assert mc.release_version(SLUG) == mc.VERSION == "0.1.0"
    cir = l0.cir_for("key_basket")
    assert cir.version == "0.1.0" and cir.fingerprint.startswith("c63743691cf8"), (
        cir.version, cir.fingerprint)   # the release W4-CAP1 certified, unchanged


def test_adoption_changes_the_release_identity_and_nothing_in_the_pattern():
    saved = dict(mc.ADOPTED_RELEASE)
    try:
        mc.ADOPTED_RELEASE.update(mc.PROPOSED_ADOPTION)
        adopted = l0.cir_for("key_basket")
    finally:
        mc.ADOPTED_RELEASE.clear()
        mc.ADOPTED_RELEASE.update(saved)
    pre = l0.cir_for("key_basket")
    assert adopted.version == "1.0.0" and pre.version == "0.1.0"
    a, b = adopted.to_dict(), pre.to_dict()
    a.pop("version")
    b.pop("version")
    assert a == b, "adoption must not change the pattern itself"
    assert adopted.fingerprint != pre.fingerprint   # so the chain re-certifies it


def test_the_adopted_release_certifies_under_a_new_release_hash():
    from brambleloop.gates.certificate import certify

    pre = certify(mc.housewarming_key_basket("0.1.0"))
    adopted = certify(mc.housewarming_key_basket("1.0.0"))
    assert pre.granted and adopted.granted
    assert pre.release_hash and adopted.release_hash
    assert pre.release_hash != adopted.release_hash


def test_its_own_demand_is_unknown_and_says_where_it_came_from():
    from brambleloop.runtime import pipeline

    assert pipeline.product_seed(SLUG) is None
    assert pipeline._seed_for(SLUG) is None
    why = l0.NO_RADAR_CONCEPT[SLUG]
    assert "UNKNOWN" in why and "moment-first" in why, why


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        check(name, fn)
    sys.exit(1 if FAILS else 0)
