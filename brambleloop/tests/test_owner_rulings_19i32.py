"""19i32: the owner's rulings of 2026-11-28, end to end.

* D-OWNER-LIFESTYLE-GENERATED ("1- a. Yes"): the render disclosure a generated lifestyle frame
  still needs (the policy itself: test_w5_v1_visual_correctness, test_verify_refs 9).
* D-OWNER-PHOTO-BUDGET ("up the photo budget i dont care. Get it right."): the raised plan,
  the activation amendment, the code image caps and the bounded plan redrive.
* Calibration against the owner's own FLUX product master
  (research/owner_assets/owner_method_2026-11-28/owner_basket_product.png) of "Crochet
  Hexagonal Storage Basket" v1.2.0 = market-basket-medium (35 rounds, 78 sts, wine rounds
  22-23 and 28-29; 1.2.1 is a text-only revision of the same stitches).
* D-OWNER-LAURA-OUTFIT: a unique outfit per listing, constant within it, refused (not logged)
  on the live route; a worn product is the outfit item.

No network, no paid call. Every provider answer is a TEST FIXTURE.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_owner_rulings_19i32.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import io
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.gateway import paid_provider_gate as G  # noqa: E402
from brambleloop.ops import owner_directives as D  # noqa: E402
from brambleloop.products.vessels import build_basket  # noqa: E402
from brambleloop.visual import candidate_gates as CG  # noqa: E402
from brambleloop.visual import fidelity as F  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402
from brambleloop.visual import vessel as V  # noqa: E402

OWNER = ROOT / "research" / "owner_assets" / "owner_method_2026-11-28"
MASTER = OWNER / "owner_basket_product.png"
_N = [0]


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='own19i32_')}/d{_N[0]}.db")
    db.create_all()
    G.ensure_tables(db)
    return db


# ---- calibration: the owner's master ---------------------------------------------------------

def _release():
    cir = build_basket("medium", version="1.2.0")
    rows = cir.components[0].rows
    assert cir.slug == "market-basket-medium" and cir.title == "Crochet Hexagonal Storage Basket"
    assert len(rows) == 35 and rows[-1].declared_count == 78
    assert [r.index for r in rows if r.color == "wine"] == [22, 23, 28, 29]
    return cir


def _model():
    return V.vessel_models(_release())[0]


def _png(a) -> bytes:
    b = io.BytesIO()
    Image.fromarray(np.clip(a, 0, 255).astype("uint8")).save(b, "PNG")
    return b.getvalue()


def _variants() -> dict[str, bytes]:
    """Wrong versions of the master, made by recolouring its own stitches (luminance kept)."""
    im = np.asarray(Image.open(MASTER).convert("RGB")).astype(float)
    luma = im.mean(axis=2)
    wine = (im[..., 0] - im[..., 2] > 35) & (im[..., 1] < 140)
    yy = np.arange(im.shape[0])[:, None] * np.ones((1, im.shape[1]))
    xx = np.ones((im.shape[0], 1)) * np.arange(im.shape[1])[None, :]
    wl, cl = luma[wine].mean(), np.median(luma[(~wine) & (luma > 150)])
    cream, wine_rgb, navy = (np.array([238, 232, 218.]), np.array([110, 31, 42.]),
                             np.array([31, 42, 110.]))

    def to(base, colour, sel, ref):
        out = base.copy()
        out[sel] = colour * (luma[sel] / ref)[:, None]
        return out

    def band(y0, y1):
        return (~wine) & (yy >= y0) & (yy < y1) & (luma > 120) & (xx > 150) & (xx < 930)

    moved = to(im, wine_rgb, band(640, 690), cl)
    moved = to(moved, cream, wine & (yy > 690), wl)
    return {"missing stripe": _png(to(im, cream, wine & (yy > 480) & (yy < 650), wl)),
            "extra stripe": _png(to(im, wine_rgb, band(790, 835), cl)),
            "wrong colour": _png(to(im, navy, wine, wl)),
            "wrong spacing": _png(moved)}


def _by(checks):
    return {c["check"]: c for c in checks}


def test_1_the_masters_wall_palette_and_rim_pass_and_the_old_misread_is_named():
    data = MASTER.read_bytes()
    mask, _lab, why = V._product_mask(data)
    # the colour separation took the oak table for product (the mask ran off the frame); the
    # stitch texture separates the basket itself
    assert why == V.TEXTURE_SEPARATED and not V._touches_frame(mask), why
    c = _by(V.verify_side(data, _model()))
    assert c["basket:palette"]["status"] == "PASS", c["basket:palette"]
    wb = c["basket:wall_bands"]
    assert wb["status"] == "PASS" and wb["bands"] == ["cream", "wine", "cream", "wine",
                                                      "cream"], wb
    # the deterministic rim reading is a width test: the master's braid does not jut out
    assert c["basket:rim"]["status"] == "PASS", c["basket:rim"]
    print("OK 1 owner master: palette, wall bands (two wine bands, cream ground), rim PASS")


def test_2_wrong_variants_still_fail():
    m = _model()
    variants = _variants()
    assert set(variants) == {"missing stripe", "extra stripe", "wrong colour", "wrong spacing"}
    for name, data in variants.items():
        c = _by(V.verify_side(data, m))
        assert c["basket:wall_bands"]["status"] == "FAIL", (name, c["basket:wall_bands"])
    print("OK 2 extra stripe, missing stripe, wrong colour, wrong spacing: FAIL")


def test_3_the_braided_rim_is_a_genuine_deviation_the_craft_comparison_refuses():
    """The pattern ends in a plain cream final round; the master shows a braid. The vision
    question reports it, and the deterministic comparison refuses it (INVENTED_EDGING); a
    plain final round passes. The edging check is not loosened."""
    exp = F.expectation(_release())
    plain = {"fabric_visible_clearly": "true", "craft": "crochet", "cable_style": "none",
             "ribbing_visible": "false", "border_or_edging_visible": "false",
             "added_edging_visible": "false"}
    assert F.compare_craft(plain, exp)["status"] == "PASS"
    braid = {**plain, "border_or_edging_visible": "true", "added_edging_visible": "true"}
    got = F.compare_craft(braid, exp)
    assert got["status"] == "FAIL" and got.get("code") == "INVENTED_EDGING", got
    print("OK 3 braided rim: craft_texture FAIL INVENTED_EDGING (genuine deviation)")


def test_4_the_check_version_moves_so_parked_runs_are_rejudged():
    # 19i32 moved it to "/3"; later changes (ENG-COASTER-SIDES "/4") may only move it further
    assert int(F.FIDELITY_CHECK_VERSION.rsplit("/", 1)[1]) >= 3, F.FIDELITY_CHECK_VERSION
    assert F.FIDELITY_CHECK_VERSION in IP.verify_redrive_version()
    print(f"OK 4 {F.FIDELITY_CHECK_VERSION}")


# ---- D-OWNER-LIFESTYLE-GENERATED: disclosure -------------------------------------------------

def test_5_a_generated_lifestyle_frame_must_be_disclosed_as_a_render():
    from brambleloop.gates import platform_policy as PP
    from brambleloop.gates.policy import check_ai_disclosure
    from brambleloop.publish import eligibility as el

    d = CG.disclosure(el.LIFESTYLE)
    assert d["status"] == "PASS" and "not a photograph" in d["label"], d
    cand = {"slug": "x", "version": "1", "role": "lifestyle",
            "references": [{"kind": "pattern_derived"}]}
    fid = {"checks": [{"check": k, "status": "PASS"} for k in CG.GENERATED_FIDELITY_CHECKS]}
    assert CG.lifestyle_reading(cand, {"pieces": 1}, fid)["status"] == "PASS"
    saved = CG.disclosure
    CG.disclosure = lambda job: {"status": "FAIL", "why": "fixture: no label"}
    try:
        got = CG.lifestyle_reading(cand, {"pieces": 1}, fid)
        assert got["status"] == "FAIL" and "disclosure" in got["failed"], got
    finally:
        CG.disclosure = saved
    # the listing copy: a generated image owes the generated_imagery sentence, verbatim
    cls = PP.classify(product_class=PP.SELLER_DESIGNED_DIGITAL, assets=[
        PP.AssetClaim(ref="lifestyle-1", role="mood_frame", generated=True, labelled=True)])
    sentence = PP.DISCLOSURES["generated_imagery"]
    assert sentence in cls.disclosures and "rather than photographs" in sentence
    errs = check_ai_disclosure("A cosy basket pattern.", cls)
    assert [f.code for f in errs] == ["POLICY_AI_DISCLOSURE_MISSING"], errs
    assert check_ai_disclosure("A cosy basket pattern. " + sentence, cls) == []
    print("OK 5 disclosure: image label required, listing copy sentence enforced")


# ---- D-OWNER-PHOTO-BUDGET ----------------------------------------------------------------------

def test_6_the_plan_and_the_caps_are_raised_and_the_company_cap_is_not():
    from brambleloop.gateway import providers as gw
    from brambleloop.publish import sale_pipeline

    assert IP.MAX_SPEND_CAD_PER_GALLERY == 6.00
    assert IP.MAX_GENERATION_CALLS == 36 and IP.FLUX_MAX_GENERATION_CALLS == 60
    assert IP._spend_plan("x")["call_count"] == 36
    assert IP._spend_plan("x" + IP.ROUTE_SUFFIX)["call_count"] == 60
    assert IP._spend_plan("x")["max_spend_cad"] == 6.00
    assert sale_pipeline.PER_LISTING_IMAGE_CAP_CAD == 6.00
    flux = D.ACTIVATIONS[("flux-3-image", "generation")]
    assert flux == {"daily_ceiling_cad": 10.0, "monthly_ceiling_cad": 40.0,
                    "per_gallery_cad": 6.0}, flux
    assert G.GALLERY_CAD_CAP >= IP.MAX_SPEND_CAD_PER_GALLERY
    assert G.GALLERY_IMAGE_CAP >= IP.FLUX_MAX_GENERATION_CALLS
    assert gw.monthly_ceiling_cad() == 100.0
    print("OK 6 plan CA$6 / 36 / 60; FLUX CA$10 daily, CA$40 monthly; company CA$100")


def test_7_the_live_directive_row_is_amended_once_upwards_only():
    db = _db()
    given = datetime(2026, 11, 21, 1, 0, tzinfo=timezone.utc)
    with db.session() as s:              # the row production wrote on 2026-11-21
        s.add(G.PaidProviderActivation(
            provider="flux-3-image", scope="generation", activated_by=D.ACTOR,
            activated_at=given, step_up={"owner_directive": D.DIRECTIVE_ID,
                                         "session_public_id": None},
            daily_ceiling_cad=5.0, monthly_ceiling_cad=40.0, per_gallery_cad=2.5,
            max_attempts_per_request=G.DEFAULT_MAX_ATTEMPTS,
            max_calls_per_run=G.DEFAULT_MAX_CALLS_PER_RUN,
            expires_at=given + D.EXPIRY))
    before = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    assert not D.apply(db, now=before).get("amended")          # before the owner decided
    now = datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)
    out = D.apply(db, now=now)
    am = out.get("amended") or []
    assert len(am) == 1 and am[0]["decision"] == "D-OWNER-PHOTO-BUDGET", out
    act = G.activation_state(db, "flux-3-image", "generation", now=now)
    assert act["active"], act
    a = act["activation"]
    assert (a["daily_ceiling_cad"], a["per_gallery_cad"], a["monthly_ceiling_cad"]) == (
        10.0, 6.0, 40.0), a
    with db.session() as s:
        row = s.query(G.PaidProviderActivation).filter_by(provider="flux-3-image").one()
        assert D.authorises(row)
        assert row.expires_at.replace(tzinfo=timezone.utc) == given + D.EXPIRY   # not renewed
    assert not D.apply(db, now=now + timedelta(hours=1)).get("amended")      # once
    # a revoked row is never amended
    db2 = _db()
    with db2.session() as s:
        s.add(G.PaidProviderActivation(
            provider="flux-3-image", scope="generation", activated_by=D.ACTOR,
            activated_at=given, step_up={"owner_directive": D.DIRECTIVE_ID},
            daily_ceiling_cad=5.0, monthly_ceiling_cad=40.0, per_gallery_cad=2.5,
            max_attempts_per_request=1, max_calls_per_run=1, expires_at=given + D.EXPIRY,
            revoked_at=given + timedelta(days=1), revoked_by="owner"))
    assert not D.apply(db2, now=now).get("amended")
    print("OK 7 directive row: CA$10 daily, CA$6 per gallery, monthly CA$40, once, not revoked")


PLAN_STOP = ("budget stop: paid visual experiment refused: call 21 exceeds the plan's "
             "call_count 20 (F-877)")


def _plan_blocked(db, slug="market-basket-small", *, calls=20, spent=2.0, route=True):
    from brambleloop.agents.registry import Registry
    from brambleloop.visual.image_records import (ImageCandidate, ImageProductionRun,
                                                  ensure_tables)

    Registry(db).seed_defaults()
    ensure_tables(db)
    key = IP.run_key(slug, "1.3.0", "r" * 64) + (IP.ROUTE_SUFFIX if route else "")
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug=slug, version="1.3.0", release="r" * 64,
                                 listing=slug, stage="product_generation", status="blocked",
                                 blocked_reason=PLAN_STOP, stages={}, generation_calls=calls,
                                 spent_cad=spent, attempts_exhausted=True))
        s.add(ImageCandidate(sha256="ab" * 32, run_key=key, method="autonomous",
                             provenance_kind="ai_generated_autonomous", slug=slug,
                             version="1.3.0", release="r" * 64, listing=slug,
                             role=IP.ANCHOR_ROLE, stage="product_generation", attempt=1,
                             checks={"product_truth": {"status": "FAIL", "why": "fixture"}},
                             technical_status="FAIL", outcome="rejected"))
    return key


def _follow(calls):
    def follow(inputs, key, *, session=None):
        calls.append((inputs, key))
        return object()
    return follow


def test_8_runs_stopped_by_the_old_plan_are_redriven_once_under_the_new_one():
    db = _db()
    key = _plan_blocked(db)
    assert IP.plan_budget_block(PLAN_STOP)
    assert IP._redrive_kind(PLAN_STOP, "product_generation") == "spend_plan_raised"
    with db.session() as s:
        v = IP.redrive_readback(s)["runs"][key]
        due = IP.redrive_due(s, None)
    assert v["kind"] == "spend_plan_raised" and v["eligible"], v
    assert due and due["run_key"] == key and due["kind"] == "spend_plan_raised", due
    calls: list = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert len(calls) == 1 and out["restarted"][0]["kind"] == "spend_plan_raised", out
    from sqlalchemy import select

    from brambleloop.visual.image_records import ImageProductionRun

    run = IP.get_run(db, key)
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        hist = (r.stages or {})[IP.RESTART_KEY]["history"]
    assert hist[-1]["by"] == IP.PLAN_REDRIVE_BY and hist[-1]["plan_version"] == \
        IP.PLAN_VERSION_TAG, hist
    assert run["generation_calls"] == 20 and abs(run["spent_cad"] - 2.0) < 1e-9   # never reset
    # re-blocked on the same stop: once per plan version
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        r.status, r.stage, r.blocked_reason = "blocked", "product_generation", PLAN_STOP
    with db.session() as s:
        assert IP.redrive_readback(s)["runs"][key]["refused"] == "already_redriven"
    again: list = []
    IP.redrive_capability_blocked(db, follow=_follow(again))
    assert again == []
    print("OK 8 plan stop: due once under gallery-plan/2, calls and spend carried over")


def test_9_a_run_the_new_plan_cannot_cover_and_the_restart_cap_stay_final():
    db = _db()
    full = _plan_blocked(db, "basket-full", calls=60, spent=2.0)
    broke = _plan_blocked(db, "basket-broke", calls=5, spent=5.99, route=False)
    with db.session() as s:
        rb = IP.redrive_readback(s)["runs"]
    assert rb[full]["refused"] == "final_block" and rb[broke]["refused"] == "final_block", rb
    calls: list = []
    IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert calls == []
    assert IP.restartable(db, full)["restartable"] is False
    db2 = _db()
    key = _plan_blocked(db2)
    from sqlalchemy import select

    from brambleloop.visual.image_records import ImageProductionRun

    with db2.session() as s:             # a run that has a restart record (read by the cap)
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        r.stages = {IP.RESTART_KEY: {"epoch": 3, "history": []}}
    saved = IP.restart_counts

    def at_cap(session, row, current=None):
        return {**saved(session, row, current=current), "current": IP.MAX_RESTARTS,
                "total": IP.MAX_RESTARTS}

    IP.restart_counts = at_cap
    try:
        with db2.session() as s:
            assert IP.redrive_readback(s)["runs"][key]["refused"] == "max_restarts"
    finally:
        IP.restart_counts = saved
    print("OK 9 no headroom under the new plan, or MAX_RESTARTS: final")


# ---- D-OWNER-LAURA-OUTFIT ----------------------------------------------------------------------

def test_10_rule_1_one_outfit_per_listing_on_the_live_route_and_a_duplicate_is_refused():
    import test_w4_ownerimg as O
    import test_w5_v1_visual_correctness as W

    from brambleloop.visual import outfits, styling
    from brambleloop.visual.image_records import ImageCandidate

    db, cir, rel = W._basket_db()
    gen, judges = O.StubGenerator(), W._judges(db)
    with W._FidelityPass():
        follow, _ = O.drain(db, generator=gen, judges=judges)
        IP.trigger(follow, slug=cir.slug, version=cir.version, release=rel)
        O.drain(db, generator=gen, judges=judges)
    run = IP.get_run(db, IP.run_key(cir.slug, cir.version, rel))
    oid = run["outfit_id"]
    assert oid, run
    # the reservation reaches every Laura generation and every Laura frame's record
    laura_outfits = {(o or {}).get("outfit_id") for role, _k, o in gen.seen if o}
    assert laura_outfits == {oid}, gen.seen
    with db.session() as s:
        rows = s.query(ImageCandidate).filter_by(
            laura_present=True, run_key=IP.run_key(cir.slug, cir.version, rel)).all()
        got = {(r.role, r.outfit_id) for r in rows}
        assert rows and {o for _r, o in got} == {oid}, got
    held = outfits.reserved_for(db, run["listing"])
    assert held and held["outfit_id"] == oid
    # another listing may not take it: the live stage refuses it and blocks the run
    assert outfits.reserve(db, oid, "another-listing")["status"] == "FAIL"
    taken = outfits.get(db, oid)
    db2, cir2, rel2 = W._basket_db()
    outfits.register(db2, outfit_id=oid, garments=taken["garments"],
                     colours=taken.get("colours") or ())
    outfits.approve(db2, oid)
    assert outfits.reserve(db2, oid, "another-listing")["status"] == "PASS"
    saved = styling.select_for_listing
    styling.select_for_listing = lambda db_, listing, **k: {
        "outfit": {"outfit_id": oid, "garments": taken["garments"],
                   "colours": taken.get("colours") or []}, "concept": {}}
    gen2 = O.StubGenerator()
    try:
        with W._FidelityPass():
            follow2, _ = O.drain(db2, generator=gen2, judges=W._judges(db2))
            IP.trigger(follow2, slug=cir2.slug, version=cir2.version, release=rel2)
            O.drain(db2, generator=gen2, judges=W._judges(db2))
    finally:
        styling.select_for_listing = saved
    run2 = IP.get_run(db2, IP.run_key(cir2.slug, cir2.version, rel2))
    assert run2["state"] == "blocked" and "outfit reservation FAIL" in run2["blocked_reason"], \
        run2
    assert not [o for _r, _k, o in gen2.seen if o], gen2.seen     # no Laura frame was made
    print("OK 10 rule 1: one outfit per listing on every Laura frame; a duplicate blocks")


def test_11_rule_2_a_worn_product_is_the_outfit_item():
    from brambleloop.visual import shot_plans as SP
    from brambleloop.visual import styling
    from brambleloop.visual.wardrobe import parse_garment

    laura, brief = SP.LIFESTYLE_BRIEF["garment"]
    assert laura and "wearing the finished garment" in brief
    got = styling.select("cardigan-listing", category="garment", product_colours=["wine"])
    g = got["outfit"]["garments"]
    assert parse_garment("outerwear", g["outerwear"])["category"] == "none", g
    assert parse_garment("top_or_dress", g["top_or_dress"])["category"] not in (
        "cardigan", "jumper", "dress"), g
    assert got["concept"]["product_worn"] is True
    assert styling.worn_conflicts("garment", g) == []
    assert styling.worn_conflicts("garment", {**g, "outerwear": "denim jacket"})
    assert styling.worn_conflicts("basket", {**g, "outerwear": "denim jacket"}) == []
    # the rest of the outfit is still unique per listing
    other = styling.select("shawl-listing-2", category="garment", product_colours=["wine"],
                           used_outfits=[("cardigan-listing", g)])
    assert other["outfit"]["garments"] != g
    assert styling.worn_conflicts("garment", other["outfit"]["garments"]) == []
    print("OK 11 rule 2: garment worn by Laura; base layer, no outerwear; still unique")


def test_12_the_generated_floor_unknown_is_replaced_by_the_cir_fidelity_verdict():
    """Production: every candidate's product_truth `why` names "structural floor UNKNOWN: no
    qualified whole-product construction/gauge evidence producer". For a generated frame that
    UNKNOWN is not the verdict: `RealJudges.product_truth` takes `visual.fidelity`'s
    deterministic, CIR-driven verdict (piece count, isolation, vessel side count and wall bands,
    palette, craft) in its place, and the floor only vetoes on a FAIL (a wrong stitch scale)."""
    db = _db()
    j = CG.RealJudges(db, second_vision=None, embedder=None)
    cand = {"slug": "market-basket-medium", "version": "1.2.0", "role": IP.ANCHOR_ROLE,
            "sha256": "0" * 64}
    saved_f, saved_s = CG.fidelity_reading, None
    from brambleloop.visual import product_authority as PA

    for verdict in ("PASS", "FAIL", "UNKNOWN"):
        CG.fidelity_reading = lambda *a, _v=verdict, **k: {
            "status": _v, "why": "fixture", "codes": [], "failed": [], "unknown": []}
        try:
            pt = j.product_truth(cand, {})
        finally:
            CG.fidelity_reading = saved_f
        assert pt["structural_floor"]["status"] == "UNKNOWN", pt["structural_floor"]
        assert pt["status"] == verdict, (verdict, pt["status"], pt["why"])
    # a floor FAIL (a wrong stitch scale) still vetoes a fidelity PASS
    saved_s = PA.stitch_scale_reading
    PA.stitch_scale_reading = lambda frame: {"verdict": "FAIL", "measured_px": 9,
                                             "expected_px": 4}
    CG.fidelity_reading = lambda *a, **k: {"status": "PASS", "why": "fixture", "codes": [],
                                           "failed": [], "unknown": []}
    try:
        pt = j.product_truth(cand, {})
    finally:
        CG.fidelity_reading, PA.stitch_scale_reading = saved_f, saved_s
    assert pt["structural_floor"]["status"] == "FAIL" and pt["status"] == "FAIL", pt
    print("OK 12 generated frame: floor UNKNOWN is replaced by the CIR fidelity verdict; "
          "a floor FAIL still vetoes")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    tests.sort(key=lambda f: int(f.__name__.split("_")[1]))
    for t in tests:
        t()
    print(f"ALL {len(tests)} OK")
