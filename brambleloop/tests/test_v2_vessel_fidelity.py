"""V2 / P0-c: the vessel verifier, calibrated on renders of market-basket-small's own CIR.

Positives are synthetic product-only views drawn from the certified CIR and its twin:
- the top-down outline is a regular polygon with the twin's `sides`;
- the side view stacks the wall's colour bands at their row shares.
Each positive is checked under photographic perturbations: blur, rotation, a lighting
gradient and JPEG. Negatives are the same renders with one defect each, and every one FAILs
with its own code:
- a 5-sided, 8-sided or round basket gives WRONG_REPEAT_COUNT;
- a three-stripe wall gives WRONG_COLOUR_LAYOUT;
- a rim band the CIR does not work, or a rim wider than the wall, gives INVENTED_EDGING.
Offline, deterministic, no model call, no paid generation.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_v2_vessel_fidelity.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import io
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

from brambleloop.products import launch0  # noqa: E402
from brambleloop.visual import vessel as V  # noqa: E402

SURFACE = (94, 122, 138)          # slate: far from cream and wine
CIR = launch0.cir_for("basket_small")
MODEL = V.vessel_models(CIR)[0]
HEX = CIR.colors


def _rgb(cid, model=None):
    h = ((model.palette if model else None) or HEX).get(cid, cid).lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _texture(im, amp=10, seed=7):
    a = np.asarray(im, dtype=np.int16)
    rng = np.random.default_rng(seed)
    a = a + rng.integers(-amp, amp + 1, size=a.shape[:2])[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def _perturb(im, *, rotate=0.0, blur=0.0, gradient=0.0, jpeg=None):
    if rotate:
        im = im.rotate(rotate, resample=Image.BICUBIC, fillcolor=SURFACE)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    if gradient:
        a = np.asarray(im, dtype=np.float64)
        g = np.linspace(1.0 - gradient / 2, 1.0 + gradient / 2, a.shape[1])[None, :, None]
        im = Image.fromarray(np.clip(a * g, 0, 255).astype(np.uint8))
    buf = io.BytesIO()
    if jpeg:
        im.save(buf, "JPEG", quality=jpeg)
    else:
        im.save(buf, "PNG")
    return buf.getvalue()


def top_view(sides=None, *, size=1600, bump=0.0, lobes=0.0, model=None, **pert):
    """The basket standing on its base, from directly above: the outline is the twin's
    polygon (`sides`), the rim is the top wall row's colour, the inside a shade darker.
    `lobes` draws a near-circle r(1 + a*cos 6t) instead (review V2 F5)."""
    model = model or MODEL
    sides = model.sides if sides is None else sides
    im = Image.new("RGB", (size, size), SURFACE)
    d = ImageDraw.Draw(im)
    c, r = size / 2, size * 0.32
    rim = _rgb(model.rim_colour, model)
    if lobes:
        pts = [(c + r * (1 + lobes * math.cos(6 * t)) * math.cos(t),
                c + r * (1 + lobes * math.cos(6 * t)) * math.sin(t))
               for t in (2 * math.pi * k / 720 for k in range(720))]
        d.polygon(pts, fill=rim)
        d.ellipse([c - r * .85, c - r * .85, c + r * .85, c + r * .85],
                  fill=tuple(int(v * .82) for v in rim))
    elif sides == 0:
        d.ellipse([c - r, c - r, c + r, c + r], fill=rim)
        d.ellipse([c - r * .85, c - r * .85, c + r * .85, c + r * .85],
                  fill=tuple(int(v * .82) for v in rim))
    else:
        pts = [(c + r * math.cos(math.radians(90 + 360 * k / sides)),
                c + r * math.sin(math.radians(90 + 360 * k / sides))) for k in range(sides)]
        if bump:
            # A jagged flat: a small outward point at each side's midpoint (a slubby or
            # uneven stitch), well inside the corner's prominence floor.
            jag = []
            for k in range(sides):
                jag.append(pts[k])
                a = math.radians(90 + 360 * (k + 0.5) / sides)
                rr = r * math.cos(math.pi / sides) * (1 + bump)
                jag.append((c + rr * math.cos(a), c + rr * math.sin(a)))
            pts = jag
        inner = [(c + (x - c) * .85, c + (y - c) * .85) for x, y in pts]
        d.polygon(pts, fill=rim)
        d.polygon(inner, fill=tuple(int(v * .82) for v in rim))
    return _perturb(_texture(im), **pert)


def side_view(bands=None, rows=None, *, rim=None, rim_bulge=1.0, size=(1600, 1200), model=None,
              **pert):
    """The basket standing, camera level with the wall: the wall's colour bands, bottom to
    top, at their row shares (the twin's width:height). A band may be a palette id or a hex."""
    model = model or MODEL
    bands = model.wall_bands if bands is None else bands
    rows = model.wall_rows if rows is None else rows
    im = Image.new("RGB", size, SURFACE)
    d = ImageDraw.Draw(im)
    w = size[0] * 0.6
    h = w * 8.7 / 16.0
    x0, y_bottom = (size[0] - w) / 2, size[1] * 0.75
    total = sum(rows)
    y = y_bottom
    for cid, n in zip(bands, rows):
        bh = h * n / total
        d.rectangle([x0, y - bh, x0 + w, y], fill=_rgb(cid, model))
        y -= bh
    if rim is not None or rim_bulge != 1.0:
        colour = _rgb(rim or model.rim_colour, model)
        extra = w * (rim_bulge - 1.0) / 2
        rh = h * (0.10 if rim else 0.07)
        d.rectangle([x0 - extra, y - rh, x0 + w + extra, y], fill=colour)
    return _perturb(_texture(im), **pert)


PERTURBATIONS = ({}, {"blur": 2.0}, {"gradient": 0.3}, {"rotate": 4.0}, {"jpeg": 60},
                 {"rotate": -3.0, "blur": 1.5, "gradient": 0.2, "jpeg": 75})


def test_the_model_is_the_cirs_wall_and_side_count():
    assert MODEL.sides == 6
    assert MODEL.wall_bands == ["cream", "wine", "cream", "wine", "cream"], MODEL.wall_bands
    assert MODEL.wall_rows == [4, 2, 1, 2, 3] and MODEL.wall_total_rows == 12
    assert MODEL.base_rows == 10 and MODEL.rim_colour == "cream"


def test_the_baskets_own_render_passes_under_photographic_perturbation():
    for p in PERTURBATIONS:
        v = V.verify(top_view(**p), side_view(**p), CIR)
        assert v["status"] == "PASS", (p, [(c["check"], c["status"], c["why"])
                                           for c in v["checks"]])


def _codes(v):
    return set(v["codes"]), v["status"]


def test_a_five_eight_or_round_basket_fails_the_side_count():
    for sides in (5, 8, 0):
        for p in ({}, {"blur": 1.5, "rotate": 3.0, "jpeg": 75}):
            codes, status = _codes(V.verify(top_view(sides, **p), side_view(**p), CIR))
            assert status == "FAIL" and "WRONG_REPEAT_COUNT" in codes, (sides, p, codes)


def test_a_three_stripe_wall_fails_the_colour_layout():
    bands = ["cream", "wine", "cream", "wine", "cream", "wine", "cream"]
    rows = [3, 2, 1, 2, 1, 2, 1]
    for p in ({}, {"blur": 1.5, "jpeg": 75}):
        codes, status = _codes(V.verify(top_view(**p), side_view(bands, rows, **p), CIR))
        assert status == "FAIL" and "WRONG_COLOUR_LAYOUT" in codes, (p, codes)


def test_an_invented_rim_fails_as_invented_edging():
    # A wine braid on top of the cream rim the CIR works.
    codes, status = _codes(V.verify(top_view(), side_view(rim="wine"), CIR))
    assert status == "FAIL" and "INVENTED_EDGING" in codes, codes
    # A rolled rim in the wall's own colour: only its silhouette shows it.
    codes, status = _codes(V.verify(top_view(), side_view(rim_bulge=1.15), CIR))
    assert status == "FAIL" and "INVENTED_EDGING" in codes, codes


def test_an_unreadable_view_is_unknown_never_pass():
    noise = np.random.default_rng(3).integers(0, 255, size=(800, 800, 3)).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(noise).save(buf, "PNG")
    v = V.verify(buf.getvalue(), side_view(), CIR)
    assert v["status"] == "UNKNOWN" and "UNVERIFIABLE_COUNT" in v["codes"], v["status"]


def test_a_flat_design_has_no_vessel_check():
    cir = launch0.cir_for("hexagon_coasters")
    assert not V.is_vessel(cir)


def test_the_anchor_verifier_delegates_a_vessel_and_never_uses_the_round_check():
    from brambleloop.visual import fidelity as F

    alone = F.verify_anchor(top_view(), CIR)
    assert alone["status"] == "UNKNOWN" and alone["kind"] == "vessel_anchor", alone["status"]
    assert [c["check"] for c in alone["checks"]] == ["vessel_views"]
    # An octagon used to pass the round aspect check; with its side view it fails by count.
    bad = F.verify_anchor(top_view(8), CIR, side=side_view())
    assert bad["status"] == "FAIL" and "WRONG_REPEAT_COUNT" in bad["codes"], bad["codes"]
    good = F.verify_anchor(top_view(), CIR, side=side_view())
    vessel_checks = [c for c in good["checks"] if c["check"].startswith("basket:")]
    assert vessel_checks and all(c["status"] == "PASS" for c in vessel_checks), vessel_checks


def test_a_vessels_product_brief_is_standing_not_laid_flat():
    from brambleloop.creative import image_stages as IS
    from brambleloop.creative import pattern_refs

    rules = pattern_refs.technical_rules(CIR, release_hash=pattern_refs.release_hash_of(CIR))
    assert IS.is_vessel_release(rules)
    top = IS.product_scene(rules, ["#FAF6EB", "#6E1F2A"], view="top")
    side = IS.product_scene(rules, ["#FAF6EB", "#6E1F2A"], view="side")
    assert "standing upright" in top["pose"] and "directly above" in top["pose"]
    assert "from the side" in side["pose"] and "flat" not in top["pose"].replace("flat side", "")
    flat = IS.product_scene({"components": [{"shape": "rectangle"}]}, ["#FAF6EB"])
    assert "laid completely flat" in flat["pose"]
    try:
        IS.product_scene(rules, ["#FAF6EB"], view="front")
    except IS.StageRefused:
        pass
    else:
        raise AssertionError("an unknown vessel view must be refused")


def test_the_right_number_of_bands_in_the_wrong_order_fails():
    swapped = ["wine", "cream", "wine", "cream", "wine"]
    codes, status = _codes(V.verify(top_view(), side_view(swapped, MODEL.wall_rows), CIR))
    assert status == "FAIL" and "WRONG_COLOUR_LAYOUT" in codes, codes


def test_a_side_view_too_small_to_read_its_rows_is_unknown():
    tiny = side_view(size=(50, 38))
    v = V.verify(top_view(), tiny, CIR)
    side = [c for c in v["checks"] if c["check"].endswith("wall_bands")]
    assert side and side[0]["status"] == "UNKNOWN", side


def test_a_jagged_flat_is_not_a_corner():
    """A small bump mid-side is a radius maximum within its own +-18 deg window (the corners
    are 30 deg away); only the prominence floor keeps it from being counted as a corner."""
    for p in ({}, {"blur": 1.5, "jpeg": 75}):
        v = V.verify(top_view(bump=0.02, **p), side_view(**p), CIR)
        sides = next(c for c in v["checks"] if c["check"].endswith(":sides"))
        assert sides["status"] == "PASS" and sides["counted"] == 6, (p, sides)


# ---- review V2 6799f1d4 F1-F7 ------------------------------------------------------------

def test_the_wrong_colourway_fails_off_palette():
    """F1: the right band layout in yellow and navy is not the CIR's cream and wine."""
    wrong = {"cream": "#E8C547", "wine": "#1F2A5A"}
    bands = [wrong[b] for b in MODEL.wall_bands]
    for p in ({}, {"blur": 1.5, "jpeg": 75}):
        v = V.verify(top_view(**p), side_view(bands, **p), CIR)
        codes, status = _codes(v)
        assert status == "FAIL" and "OFF_PALETTE_COLOUR" in codes, (p, codes)
    good = V.verify(top_view(), side_view(), CIR)
    pal = next(c for c in good["checks"] if c["check"].endswith(":palette"))
    assert pal["status"] == "PASS" and pal["coverage"] > 0.95, pal


KEY = launch0.cir_for("key_basket")
KEY_MODEL = V.vessel_models(KEY)[0]


def test_a_round_basket_requires_no_corners():
    """F2: sides == 0 is a round vessel, a real requirement, not "no side count"."""
    assert KEY_MODEL.sides == 0 and KEY_MODEL.modelled
    for p in ({}, {"blur": 1.5, "rotate": 3.0, "jpeg": 75}):
        v = V.verify(top_view(model=KEY_MODEL, **p), side_view(model=KEY_MODEL, **p), KEY)
        assert v["status"] == "PASS", (p, [(c["check"], c["status"], c["why"])
                                           for c in v["checks"]])
        for sides in (4, 6):
            codes, status = _codes(V.verify(top_view(sides, model=KEY_MODEL, **p),
                                            side_view(model=KEY_MODEL, **p), KEY))
            assert status == "FAIL" and "WRONG_REPEAT_COUNT" in codes, (sides, p, codes)


def test_a_vessel_whose_side_count_is_unknown_is_unknown():
    """F2: a twin that states no side count gives UNKNOWN, never NA."""
    from dataclasses import replace

    c = V.verify_top(top_view(), replace(MODEL, sides=None))
    assert c["status"] == "UNKNOWN" and c["code"] == "UNVERIFIABLE_COUNT", c


def test_a_top_view_too_small_to_count_corners_is_unknown():
    """F3: a few dozen pixels of outline cannot show six corners."""
    for size in (100, 150):
        c = V.verify_top(top_view(size=size), MODEL)
        assert c["status"] == "UNKNOWN" and c["code"] == "UNVERIFIABLE_COUNT", (size, c)
    assert V.verify_top(top_view(size=400), MODEL)["status"] == "PASS"


def test_a_vessel_twin_without_a_wall_model_is_unknown_never_the_round_check():
    """F4: shape == "vessel" with no constant trailing rounds is not verifiable."""
    from brambleloop.visual import fidelity as F

    real = V.vessel_models
    try:
        V.vessel_models = lambda cir: [V.VesselModel("basket", 6, [], [], "", 10, 0,
                                                     dict(cir.colors), modelled=False)]
        assert V.is_vessel(CIR)
        v = V.verify(top_view(), side_view(), CIR)
        assert v["status"] == "UNKNOWN", v["status"]
        assert [c["check"] for c in v["checks"]] == ["basket:vessel_model"], v["checks"]
        a = F.verify_anchor(top_view(), CIR, side=side_view())
        assert a["status"] == "UNKNOWN" and not any(
            c["check"] == "aspect" for c in a["checks"]), a
    finally:
        V.vessel_models = real


def test_a_lobed_circle_is_round_not_a_hexagon():
    """F5: a circle with a slight 6-fold ripple has six radius maxima 60 deg apart; only the
    prominence floor stops them being counted as a hexagon's corners."""
    for a in (0.005, 0.01, 0.015):
        for p in ({}, {"blur": 1.5, "jpeg": 75}):
            c = V.verify_top(top_view(lobes=a, **p), MODEL)
            assert c["status"] == "FAIL" and c["counted"] != 6, (a, p, c)


def test_band_shares_far_from_the_cirs_rows_fail():
    """F6: [6,1,1,1,3] against the CIR's [4,2,1,2,3] is a different wall."""
    for rows in ([6, 1, 1, 1, 3], [2, 2, 1, 2, 5]):
        codes, status = _codes(V.verify(top_view(), side_view(rows=rows), CIR))
        assert status == "FAIL" and "WRONG_COLOUR_LAYOUT" in codes, (rows, codes)


def test_one_off_palette_band_in_an_otherwise_right_wall_fails_the_layout():
    """F1: a single yellow row where the CIR works cream keeps palette coverage above its
    floor (11 of 12 rows), so only the per-row "off" label catches it."""
    bands = list(MODEL.wall_bands)
    assert bands[2] == "cream" and MODEL.wall_rows[2] == 1
    bands[2] = "#E8C547"
    v = V.verify(top_view(), side_view(bands), CIR)
    codes, status = _codes(v)
    assert status == "FAIL" and "WRONG_COLOUR_LAYOUT" in codes, codes
    pal = next(c for c in v["checks"] if c["check"].endswith(":palette"))
    assert pal["status"] == "PASS", pal


def test_an_undecodable_vessel_view_is_a_fail_never_unknown_or_a_raise():
    """Review VISUAL_STACK N1/N2: V1 pins an undecodable anchor as a deterministic FAIL; the
    vessel path decodes both views first and never raises."""
    from brambleloop.visual import fidelity as F

    junk, top, side = b"not an image", top_view(), side_view()
    for t_, s_ in ((junk, None), (junk, side), (top, junk), (junk, junk)):
        v = F.verify_anchor(t_, CIR, side=s_)
        assert v["status"] == "FAIL", (t_ is junk, s_ is junk, v["status"], v["checks"])
        assert v["checks"][0]["check"] == "decode", v["checks"]
    assert F.verify_anchor(top, CIR)["status"] == "UNKNOWN"          # one good view: UNKNOWN
    assert V.verify_top(junk, MODEL)["status"] == "FAIL"
    assert [c["status"] for c in V.verify_side(junk, MODEL)] == ["FAIL"]
    assert V.verify(top, junk, CIR)["status"] == "FAIL"


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                import traceback

                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
