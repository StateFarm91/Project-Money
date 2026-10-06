"""Wave 3 lane B, K2: the storefront trust gate checks rendered assets and real copy
(F-233/234/235/237/263/279), never a brief string.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w3_store_ux_gate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.store_foundation import preview_sources as S  # noqa: E402
from brambleloop.store_foundation import storefront_gate as G  # noqa: E402

FAILS = 0


def check(name: str, fn) -> None:
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as exc:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")


def codes(result) -> set[str]:
    return {f["code"] for f in result["findings"]}


def test_every_row_is_reported():
    r = G.evaluate()
    assert set(r["rows"]) == set(G.ROWS)
    for row in r["rows"].values():
        assert row["status"] in ("PASS", "FAIL")
    # the ads gate inherits every storefront finding (F-263)
    assert len(r["rows"]["F-263"]["findings"]) == len(r["findings"])


def test_missing_assets_fail_closed_not_on_briefs():
    real = S._import
    S._import = lambda path: None
    try:
        r = G.evaluate()
    finally:
        S._import = real
    c = codes(r)
    assert {"STORE_ICON_NOT_RENDERED", "STORE_BANNER_NOT_RENDERED", "STORE_COPY_INTERIM"} <= c
    assert r["rows"]["F-233"]["status"] == "FAIL" and not r["ok"]
    assert G.problems.__doc__ and all(isinstance(p, str) for p in G.problems())


def test_icon_is_measured_at_etsy_sizes():
    import numpy as np

    good = np.full((40, 40, 3), 246.0)
    good[8:32, 8:14] = 47.0
    good[8:14, 8:32] = 47.0
    m = G.icon_legibility(good, 40)
    assert m["ok"], m
    faint = np.full((40, 40, 3), 246.0)
    faint[10:30, 10:30] = 225.0                  # a mark nobody can see at 40 px
    bad = G.icon_legibility(faint, 40)
    assert not bad["ok"] and bad["problems"], bad
    hairline = np.full((40, 40, 3), 246.0)
    for i in range(40):
        hairline[i, i] = 40.0                    # one-pixel diagonal: no surviving stroke
    assert not G.icon_legibility(hairline, 40)["ok"]


def test_lane_a_icon_passes_when_present():
    f, info = G.check_icon()
    if not info.get("rendered"):
        print("OK note: lane A identity_system absent; icon check reports NOT_RENDERED")
        assert {x["code"] for x in f} == {"STORE_ICON_NOT_RENDERED"}
        return
    assert set(info["sizes"]) == set(G.ICON_SIZES)
    for px, m in info["sizes"].items():
        assert m["ok"], (px, m)


def test_banner_checks_geometry_and_export():
    f, info = G.check_banner("Crochet patterns for a calmer, cosier home")
    c = {x["code"] for x in f}
    if not info["lockup"]:
        assert "STORE_BANNER_NOT_RENDERED" in c
        return
    assert info["lockup_phone_px"] >= G.LOCKUP_MIN_PHONE_PX
    assert "STORE_BANNER_LOCKUP_CROPPED" not in c
    # no raster export exists yet: that is a FAIL, not a pass on a description
    assert ("STORE_BANNER_NOT_EXPORTED" in c) == (not info["raster_export"])


def test_untrue_or_technical_copy_fails():
    real = S.copy

    def bad():
        v = dict(real().value)
        v["announcement"] = "Every row checked by our compiler. Handmade by Laura."
        v["about"] = ["Laura crochets every sample by hand."]
        v["laura_intro"] = ""
        v["trust"] = [{"title": "1,200 happy customers", "text": ""}]
        return S.Sourced(v, S.PEER, "test", [])

    S.copy = bad
    try:
        r = G.evaluate()
    finally:
        S.copy = real
    c = codes(r)
    assert "STORE_TOP_COPY_TECHNICAL" in c and "STORE_COPY_UNTRUE" in c, c
    assert "STORE_ABOUT_THIN" in c and "STORE_TRUST_THIN" in c, c
    assert "STORE_SOCIAL_PROOF_CLAIM" in c, c
    assert r["rows"]["F-234"]["status"] == "FAIL" and r["rows"]["F-235"]["status"] == "FAIL"


def test_announcement_must_match_the_grid():
    real = S.copy

    def off():
        v = dict(real().value)
        v["announcement"] = "New this week: a cabled cardigan and a market tote."
        return S.Sourced(v, S.PEER, "test", [])

    S.copy = off
    try:
        f, _ = G.check_continuity()
    finally:
        S.copy = real
    assert {x["code"] for x in f} == {"STORE_ANNOUNCEMENT_OFF_GRID"}
    assert all(x["row"] == "F-279" for x in f)


def test_sections_read_as_a_buyer_browses():
    assert G.INTERNAL_SECTION.search("launch0_home")
    assert G.INTERNAL_SECTION.search("Misc")
    assert not G.INTERNAL_SECTION.search("Home & Table")
    assert not G.INTERNAL_SECTION.search("Baby & Nursery")
    f, info = G.check_sections()
    assert info["sections"]
    assert not [x for x in f if x["code"] == "STORE_SECTION_NAME_INTERNAL"], f


def test_current_state_is_reported_honestly():
    r = G.evaluate()
    for row in ("F-234", "F-235", "F-237", "F-279"):
        assert r["rows"][row]["status"] == "PASS", (row, r["rows"][row]["findings"])
    # the only open storefront finding today is the banner raster export (or a missing peer)
    allowed = {"STORE_BANNER_NOT_EXPORTED", "STORE_ICON_NOT_RENDERED",
               "STORE_BANNER_NOT_RENDERED", "STORE_COPY_INTERIM", "STORE_BANNER_SIZE_UNSOURCED"}
    assert codes(r) <= allowed, codes(r)
    assert "STORE_BANNER_NOT_EXPORTED" in codes(r) or "STORE_BANNER_NOT_RENDERED" in codes(r)


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)

if FAILS:
    sys.exit(1)
