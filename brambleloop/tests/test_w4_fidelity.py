"""W-FIDELITY: the independent product-fidelity verifier for generated images (OWNERIMG E3).

Offline. No provider is called and nothing is spent. Calibration images are synthetic flat
lays rendered from the certified CIR by the existing fabric renderer (`publish.charts`, the
renderer behind `pattern_refs` 'layout'), then perturbed photographically (blur, lighting
gradient, rotation, JPEG, contact shadow, yarn texture). Negatives are the same renders with
one named defect each. The owner's wrap image is the one real-world case.
"""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import io
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
_ART = tempfile.mkdtemp(prefix="fidelity-art-")
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", _ART)

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

from brambleloop.visual import fidelity as F  # noqa: E402

WRAP_DIR = (ROOT / "research" / "final_build" / "w4" / "flux_experiments"
            / "2026-10-19_reading_nook_cable_wrap")
BG = (122, 116, 108)          # a plain warm taupe surface, contrasting every catalogue yarn


def _cir(slug):
    from brambleloop.runtime.pipeline import _engineered_cir
    from brambleloop.visual.render_verification import authoritative_cir

    return authoritative_cir(slug) or _engineered_cir(slug)


# ---- synthetic flat lays -------------------------------------------------------------------

def _piece_images(cir, cell=12):
    """(RGB image, alpha mask, twin) per piece, at true centimetre proportion."""
    from brambleloop.creative import pattern_refs as PR
    from brambleloop.publish import charts

    out = []
    for comp, twin, is_round in PR._components(cir):
        for _ in range(int(getattr(comp, "make", 1) or 1)):
            if is_round:
                im = charts.render_round_fabric(cir, twin).convert("RGB")
                a = Image.new("L", im.size, 0)
                ImageDraw.Draw(a).ellipse((0, 0, im.size[0] - 1, im.size[1] - 1), fill=255)
            else:
                im = _weighted_rows(cir, comp, twin, charts.render_fabric(
                    cir, twin, cell_px=cell).convert("RGB"))
                a = Image.new("L", im.size, 255)
            out.append([im, a, twin, is_round])
    return out


def _weighted_rows(cir, comp, twin, im):
    """The fabric render with each row at its compiled height (stitch-weighted, PT-08), at
    the twin's true centimetre proportion. Every row band of the render is resampled to its
    own height, so an sc end band is as short as the yarn makes it."""
    from brambleloop.visual.render_verification import expected_model

    rows = len(twin.chart_grid())
    heights = [r["height_cm"] for r in expected_model(cir, comp.name, shape=False)["rows"]]
    assert len(heights) == rows
    src = np.asarray(im)
    hs = src.shape[0]
    band = hs / rows
    w = src.shape[1]
    h = int(round(w * float(twin.height_cm) / float(twin.width_cm)))
    out, y = [], 0.0
    scale = h / sum(heights)
    for r in range(rows - 1, -1, -1):          # top row first
        top = int(round(hs - (r + 1) * band))
        strip = Image.fromarray(src[top:int(round(top + band))])
        y_next = y + heights[r] * scale
        out.append(strip.resize((w, max(1, int(round(y_next)) - int(round(y)))), Image.NEAREST))
        y = y_next
    canvas = Image.new("RGB", (w, sum(o.size[1] for o in out)))
    yy = 0
    for o in out:
        canvas.paste(o, (0, yy))
        yy += o.size[1]
    return canvas


def _yarn_texture(im, period):
    arr = np.asarray(im, dtype=np.float64)
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    t = 1.0 + 0.06 * np.sin(2 * np.pi * xx / period) * np.cos(2 * np.pi * yy / (period * 0.62))
    return Image.fromarray(np.clip(arr * t[..., None], 0, 255).astype(np.uint8))


def flat_lay(cir, *, canvas=2048, rotate=0.0, blur=0.0, gradient=0.0, jpeg=None,
             shadow=True, texture=True, piece_edit=None, final_edit=None, drop=0,
             bg=BG, fill=0.72, order=None):
    pieces = _piece_images(cir)
    if drop:
        pieces = pieces[:-drop]
    for i, p in enumerate(pieces):
        if piece_edit:
            p[0], p[1] = piece_edit(i, p[0], p[1])
        if texture:
            p[0] = _yarn_texture(p[0], 12)
    gap = 0.08
    tot_w = sum(p[0].size[0] for p in pieces) * (1 + gap)
    tall = max(p[0].size[1] for p in pieces)
    s = fill * canvas / max(tot_w, tall)
    img = Image.new("RGB", (canvas, canvas), bg)
    layer = Image.new("RGB", (canvas, canvas), bg)
    alpha = Image.new("L", (canvas, canvas), 0)
    x = (canvas - tot_w * s) / 2
    for im, a, _, _ in pieces:
        w, h = max(2, int(im.size[0] * s)), max(2, int(im.size[1] * s))
        im2, a2 = im.resize((w, h), Image.LANCZOS), a.resize((w, h), Image.LANCZOS)
        y = (canvas - h) // 2
        layer.paste(im2, (int(x), y), a2)
        alpha.paste(a2, (int(x), y), a2)
        x += w * (1 + gap)
    if rotate:
        layer = layer.rotate(rotate, resample=Image.BICUBIC, fillcolor=bg)
        alpha = alpha.rotate(rotate, resample=Image.BICUBIC, fillcolor=0)
    if shadow:
        sh = alpha.filter(ImageFilter.GaussianBlur(18))
        dark = Image.new("RGB", img.size, tuple(int(c * 0.72) for c in bg))
        img = Image.composite(dark, img, sh.point(lambda v: int(v * 0.6)))
        img = img.transform(img.size, Image.AFFINE, (1, 0, -10, 0, 1, -14), fillcolor=bg)
    img.paste(layer, (0, 0), alpha)
    if final_edit:
        img = final_edit(img)
    if gradient:
        arr = np.asarray(img, dtype=np.float64)
        ramp = np.linspace(1 - gradient, 1 + gradient / 2, canvas)[None, :, None]
        img = Image.fromarray(np.clip(arr * ramp, 0, 255).astype(np.uint8))
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    buf = io.BytesIO()
    if jpeg:
        img.save(buf, format="JPEG", quality=jpeg)
    else:
        img.save(buf, format="PNG")
    return buf.getvalue()


class FakeJudge:
    """A test double for the vision judge: answers with a fixed reading, spends nothing."""

    name = "fake-vision"

    def __init__(self, reading=None, same=True):
        self.reading = reading or {"craft": "crochet", "ribbing_visible": "false",
                                   "border_or_edging_visible": "false",
                                   "cable_style": "crochet_post_stitch_crossings",
                                   "fabric_visible_clearly": "true"}
        self.same = same
        self.calls = 0

    def read(self, prompt, images, **kw):
        self.calls += 1
        if "Image 1" in prompt:
            return {"answered": True, "reading": {"same_item": "true" if self.same else "false",
                                                  "differences": [] if self.same else
                                                  ["a ribbed border along the edges"]}}
        return {"answered": True, "reading": self.reading}


PASSING_JUDGE = FakeJudge()


def codes(v):
    return set(v["codes"])


def st(v, name):
    return [c for c in v["checks"] if c["check"].endswith(name)]


# ---- piece edits (one named defect each) ---------------------------------------------------

def _hexrgb(h):
    return F._hex_rgb(h)


def stripe_in_top_band(colour_hex, y_frac):
    def edit(i, im, a):
        im = im.copy()
        w, h = im.size
        ImageDraw.Draw(im).rectangle((0, int(y_frac[0] * h), w, int(y_frac[1] * h)),
                                     fill=_hexrgb(colour_hex))
        return im, a
    return edit


def edging(colour, frac, ribbed=False):
    def edit(i, im, a):
        im = im.copy()
        w, h = im.size
        e = max(2, int(frac * w))
        d = ImageDraw.Draw(im)
        for x0 in (0, w - e):
            if ribbed:
                for x in range(x0, x0 + e):
                    k = 0.62 if (x // max(2, e // 6)) % 2 else 1.25
                    d.line((x, 0, x, h), fill=tuple(min(255, int(c * k)) for c in colour))
            else:
                d.rectangle((x0, 0, x0 + e, h), fill=colour)
        return im, a
    return edit


def fewer_repeats(keep, of):
    def edit(i, im, a):
        w, h = im.size
        return im.crop((0, 0, int(w * keep / of), h)).resize((w, h), Image.NEAREST), a
    return edit


def recolour_rows(src_hex, dst_hex, y_frac):
    def edit(i, im, a):
        arr = np.asarray(im).copy()
        h = arr.shape[0]
        sl = arr[int(y_frac[0] * h):int(y_frac[1] * h)]
        src = np.array(_hexrgb(src_hex))
        mask = np.abs(sl.astype(int) - src).sum(-1) < 60
        sl[mask] = _hexrgb(dst_hex)
        return Image.fromarray(arr), a
    return edit


def squash_to_square(i, im, a):
    w, _ = im.size
    return im.resize((w, w), Image.NEAREST), a.resize((w, w))


def flatten_relief(colour_hex):
    def edit(i, im, a):
        arr = np.asarray(im).astype(int)
        ref = np.array(_hexrgb(colour_hex))
        near = np.abs(arr - ref).sum(-1) < 90
        arr[near] = ref
        return Image.fromarray(arr.astype(np.uint8)), a
    return edit


def _product_bbox(img):
    arr = np.asarray(img).astype(int)
    diff = np.abs(arr - np.array(BG)).sum(-1) > 60
    ys, xs = np.nonzero(diff)
    return xs.min(), ys.min(), xs.max(), ys.max()


def fold_corner(img):
    x0, y0, x1, y1 = _product_bbox(img)
    leg = int(0.45 * (x1 - x0))
    img = img.copy()
    ImageDraw.Draw(img).polygon([(x1 + 4, y1 + 4), (x1 - leg, y1 + 4), (x1 + 4, y1 - leg)],
                                fill=BG)
    return img


def occlude(img):
    x0, y0, x1, y1 = _product_bbox(img)
    cx, cy, r = (x0 + x1) // 2, (y0 + y1) // 2, int(0.16 * (x1 - x0))
    img = img.copy()
    ImageDraw.Draw(img).ellipse((cx - r, cy - r, cx + r, cy + r), fill=(107, 68, 35))
    return img


CLOUD = "cloudline-baby-blanket"
WRAP = "reading-nook-cable-wrap"
COASTERS = "hexagon-coaster-set"
PERTURBATIONS = [
    {},
    {"blur": 2.0},
    {"gradient": 0.3},
    {"rotate": 6.0},
    {"jpeg": 60},
    {"rotate": -3.0, "blur": 1.5, "gradient": 0.2, "jpeg": 75},
]


# ---- positives -----------------------------------------------------------------------------

def test_positive_flat_lays_pass_under_photographic_perturbation():
    for slug in (CLOUD, WRAP, COASTERS):
        cir = _cir(slug)
        for kw in PERTURBATIONS:
            v = F.verify_anchor(flat_lay(cir, **kw), cir, judge=PASSING_JUDGE)
            assert v["status"] == "PASS", (slug, kw, v["failed"], v["unknown"], [
                (c["check"], c["why"]) for c in v["checks"] if c["status"] != "PASS"])
            assert v["codes"] == [] and v["reads_generator_claims"] is False


def test_positive_measures_the_declared_facts():
    cir = _cir(CLOUD)
    v = F.verify_anchor(flat_lay(cir, rotate=4), cir, judge=PASSING_JUDGE)
    rc = st(v, "repeat_count")[0]
    assert rc["status"] == "PASS" and rc["expected"] == 11 and abs(rc["measured"] - 11) < 0.3
    assert {c["check"] for c in v["checks"]} >= {
        "isolation", "piece_count", "panel:flat", "panel:aspect", "panel:palette",
        "panel:colour_layout", "panel:end_band_top", "panel:end_band_bottom", "panel:edges",
        "panel:repeat_count", "craft_texture"}
    w = _cir(WRAP)
    vw = F.verify_anchor(flat_lay(w), w, judge=PASSING_JUDGE)
    rw = st(vw, "repeat_count")[0]
    assert rw["what"] == "cable columns" and rw["expected"] == 8 and round(rw["measured"]) == 8
    vc = F.verify_anchor(flat_lay(_cir(COASTERS)), _cir(COASTERS), judge=PASSING_JUDGE)
    assert st(vc, "piece_count")[0]["measured"] == 4


# ---- negatives: each FAILs with its own code ----------------------------------------------

def _neg(slug, code, **kw):
    cir = _cir(slug)
    v = F.verify_anchor(flat_lay(cir, **kw), cir, judge=PASSING_JUDGE)
    assert v["status"] == "FAIL", (slug, code, v["status"], v["unknown"], v["codes"])
    assert code in codes(v), (slug, code, v["codes"], [
        (c["check"], c["why"]) for c in v["checks"] if c["status"] != "PASS"])
    return v


def test_added_stripe_in_end_band_fails_invented_end_band_treatment():
    _neg(CLOUD, "INVENTED_END_BAND_TREATMENT",
         piece_edit=stripe_in_top_band("#1A2B3C", (0.018, 0.026)))
    _neg(WRAP, "INVENTED_END_BAND_TREATMENT",
         piece_edit=stripe_in_top_band("#244A3A", (0.007, 0.011)), rotate=2.0)


def test_added_edging_fails_invented_edging():
    _neg(CLOUD, "INVENTED_EDGING", piece_edit=edging(_hexrgb("#FAF6EB"), 0.03))
    v = _neg(WRAP, "INVENTED_EDGING", piece_edit=edging(_hexrgb("#244A3A"), 0.06, ribbed=True))
    assert st(v, "edges")[0]["status"] == "FAIL"


def test_wrong_repeat_count_fails_wrong_repeat_count():
    v = _neg(CLOUD, "WRONG_REPEAT_COUNT", piece_edit=fewer_repeats(10, 11))
    rc = st(v, "repeat_count")[0]
    assert rc["expected"] == 11 and round(rc["measured"]) == 10


def test_extra_colour_fails_off_palette_colour():
    v = _neg(CLOUD, "OFF_PALETTE_COLOUR",
             piece_edit=recolour_rows("#1A2B3C", "#D4A017", (0.40, 0.46)))
    assert st(v, "palette")[0]["status"] == "FAIL"


def test_wrong_aspect_ratio_fails():
    v = _neg(CLOUD, "WRONG_ASPECT_RATIO", piece_edit=squash_to_square)
    a = st(v, "aspect")[0]
    assert abs(a["measured"] - 1.0) < 0.05 and abs(a["expected"] - 96.4 / 79.2) < 0.01


def test_missing_piece_fails_wrong_piece_count():
    v = _neg(COASTERS, "WRONG_PIECE_COUNT", drop=1)
    pc = st(v, "piece_count")[0]
    assert pc["expected"] == 4 and pc["measured"] == 3


# ---- UNKNOWN is never PASS ----------------------------------------------------------------

def test_low_confidence_count_is_unverifiable_unknown():
    cir = _cir(WRAP)
    v = F.verify_anchor(flat_lay(cir, piece_edit=flatten_relief("#244A3A")), cir,
                        judge=PASSING_JUDGE)
    rc = st(v, "repeat_count")[0]
    assert rc["status"] == "UNKNOWN" and rc["code"] == "UNVERIFIABLE_COUNT"
    assert v["status"] == "UNKNOWN" and "UNVERIFIABLE_COUNT" in codes(v)


def test_folded_or_occluded_is_unknown():
    cir = _cir(CLOUD)
    v = F.verify_anchor(flat_lay(cir, final_edit=fold_corner), cir, judge=PASSING_JUDGE)
    assert v["status"] == "UNKNOWN" and st(v, ":flat")[0]["status"] == "UNKNOWN", v["checks"]
    v = F.verify_anchor(flat_lay(cir, final_edit=occlude), cir, judge=PASSING_JUDGE)
    assert v["status"] == "UNKNOWN", [(c["check"], c["status"], c["why"]) for c in v["checks"]]
    assert st(v, "palette")[0]["status"] == "UNKNOWN"


def test_background_too_close_to_a_yarn_colour_is_unknown():
    cir = _cir(CLOUD)
    v = F.verify_anchor(flat_lay(cir, bg=(236, 232, 222)), cir, judge=PASSING_JUDGE)
    assert v["status"] == "UNKNOWN" and st(v, "isolation")[0]["status"] == "UNKNOWN"


def test_cropped_product_is_unknown():
    cir = _cir(CLOUD)
    v = F.verify_anchor(flat_lay(cir, fill=1.3), cir, judge=PASSING_JUDGE)
    assert v["status"] == "UNKNOWN" and st(v, "isolation")[0]["status"] == "UNKNOWN"

    def shift_off_edge(img):   # the piece slid partly out of frame, background still plain
        out = Image.new("RGB", img.size, BG)
        out.paste(img, (int(0.35 * img.size[0]), 0))
        return out

    v = F.verify_anchor(flat_lay(cir, final_edit=shift_off_edge, shadow=False), cir,
                        judge=PASSING_JUDGE)
    assert v["status"] == "UNKNOWN" and "cropped" in st(v, "isolation")[0]["why"], v["checks"]


# ---- craft texture is a vision question ---------------------------------------------------

def test_craft_texture_unfunded_is_unknown_and_blocks():
    cir = _cir(CLOUD)
    good = flat_lay(cir)
    v = F.verify_anchor(good, cir, judge=None)
    assert v["status"] == "UNKNOWN" and st(v, "craft_texture")[0]["status"] == "UNKNOWN"
    assert all(c["status"] in ("PASS", "NOT_APPLICABLE") for c in v["checks"]
               if c["check"] != "craft_texture")

    class NoCalls:
        model = "never"

        def see(self, *a, **k):
            raise AssertionError("a closed image_vision gate must not call a provider")

    from test_w4_ownerimg import make_db

    j = F.GatewayVisionJudge(make_db(), provider=NoCalls())
    assert j.gate_open() is False
    v = F.verify_anchor(good, cir, judge=j)
    ct = st(v, "craft_texture")[0]
    assert ct["status"] == "UNKNOWN" and "unfunded" in ct["why"] and v["status"] == "UNKNOWN"


def test_craft_texture_fail_reading_is_wrong_craft_texture():
    cir = _cir(WRAP)
    knit = FakeJudge({"craft": "knitting", "ribbing_visible": "true",
                      "border_or_edging_visible": "true", "cable_style": "knitted_rope",
                      "fabric_visible_clearly": "true"})
    v = F.verify_anchor(flat_lay(cir), cir, judge=knit)
    assert v["status"] == "FAIL" and "WRONG_CRAFT_TEXTURE" in codes(v)
    unclear = FakeJudge({"craft": "unclear", "fabric_visible_clearly": "false"})
    v = F.verify_anchor(flat_lay(cir), cir, judge=unclear)
    assert v["status"] == "UNKNOWN"
    # the judge is asked blind: the prompt names no product fact
    p = F.craft_prompt().lower()
    assert "cable2x2" not in p and "forest" not in p and "wrap" not in p


# ---- the owner's real wrap image ------------------------------------------------------------

def test_owner_wrap_image_is_never_pass():
    data = (WRAP_DIR / "output_image.png").read_bytes()
    cir = _cir(WRAP)
    as_anchor = F.verify_anchor(data, cir, judge=PASSING_JUDGE)
    assert as_anchor["status"] != "PASS"
    assert st(as_anchor, "isolation")[0]["status"] == "UNKNOWN"
    rel = __import__("brambleloop.creative.pattern_refs", fromlist=["x"]).release_hash_of(cir)
    for kw in ({}, {"anchor": {"status": "UNKNOWN", "release_hash": rel}},
               {"anchor": {"status": "PASS", "release_hash": rel}},
               {"anchor": {"status": "PASS", "release_hash": rel},
                "product_region": (310, 215, 645, 650)}):
        v = F.verify_lifestyle(data, cir, release_hash=rel, anchor=kw.get("anchor"),
                               product_region=kw.get("product_region"), judge=None)
        assert v["status"] in ("UNKNOWN", "FAIL"), (kw, v["status"])
    # a funded judge that sees what the owner saw makes it a FAIL with the owner's codes
    seen = FakeJudge({"craft": "knitting", "ribbing_visible": "true",
                      "border_or_edging_visible": "true", "cable_style": "knitted_rope",
                      "fabric_visible_clearly": "true"}, same=False)
    v = F.verify_lifestyle(data, cir, release_hash=rel,
                           anchor={"status": "PASS", "release_hash": rel},
                           anchor_data=flat_lay(cir), product_region=(310, 215, 645, 650),
                           judge=seen)
    assert v["status"] == "FAIL" and {"WRONG_CRAFT_TEXTURE", "INVENTED_EDGING"} <= codes(v)


def test_lifestyle_needs_anchor_pass_region_and_vision():
    cir = _cir(CLOUD)
    from brambleloop.creative.pattern_refs import release_hash_of

    rel = release_hash_of(cir)
    img = flat_lay(cir)
    full = {"anchor": {"status": "PASS", "release_hash": rel}, "anchor_data": img,
            "product_region": (300, 200, 1750, 1850), "judge": PASSING_JUDGE}
    assert F.verify_lifestyle(img, cir, release_hash=rel, **full)["status"] == "PASS"
    for drop, val in (("anchor", None), ("anchor", {"status": "PASS", "release_hash": "f" * 64}),
                      ("anchor", {"status": "FAIL", "release_hash": rel}),
                      ("anchor_data", None), ("product_region", None), ("judge", None)):
        v = F.verify_lifestyle(img, cir, release_hash=rel, **{**full, drop: val})
        assert v["status"] == "UNKNOWN", (drop, val, v["status"])


def test_codes_and_verdict_contract():
    from brambleloop.creative import failure_codes as FCm

    assert set(FCm.ALL_CODES) <= F.ALL_CODES
    assert not set(F.LOCAL_CODES) & set(FCm.ALL_CODES)      # nothing redefined
    assert all(r["category"] == FCm.PRODUCT_FIDELITY for r in F.LOCAL_CODES.values())
    assert F.worst(["PASS", "UNKNOWN"]) == "UNKNOWN" and F.worst([]) == "UNKNOWN"
    assert F.worst(["NOT_APPLICABLE"]) == "UNKNOWN" and F.worst(["PASS", "FAIL"]) == "FAIL"
    v = F._verdict([F._check("x", "PASS", "ok", code="INVENTED_EDGING")], data=b"x", exp=None,
                   kind="anchor")
    assert v["status"] == "PASS" and v["codes"] == []
    assert F.verify_anchor(b"not an image", _cir(CLOUD))["status"] == "FAIL"


# ---- wiring: candidate_gates Product Truth and image_production stage 4 --------------------

class FlatLayGenerator:
    """A non-paid test generator whose product-only image is a synthetic flat lay."""

    name, paid, max_cost_cad_per_call = "flatlay-stub", False, 0.0

    def __init__(self, slug, **kw):
        self.cir, self.kw = _cir(slug), kw
        self.calls, self.repairs = 0, []

    def prepare_references(self, **kw):
        return [{"kind": "pattern_derived", "data": flat_lay(self.cir, canvas=256),
                 "label": "layout"}]

    def generate(self, **kw):
        self.calls += 1
        self.repairs.append(kw.get("repair"))
        return {"data": flat_lay(self.cir, **self.kw), "provider": "stub", "model": "stub-1",
                "prompt": kw["brief"], "cost_cad": 0.0, "latency_s": 0.01}


def _run(db, gen, judges):
    from test_w4_ownerimg import RELEASE, drain
    from brambleloop.visual import image_production as IP

    follow, _ = drain(db, generator=gen, judges=judges)
    import test_w4_ownerimg as O

    IP.trigger(follow, slug=CLOUD, version="1.2.0", release=O.RELEASE)
    drain(db, generator=gen, judges=judges, limit=12)
    return IP.get_run(db, IP.run_key(CLOUD, "1.2.0", O.RELEASE))


def test_stage4_passes_a_faithful_anchor_with_a_vision_reading():
    import test_w4_ownerimg as O
    from brambleloop.visual import candidate_gates as CG
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    run = _run(db, FlatLayGenerator(CLOUD, rotate=3, blur=1.0),
               CG.RealJudges(db, vision=FakeJudge()))
    assert "fidelity_gate" in run["stages"] and "load_laura_references" in run["stages"], run
    best = IP._best(db, listing="cloudline-baby-blanket", role=IP.ANCHOR_ROLE,
                    run=run["run_key"])
    assert best["technical_status"] == "PASS" and best["fidelity"]["status"] == "PASS"


def test_stage4_blocks_without_a_vision_judge_and_names_it():
    import test_w4_ownerimg as O
    from brambleloop.visual import candidate_gates as CG

    db = O.make_db()
    run = _run(db, FlatLayGenerator(CLOUD), CG.RealJudges(db))   # image_vision closed
    assert run["state"] == "blocked" and "fidelity cannot be verified" in run["blocked_reason"]
    assert "craft_texture" in run["blocked_reason"] and "vision judge" in run["blocked_reason"]
    assert run["generation_calls"] == 1 and not run["attempts_exhausted"]


def test_stage4_regenerates_a_failing_anchor_with_a_targeted_repair_then_blocks():
    import test_w4_ownerimg as O
    from brambleloop.visual import candidate_gates as CG
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    gen = FlatLayGenerator(CLOUD, piece_edit=stripe_in_top_band("#1A2B3C", (0.018, 0.026)))
    run = _run(db, gen, CG.RealJudges(db, vision=FakeJudge()))
    assert run["state"] == "blocked" and run["attempts_exhausted"], run
    assert gen.calls == IP.MAX_ATTEMPTS_PER_ROLE
    assert gen.repairs[0] is None and gen.repairs[1] and \
        gen.repairs[1]["codes"] == ["INVENTED_END_BAND_TREATMENT"]
    learn = IP.learning_summary(db, slug=CLOUD)
    assert learn["failure_categories"].get("INVENTED_END_BAND_TREATMENT") == \
        IP.MAX_ATTEMPTS_PER_ROLE


def test_publication_gates_are_not_relaxed():
    """A generated image whose fidelity PASSes is still refused publication (F-852)."""
    import test_w4_ownerimg as O
    from brambleloop.visual import candidate_gates as CG

    db = O.make_db()
    _run(db, FlatLayGenerator(CLOUD), CG.RealJudges(db, vision=FakeJudge()))   # anchor PASS
    img = flat_lay(_cir(CLOUD))
    for role in ("lifestyle", "detail", "colour_context"):
        v = CG.evaluate(db, O.cand(data=img, role=role, release=O.RELEASE,
                                   product_region=(300, 200, 1750, 1850)),
                        judges=CG.RealJudges(db, vision=FakeJudge()))
        assert v["publishable"] is False and any("F-852" in b for b in
                                                 v["publication"]["blockers"]), role
        assert "fidelity" in v["checks"]["product_truth"]
    lif = CG.evaluate(db, O.cand(data=img, role="lifestyle", release=O.RELEASE,
                                 references=[{"sha256": "a" * 64, "kind": "pattern_derived"}]),
                      judges=CG.RealJudges(db, vision=FakeJudge()))
    assert lif["checks"]["product_truth"]["status"] == "FAIL"    # lifestyle_evidence kept
    # an anchor with no vision reading is never PASS through the gates
    pt = CG.RealJudges(db).product_truth({**O.cand(data=img), "role": "product_anchor"},
                                         CG.binding(db, CLOUD, "1.2.0", O.RELEASE))
    assert pt["status"] == "UNKNOWN"


def test_binding_records_the_real_cir_fingerprint():
    import test_w4_ownerimg as O
    from brambleloop.visual import candidate_gates as CG

    db = O.make_db()
    b = CG.binding(db, CLOUD, "1.2.0", O.RELEASE)
    assert b["status"] == "PASS" and b["cir_fingerprint"] == _cir(CLOUD).fingerprint
    rows = [{"listing": "l", "version": "1", "release": "r", "cir_fingerprint": fp}
            for fp in (b["cir_fingerprint"], "0" * 16)]
    assert CG.campaign_consistency(rows)["status"] == "FAIL"


if __name__ == "__main__":
    fails = passes = 0
    only = sys.argv[1:]
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn) and (not only or name in only):
            try:
                fn()
                passes += 1
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e)[:300])
    print(f"\n{passes} passed, {fails} failed")
    sys.exit(1 if fails else 0)
