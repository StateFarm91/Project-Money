"""ENG-COASTER-SIDES: a flat piece's polygon side count, from the release's own CIR.

Production 2026-11-26: hexagon-coaster-set@1.2.1's accepted product anchor (candidate 40)
shows four 6-sided coasters, and every derivative gallery frame (62 hero, 63 colour_context,
64 angle, 65 detail, 66 size) shows OCTAGONS. Those frames were recorded "unverified"
(product_truth UNKNOWN) because no check counted a flat piece's sides. Now
`<component>:sides` (`visual.piece_sides`) runs on the anchor and on every derivative frame:
  - correct hexagons PASS (top-down, rounded corners, oblique, on a textured table);
  - octagons FAIL with WRONG_SIDE_COUNT, and so do circles for a hexagon CIR;
  - unsegmentable frames are UNKNOWN, never PASS, and a close-up with no whole piece is NA;
  - the expectation is the twin's `sides` (hexagon 6, square 4, round: no count);
  - the repair names the fix ("coaster has 8 sides; must be 6 (a hexagon)");
  - a frame whose verdict is UNKNOWN never counts toward a valid gallery.

Every image is a deterministic local render. There is no network and no paid call.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_eng_coaster_sides.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import io
import math
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402
from scipy import ndimage  # noqa: E402

import test_image_fidelity_3 as T3  # noqa: E402  (the photographic coaster harness)
import test_w4_fidelity as W  # noqa: E402
from brambleloop.creative import failure_codes as FC  # noqa: E402
from brambleloop.visual import fidelity as F  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402
from brambleloop.visual import piece_sides as PS  # noqa: E402
from brambleloop.visual import repair_routes as RR  # noqa: E402

RELEASE = "a" * 64


def _ctx():
    return T3._ctx()


def _poly_t(size, rot, n, p):
    """Normalised radius (1 on the outline) of an n-gon (n=0: a circle); `p` rounds corners
    (a p-norm over the edge projections; large is sharp)."""
    yy, xx = np.mgrid[0:size, 0:size]
    c = (size - 1) / 2
    px, py = xx - c, yy - c
    R = size / 2 - 1
    if n == 0:
        return np.hypot(px, py) / (R * 0.93), np.arctan2(py, px)
    apothem = R * math.cos(math.pi / n)
    acc = np.zeros((size, size))
    for k in range(n):
        a = math.radians(rot) + math.pi / n + 2 * math.pi * k / n
        acc += np.maximum(0, (px * math.cos(a) + py * math.sin(a)) / apothem) ** p
    return acc ** (1 / p), np.arctan2(py, px)


_EXTENT: dict = {}


def _src_extent(src):
    """The certified render's own outline radius per degree (it is drawn as the twin's
    hexagon): a fixture of another shape samples the rounds inside it, not the backdrop."""
    if "r" not in _EXTENT:
        h, w = src.shape[:2]
        corner = src[2, 2]
        fab = np.abs(src - corner).sum(-1) > 30
        yy, xx = np.nonzero(fab)
        a = (np.degrees(np.arctan2(yy - (h - 1) / 2, xx - (w - 1) / 2)) + 360) % 360
        r = np.hypot(yy - (h - 1) / 2, xx - (w - 1) / 2)
        ext = np.zeros(360)
        np.maximum.at(ext, a.astype(int) % 360, r)
        _EXTENT["r"] = ext * 0.97
    return _EXTENT["r"]


def _piece(size, rot, n, p, src):
    rounds = _ctx()["rounds"]
    t, ang = _poly_t(size, rot, n, p)
    h, w = src.shape[:2]
    ext = _src_extent(src)
    rs = np.minimum(t, 1) * ext[((np.degrees(ang) + 360) % 360).astype(int) % 360]
    sx = np.clip((w - 1) / 2 + rs * np.cos(ang), 0, w - 1).astype(int)
    sy = np.clip((h - 1) / 2 + rs * np.sin(ang), 0, h - 1).astype(int)
    rgb = src[sy, sx]
    rp = (t * rounds) % 1.0
    sp = (ang / (2 * np.pi) * np.maximum(6, np.floor(t * rounds) * 6 + 6)) % 1.0
    shade = 0.55 + 0.45 * np.sin(np.pi * rp) ** 0.7 * np.sin(np.pi * sp) ** 0.5
    out = T3._srgb(F._lin(rgb) * shade[..., None])
    edge = 1 - 0.03 * (0.5 + 0.5 * np.cos(ang * 12 * rounds))
    return (Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)),
            Image.fromarray(((t <= edge) * 255).astype(np.uint8)))


def _grain(canvas, table):
    """A wooden table with visible grain (not a plain surface: isolation fails)."""
    yy, xx = np.mgrid[0:canvas, 0:canvas]
    g = 0.82 + 0.18 * np.sin(yy / 9.0 + 3 * np.sin(xx / 140.0)) * np.sin(yy / 31.0)
    return np.array(table, float)[None, None, :] * g[..., None]


def scene(n=6, *, p=60, table=T3.WALNUT, grain=False, squash=1.0, crop=None,
          mug=False, canvas=1400, count=None):
    """`count` coasters (n sides) on a table; `squash` foreshortens (an oblique camera);
    `crop` (x0, y0, x1, y1) of the canvas makes a close-up; `mug` adds a cream mug."""
    cx = _ctx()
    src = cx["src"]
    k = count or cx["make"]
    base = _grain(canvas, table) if grain else np.ones((canvas, canvas, 3)) * np.array(table, float)
    layer = Image.new("RGB", (canvas, canvas))
    alpha = Image.new("L", (canvas, canvas), 0)
    size = int(0.8 * canvas / (k * 1.1))
    x = (canvas - k * size * 1.1) / 2
    for i in range(k):
        im, a = _piece(size, 7 * i, n, p, src)
        X, Y = int(x), (canvas - size) // 2
        layer.paste(im, (X, Y), a)
        alpha.paste(a, (X, Y), a)
        x += size * 1.1
    dist = ndimage.distance_transform_edt(~(np.asarray(alpha) > 127))
    occlusion = np.where(dist > 0, np.exp(-dist / 6.0), 0) * 0.75
    img = Image.fromarray(np.clip(T3._srgb(F._lin(base) * (1 - occlusion)[..., None]), 0, 255)
                          .astype(np.uint8))
    img.paste(layer, (0, 0), alpha.filter(ImageFilter.GaussianBlur(1.0)))
    if mug:
        d = ImageDraw.Draw(img)
        r = int(size * 0.45)
        mx, my = canvas // 2, canvas // 5
        d.ellipse((mx - r, my - r, mx + r, my + r), fill=F._hex_rgb(T3.CREAM))
    if squash != 1.0:
        img = img.resize((canvas, int(canvas * squash)), Image.BICUBIC)
    if crop:
        img = img.crop(crop)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def anchor(data):
    return F.verify_anchor(data, _ctx()["cir"], judge=W.PASSING_JUDGE)


def derivative(data, role="hero"):
    return F.verify_lifestyle(data, _ctx()["cir"], release_hash=RELEASE,
                              anchor={"status": "PASS", "release_hash": RELEASE},
                              anchor_data=scene(), judge=W.PASSING_JUDGE, role=role)


def sides(v):
    got = [c for c in v["checks"] if c["check"] == "coaster:sides"]
    assert len(got) == 1, [c["check"] for c in v["checks"]]
    return got[0]


# ---- 1. the expectation comes from the CIR -------------------------------------------------

def test_1_the_expected_count_is_the_twins_sides_never_a_product_name():
    exp = F.expectation(_ctx()["cir"])
    assert [(p.name, p.sides) for p in exp.pieces] == [("coaster", 6)], exp.pieces
    assert PS.expected_sides(SimpleNamespace(sides=6)) == 6
    assert PS.expected_sides(SimpleNamespace(sides=4)) == 4          # a square
    assert PS.expected_sides(SimpleNamespace(sides=8)) == 8          # an octagon
    assert PS.expected_sides(SimpleNamespace(sides=0)) is None       # round: no count
    assert PS.expected_sides(SimpleNamespace(sides=None)) is None    # unstated: no count
    src = (ROOT / "src/brambleloop/visual/piece_sides.py").read_text()
    assert "coaster" not in src.split('"""', 2)[2].lower(), "piece_sides names no product"


# ---- 2. the measurement, calibrated ---------------------------------------------------------

def _mask(n, p=60, size=360, rot=11):
    t, _ = _poly_t(size, rot, n, p)
    m = np.zeros((size + 40, size + 40), bool)
    m[20:-20, 20:-20] = t <= 1.0
    return m


def test_2_the_counter_reads_each_polygon_and_a_circle():
    for n in (3, 4, 5, 6, 7, 8):
        r = PS.count_sides(_mask(n))
        assert r["readable"] and r["sides"] == n, (n, r)
    r = PS.count_sides(_mask(0))
    assert r["readable"] and r["sides"] == 0, r
    # rounded corners, as a crochet piece's are (the p-norm rounds an octagon's corners more
    # at the same p; at p=14 it is 1.04 points-to-flats, below the prominence floor: round)
    for n, p in ((6, 14), (8, 24)):
        r = PS.count_sides(_mask(n, p=p))
        assert r["readable"] and r["sides"] == n, (n, r)


def test_3_an_oblique_view_is_normalised_and_a_merged_blob_is_unreadable():
    for n in (6, 8, 0):
        m = _mask(n)
        im = Image.fromarray((m * 255).astype(np.uint8))
        sq = np.asarray(im.resize((im.width, int(im.height * 0.6)), Image.BILINEAR)) > 127
        r = PS.count_sides(sq)
        assert r["readable"] and r["sides"] == n and r["foreshortening"] > 1.5, (n, r)
    two = _mask(6)
    two = np.concatenate([two, two[:, ::-1]], axis=1)[:, 100:-100]
    two = ndimage.binary_closing(two, iterations=3)
    r = PS.count_sides(two)
    assert not r["readable"] and r["sides"] is None, r
    tiny = _mask(8, size=50)
    assert not PS.count_sides(tiny)["readable"], "a tiny outline is not countable"


# ---- 3. the anchor -----------------------------------------------------------------------

def test_4_hexagon_coasters_pass_on_the_anchor():
    for kw in ({}, {"p": 14}, {"table": T3.HONEY}, {"table": W.BG}):
        v = anchor(scene(**kw))
        s = sides(v)
        assert s["status"] == "PASS" and s["counted"] == [6], (kw, s)
        assert v["status"] == "PASS", (kw, v["failed"], v["unknown"])
        assert len([p for p in s["pieces"] if p["readable"]]) == 4, s["pieces"]


def test_5_octagon_and_round_coasters_fail_on_the_anchor_by_name():
    for n, word in ((8, "8 sides"), (0, "round")):
        v = anchor(scene(n))
        s = sides(v)
        assert s["status"] == "FAIL" and s["code"] == FC.WRONG_SIDE_COUNT, (n, s)
        assert v["status"] == "FAIL" and FC.WRONG_SIDE_COUNT in v["codes"], (n, v["codes"])
        assert word in s["fix"] and s["fix"].endswith("must be 6 (a hexagon)"), s["fix"]
    assert sides(anchor(scene(8)))["fix"] == "coaster has 8 sides; must be 6 (a hexagon)"


# ---- 4. every derivative frame ------------------------------------------------------------

def test_6_hexagons_pass_on_every_derivative_frame():
    frames = {"hero": scene(grain=True), "colour_context": scene(),
              "angle": scene(squash=0.65, grain=True), "size": scene(table=T3.HONEY, mug=True),
              "hero_rounded": scene(p=14, grain=True, table=T3.LIGHT_OAK)}
    assert len(frames) == 5
    for role, data in frames.items():
        s = sides(derivative(data, role.split("_")[0]))
        assert s["status"] == "PASS" and s["counted"] == [6], (role, s["why"], s["pieces"])


def test_7_octagons_fail_on_every_derivative_frame_the_production_defect():
    """Production 62-66: octagons in hero, colour_context, angle, detail and size frames."""
    frames = {"hero": scene(8, grain=True), "colour_context": scene(8),
              "angle": scene(8, squash=0.65, grain=True),
              "detail": scene(8, count=2, crop=(0, 250, 1400, 1150)),
              "size": scene(8, table=T3.HONEY, mug=True)}
    assert len(frames) == 5
    for role, data in frames.items():
        v = derivative(data, role)
        s = sides(v)
        assert s["status"] == "FAIL" and s["code"] == FC.WRONG_SIDE_COUNT, (role, s["why"])
        assert v["status"] == "FAIL" and FC.WRONG_SIDE_COUNT in v["codes"], (role, v["codes"])
        assert s["fix"] == "coaster has 8 sides; must be 6 (a hexagon)", s["fix"]


def test_8_circles_fail_for_a_hexagon_cir():
    for data in (scene(0), scene(0, grain=True), scene(0, squash=0.7)):
        s = sides(derivative(data))
        assert s["status"] == "FAIL" and s["counted"] == [0], s
        assert "round" in s["fix"], s["fix"]


def test_9_unsegmentable_is_unknown_never_pass_and_a_close_up_is_na():
    full = derivative(scene(crop=(500, 600, 900, 800)), "hero")   # every coaster cropped
    s = sides(full)
    assert s["status"] == "UNKNOWN" and full["status"] != "PASS", s
    assert s["code"] == FC.UNVERIFIABLE_COUNT, s
    close = sides(derivative(scene(crop=(300, 620, 1100, 780)), "detail"))
    assert close["status"] == F.NA, close
    blank = io.BytesIO()
    Image.new("RGB", (900, 900), T3.WALNUT).save(blank, "PNG")
    s = sides(derivative(blank.getvalue(), "hero"))
    assert s["status"] == "UNKNOWN", s
    # the vision judge may corroborate, never override
    ok = sides(derivative(scene()))
    assert PS.corroborate(ok, {"answered": True, "reading": {"sides": 6}})["status"] == "PASS"
    assert PS.corroborate(ok, {"answered": True, "reading": {"sides": 8}})["status"] == "UNKNOWN"
    bad = sides(derivative(scene(8)))
    assert PS.corroborate(bad, {"answered": True, "reading": {"sides": 6}})["status"] == "FAIL"


def test_10_a_cream_mug_is_not_a_coaster():
    """A mug in the yarn's colour is whole and round, but it lacks the wine round."""
    s = sides(derivative(scene(mug=True, table=T3.HONEY), "size"))
    assert s["status"] == "PASS" and all(p["sides"] == 6 for p in s["pieces"]), s["pieces"]


# ---- 5. repair and the gallery ------------------------------------------------------------

def test_11_the_code_is_shared_and_its_repair_names_the_fix():
    assert FC.WRONG_SIDE_COUNT in FC.ALL_CODES and F.WRONG_SIDE_COUNT is FC.WRONG_SIDE_COUNT
    assert FC.CATEGORY_OF[FC.WRONG_SIDE_COUNT] == FC.PRODUCT_FIDELITY
    assert RR.route([FC.WRONG_SIDE_COUNT])["repairable"]
    v = derivative(scene(8))
    best = {"failure_categories": ["product_fidelity", *v["codes"]],
            "fidelity": {"checks": v["checks"]}}
    rp = IP._repair_for(best)
    d = [x for x in rp["directives"] if x["code"] == FC.WRONG_SIDE_COUNT][0]
    assert d["negatives"][0] == "to fix: coaster has 8 sides; must be 6 (a hexagon)", d
    from brambleloop.creative import flux3_generator as FG

    assert "to fix: coaster has 8 sides; must be 6 (a hexagon)" in FG._repair_negatives(rp)


def test_12_the_check_version_is_bumped_so_parked_unknown_frames_are_rejudged():
    # "/4" adds the side check (19i35); later bumps may only move it further
    assert int(F.FIDELITY_CHECK_VERSION.rsplit("/", 1)[1]) >= 4, F.FIDELITY_CHECK_VERSION
    assert F.FIDELITY_CHECK_VERSION == IP.fidelity_check_version()
    assert F.VERIFIER_VERSION == "product-fidelity/1.0.0", "accepted anchors still match"


def test_13_an_unknown_frame_never_counts_toward_a_valid_gallery():
    """Even when a stored row says publishable, an UNKNOWN frame fills no gallery role, and a
    Laura frame whose Product Truth is UNKNOWN does not satisfy the Laura requirement."""
    saved = IP._best, IP._dashboard_identity

    def best_of(tech, unknown):
        return lambda db, **kw: {"candidate_id": 1, "sha256": "0" * 64,
                                 "technical_status": tech, "publishable": True,
                                 "unknown": list(unknown), "blockers": [],
                                 "laura_present": False}

    IP._dashboard_identity = lambda db, listing: ({"slug": "hexagon-coaster-set",
                                                   "version": "1.2.1", "release": RELEASE},
                                                  False)
    try:
        IP._best = best_of("UNKNOWN", ["product_truth"])
        v = IP.readiness(None, "hexagon-coaster-set")
        assert not any(r["status"] == "publishable" for r in v["roles"]), v["roles"]
        assert v["gallery_ready"] is False and v["laura_lifestyle_ok"] is False, v
        IP._best = best_of("PASS", [])
        v = IP.readiness(None, "hexagon-coaster-set")
        assert any(r["status"] == "publishable" for r in v["roles"]), v["roles"]
        assert v["laura_lifestyle_ok"] is True, v
    finally:
        IP._best, IP._dashboard_identity = saved


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
