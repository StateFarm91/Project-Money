"""W4-VISUAL: disclosed gallery frames and the Launch-0 imagery ledger.

The frames answer K1's further gallery jobs (MATERIALS, COLOUR_CONTEXT, CONSTRUCTION, SIZING)
from the certified CIR alone, and the verifier passes a frame only when its bytes are the
redraw of independently recomputed facts. LIFESTYLE and FIT are never drawn. Local,
deterministic, no network, no provider, no spend.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import io
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_visual_gf_")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from PIL import Image, ImageDraw  # noqa: E402

from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.visual import gallery_frames as G  # noqa: E402
from brambleloop.visual import launch_imagery as LI  # noqa: E402
from brambleloop.visual import render_contract as K  # noqa: E402

_C: dict = {}


def cir(key):
    if key not in _C:
        _C[key] = launch0.cir_for(key)
    return _C[key]


def baskets():
    return cir("basket_small"), [cir("basket_medium"), cir("basket_large")]


def test_every_drawable_job_verifies_on_launch0():
    cases = [(cir("hexagon_coasters"), []), (cir("cloudline_blanket"), []), baskets()]
    seen = []
    for c, sib in cases:
        jobs = G.applicable_jobs(c, siblings=sib)
        assert jobs, c.slug
        for job in jobs:
            fr = G.render(c, job, siblings=sib)
            v = G.verify(fr.png, c, fr.manifest, siblings=sib)
            assert v["status"] == "PASS", (c.slug, job, v)
            assert fr.manifest["disclosure"] == K.DISCLOSURE
            assert fr.manifest["generated"] is False and fr.manifest["photograph"] is False
            seen.append(job)
    assert set(seen) == set(G.JOBS), seen


def test_rendering_is_deterministic():
    c = cir("hexagon_coasters")
    a = G.render(c, G.COLOUR_CONTEXT).png
    b = G.render(c, G.COLOUR_CONTEXT).png
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()


def test_colour_shares_are_counted_two_ways_and_agree():
    c = cir("cloudline_blanket")
    mine = G.facts(c, G.COLOUR_CONTEXT)
    theirs = G.independent_facts(c, G.COLOUR_CONTEXT)
    assert mine["shares"] and mine == theirs
    assert abs(sum(s["percent"] for s in mine["shares"]) - 100.0) < 0.5
    assert mine["total_stitches"] == sum(s["stitches"] for s in mine["shares"])


def test_a_lettered_claim_the_cir_does_not_make_fails():
    c = cir("hexagon_coasters")
    fr = G.render(c, G.MATERIALS)
    img = Image.open(io.BytesIO(fr.png)).convert("RGB")
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    d.text((200, 1400), "Certified safe for newborns", fill=K.CAPTION, font=K.font(50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    tampered = buf.getvalue()
    manifest = dict(fr.manifest, image_sha256=hashlib.sha256(tampered).hexdigest())
    v = G.verify(tampered, c, manifest)
    assert v["status"] == "FAIL" and "pixels_are_the_facts" in v["failed"], v


def test_a_manifest_overstating_the_facts_fails():
    c = cir("hexagon_coasters")
    fr = G.render(c, G.MATERIALS)
    facts = dict(fr.manifest["facts"])
    facts["yarn"] = dict(facts["yarn"], hook_mm=9.0)
    v = G.verify(fr.png, c, dict(fr.manifest, facts=facts))
    assert v["status"] == "FAIL" and "facts_agree" in v["failed"], v


def test_a_frame_for_another_design_fails():
    fr = G.render(cir("hexagon_coasters"), G.MATERIALS)
    v = G.verify(fr.png, cir("cloudline_blanket"), fr.manifest)
    assert v["status"] == "FAIL", v


def test_unstated_yardage_is_left_off_not_estimated():
    c = cir("cloudline_blanket")
    f = G.facts(c, G.MATERIALS)
    if any(m.metres_estimate is None for m in c.materials):
        assert f["yarn"]["metres_total"] is None


def test_lifestyle_and_fit_are_never_drawn():
    for job in ("LIFESTYLE", "FIT"):
        assert job in G.NOT_DRAWABLE and job not in G.JOBS
        try:
            G.render(cir("hexagon_coasters"), job)
        except G.FrameRefused:
            continue
        raise AssertionError(f"{job} was drawn")


def test_launch_imagery_ledger_and_registration():
    store = ArtifactStore(os.path.join(_TMP, "store"))
    rec = LI.assemble("hexagon-coaster-set", store=store)
    assert rec["applicable_jobs"], rec
    assert set(rec["covered"]) | set(rec["missing"]) == set(rec["applicable_jobs"])
    assert not set(rec["covered"]) & set(rec["missing"])
    assert rec["hero_ready"] is True and "DESIRE" in rec["covered"], rec["covered"]
    for job in ("MATERIALS", "COLOUR_CONTEXT"):
        assert job in rec["covered"], (job, rec["missing"].get(job))
    assert "LIFESTYLE" in rec["missing"] and "LIFESTYLE" in rec["paid_or_physical_only"]
    for f in rec["gallery_frames"]:
        assert store.get(f["sha256"]), f["job"]
    db = Database(f"sqlite:///{_TMP}/li.sqlite")
    db.create_all()
    assert LI.last(db, "hexagon-coaster-set") is None
    LI.register(db, rec)
    back = LI.last(db, "hexagon-coaster-set")
    assert back and back["covered"] == rec["covered"] and back["gallery_frames"]


def test_refresh_registers_once_and_skips_an_unchanged_listing():
    db = Database(f"sqlite:///{_TMP}/refresh.sqlite")
    db.create_all()
    saved = launch0.LAUNCH0_SLUGS
    launch0.LAUNCH0_SLUGS = ("hexagon-coaster-set",)
    try:
        store = ArtifactStore(os.path.join(_TMP, "store2"))
        first = LI.refresh(db, store=store)
        assert first and first["hexagon-coaster-set"]["refreshed"] is True, first
        second = LI.refresh(db, store=store)
        assert second["hexagon-coaster-set"]["refreshed"] is False, second
        assert second["hexagon-coaster-set"]["covered"] == first["hexagon-coaster-set"]["covered"]
    finally:
        launch0.LAUNCH0_SLUGS = saved


if __name__ == "__main__":
    import time

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, test in tests:
        started = time.time()
        try:
            test()
            print("OK  ", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(bool(failures))
