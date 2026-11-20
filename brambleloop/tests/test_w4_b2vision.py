"""W4-B2VISION (1): #67 Competitive Creative Benchmark, #218 MJs Challenge Gate, #126 grid.

The image_vision gate opened in production on 2026-10-12 (vision.probe ok 00:00Z). The first
production runs then showed three software gaps, which this file closes. Every provider here
is a stub, and nothing is spent.

1. `creative.grid_tournament` (2026-10-11T18:05Z) sent all three judges our hero as
   `/tmp/owned-asset-.../gpt-image-2-....png`. That is the render's path in a container that
   no longer existed. Every judge failed, CA$0.93 bought no reading, and the pod "failed"
   unjudged. Fix: the handler resolves each render through the artifact store by its digest,
   and a render it cannot show is never sent.
2. #218's desirability, distinctiveness and giftability were "unjudged" by construction: no
   reading of our own product existed. Fix: the grid panel's blinded scores are recorded per
   product, and the challenge reads them. Giftability is the gift-buyer judge's desire score.
   Being behind on two of the three returns the product to development.
3. `creative.blind_review` read UNKNOWN for every pod ("0 judged images", 2026-10-12T00:23Z).
   Gallery vision judges ~4 images a run and spent them on one listing's whole gallery. Fix:
   the drain goes breadth-first through the pods our catalogue is judged in.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_b2vision.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, BenchmarkListing  # noqa: E402
from brambleloop.creative import blind_review as BR  # noqa: E402
from brambleloop.creative import blinded as B  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402

_TMP = tempfile.mkdtemp()


def ok(m):
    print(f"  ok  {m}")


def _db():
    db = Database(f"sqlite:///{_TMP}/d{len(os.listdir(_TMP))}.sqlite")
    db.create_all()
    return db


def _stored_png(name: bytes = b"ours") -> str:
    from brambleloop.core.artifacts import ArtifactStore

    return ArtifactStore().put("test/hero.png", b"\x89PNG fixture " + name, "image/png").sha256


def _audited_pod(db, pod="blankets", n=6):
    with db.session() as s:
        for i in range(n):
            s.add(BenchmarkListing(
                benchmark_key=benchmarks.MJS_KEY, listing_ref=f"{pod}-{i}",
                title=f"Chunky Throw Blanket {i}", pod=pod, audit_state="audited",
                price_cad=9.0, media_count=6,
                detail={"image_urls": [f"https://i.etsystatic.com/{pod}-{i}_fullxfull.jpg"],
                        "num_favorers": 400}))


class _Response:
    def __init__(self, text):
        self.text, self.input_tokens, self.output_tokens = text, 1200, 300


class _Judge:
    """Stub vision judge: scores a picture by what the TEST says it shows (a path->score
    table), never by where it came from. Refuses a reference that is not a URL or a file,
    exactly as the real provider's `_image_block` does."""
    name, model = "anthropic", "claude-sonnet-5"
    cost_per_1k_input_cad, cost_per_1k_output_cad = 0.004, 0.02

    def __init__(self, ours: float, theirs: float, gift_ours: float | None = None):
        self.ours, self.theirs, self.gift_ours = ours, theirs, gift_ours
        self.seen: list[str] = []

    def see(self, system, prompt, urls, *, max_tokens):
        from brambleloop.gateway.anthropic import ProviderUnusable

        for u in urls:
            if not u.startswith("https://") and not Path(u).is_file():
                raise ProviderUnusable(f"{u!r} is neither a URL nor a file on this disk")
        self.seen.extend(urls)
        labels = re.search(r"in this order: ([^.]+)\.", prompt).group(1).split(", ")
        rows = []
        for label, url in zip(labels, urls):
            mine = not url.startswith("https://")
            v = self.ours if mine else self.theirs
            d = (self.gift_ours if (mine and "gift" in system and self.gift_ours is not None)
                 else v)
            rows.append({"cell": label, "attention": v, "comprehension": v, "desire": d,
                         "distinctiveness": v})
        return _Response(json.dumps({"cells": rows}))


# ---- 1. our render is resolved before a judge is paid ------------------------------------


def test_resolve_image_uses_the_artifact_store_when_the_render_path_is_gone():
    db = _db()
    assert B.resolve_image(db, {"image_ref": "https://x.invalid/a.jpg"}) == (
        "https://x.invalid/a.jpg", "")
    sha = _stored_png()
    dead = {"image_ref": "/tmp/owned-asset-gone/gpt-image-2-1.png", "image": {"sha256": sha}}
    ref, why = B.resolve_image(db, dead)
    assert ref and Path(ref).is_file() and ref.endswith(sha) and not why, (ref, why)
    ref2, _ = B.resolve_image(db, {"image_ref": f"sha256:{sha}"})
    assert ref2 == ref
    gone, why = B.resolve_image(db, {"image_ref": "/tmp/owned-asset-gone/x.png"})
    assert gone == "" and "no artifact digest" in why
    gone, why = B.resolve_image(db, {"image_ref": "", "image": {"sha256": "0" * 64}})
    assert gone == "" and "bytes are gone" in why
    ok("a dead /tmp path resolves through the artifact digest; nothing else is invented")


def test_the_grid_handler_never_sends_an_unresolvable_render_and_scores_each_product():
    from brambleloop.gateway import anthropic as gw
    from brambleloop.publish import listing_asset
    from brambleloop.runtime import release

    db = _db()
    _audited_pod(db)
    sha = _stored_png()
    frames = {
        "good-throw": [{"made": True, "role": "hero", "image": {"sha256": sha},
                        "image_ref": "/tmp/owned-asset-gone/gpt-image-2-1.png"}],
        "lost-throw": [{"made": True, "role": "hero",
                        "image_ref": "/tmp/owned-asset-gone/gpt-image-2-2.png"}],
    }
    judge = _Judge(0.8, 0.4, gift_ours=0.3)
    audits: list[tuple[str, dict]] = []
    saved = (BR.catalogue_slugs, BR.pod_for, listing_asset.frames_for, gw.provider_for)
    try:
        BR.catalogue_slugs = lambda: [("good-throw", "Good Throw"), ("lost-throw", "Lost Throw")]
        BR.pod_for = lambda slug, title="": "blankets"
        listing_asset.frames_for = lambda db_, slug: frames[slug]
        gw.provider_for = lambda task: judge
        ctx = SimpleNamespace(db=db, job=SimpleNamespace(id=None, inputs={}),
                              audit=lambda action, detail=None, **kw: audits.append(
                                  (action, detail or {})))
        out = release.handle_grid_tournament(ctx)
    finally:
        BR.catalogue_slugs, BR.pod_for, listing_asset.frames_for, gw.provider_for = saved
    detail = dict(audits)["creative.grid_tournament"]
    assert out["pods"]["blankets"] == "clear", detail["pods"]
    assert not [u for u in judge.seen if "/tmp/owned-asset-gone" in u], judge.seen
    assert detail["unresolvable"].keys() == {"lost-throw"}
    assert detail["products"]["lost-throw"]["unresolvable"] is True
    good = detail["products"]["good-throw"]
    assert good["scores"]["desire"] == 0.8 and good["by_judge"]["gift_buyer"]["desire"] == 0.3
    ok("the judges saw the stored render, never the dead path; each product carries its scores")


# ---- 2. #218 reads the panel's reading of THIS product -----------------------------------


def _grid_row(db, slug, *, desire, distinct, gift, days_ago=0):
    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action="creative.grid_tournament",
                       at=datetime.now(timezone.utc) - timedelta(days=days_ago),
                       detail={"products": {slug: {
                           "pod": "blankets", "verdict": "fail",
                           "scores": {"attention": 0.6, "comprehension": 0.6,
                                      "desire": desire, "distinctiveness": distinct},
                           "by_judge": {"gift_buyer": {"desire": gift}}}}}))


def test_the_challenge_reads_desirability_distinctiveness_and_giftability_from_the_panel():
    db = _db()
    _grid_row(db, "weak-throw", desire=0.3, distinct=0.2, gift=0.4)
    r = BR.review(db, slug="weak-throw", title="Weak Throw", pod="blankets")
    dims = r["mjs_challenge"]["dimensions"]
    assert dims["concept_desirability"]["state"] == "behind", dims["concept_desirability"]
    assert dims["distinctiveness"]["state"] == "behind"
    assert dims["giftability"]["state"] == "behind" and "gift_buyer" in dims["giftability"]["from"]
    assert r["returns_to_development"] is True, "generic beside the MJs set goes back"
    assert r["grid_reading"]["audit_id"]

    db2 = _db()
    _grid_row(db2, "good-throw", desire=0.7, distinct=0.6, gift=0.4)
    r2 = BR.review(db2, slug="good-throw", title="Good Throw", pod="blankets")
    d2 = r2["mjs_challenge"]["dimensions"]
    assert d2["concept_desirability"]["state"] == "level"
    assert d2["giftability"]["state"] == "behind"
    assert r2["returns_to_development"] is False  # one of three behind is not "obviously"
    ok("panel scores answer the three judged dimensions; two behind returns to development")


def test_a_stale_or_absent_panel_reading_stays_unjudged():
    db = _db()
    _grid_row(db, "old-throw", desire=0.1, distinct=0.1, gift=0.1,
              days_ago=BR.GRID_READING_MAX_AGE_DAYS + 1)
    r = BR.review(db, slug="old-throw", title="Old Throw", pod="blankets")
    for n in BR.GRID_READS:
        assert r["mjs_challenge"]["dimensions"][n]["state"] == "unjudged", n
    assert r["grid_reading"] is None and r["returns_to_development"] is False
    r = BR.review(_db(), slug="never", title="Never", pod="blankets")
    assert "giftability" in r["mjs_challenge"]["unjudged"]
    ok("a reading older than two tournaments, or none, is UNKNOWN -- never a pass")


# ---- 3. gallery vision drains our pods breadth-first ------------------------------------


def test_gallery_drain_is_breadth_first_through_the_catalogue_pods():
    from brambleloop.intel import vision

    db = _db()
    with db.session() as s:
        for pod, n in (("hats", 3), ("blankets", 3)):
            for i in range(n):
                s.add(BenchmarkListing(
                    benchmark_key=benchmarks.MJS_KEY, listing_ref=f"{pod}{i}", pod=pod,
                    title="t", audit_state="audited",
                    last_seen=datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(
                        hours=(10 if pod == "hats" else 0) + i),
                    detail={"image_urls": [f"https://e/{pod}{i}-{r}.jpg" for r in range(4)]}))
    legacy = vision.pending(db, benchmarks.MJS_KEY, limit=4)
    assert len({p.listing_ref for p in legacy}) == 1, "the old order: one gallery first"
    got = vision.pending(db, benchmarks.MJS_KEY, limit=6, prefer_pods={"blankets"})
    assert [p.rank for p in got[:3]] == [1, 1, 1]
    assert {p.listing_ref for p in got[:3]} == {"blankets0", "blankets1", "blankets2"}
    assert [p.listing_ref[:4] for p in got[3:]] == ["blan", "blan", "blan"]
    assert vision.pending(db, benchmarks.MJS_KEY, limit=100, prefer_pods=set()) and len(
        vision.pending(db, benchmarks.MJS_KEY, limit=100, prefer_pods=set())) == 24
    ok("our pods' hero images first, then second images; nothing is dropped")


# ---- 4. #116: the decomposition carries every primitive the requirement names -----------


def test_reference_decomposition_carries_personalization_bundle_and_thumbnail_primitives():
    from brambleloop.creative import reference as R

    body_names = ("silhouette", "motif_density", "dimensionality", "palette_role",
                  "prop_context", "function", "emotional_tone", "construction_novelty",
                  "personalization", "bundle_logic", "thumbnail_readability")
    assert R.PRIMITIVES == body_names
    obs = [{"thumbnail_readability": "reads clearly at grid size", "palette_role": "accent",
            "setting": "studio", "emotional_merchandising": "calm"}]
    readings = [{"silhouette_class": "rectangle", "edge_finish": "ribbed"}]
    listings = [{"title": "Throw Blanket Crochet Pattern", "options": {"is_personalizable": False,
                                                                      "has_variations": False}},
                {"title": "Blanket Pattern Bundle, set of 3",
                 "options": {"is_personalizable": True}},
                {"title": "Granny Throw Pattern", "options": {"is_personalizable": False}}]
    got = R.primitives(obs, readings, listings)["primitives"]
    assert got["thumbnail_readability"] == "reads clearly at grid size"
    assert got["personalization"] == "none" and got["bundle_logic"] == "single"
    unmeasured = R.primitives(obs, readings, [{"title": "", "options": None}])
    assert "personalization" in unmeasured["absent"], "no option block is unmeasured, not none"
    ok("all eleven #116 primitives; absent option facts stay absent")


# ---- 5. #88: a held winner's board is shown by its bytes, not its dead path -------------


def test_a_held_board_is_judged_from_the_artifact_store_not_a_dead_path():
    from brambleloop.creative import intake
    from brambleloop.gateway.model_gateway import ModelResponse

    db = _db()
    sha = _stored_png(b"board")
    seen: list = []

    class Judge:
        model = "claude-sonnet-5"
        cost_per_1k_input_cad = cost_per_1k_output_cad = 0.0

        def see(self, system, prompt, urls, *, max_tokens):
            seen.extend(urls)
            for u in urls:
                assert Path(u).is_file(), u
            return ModelResponse(text='{"thumbnail_reads_small": true, "craft_impression": 4.0}',
                                 provider="fixture", model=self.model, input_tokens=1,
                                 output_tokens=1, latency_ms=1.0)

    saved = intake.board_digest_for
    try:
        intake.board_digest_for = lambda db_, slug: sha
        ctx = SimpleNamespace(db=db, job=SimpleNamespace(id=None, agent="creative_director"),
                              audit=lambda *a, **k: None)
        out = intake.judge_held(ctx, slug="held-1", board="/tmp/gone/board.png",
                                provider=Judge())
        assert out["judged"] is True and seen and seen[0].endswith(sha), (out, seen)
        intake.board_digest_for = lambda db_, slug: "f" * 64
        out = intake.judge_held(ctx, slug="held-2", board="/tmp/gone/board2.png",
                                provider=Judge())
        assert out["judged"] is False and "cannot be shown" in out["why"]
    finally:
        intake.board_digest_for = saved
    ok("the judge saw the stored board; bytes nobody kept are never sent")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for t in tests:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            bad += 1
            import traceback

            traceback.print_exc()
            print(f"FAIL {t.__name__}: {e}")
        else:
            print(f"OK   {t.__name__}")  # run_tests.sh counts ^OK lines
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)
