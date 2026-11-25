"""IMAGE-FIDELITY-2 (19i26): two false Product Truth rejections, fixed at the root, and the five
exhausted gallery runs re-judged once.

Production 19i25 (3f1727b65, evidence 2026-11-25T07:24Z): FLUX generating again (41
candidates, 14 accepted, 21 rejected) and every gallery dead-ends at
`fidelity_gate:product_truth:exhausted` (5 runs): hexagon-coaster-set@1.2.1 x2,
market-basket-small@1.3.0 and housewarming-key-basket@0.1.0. By code: INVENTED_EDGING 10
(all `craft_texture`), WRONG_COLOUR_LAYOUT 14 (`basket:wall_bands`), WRONG_REPEAT_COUNT 9
(`basket:sides`), OFF_PALETTE_COLOUR 6 (`basket:palette`).

1. Coaster INVENTED_EDGING. The coaster's certified design has a wine contrast round 6 of 7,
   one round inside the outer edge, and no edging. The craft judge was asked
   "border_or_edging_visible (a band of different stitches or colour worked around or along
   the edges)" -- which is exactly what a declared contrast round near the edge is -- and
   `compare_craft` turned that `true` into INVENTED_EDGING. The repair then told FLUX "no
   edging, no border", which pushed it away from the certified wine round. Fixed: the judge
   (`fidelity-judge/2`) is told the declared colour layout and asked `added_edging_visible`
   (anything worked onto or BEYOND it); the prompt builder names the contrast round as part
   of the fabric and forbids its loss after every other negative; the INVENTED_EDGING repair
   names what an edging is and keeps every charted round.
2. Basket wall_bands / palette. The side-view check read the whole silhouette's centre
   column. A view from even slightly above the rim shows the opening and, through it, the
   INSIDE of the far wall -- the same stripes again -- so a correct two-stripe basket read
   four stripes (and its shadowed inside pulled the palette coverage down). The certified
   PDF's own renderings (the owner's method sends them to FLUX as references) are such
   views, and FAIL the old check. Fixed: the near wall's projected height is read from the
   steep part of the side outlines and only the near wall is read. Also: band shares were by
   ROUND COUNT; the key basket's wall has double-crochet rounds and a slip-stitch rim, so a
   faithful render failed even at eye level. Shares are now by height (the twin's rule).
3. The FLUX side and top prompts name their camera and say the angled PDF renderings are for
   colours and shape only.
4. The five runs: the hourly sweep re-judges each once under the new judge version
   (`fidelity_rejudge_redrive`), with no generation; every cap binds.

Every judge answer here is a TEST FIXTURE. There is no network and no paid call.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_image_fidelity_2.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import io
import math
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
_TMP = tempfile.mkdtemp(prefix="fid2_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("BRAMBLELOOP_IMAGE_KEY_OPENAI", None)


def _no_network(*_a, **_k):
    raise OSError("network refused by the IMAGE-FIDELITY-2 harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.cir.model import CIR  # noqa: E402
from brambleloop.creative import flux_prompt as FP  # noqa: E402
from brambleloop.creative import image_stages as S  # noqa: E402
from brambleloop.creative import pattern_refs as PR  # noqa: E402
from brambleloop.creative import failure_codes as FC  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.visual import disclosed_render as D  # noqa: E402
from brambleloop.visual import fidelity as F  # noqa: E402
from brambleloop.visual import render_contract as K  # noqa: E402
from brambleloop.visual import repair_routes as RR  # noqa: E402
from brambleloop.visual import vessel as V  # noqa: E402

COASTERS = "hexagon-coaster-set"
WINE = "#6E1F2A"


# ---- fixtures ---------------------------------------------------------------------------------

class _Judge:
    """FIXTURE craft judge. It answers as the production judge did on a faithful coaster
    frame: the wine round near the edge IS "a band of colour along the edges", so
    `border_or_edging_visible` is true. Asked the versioned question (the prompt states the
    declared design and asks `added_edging_visible`), it answers that key: `added`.
    Never a model answer; spends nothing."""

    name = "fixture-vision"

    def __init__(self, added="false", border="true", **extra):
        self.added, self.border, self.extra, self.prompts = added, border, extra, []

    def read(self, prompt, images, **_kw):
        self.prompts.append(prompt)
        reading = {"craft": "crochet", "ribbing_visible": "false",
                   "border_or_edging_visible": self.border, "edge_placement": "around_or_sides",
                   "all_edges_visible": "true", "cable_style": "none",
                   "fabric_visible_clearly": "true", **self.extra}
        if "added_edging_visible" in prompt:
            reading["added_edging_visible"] = self.added
        return {"answered": True, "reading": reading}


_LAY: dict = {}


def _coasters():
    if not _LAY:
        import test_w4_fidelity as W

        cir = W._cir(COASTERS)
        _LAY.update(W=W, cir=cir, good=W.flat_lay(cir))
    return _LAY


def _outer_ring(colour_hex, frac):
    """A piece edit: an extra round worked around the outside (the coaster's edge)."""
    rgb = tuple(int(colour_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))

    def edit(_i, im, a):
        from scipy import ndimage

        im = im.copy()
        w, _h = im.size
        e = max(3, int(frac * w))
        inside = np.asarray(a) > 127
        ring = inside & ~ndimage.binary_erosion(inside, iterations=e)
        arr = np.asarray(im).copy()
        arr[ring] = rgb
        return Image.fromarray(arr), a
    return edit


def _craft(v):
    return next(c for c in v["checks"] if c["check"] == "craft_texture")


def _oblique(cir, deg):
    """The certified basket drawn by the disclosed renderer (the PDF's own renderer) at camera
    elevation `deg`: deterministic, CA$0. Only the product zone, no caption or scale bar."""
    saved = K.camera_deg
    K.camera_deg = lambda view: deg
    try:
        frame = D.render(cir, "hero")
    finally:
        K.camera_deg = saved
    im = Image.open(io.BytesIO(frame.png)).convert("RGB")
    zx0, zy0, zx1, zy1 = K.zone_px(K.PRODUCT_ZONE)
    im = im.crop((int(zx0) - 20, int(zy0) - 20, int(zx1) + 20, int(zy1) + 20))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _variant(key, recolour):
    """(certified CIR, a WRONG product): the same basket with rounds recoloured."""
    good = launch0.cir_for(key)
    d = good.to_dict()
    for r in d["components"][0]["rows"]:
        if r["index"] in recolour:
            r["color"] = recolour[r["index"]]
    return good, CIR.from_dict(d)


def _status(checks):
    st = [c["status"] for c in checks]
    return "FAIL" if "FAIL" in st else "UNKNOWN" if "UNKNOWN" in st else "PASS"


# ---- 1. the coaster: a declared contrast round is not an edging ---------------------------------

def test_1_the_old_question_reads_the_declared_wine_round_as_invented_edging():
    """Reproduces 19i25: the unversioned question ("a band of different stitches or colour
    along the edges") answered true for the wine round -> INVENTED_EDGING on a faithful
    coaster. A reading without the new key is still judged by that stricter old field."""
    lay = _coasters()
    exp = F.expectation(lay["cir"])
    assert exp.edging_declared is False, exp.edging_declared
    old = F.compare_craft({"craft": "crochet", "ribbing_visible": "false",
                           "border_or_edging_visible": "true", "cable_style": "none",
                           "fabric_visible_clearly": "true"}, exp)
    assert old["status"] == "FAIL" and old["code"] == FC.INVENTED_EDGING, old


def test_2_the_judge_is_told_the_declared_rounds_and_a_faithful_coaster_passes():
    lay = _coasters()
    exp = F.expectation(lay["cir"])
    prompt = F.craft_prompt(exp)
    assert "DECLARED DESIGN" in prompt and "round 6 wine #6E1F2A" in prompt, prompt
    assert "round 7 is the outermost round" in prompt and "never an edging" in prompt
    assert "added_edging_visible" in prompt and "picot" in prompt and "scallop" in prompt
    assert "extra round or row beyond the declared outermost one" in prompt
    judge = _Judge(added="false", border="true")
    v = F.verify_anchor(lay["good"], lay["cir"], judge=judge)
    assert v["status"] == "PASS" and v["codes"] == [], [
        (c["check"], c["status"], c["why"]) for c in v["checks"] if c["status"] != "PASS"]
    assert v["judge_version"] == F.FIDELITY_JUDGE_VERSION == "fidelity-judge/2"
    assert judge.prompts and "DECLARED DESIGN" in judge.prompts[0]


def test_3_an_undeclared_textured_edging_still_fails():
    """A picot/scallop/crab-stitch edging in the outer round's own colour: the colour layout
    cannot see it, the judge can, and it is INVENTED_EDGING."""
    lay = _coasters()
    v = F.verify_anchor(lay["good"], lay["cir"], judge=_Judge(added="true", border="true"))
    assert v["status"] == "FAIL" and FC.INVENTED_EDGING in v["codes"], v["codes"]
    assert _craft(v)["code"] == FC.INVENTED_EDGING


def test_4_an_extra_round_still_fails():
    """An extra round worked around the outside, one round wide (1/7 of the radius):
    in wine, the deterministic colour layout FAILs it whatever the judge says; in the outer
    round's own cream, colour cannot see it (a pre-existing blind spot) and the judge's
    `added_edging_visible: true` ("an extra round beyond the declared outermost one") FAILs it."""
    lay = _coasters()
    W = lay["W"]
    wine = W.flat_lay(lay["cir"], piece_edit=_outer_ring(WINE, 0.065))
    v = F.verify_anchor(wine, lay["cir"], judge=_Judge(added="false"))
    assert v["status"] == "FAIL" and FC.INVENTED_EDGING in v["codes"], v["codes"]
    layout = [c for c in v["checks"] if c["check"].endswith(":colour_layout")]
    assert layout and all(c["status"] == "FAIL" for c in layout), layout
    cream = W.flat_lay(lay["cir"], piece_edit=_outer_ring("#FAF6EB", 0.065))
    v2 = F.verify_anchor(cream, lay["cir"], judge=_Judge(added="true", border="true"))
    assert v2["status"] == "FAIL" and FC.INVENTED_EDGING in v2["codes"], v2["codes"]
    assert _craft(v2)["status"] == "FAIL"


def test_5_unclear_stays_unknown_and_other_codes_are_unchanged():
    lay = _coasters()
    exp = F.expectation(lay["cir"])
    base = {"craft": "crochet", "ribbing_visible": "false", "border_or_edging_visible": "true",
            "cable_style": "none", "fabric_visible_clearly": "true"}
    assert F.compare_craft({**base, "added_edging_visible": "unclear"}, exp)["status"] == "UNKNOWN"
    knit = F.compare_craft({**base, "craft": "knitting", "added_edging_visible": "false"}, exp)
    assert knit["status"] == "FAIL" and knit["code"] == FC.WRONG_CRAFT_TEXTURE, knit
    rib = F.compare_craft({**base, "ribbing_visible": "true", "added_edging_visible": "false"},
                          exp)
    assert rib["status"] == "FAIL", rib


def test_6_the_repair_and_the_prompt_never_remove_a_declared_colour_round():
    """The INVENTED_EDGING repair names what an edging is; no bare "no border"/"no stripe";
    and the built prompt, repair included, keeps the wine round after every negative."""
    negs = RR.ROUTES[FC.INVENTED_EDGING]["negatives"]
    joined = " ".join(negs).lower()
    assert "no border" not in joined and "no stripe" not in joined and "no contrast" not in joined
    assert "picot" in joined and "every charted colour row or round kept" in joined
    assert negs[0].startswith("no edging")          # existing callers read "no edging"
    cir = launch0.cir_for("hexagon_coasters")
    rules = PR.technical_rules(cir, PR._components(cir), release_hash="x" * 64)
    rules["negatives"] = list(rules["negatives"]) + list(negs)       # as the generator does
    text = FP.build(rules=rules, roles=list(FP.PRODUCT_ROLES), role="product-only flat lay",
                    scene=S.product_scene(rules, ["#FAF6EB", WINE])).text
    neg_line = next(l for l in text.split("\n") if l.startswith("THIS FABRIC MUST NOT SHOW"))
    keep = "a missing, moved, merged or recoloured contrast band: wine #6E1F2A round 6"
    assert keep in neg_line and neg_line.index(keep) > neg_line.index("no edging worked"), \
        neg_line
    assert "never an edging, border or trim, and must be shown" in neg_line
    assert "part of the design, not an edging or border" in text
    assert "the outer edge is the final round (round 7) in cream" in text
    assert FP.BUILDER_VERSION == "flux3-prompt-builder/2.4.0"


# ---- 2. the basket: read the near wall, shares by height ------------------------------------

def test_7_the_certified_baskets_own_angled_render_failed_the_old_full_column_reading():
    """Root cause, reproduced on the certified basket drawn by the PDF's renderer at 20
    degrees: the whole centre column reads the far wall's inside as two more stripes."""
    cir = launch0.cir_for("basket_small")
    m = V.vessel_models(cir)[0]
    data = _oblique(cir, 20)
    mask, _lab, _why = V._product_mask(data)
    lab, _ = V.illumination_corrected(F._load(data), mask, m.palette)
    full = [r[0] for r in V._bands(mask, lab, m.palette, m.wall_total_rows)[0]]
    assert full.count("wine") == 4 and m.wall_bands.count("wine") == 2, full
    view = V.near_wall(mask)
    assert view["opening"] and view["ratio"] > 1.3, view


def test_8_a_faithful_basket_passes_from_eye_level_to_well_above_the_rim():
    for key, angles in (("basket_small", (0, 5, 10, 15, 20, 30, 40)),
                        ("key_basket", (0, 5, 10, 15, 20))):
        cir = launch0.cir_for(key)
        m = V.vessel_models(cir)[0]
        assert len(angles) >= 5, angles
        for deg in angles:
            out = V.verify_side(_oblique(cir, deg), m)
            assert _status(out) == "PASS", (key, deg, [(c["check"], c["status"], c["why"])
                                                       for c in out if c["status"] != "PASS"])
            pal = next(c for c in out if c["check"].endswith(":palette"))
            assert pal["view"]["opening"] == (deg >= 5 and pal["view"]["ratio"] > 1.15), pal


def test_9_a_wrong_wall_still_fails_at_every_angle():
    cases = {"extra stripe at the top": ("basket_small", {21: "wine"}),
             "extra stripe low": ("basket_small", {12: "wine"}),
             "one stripe missing": ("basket_small", {18: "cream", 19: "cream"}),
             "thin stripes, wide gap": ("basket_small", {16: "cream", 17: "cream",
                                                         18: "cream", 19: "wine"}),
             "fat stripes": ("basket_small", {14: "wine", 20: "wine"}),
             "key basket stripe missing": ("key_basket", {18: "cream"})}
    assert len(cases) == 6, cases
    for name, (key, recolour) in cases.items():
        good, bad = _variant(key, recolour)
        m = V.vessel_models(good)[0]
        for deg in (0, 10, 20, 30):
            out = V.verify_side(_oblique(bad, deg), m)
            assert _status(out) == "FAIL", (name, deg, [(c["check"], c["status"], c["why"])
                                                        for c in out])


def test_10_band_shares_are_by_height_and_the_prompt_says_so():
    """The key basket's wall: dc rounds stand 1.5x an sc round and the slip-stitch rim is a
    sliver. Round-count shares said 3 pine rounds = 25% of the wall; the twin says ~15%."""
    key = launch0.cir_for("key_basket")
    m = V.vessel_models(key)[0]
    assert m.wall_rows[-1] == 3 and abs(m.wall_rows[-1] / m.wall_total_rows - 0.25) < 1e-9
    assert 0.13 < m.wall_shares[-1] < 0.17, m.wall_shares
    assert abs(sum(m.wall_shares) - 1.0) < 1e-9
    small = V.vessel_models(launch0.cir_for("basket_small"))[0]
    assert [round(x, 3) for x in small.wall_shares] == [round(n / 12, 3)
                                                        for n in small.wall_rows]
    rules = PR.technical_rules(key, PR._components(key), release_hash="x" * 64)
    assert [b["share"] for b in rules["vessel"]["wall_bands"]] == [
        round(x, 3) for x in m.wall_shares]
    text = FP.counts_and_proportion(rules)
    assert "3 rounds of pine #244A3A (15% of the wall height)" in text, text
    # the eye-level render of the certified key basket passes now (it failed on shares)
    out = V.verify_side(_oblique(key, 0), m)
    assert _status(out) == "PASS", [(c["check"], c["why"]) for c in out]


def test_11_the_vessel_views_name_their_camera_and_refuse_the_angled_renderings():
    cir = launch0.cir_for("basket_small")
    rules = PR.technical_rules(cir, PR._components(cir), release_hash="x" * 64)
    pal = [c["hex"] for c in rules["colours"]]
    side = FP.build(rules=rules, roles=list(FP.PRODUCT_ROLES), role="product-only side view, "
                    "standing", scene=S.product_scene(rules, pal, view="side")).text
    top = FP.build(rules=rules, roles=list(FP.PRODUCT_ROLES), role="product-only top view, "
                   "standing", scene=S.product_scene(rules, pal, view="top")).text
    for text in (side, top):
        assert "never for the camera angle of this image" in text
        assert "SCENE (product-only flat lay)" not in text
    assert "The opening and the inside are NOT visible" in side
    assert "straight down at 90 degrees" in top and "none of the outside of the wall" in top


# ---- 3. the exhausted runs are re-judged once --------------------------------------------------

def _db():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.visual.image_records import ensure_tables

    _db.n = getattr(_db, "n", 0) + 1
    db = Database(f"sqlite:///{_TMP}/r{_db.n}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    ensure_tables(db)
    return db


def _vision(db, on=True):
    import _paid_activation as paid
    from brambleloop.gateway import paid_provider_gate as G

    if on:
        paid.activate(db, G.OPENAI_VISION, G.VISION, daily=2.0, monthly=10.0, per_gallery=1.0)
        os.environ["BRAMBLELOOP_IMAGE_KEY_OPENAI"] = "fixture-key-not-a-secret"
    else:
        os.environ.pop("BRAMBLELOOP_IMAGE_KEY_OPENAI", None)


EXHAUSTED = "product fidelity FAIL after 3 attempts: ['craft_texture']"


def _run(db, slug=COASTERS, *, failed=("craft_texture",), judge_version=None, n=3,
         restarts=0, reason=EXHAUSTED, ns=""):
    from brambleloop.visual import image_production as IP
    from brambleloop.visual.image_records import ImageCandidate, ImageProductionRun

    key = IP.run_key(slug, "1.2.1", f"{slug}-83b5db1f2cb4", ns=ns, route=IP.SP.FLUX_ROUTE)
    stages = {}
    if restarts:
        stages[IP.RESTART_KEY] = {"epoch": restarts, "history": [
            {"epoch": i + 1, "by": "owner:test", "reason": "earlier"} for i in range(restarts)]}
    fid = {"status": "FAIL", "failed": list(failed),
           "codes": [FC.INVENTED_EDGING] if "craft_texture" in failed else ["X"]}
    if judge_version:
        fid["judge_version"] = judge_version
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug=slug, version="1.2.1",
                                 release=f"{slug}-83b5db1f2cb4", listing=slug,
                                 stage="fidelity_gate", status="blocked", blocked_reason=reason,
                                 stages=stages, generation_calls=n, spent_cad=0.21,
                                 attempts_exhausted=True))
        for a in range(1, n + 1):
            s.add(ImageCandidate(
                sha256=f"{a:064x}", run_key=key, method="autonomous",
                provenance_kind="ai_generated_autonomous", slug=slug, version="1.2.1",
                release=f"{slug}-83b5db1f2cb4", listing=slug, role=IP.ANCHOR_ROLE,
                stage="product_generation", attempt=a,
                checks={"product_truth": {"status": "FAIL", "fidelity": fid}},
                technical_status="FAIL", outcome="rejected"))
    return key


def _follow(calls):
    def follow(inputs, key, *, session=None):
        calls.append((inputs, key))
        return object()
    return follow


def _row(db, key):
    from brambleloop.visual.image_records import ImageProductionRun

    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        return {"status": r.status, "stage": r.stage, "calls": r.generation_calls,
                "spent": r.spent_cad, "reason": r.blocked_reason, "stages": dict(r.stages or {})}


def _due(db):
    from brambleloop.visual import image_production as IP

    with db.session() as s:
        return IP.redrive_due(s, None)


def test_12_an_exhausted_run_failed_by_the_old_judge_is_rejudged_once_without_generating():
    from brambleloop.visual import image_production as IP

    db = _db()
    _vision(db)
    key = _run(db)
    assert IP.rejudge_candidate_ids(db, key) and len(IP.rejudge_candidate_ids(db, key)) == 3
    due = _due(db)
    assert due["run_key"] == key and due["kind"] == "fidelity_rejudge", due
    calls = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert [r["run_key"] for r in out["restarted"]] == [key], out
    assert len(calls) == 1
    inputs, job_key = calls[0]
    assert inputs["stage"] == "fidelity_gate" and inputs["reverify"] is True, inputs
    assert inputs["rejudge"] is True and job_key.endswith(":e1"), (inputs, job_key)
    row = _row(db, key)
    assert row["status"] != "blocked" and row["calls"] == 3 and abs(row["spent"] - 0.21) < 1e-9
    hist = row["stages"][IP.RESTART_KEY]["history"][-1]
    assert hist["by"] == IP.FIDELITY_REJUDGE_BY and hist["judge_version"] == "fidelity-judge/2"
    assert IP._attempts(db, key, IP.ANCHOR_ROLE) == 3, "a re-judgement adds no attempt"
    # blocked again with the same FAILs: never re-judged again under this version
    from brambleloop.visual.image_records import ImageProductionRun
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        r.status, r.blocked_reason, r.stage = "blocked", EXHAUSTED, "fidelity_gate"
    assert not IP._rejudge_redrive_candidate(db, key, EXHAUSTED, _row(db, key)["stages"])
    calls2 = []
    out2 = IP.redrive_capability_blocked(db, follow=_follow(calls2))
    assert not any(h.get("by") == IP.FIDELITY_REJUDGE_BY
                   for h in (_row(db, key)["stages"][IP.RESTART_KEY]["history"][1:])), out2
    assert (_due(db) or {}).get("kind") != "fidelity_rejudge"


def test_13_no_vision_route_waits_for_the_day_and_spends_nothing():
    from brambleloop.visual import image_production as IP

    db = _db()
    _vision(db, on=False)
    key = _run(db)
    calls = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert calls == [] and [w["run_key"] for w in out["waiting"]] == [key], out
    rec = _row(db, key)["stages"][IP.FIDELITY_REJUDGE_KEY]
    assert rec["judge_version"] == F.FIDELITY_JUDGE_VERSION and rec["day"], rec
    assert (_due(db) or {}).get("kind") != "fidelity_rejudge"


def test_14_only_frames_this_version_reads_differently_and_every_cap_binds():
    from brambleloop.visual import image_production as IP

    db = _db()
    _vision(db)
    # a FAIL on a check this version does not change (piece_count): not re-judged here
    other = _run(db, "coaster-piece-count", failed=("piece_count",))
    # already judged under the current version
    current = _run(db, "coaster-current", judge_version=F.FIDELITY_JUDGE_VERSION)
    # the restart cap is spent
    capped = _run(db, "coaster-capped", restarts=IP.MAX_RESTARTS)
    # an experiment run is one-shot
    xp = _run(db, "coaster-xp", ns="xp1")
    # basket checks this version reads differently are eligible
    basket = _run(db, "market-basket-small", failed=("basket:wall_bands", "basket:palette"),
                  reason="product fidelity FAIL after 3 attempts: ['basket:wall_bands']")
    assert not IP.rejudge_candidate_ids(db, other)
    assert not IP.rejudge_candidate_ids(db, current)
    assert IP.rejudge_candidate_ids(db, basket)
    assert not IP._rejudge_redrive_candidate(db, xp, EXHAUSTED, {})
    calls = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    by_rejudge = [r["run_key"] for r in out["restarted"] if r.get("kind") == "fidelity_rejudge"]
    assert by_rejudge == [basket], out
    for key in (other, current, capped, xp):
        hist = (_row(db, key)["stages"].get(IP.RESTART_KEY) or {}).get("history") or []
        assert not any(h.get("by") == IP.FIDELITY_REJUDGE_BY for h in hist), (key, hist)
    rec = _row(db, capped)["stages"].get(IP.FIDELITY_REJUDGE_KEY) or {}
    assert rec.get("day") is None and "cap" in rec.get("why", ""), rec
    assert _row(db, capped)["status"] == "blocked"


def _stage_after_rejudge(flip=None):
    """Run the re-driven `fidelity_gate` job with `reverify` stubbed (it re-reads stored bytes
    with the real judges in production; here it records the ids, and `flip` turns one frame's
    re-read into a PASS). Sale admission is stubbed open: these runs were admitted."""
    from brambleloop.visual import image_production as IP
    from brambleloop.visual.image_records import ImageCandidate

    db = _db()
    _vision(db)
    key = _run(db)
    calls = []
    IP.redrive_capability_blocked(db, follow=_follow(calls))
    seen = []

    def fake_reverify(db_, cid, judges=None, exp=None):
        seen.append(cid)
        if flip == cid:
            with db_.session() as s:
                row = s.get(ImageCandidate, cid)
                row.technical_status, row.outcome = "PASS", "accepted"
        return {"reverified": True}

    saved = (IP.reverify, IP._spend_admitted, IP._sale_owned, IP.sale_admission)
    IP.reverify = fake_reverify
    IP._spend_admitted = lambda *a, **k: True
    IP._sale_owned = lambda *a, **k: False
    IP.sale_admission = lambda *a, **k: {"admitted": True}
    nxt = []
    try:
        IP.run_stage(db, dict(calls[0][0]), follow=_follow(nxt), generator=None,
                     judges=object())
    finally:
        IP.reverify, IP._spend_admitted, IP._sale_owned, IP.sale_admission = saved
    return db, key, seen, nxt


def test_16_the_rejudge_job_rereads_every_failed_frame_and_generates_nothing():
    from brambleloop.visual import image_production as IP

    db, key, seen, nxt = _stage_after_rejudge()
    ids = sorted(seen, reverse=True)
    assert seen == ids and len(seen) == 3, seen            # every FAILed frame, newest first
    run = IP.get_run(db, key)
    assert run["state"] == "blocked" and run["attempts_exhausted"], run
    assert run["generation_calls"] == 3 and nxt == [], "a FAIL stays a FAIL; nothing generated"
    # one frame now PASSes under the corrected judge: the gallery moves on, still no generation
    db2, key2, seen2, nxt2 = _stage_after_rejudge(flip=2)
    run2 = IP.get_run(db2, key2)
    assert run2["state"] != "blocked" and run2["generation_calls"] == 3, run2
    assert nxt2 and nxt2[0][0]["stage"] != "product_generation", nxt2


def test_15_the_readback_names_the_due_kind():
    from brambleloop.ops import production_evidence as PE

    db = _db()
    _vision(db)
    _run(db)
    assert PE._redrive_due_kind(db) == "fidelity_rejudge"


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
