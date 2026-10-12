"""W4-HEROTOURNEY: F-278, two or more truthful hero candidates per product in the blinded grid.

* `visual.hero_candidates` offers each product's hero on file. A disclosed hero is resolved
  from its `sha256:` address to a file a judge can be shown; before this, the provider
  refused that address and every Launch-0 grid stayed unjudged. It also offers verified
  alternatives: a vessel's ANGLE view, and a multi-piece round hero at another spacing.
* `blinded.render_grid` places every candidate in the same blinded grid. Only the hero on
  file counts toward the pod's #126 verdict, and `grid_tournament` reports every
  candidate's scores.
* `hero_candidates.winner` decides between at least two fully scored candidates;
  otherwise it reports `insufficient_candidates` or `unjudged`.
Stub judges only: no network, no spend.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_herotourney.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import re
import shutil
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_herotourney_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-HEROTOURNEY harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing, Phase  # noqa: E402
from brambleloop.creative import blinded as B  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402
from brambleloop.visual import hero_candidates as H  # noqa: E402

_C: dict = {}


def _db():
    if "db" not in _C:
        db = Database(f"sqlite:///{_TMP}/ht.sqlite")
        db.create_all()
        Registry(db).seed_defaults()
        for slug in ("hexagon-coaster-set", "market-basket-small", "cloudline-baby-blanket"):
            cir = pipeline._engineered_cir(slug)
            JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                                 idempotency_key=f"c-{slug}", priority=0)
            Worker(db, "c", phase=Phase.SHADOW, job_types=["gate.certify"]).run_once()
            JobQueue(db).enqueue("publishing", "assets.build",
                                 {"slug": slug, "version": cir.version, "release": "",
                                  "rebuild": "disclosed"}, idempotency_key=f"d-{slug}",
                                 priority=0)
            Worker(db, "b", phase=Phase.SHADOW, job_types=["assets.build"]).run_once()
        _C["db"] = db
    return _C["db"]


def _offer(slug):
    key = ("offer", slug)
    if key not in _C:
        work = tempfile.mkdtemp(dir=_TMP)
        _C[key] = H.candidates(_db(), slug, work_dir=work)
    return _C[key]


def test_a_disclosed_hero_is_offered_as_a_file_a_judge_can_open():
    got = _offer("hexagon-coaster-set")
    hero = next(c for c in got["candidates"] if c["candidate"] == "hero")
    assert os.path.isfile(hero["image_ref"]) and not hero["image_ref"].startswith("sha256:")


def test_round_sets_and_vessels_get_a_verified_second_candidate_flat_pieces_do_not():
    coasters = _offer("hexagon-coaster-set")
    labels = [c["candidate"] for c in coasters["candidates"]]
    assert labels == ["hero", f"hero_gap_{H.ALT_GAP_RATIO}"], (labels, coasters["refused"])
    assert coasters["enough"] is True and "angle" in coasters["refused"]
    basket = _offer("market-basket-small")
    assert [c["candidate"] for c in basket["candidates"]] == ["hero", "angle"], basket["refused"]
    alt = [c for c in coasters["candidates"] + basket["candidates"] if c["candidate"] != "hero"]
    assert alt and all(c["verified"] == "PASS" for c in alt)
    blanket = _offer("cloudline-baby-blanket")
    assert [c["candidate"] for c in blanket["candidates"]] == ["hero"]
    assert blanket["enough"] is False


def test_winner_needs_two_fully_scored_candidates():
    full = {f: 0.7 for f in B.GRID_JUDGE_FIELDS}
    assert H.winner({"hero": full})["verdict"] == "insufficient_candidates"
    assert H.winner({"hero": full, "angle": {**full, "desire": None}})["verdict"] == "unjudged"
    got = H.winner({"hero": full, "angle": {f: 0.9 for f in B.GRID_JUDGE_FIELDS}})
    assert got["verdict"] == "decided" and got["winner"] == "angle"


class _Judge:
    name, model = "anthropic", "claude-sonnet-5"
    cost_per_1k_input_cad, cost_per_1k_output_cad = 0.004, 0.02

    def __init__(self, scores):
        self.scores, self.seen = scores, []

    def see(self, system, prompt, urls, *, max_tokens):
        labels = re.search(r"in this order: ([^.]+)\.", prompt).group(1).split(", ")
        rows = []
        for label, url in zip(labels, urls):
            self.seen.append(url)
            v = next((s for k, s in self.scores.items() if k in os.path.basename(url)), 0.3)
            rows.append({"cell": label, **{f: v for f in B.GRID_JUDGE_FIELDS}})

        class R:
            text = json.dumps({"cells": rows})
            input_tokens, output_tokens = 1200, 300
        return R()


def test_the_grid_ranks_every_candidate_but_only_the_hero_counts_for_the_pod():
    db = _db()
    with db.session() as s:
        for i in range(6):
            s.add(BenchmarkListing(
                benchmark_key=benchmarks.MJS_KEY, listing_ref=f"hd-{i}",
                title=f"Coaster Set {i}", pod="home_decor", audit_state="audited",
                price_cad=5.0, media_count=6,
                detail={"image_urls": [f"https://i.etsystatic.com/hd-{i}_fullxfull.jpg"]}))
    ours = [dict(c, counts_for_verdict=(c["candidate"] == "hero"))
            for c in _offer("hexagon-coaster-set")["candidates"]]
    judge = _Judge({"-hero.png": 0.6, "-hero_gap_": 0.9})
    out = B.grid_tournament(db, ours, pod="home_decor", provider=judge, seed=3)
    assert out["our_cells"] == 2 and "key" not in out
    assert all(v == 0.6 for v in out["our_scores"].values()), out["our_scores"]
    scores = out["candidate_scores"]
    assert set(scores) == {"hexagon-coaster-set#hero",
                           f"hexagon-coaster-set#hero_gap_{H.ALT_GAP_RATIO}"}
    ours_scored = {ref.split("#")[1]: v for ref, v in scores.items()}
    assert H.winner(ours_scored)["winner"] == f"hero_gap_{H.ALT_GAP_RATIO}"
    # every image a judge received was a URL or a file it could open, never a sha256: address
    assert judge.seen and all(u.startswith("https://") or os.path.isfile(u) for u in judge.seen)


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
