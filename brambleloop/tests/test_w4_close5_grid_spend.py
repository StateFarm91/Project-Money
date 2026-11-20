"""W4-CLOSE5: the weekly creative.grid_tournament's token spend, cut without changing the
models, the judge count, the batching, the median, the threshold or any limit.

  * every cell is shown to a judge at Etsy's search-card width (570 px; il_570xN), on both
    sides, never at full size;
  * a grid identical picture for picture to one a complete panel already judged reuses that
    panel (no call, no spend); an incomplete panel is never stored, so never reused;
  * the estimated saving on the measured production run (CA$13, 84 calls, 2.89M input
    tokens) is computed from the provider's published (w x h) / 750 rule.

Local, deterministic; a fake provider; no network.
Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close5_grid_spend.py
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from PIL import Image  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, BenchmarkListing  # noqa: E402
from brambleloop.creative import blinded as B  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402

ETSY = ("https://i.etsystatic.com/15888388/r/il/5f5ab7/{n}/il_fullxfull.{n}_gmdw.jpg")


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/grid.sqlite")
    db.create_all()
    return db


def _png(name: str, w: int, h: int, colour=(200, 120, 40)) -> str:
    d = Path(tempfile.mkdtemp())
    p = d / name
    Image.new("RGB", (w, h), colour).save(p, format="PNG")
    return str(p)


def _pod(db, pod="blankets", n=7, start=6587305673):
    with db.session() as s:
        for i in range(n):
            s.add(BenchmarkListing(
                benchmark_key=benchmarks.MJS_KEY, listing_ref=f"{pod}-{start + i}",
                title=f"Throw {i}", pod=pod, audit_state="audited", price_cad=9.0,
                media_count=6, detail={"image_urls": [ETSY.format(n=start + i)]}))


class _Resp:
    def __init__(self, text, n_images):
        self.text = text
        self.input_tokens, self.output_tokens = 200 + 500 * n_images, 300


class _Judge:
    name, model = "anthropic", "claude-sonnet-5"
    cost_per_1k_input_cad, cost_per_1k_output_cad = 0.004, 0.02

    def __init__(self, ours=0.8, theirs=0.4, silent=""):
        self.ours, self.theirs, self.silent, self.calls = ours, theirs, silent, []

    def see(self, system, prompt, urls, *, max_tokens):
        self.calls.append(list(urls))
        if self.silent and self.silent in system:
            return _Resp("no", len(urls))
        labels = re.search(r"in this order: ([^.]+)\.", prompt).group(1).split(", ")
        rows = [{"cell": l, **{f: (self.theirs if "etsystatic" in u else self.ours)
                               for f in B.GRID_JUDGE_FIELDS}} for l, u in zip(labels, urls)]
        return _Resp(json.dumps({"cells": rows}), len(urls))


def _ours(w=2048, h=2048):
    return [{"made": True, "slug": "autumn-oak", "image_ref": _png("autumn-oak-hero.png", w, h)}]


# --------------------------------------------------------------------- downscaling

def test_an_etsy_original_is_shown_as_its_search_card_variant():
    url = ETSY.format(n=1)
    assert B.judge_view(url) == url.replace("il_fullxfull.", "il_570xN.")
    # anything that is not an Etsy original goes unchanged
    for other in ("https://example.com/a.jpg", "fixture://x", "artifacts/missing.png", ""):
        assert B.judge_view(other) == other


def test_our_render_is_resized_to_the_same_width_keeping_aspect_and_name():
    src = _png("cloud-hero.png", 2048, 2560)
    view = B.judge_view(src)
    assert view != src and os.path.basename(view) == "cloud-hero.png"
    with Image.open(view) as im:
        assert im.size == (570, 712), im.size
        assert im.format == "PNG"
    assert B.judge_view(src) == view, "a second call resized again instead of reusing"
    # never enlarged: an image already at or under the width is sent as it is
    small = _png("small.png", 400, 400)
    assert B.judge_view(small) == small
    # a JPEG stays a JPEG
    jp = Path(tempfile.mkdtemp()) / "x.jpg"
    Image.new("RGB", (1200, 1400)).save(jp, format="JPEG")
    with Image.open(B.judge_view(str(jp))) as im:
        assert im.format == "JPEG" and im.size == (570, 665)


def test_the_judges_receive_only_search_card_sized_images():
    db = _db()
    _pod(db)
    judge = _Judge()
    out = B.grid_tournament(db, _ours(), pod="blankets", provider=judge, seed=5)
    assert out["verdict"] == "clear", out["why"]
    sent = [u for call in judge.calls for u in call]
    assert sent and len(judge.calls) == len(B.GRID_JUDGES) * 1  # 8 cells, one batch per judge
    for u in sent:
        if u.startswith("https://"):
            assert "/il_570xN." in u and "fullxfull" not in u, u
        else:
            with Image.open(u) as im:
                assert im.width == B.JUDGE_VIEW_WIDTH, (u, im.size)
    # unchanged: three judges, the batch limit, the model
    assert len(B.GRID_JUDGES) == 3 and gw.MAX_IMAGES_PER_CALL == 8
    assert out["panel"]["judged_by"] == sorted(j for j, _ in B.GRID_JUDGES)


def test_estimated_saving_on_the_measured_production_run():
    """Measured run: CA$13, 84 calls, 2.89M input tokens (~34,400 per call, ~4,300 per image
    at eight images a call; IMAGE_TOKENS_ESTIMATE's measured mean is ~5,000 at full size).
    At 570 px wide a square cell is 434 tokens, Etsy's 1200x1400 original 506 (from 2,240),
    and even a 2:3 portrait 650. Image tokens fall by at least 84%."""
    calls, tokens_in, cad = 84, 2_890_000, 13.0
    per_call = tokens_in / calls
    images_per_call = gw.MAX_IMAGES_PER_CALL
    prompt_tokens = len(B.grid_judge_prompt([{"cell": "c00000000"}] * 8)) // 4 + 60
    per_image_before = (per_call - prompt_tokens) / images_per_call
    assert 4000 < per_image_before < 4400, per_image_before
    assert B.judge_view_tokens(570, 570) == 434
    assert B.judge_view_tokens(570, 665) == 506 and B.judge_view_tokens(1200, 1400) == 2240
    worst_after = B.judge_view_tokens(570, 855)  # 2:3 portrait
    per_call_after = prompt_tokens + images_per_call * worst_after
    tokens_after = calls * per_call_after
    saving = 1 - tokens_after / tokens_in
    assert saving >= 0.84, saving
    # input tokens dominate the bill: output is at most 84 x 700 tokens
    out_tokens_max = calls * B.GRID_JUDGE_MAX_TOKENS
    assert out_tokens_max < 0.03 * tokens_in
    est_cad_after = cad * (1 - saving)
    assert est_cad_after < 2.2, est_cad_after  # ~CA$2.1 at worst, before any reuse


# --------------------------------------------------------------------- reuse

def test_an_identical_grid_reuses_the_complete_panel_with_no_call_or_spend():
    db = _db()
    _pod(db)
    ours = _ours()
    first = _Judge()
    a = B.grid_tournament(db, ours, pod="blankets", provider=first, seed=11)
    assert first.calls and a["panel"]["stored_for_reuse"] is True
    assert a["panel"]["cost_cad"] > 0
    # next week: a different seed (job id), so different cell ids and shuffle -- same pictures
    second = _Judge(ours=0.1, theirs=0.9)
    b = B.grid_tournament(db, ours, pod="blankets", provider=second, seed=99)
    assert second.calls == [], "an identical grid was judged again"
    assert b["panel"]["cost_cad"] == 0.0 and b["panel"]["reused_from"]["audit_id"]
    assert b["verdict"] == a["verdict"] == "clear"
    assert b["our_scores"] == a["our_scores"]
    assert b["by_product"]["autumn-oak"]["scores"] == a["by_product"]["autumn-oak"]["scores"]
    assert b["panel"]["judged_by"] == a["panel"]["judged_by"]


def test_any_change_to_the_page_or_the_panel_is_judged_afresh():
    db = _db()
    _pod(db)
    ours = _ours()
    B.grid_tournament(db, ours, pod="blankets", provider=_Judge(), seed=1)
    # our hero changed (different pixels, same name)
    changed = [{**ours[0], "image_ref": _png("autumn-oak-hero.png", 2048, 2048, (10, 10, 10))}]
    j = _Judge()
    B.grid_tournament(db, changed, pod="blankets", provider=j, seed=2)
    assert j.calls, "a changed hero reused the old panel"
    # a benchmark was added to the pod: the page changed, so every relative score may change
    _pod(db, n=1, start=7000000000)
    j = _Judge()
    B.grid_tournament(db, ours, pod="blankets", provider=j, seed=3)
    assert j.calls, "a changed benchmark set reused the old panel"
    # a different model is a different panel
    j = _Judge()
    j.model = "claude-opus-5"
    B.grid_tournament(db, ours, pod="blankets", provider=j, seed=4)
    assert j.calls, "a different model reused the old panel"


def test_an_incomplete_panel_is_never_stored_or_reused():
    db = _db()
    _pod(db)
    ours = _ours()
    a = B.grid_tournament(db, ours, pod="blankets", provider=_Judge(silent="gift"), seed=1)
    assert a["verdict"] == "fail" and a["unjudged"]
    assert a["panel"]["stored_for_reuse"] is False
    with db.session() as s:
        assert s.query(AuditLog).filter(AuditLog.action == B.GRID_PANEL_ACTION).count() == 0
    j = _Judge()
    B.grid_tournament(db, ours, pod="blankets", provider=j, seed=2)
    assert j.calls, "an unjudged grid was reused instead of judged"


def test_a_stale_or_tampered_panel_is_not_reused():
    db = _db()
    _pod(db)
    ours = _ours()
    B.grid_tournament(db, ours, pod="blankets", provider=_Judge(), seed=1)
    grid = B.render_grid(db, ours, pod="blankets", seed=1)
    fp, content = B.grid_fingerprint(grid, provider=_Judge())
    assert B.cached_panel(db, fp, content) is not None
    later = datetime.now(timezone.utc) + timedelta(days=B.PANEL_REUSE_DAYS + 1)
    assert B.cached_panel(db, fp, content, now=later) is None
    assert B.PANEL_REUSE_DAYS < 90  # inside ops.retention's 90-day audit horizon
    # a stored row missing one judge's reading is refused by deterministic validation
    with db.session() as s:
        row = s.query(AuditLog).filter(AuditLog.action == B.GRID_PANEL_ACTION).one()
        d = dict(row.detail)
        pj = dict(d["per_judge"])
        pj.pop(B.GRID_JUDGES[0][0])
        d["per_judge"] = pj
        s.add(AuditLog(actor="x", action=B.GRID_PANEL_ACTION, artifact=row.artifact, detail=d))
    assert B.cached_panel(db, fp, content) is None


def test_duplicate_pictures_on_one_page_are_never_reused():
    grid = {"pod": "p", "cells": [{"cell": "a", "thumbnail": "https://x/1.jpg"},
                                  {"cell": "b", "thumbnail": "https://x/1.jpg"}]}
    fp, _ = B.grid_fingerprint(grid, provider=_Judge())
    assert fp is None


def test_the_panel_action_is_registered_with_retention():
    from brambleloop.ops import retention

    assert retention.KNOWN_READ_ACTIONS["creative.grid_panel"][0] == "windowed"
    assert "creative.grid_panel" not in retention.unknown_read_actions()


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 10, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
