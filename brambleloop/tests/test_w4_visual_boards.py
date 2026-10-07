"""W4-VISUAL: concept boards show the design being judged.

Before: `creative.board.make_board` drew every concept from a prototype authored from form
and size alone, so five different catalogue designs got byte-identical boards. A vision
judgement bound to such a board (intake.judge_held binds the board's sha256) would judge none
of them. A catalogue design is now drawn from its own certified CIR (verified disclosed hero
where drawable, else its own fabric); a concept with no CIR still gets its prototype.
Local, deterministic, no network, no provider, no spend.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_visual_boards_")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.creative import audit, board  # noqa: E402
from brambleloop.creative import emotional_brief as EB  # noqa: E402
from brambleloop.products.builder import CATALOGUE  # noqa: E402

_DB: list = []


def db():
    if not _DB:
        d = Database(f"sqlite:///{_TMP}/boards.sqlite")
        d.create_all()
        _DB.append(d)
    return _DB[0]


def test_every_catalogue_design_gets_its_own_board():
    concepts, _briefs = audit.briefed_catalogue_concepts()
    assert len(concepts) == len(CATALOGUE) and concepts
    digests, refused = {}, {}
    for c in concepts:
        r = board.make_board(db(), c)
        assert r.get("slug") == c.key, (c.key, r)
        if not r.get("board_image"):
            # Fail closed: an undrawable design gets no board, never a stand-in.
            assert r["source"] == "catalogue_cir" and "hero could not be drawn" in r["why"], r
            refused[c.key] = r["why"]
            continue
        assert r["source"] == "catalogue_cir_disclosed_hero", r
        assert "not a photograph" in r["disclosure"]
        digests[c.key] = r["sha256"]
    assert len(digests) >= 6, (digests, refused)
    assert len(set(digests.values())) == len(digests), digests


def test_drawable_designs_use_their_verified_hero():
    concepts, _ = audit.briefed_catalogue_concepts()
    by_key = {c.key: c for c in concepts}
    assert "cloudline-baby-blanket" in by_key
    r = board.make_board(db(), by_key["cloudline-baby-blanket"])
    assert r["source"] == "catalogue_cir_disclosed_hero", r
    assert len(r["from_verified_hero_sha256"]) == 64


def test_a_concept_without_a_cir_still_gets_its_prototype():
    concepts, refused = EB.candidate_concepts()
    assert concepts
    flat = [c for c in concepts if c.key not in CATALOGUE and c.construction == "flat_rows"]
    assert flat, [c.key for c in concepts]
    r = board.make_board(db(), flat[0])
    assert r.get("board_image") and r["source"] == "prototype", r


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
