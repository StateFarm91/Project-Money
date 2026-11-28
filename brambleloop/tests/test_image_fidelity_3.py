"""IMAGE-FIDELITY-3 (19i27): a faithful hexagon coaster reads PASS on a wooden table.

Production 19i26 (0d295aecf, readback 10:16Z): both hexagon-coaster-set@1.2.1 gallery runs
parked at `fidelity_gate:product_truth` (not exhausted: UNKNOWN). `fidelity_unknowns`:
5 frames, `by_check {"coaster:palette": 18}`, `needs_vision_judge 0` -- every coaster (4 per
frame) of every frame, and no coaster check FAILed. The vision route was not the cause.

Root cause. `coaster:palette` is `_palette_check(structured=False)` inside the round piece's
measured region. Its "explained colour" model is the palette and every two-colour mix; a
pixel more than 22 dE76 from all of them is off-palette, and above 3 % of the region the check
reads UNKNOWN ("an occlusion, a prop or an invented motif"). A crochet hexagon is not a solid
disc: the magic-ring centre and the eyelets an increase leaves along the six corner spokes
show the TABLE through the fabric, darkened by the fabric's shadow. On a wooden table that is
a brown nowhere near the cream-wine line -- off-palette. With realistic eyelets it is 4-6 %
of each coaster: UNKNOWN on every coaster, with `colour_layout` still PASS (it ignores
off-palette pixels), which is exactly the production signature. A second, smaller leak: the
region was cut at radius 0.97 of the equivalent-area radius, which insets a disc's rim but
not a hexagon's flats (they lie at 0.95), so the contact shadow along the flats was measured.

Fix (`visual.fidelity`): the round region is inset by distance from the piece's own outline,
and small patches that are off the palette and explained by the fitted background, lit or in
shade, are the table seen through the fabric (`_see_through`), not yarn. Bounded: patches
<= 1 % of the piece, <= 8 % in all, and no ring (radial bin) more than 30 % see-through, else
UNKNOWN. Wrong colours and a missing wine round still FAIL; a table-coloured band, a lacy
piece and a mug over a coaster never PASS.

The layout reference drew the coaster as a disc on a cream square; the generator copies the
layout. It is now drawn as the twin's hexagon (`pattern_refs` 3.1.6). The two parked runs are
re-driven once by the existing UNKNOWN redrive, now keyed by (judge version, deterministic
check version `fidelity-checks/2`).

Every image here is a deterministic local render. There is no network and no paid call.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_image_fidelity_3.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import io
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402
from scipy import ndimage  # noqa: E402

import test_image_fidelity_route as R  # noqa: E402  (its harness refuses the network)
import test_w4_fidelity as W  # noqa: E402
from brambleloop.creative import pattern_refs as PR  # noqa: E402
from brambleloop.publish import charts  # noqa: E402
from brambleloop.visual import fidelity as F  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402

COASTERS = "hexagon-coaster-set"
CREAM, WINE = "#FAF6EB", "#6E1F2A"
WALNUT = (110, 72, 46)
HONEY = (176, 128, 82)
LIGHT_OAK = (196, 160, 118)


# ---- deterministic photographic hexagon coasters ------------------------------------------

_CTX: dict = {}


def _ctx():
    if not _CTX:
        cir = W._cir(COASTERS)
        comp, twin, is_round = PR._components(cir)[0]
        assert is_round and int(twin.sides) == 6, (is_round, twin.sides)
        src = np.asarray(charts.render_round_fabric(cir, twin).convert("RGB"), float)
        _CTX.update(cir=cir, make=int(comp.make), rounds=len(twin.chart_grid()), src=src)
    return _CTX


def _srgb(lin):
    return np.where(lin <= 0.0031308, 12.92 * lin,
                    1.055 * np.power(np.clip(lin, 0, None), 1 / 2.4) - 0.055) * 255


def _hex_t(size, rot):
    """Hexagon radius (1 on the outline) and angle of every pixel of a size x size tile."""
    yy, xx = np.mgrid[0:size, 0:size]
    c = (size - 1) / 2
    px, py = xx - c, yy - c
    apothem = (size / 2 - 1) * math.cos(math.radians(30))
    t = np.zeros((size, size))
    for k in range(6):
        a = math.radians(rot + 30 + 60 * k)
        t = np.maximum(t, (px * math.cos(a) + py * math.sin(a)) / apothem)
    return t, np.arctan2(py, px)


def _coaster(size, rot, src):
    """One hexagon coaster: the certified rounds as concentric hexagons, sc stitch relief in
    linear light, a scalloped outline (one bump per edge stitch)."""
    n = _ctx()["rounds"]
    t, ang = _hex_t(size, rot)
    h, w = src.shape[:2]
    rs = np.minimum(t, 1) * (min(h, w) / 2) * 0.995
    sx = np.clip((w - 1) / 2 + rs * np.cos(ang), 0, w - 1).astype(int)
    sy = np.clip((h - 1) / 2 + rs * np.sin(ang), 0, h - 1).astype(int)
    rgb = src[sy, sx]
    rp = (t * n) % 1.0
    sp = (ang / (2 * np.pi) * np.maximum(6, np.floor(t * n) * 6 + 6)) % 1.0
    shade = 0.55 + 0.45 * np.sin(np.pi * rp) ** 0.7 * np.sin(np.pi * sp) ** 0.5
    out = _srgb(F._lin(rgb) * shade[..., None])
    edge = 1 - 0.03 * (0.5 + 0.5 * np.cos(ang * 12 * n))
    return (Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)),
            Image.fromarray(((t <= edge) * 255).astype(np.uint8)))


def _eyelets(size, rot, hole_r):
    """The magic-ring centre and one eyelet per round on each of the six corner spokes."""
    n = _ctx()["rounds"]
    c, r = (size - 1) / 2, size / 2 - 1
    yy, xx = np.mgrid[0:size, 0:size]
    m = np.hypot(xx - c, yy - c) < 0.03 * size
    for k in range(6):
        a = math.radians(rot + 60 * k)
        for j in range(1, n):
            rr = (j / n) * r * 0.97
            m |= np.hypot(xx - (c + rr * math.cos(a)), yy - (c + rr * math.sin(a))) < hole_r * size
    return m


def scene(*, table=WALNUT, hole_r=0.015, through=0.45, src=None, mug_on=None,
          mug_beside=False, canvas=1400):
    """All coasters flat on a plain wooden table, top down: contact shadow, soft outline, the
    table seen through the eyelets in the fabric's shade (`through`). PNG bytes."""
    cx = _ctx()
    src = cx["src"] if src is None else src
    n = cx["make"]
    base = np.ones((canvas, canvas, 3)) * np.array(table, float)
    layer = Image.new("RGB", (canvas, canvas))
    alpha = Image.new("L", (canvas, canvas), 0)
    holes = np.zeros((canvas, canvas), bool)
    size = int(0.8 * canvas / (n * 1.1))
    x, centres = (canvas - n * size * 1.1) / 2, []
    for i in range(n):
        im, a = _coaster(size, 7 * i, src)
        X, Y = int(x), (canvas - size) // 2
        layer.paste(im, (X, Y), a)
        alpha.paste(a, (X, Y), a)
        if hole_r:
            holes[Y:Y + size, X:X + size] |= _eyelets(size, 7 * i, hole_r)
        centres.append((X + size // 2, Y + size // 2, size))
        x += size * 1.1
    dist = ndimage.distance_transform_edt(~(np.asarray(alpha) > 127))
    occlusion = np.where(dist > 0, np.exp(-dist / 6.0), 0) * 0.75
    img = Image.fromarray(np.clip(_srgb(F._lin(base) * (1 - occlusion)[..., None]), 0, 255)
                          .astype(np.uint8))
    img.paste(layer, (0, 0), alpha.filter(ImageFilter.GaussianBlur(1.0)))
    arr = np.asarray(img).copy()
    seen = np.clip(_srgb(F._lin(base) * through), 0, 255)
    arr[holes] = seen[holes]
    img = Image.fromarray(arr.astype(np.uint8))
    d = ImageDraw.Draw(img)
    mugs = [(c[0], c[1], int(c[2] * 0.36)) for i, c in enumerate(centres) if i == mug_on]
    if mug_beside:
        mugs.append((canvas // 2, canvas // 4, int(size * 0.42)))
    for mx, my, r in mugs:     # a white mug of coffee, from above
        d.ellipse((mx - r, my - r, mx + r, my + r), fill=(232, 236, 240))
        d.ellipse((mx - int(r * .8), my - int(r * .8), mx + int(r * .8), my + int(r * .8)),
                  fill=(92, 58, 36))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def recoloured(src_hex, dst_rgb):
    """The certified render with one yarn colour replaced (a wrong product)."""
    s = _ctx()["src"].copy()
    m = np.abs(s - np.array(F._hex_rgb(src_hex), float)).sum(-1) < 60
    s[m] = np.array(dst_rgb, float)
    return s


def _verify(data):
    return F.verify_anchor(data, _ctx()["cir"], judge=W.PASSING_JUDGE)


def _palette(v):
    return [c for c in v["checks"] if c["check"] == "coaster:palette"]


def _layout(v):
    return [c for c in v["checks"] if c["check"] == "coaster:colour_layout"]


# ---- 1. the root cause, reproduced ---------------------------------------------------------

def test_1_before_the_fix_the_table_through_the_eyelets_reads_unknown_on_every_coaster():
    """The production signature: coaster:palette UNKNOWN on all four coasters, colour layout
    PASS, nothing FAILed. With the see-through reading switched off (the 19i26 behaviour for
    these pixels) the faithful frame reproduces it; the off-palette colour is the shaded
    table."""
    data = scene()
    saved = F._see_through
    F._see_through = lambda lin, lab, bg, region, exp: (np.zeros_like(region),
                                                        {"share": 0.0, "patches": 0})
    try:
        v = _verify(data)
    finally:
        F._see_through = saved
    pals = _palette(v)
    assert v["status"] == "UNKNOWN" and v["failed"] == [], (v["status"], v["failed"])
    assert len(pals) == _ctx()["make"] == 4, len(pals)
    assert all(p["status"] == "UNKNOWN" for p in pals), [p["status"] for p in pals]
    assert all(p["off_palette_share"] > F.OFF_GLOBAL_MAX for p in pals), pals
    assert all(c["status"] == "PASS" for c in _layout(v)), _layout(v)
    assert v["unknown"] == ["coaster:palette"] * 4, v["unknown"]
    brown = pals[0]["off_palette_colour"]
    r, g, b = F._hex_rgb(brown)
    assert r > g > b and r < 140, f"the off-palette colour is the shaded table: {brown}"


def test_2_a_faithful_hexagon_coaster_frame_on_a_wooden_table_passes():
    for table in (WALNUT, HONEY, LIGHT_OAK, W.BG):
        v = _verify(scene(table=table))
        pals = _palette(v)
        assert v["status"] == "PASS", (table, v["unknown"], v["failed"],
                                       [p.get("why") for p in pals])
        assert len(pals) == 4 and all(p["status"] == "PASS" for p in pals), table
        assert all(c["status"] == "PASS" for c in _layout(v)), (table, _layout(v))
        for p in pals:
            assert p["clusters"]["cream"]["de76"] < 5 and p["clusters"]["wine"]["de76"] < 10, p
            assert 0 <= p["see_through"]["share"] <= F.SEE_THROUGH_MAX, p["see_through"]


def test_3_solid_hexagons_and_dark_eyelets_pass_too():
    solid = _verify(scene(hole_r=0))
    assert solid["status"] == "PASS", (solid["unknown"], solid["failed"])
    assert all(p["see_through"]["share"] < 0.01 for p in _palette(solid)), _palette(solid)
    dark = _verify(scene(table=HONEY, hole_r=0.016, through=0.18))
    assert dark["status"] == "PASS", (dark["unknown"], dark["failed"])


def test_4_the_inset_follows_a_hexagons_outline_not_a_disc_radius():
    """The measured region is inset by distance from the outline: a hexagon's flats (at 0.95
    of the equivalent radius) are inset as far as a disc's rim."""
    size = 400
    t, _ = _hex_t(size, 0)
    hexagon = t <= 1.0
    yy, xx = np.mgrid[0:size, 0:size]
    r_eq = math.sqrt(hexagon.sum() / math.pi)
    inner = hexagon & (ndimage.distance_transform_edt(hexagon) > F.INSET * 2 * r_eq)
    outline = hexagon & ~ndimage.binary_erosion(hexagon, iterations=2)
    assert outline.sum() > 0 and not (inner & outline).any()
    old = hexagon & (np.hypot(xx - (size - 1) / 2, yy - (size - 1) / 2) / r_eq < 1 - 2 * F.INSET)
    assert (old & outline).sum() > 0.2 * outline.sum(), "the radius cut kept the flats' outline"
    disc = np.hypot(xx - (size - 1) / 2, yy - (size - 1) / 2) <= 150
    rd = math.sqrt(disc.sum() / math.pi)
    by_dist = disc & (ndimage.distance_transform_edt(disc) > F.INSET * 2 * rd)
    by_rad = disc & (np.hypot(xx - (size - 1) / 2, yy - (size - 1) / 2) / rd < 1 - 2 * F.INSET)
    assert abs(int(by_dist.sum()) - int(by_rad.sum())) < 0.01 * disc.sum(), "a disc is unchanged"


# ---- 2. a wrong product still fails; an unreadable one stays UNKNOWN -----------------------

def test_5_a_wrong_colour_fails_off_palette():
    v = _verify(scene(src=recoloured(WINE, (31, 42, 110))))        # navy for wine
    assert v["status"] == "FAIL" and "OFF_PALETTE_COLOUR" in v["codes"], (v["status"],
                                                                         v["codes"])
    assert all(p["status"] == "FAIL" for p in _palette(v)), _palette(v)
    v = _verify(scene(src=recoloured(CREAM, (238, 205, 120))))     # mustard for cream
    assert v["status"] == "FAIL" and "OFF_PALETTE_COLOUR" in v["codes"], v["codes"]


def test_6_a_missing_wine_round_fails():
    v = _verify(scene(src=recoloured(WINE, F._hex_rgb(CREAM))))
    assert v["status"] == "FAIL", (v["status"], v["unknown"])
    assert len(v["failed"]) >= 4 and set(v["failed"]) <= {"coaster:palette",
                                                          "coaster:colour_layout"}, v["failed"]


def test_7_a_band_in_the_tables_colour_is_measured_not_seen_through():
    """The wine round worked in the table's shaded brown: a ring of 'table', never holes."""
    v = _verify(scene(src=recoloured(WINE, (60, 38, 24))))
    assert v["status"] != "PASS", v["status"]
    assert all(p["status"] != "PASS" for p in _palette(v)), _palette(v)
    lacy = _verify(scene(hole_r=0.03))                       # more table than fabric
    assert lacy["status"] == "UNKNOWN" and lacy["failed"] == [], (lacy["status"],
                                                                  lacy["failed"])
    assert all("surface beneath" in p["why"] for p in _palette(lacy)), _palette(lacy)


def test_8_a_mug_never_passes_and_an_unreadable_table_stays_unknown():
    on = _verify(scene(mug_on=1))
    assert on["status"] != "PASS", "a coaster under a mug cannot be verified"
    assert on["status"] == "FAIL" or "coaster:palette" in on["unknown"], on
    beside = _verify(scene(mug_beside=True))
    assert beside["status"] != "PASS" and any(
        c["check"] == "piece_count" and c["status"] != "PASS" for c in beside["checks"]), beside
    # a table with strong grain: not a plain surface, nothing is measured
    data = scene()
    arr = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"), float)
    yy = np.arange(arr.shape[0])[:, None]
    grain = 1 + 0.35 * np.sin(yy / 5.0 + np.sin(np.arange(arr.shape[1])[None, :] / 90.0) * 4)
    buf = io.BytesIO()
    Image.fromarray(np.clip(arr * grain[..., None], 0, 255).astype(np.uint8)).save(buf, "PNG")
    busy = _verify(buf.getvalue())
    assert busy["status"] == "UNKNOWN" and "isolation" in busy["unknown"], busy["unknown"]


# ---- 3. the layout reference draws hexagons -------------------------------------------------

def test_9_the_coaster_layout_reference_is_four_hexagons_on_the_plain_ground():
    cir = _ctx()["cir"]
    assert PR.VERSION == "pattern-refs/3.1.6", PR.VERSION
    comp, twin, _ = PR._components(cir)[0]
    tile = PR.polygon_fabric(charts.render_round_fabric(cir, twin), 6)
    w, h = tile.size
    assert abs(w / h - float(twin.width_cm) / float(twin.height_cm)) < 0.02, (w, h)
    a = np.asarray(tile)
    bg = np.array(PR.BACKGROUND)
    for x, y in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3), (w // 8, 2)):
        assert (a[y, x] == bg).all(), ("a hexagon's corners are the ground", x, y, a[y, x])
    for x, y in ((w // 2, h // 2), (3, h // 2), (w - 4, h // 2), (w // 2, 3), (w // 2, h - 4)):
        assert not (a[y, x] == bg).all(), ("inside the hexagon is fabric", x, y)
    wine = np.abs(a.astype(int) - np.array(F._hex_rgb(WINE))).sum(-1) < 40
    assert wine.sum() > 0.08 * (~(a == bg).all(-1)).sum(), "the wine round is drawn"
    # the wine round is a concentric HEXAGON: the same distance in from a flat and a point
    row = wine[h // 2]
    col = wine[:, w // 2]
    from_point = int(np.argmax(row)) / (w / 2)
    from_flat = int(np.argmax(col)) / (h / 2)
    assert abs(from_point - from_flat) < 0.05, (from_point, from_flat)
    layout, _basis = PR._render_layout(cir, PR._components(cir))
    L = np.asarray(layout)
    ground = (L == bg).all(-1)
    lab, n = ndimage.label(~ground)
    assert n == _ctx()["make"] == 4, n
    for k in range(1, n + 1):
        m = lab == k
        hull = F._min_area_rect(m)
        assert 0.97 <= hull["solidity"] <= 1.01, hull
        area_ratio = m.sum() / (hull["w"] * hull["h"])
        assert 0.70 < area_ratio < 0.80, ("a hexagon fills 3/4 of its box, a disc 0.785 of a "
                                          "square; the old tile was a filled square", area_ratio)
        assert abs(hull["w"] / hull["h"] - 1.155) < 0.03 or abs(hull["h"] / hull["w"] - 1.155) \
            < 0.03, hull


def test_10_a_vessel_keeps_its_own_drawing():
    from brambleloop.products import vessels

    basket = vessels.build_basket("medium")
    parts = PR._components(basket)
    assert any(p[2] for p in parts) and PR.vessel_spec(basket) is not None
    img, _ = PR._render_layout(basket, parts)      # a vessel keeps its own drawing
    assert img.size[0] > 0 and img.size[1] > 0


# ---- 4. the parked runs are re-driven once --------------------------------------------------

def test_11_an_unknown_run_redriven_under_the_old_checks_is_redriven_once_more():
    # "fidelity-checks/2" here; ENG-COASTER-SIDES moved it to /3. The redrive is per version.
    assert F.FIDELITY_CHECK_VERSION not in (IP.LEGACY_CHECK_VERSION, "fidelity-checks/2")
    assert IP.fidelity_check_version() == F.FIDELITY_CHECK_VERSION
    db = R._db()
    R._production_vision(db)
    key = R._blocked(db, calls=1, spent=0.07)
    # 19i25 re-drove it under fidelity-judge/2 with the old deterministic checks
    from sqlalchemy import select

    from brambleloop.visual.image_records import ImageProductionRun

    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        st = dict(r.stages or {})
        st[IP.RESTART_KEY] = {"epoch": 1, "history": [
            {"epoch": 1, "by": IP.FIDELITY_REDRIVE_BY, "reason": "19i25",
             "judge_version": F.FIDELITY_JUDGE_VERSION, "reverify": True}]}
        st[IP.FIDELITY_REDRIVE_KEY] = {"judge_version": F.FIDELITY_JUDGE_VERSION, "day": None,
                                       "why": "re-judged; UNKNOWN again"}
        r.stages = st
    assert R._due(db)["kind"] == "fidelity_unknown", "the new check version is due once"
    calls = []
    out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
    assert [x["run_key"] for x in out["restarted"]] == [key], out
    assert len(calls) == 1 and calls[0][0]["stage"] == "fidelity_gate" \
        and calls[0][0]["reverify"] is True, calls
    row = R._row(db, key)
    hist = row["stages"][IP.RESTART_KEY]["history"][-1]
    assert hist["by"] == IP.FIDELITY_REDRIVE_BY and hist["check_version"] == \
        F.FIDELITY_CHECK_VERSION and hist["judge_version"] == F.FIDELITY_JUDGE_VERSION, hist
    assert row["calls"] == 1 and abs(row["spent"] - 0.07) < 1e-9, "no cap is reset"
    assert IP._attempts(db, key, IP.ANCHOR_ROLE) == 1, "a re-judgement adds no attempt"
    R._reblock(db, key)
    assert R._due(db) is None, "once per (judge version, check version)"
    out2 = IP.redrive_capability_blocked(db, follow=R._follow(calls))
    assert len(calls) == 1 and out2["restarted"] == [], out2


def test_12_the_restart_cap_still_binds_and_the_verdict_names_its_check_version():
    db = R._db()
    R._production_vision(db)
    capped = R._blocked(db, "coaster-capped", restarts=IP.MAX_RESTARTS)
    calls = []
    out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
    assert capped not in {x["run_key"] for x in out["restarted"]} and calls == [], out
    rec = R._row(db, capped)["stages"].get(IP.FIDELITY_REDRIVE_KEY) or {}
    assert rec.get("check_version") == F.FIDELITY_CHECK_VERSION and "cap" in rec.get("why", "")
    v = _verify(scene(hole_r=0))
    assert v["check_version"] == F.FIDELITY_CHECK_VERSION and v["judge_version"] == \
        F.FIDELITY_JUDGE_VERSION
    assert F.CHECKER == "visual.fidelity product-fidelity/1.0.0", \
        "accepted anchors are matched on CHECKER; it must not move"


if __name__ == "__main__":
    failed = 0
    tests = [v for k, v in sorted(globals().items(), key=lambda kv: (
        int(kv[0].split("_")[1]) if kv[0].startswith("test_") else 0, kv[0]))
        if k.startswith("test_") and callable(v)]
    for fn in tests:
        try:
            fn()
            print(f"OK   {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            traceback.print_exc()
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
