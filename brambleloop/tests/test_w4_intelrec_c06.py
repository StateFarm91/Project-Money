"""W4-INTELREC C06 (children's catalogue and launch mix): F-366 and F-370.

OFFLINE (the radar pool and fixture outcomes; not production evidence).
Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_intelrec_c06.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.creative.children import PRIORITY_FAMILY, SEGMENTS  # noqa: E402
from brambleloop.launch import mix  # noqa: E402
from brambleloop.radar import opportunity as O  # noqa: E402

TODAY = date(2026, 10, 27)


def test_f366_the_optimizer_weighs_every_segment_and_keeps_section_33():
    out = mix.optimize(today=TODAY)
    assert set(out["after"]["counts"]) == set(SEGMENTS)
    assert out["after"]["children_considered"] is True
    assert out["after"]["children_in_mix"] >= 1, out
    cap = max(1, int(mix.MAX_SEGMENT_SHARE * len(out["selected"])))
    assert all(v <= cap for v in out["after"]["counts"].values()), out["after"]
    before_ok = O.select_portfolio(today=TODAY).constraints_met
    assert all(out["constraints_met"][k] or not before_ok[k] for k in before_ok)


def test_f366_a_mix_with_no_childrens_product_is_repaired_when_one_is_eligible():
    scored = [c for c in O.score_pool(today=TODAY)]
    kids = [c for c in scored if mix.segment_of(c.seed) == PRIORITY_FAMILY]
    assert kids, "the pool holds children's seeds"
    # Bias the scores so the plain optimizer leaves children out, then let mix repair it.
    biased = [O.ScoredConcept(seed=c.seed, score=(c.score - 50 if c in kids else c.score),
                              components=c.components) for c in scored]
    plain = mix.evaluate(O.select_portfolio(biased, today=TODAY).selected)
    out = mix.optimize(scored=biased, today=TODAY)
    assert plain["children_in_mix"] == 0 or out["after"]["children_in_mix"] >= 1
    assert out["after"]["children_in_mix"] >= 1, out["reasons"]
    assert any("baby_children segment" in r for r in out["reasons"]) or \
        plain["children_in_mix"] >= 1


def test_f370_rebalancing_waits_for_evidence_and_stays_inside_owner_bounds():
    shares = {PRIORITY_FAMILY: 0.2, "home_decor": 0.4, "seasonal": 0.4}
    thin = mix.rebalance(shares, {PRIORITY_FAMILY: {"visits": 100, "orders": 9}})
    assert thin["status"] == mix.UNMEASURED and thin["proposed"] == shares
    strong = mix.rebalance(shares, {
        PRIORITY_FAMILY: {"visits": 1000, "orders": 40},          # 4% conversion
        "home_decor": {"visits": 1000, "orders": 10},             # 1%
        "seasonal": {"visits": 1000, "orders": 10}})
    assert strong["status"] == "PROPOSED"
    assert strong["proposed"][PRIORITY_FAMILY] > 0.2
    assert strong["proposed"][PRIORITY_FAMILY] - 0.2 <= mix.MAX_STEP + 1e-9
    assert strong["proposed"]["home_decor"] < 0.4
    owner = mix.OwnerConstraints(min_share={PRIORITY_FAMILY: 0.15},
                                 max_share={PRIORITY_FAMILY: 0.22})
    capped = mix.rebalance(shares, {
        PRIORITY_FAMILY: {"visits": 1000, "orders": 40},
        "home_decor": {"visits": 1000, "orders": 10}}, owner=owner)
    assert capped["proposed"][PRIORITY_FAMILY] == 0.22             # owner max holds
    weak = mix.rebalance(shares, {
        PRIORITY_FAMILY: {"visits": 1000, "orders": 1},
        "home_decor": {"visits": 1000, "orders": 40}}, owner=owner)
    assert weak["proposed"][PRIORITY_FAMILY] == 0.15               # owner min holds


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
