"""NEXT-FIXES #2: a concept admitted into a family with a verified engine gets a concept board.

Production 15:00Z (release 5297dbba): the concept gate held five concepts at
`board_missing/prototype_refused`. `radar.intake` admits a concept only into a family whose
engine is verified end to end, yet the board was drawn from `creative.prototype.author`, which
has no geometry for `toy` (ball bear, lovey), `draped_garment` (shawl, wrap) or a wearable
`fitted_garment` (socks, slippers, baby dress). Those concepts were never judged and waited
forever. The board is now drawn from the engine's own draft (`creative.board.make_engine_board`)
when the prototype refuses. Every research source and benchmark here is a TEST FIXTURE.

Run: cd brambleloop && python3 tests/test_next_fixes_engine_board.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_eng_families as T  # noqa: E402
from brambleloop.creative import board as B  # noqa: E402
from brambleloop.creative import intake as CI  # noqa: E402

BEAR = T._proposal("hearthside-ball-bear", "Ball Bear Amigurumi", "amigurumi", form="toy",
                   construction="amigurumi_shaping", motif="plain round bear",
                   pod="home_decor", function="a soft keepsake to hold",
                   palette_story="oat and bark", recipient="host",
                   premise="A plain ball-body bear worked in one oat colour with an "
                           "embroidered face")
SHAWL = T._proposal("saltgrass-shawl", "Saltgrass Shawl", "shawl", pod="garments",
                    form="draped_garment", construction="flat_rows", recipient="self",
                    premise="A soft merino triangle to wrap round the shoulders on a breezy "
                            "harbour evening", motif="stone",
                    function="keeps the cold off on the walk to school",
                    occasion="winter_nesting", feeling="serene", palette_story="oat")
SOCK = T._proposal("moorland-socks", "Moorland Socks", "sock", pod="garments",
                   form="fitted_garment", construction="in_the_round", recipient="self",
                   premise="Soft merino socks with a ribbed cuff to wear around the house in "
                           "winter", motif="stone",
                   function="keeps the cold off on the walk to school",
                   occasion="winter_nesting", feeling="serene", palette_story="oat")


def _approved(proposal):
    db = T._db()
    T._benchmarks(db, proposal["concept"]["pod"])
    T.intake.attach_proposal(db, T._answered_task(db), proposal)
    got = T._run(db, "radar.concept_intake", {})
    assert got["approved"] == [proposal["slug"]], got
    return db


def test_engine_family_concepts_the_prototype_cannot_size_get_a_board():
    from PIL import Image

    from brambleloop.products import moment_candidates as mc

    for proposal, family in ((BEAR, "amigurumi"), (SHAWL, "shawl_triangle"),
                             (SOCK, "sock")):
        db = _approved(proposal)
        slug = proposal["slug"]
        filed = CI.file_radar_board(db, slug)
        assert filed["board"].startswith("sha256:"), (slug, filed)
        rec = mc.board_record(db, slug)
        assert rec and rec["board_source"] == B.ENGINE_BOARD_SOURCE, rec
        assert rec["kind"] == B.KIND and "not a photograph" in rec["disclosure"], rec
        assert family in rec["disclosure"], rec
        assert CI.board_digest_for(db, slug) == filed["board"].split(":", 1)[1]
        cir, fam, compiled = B.engine_draft_cir(db, slug)
        assert fam == family and compiled.ok, (slug, fam)
        from brambleloop.core.artifacts import ArtifactStore

        png = ArtifactStore().get(filed["board"].split(":", 1)[1], db=db)
        img = Image.open(io.BytesIO(png)).convert("RGB")
        assert img.size == (B.BOARD_PX, B.BOARD_PX)
        colours = img.getcolors(maxcolors=1 << 20)
        assert colours is None or len(colours) > 2, "the board is a blank tile"


def test_without_the_engine_board_the_concept_is_held_prototype_refused():
    """The defect, reproduced: with the engine board removed the bear is refused a board."""
    db = _approved(BEAR)
    real = B.make_engine_board
    B.make_engine_board = lambda db, slug, **kw: {"board_image": None,
                                                  "why": "no engine draft to render: off"}
    try:
        filed = CI.file_radar_board(db, BEAR["slug"])
    finally:
        B.make_engine_board = real
    assert not filed["board"] and filed["why_code"] == "engine_draft_refused", filed


def test_no_board_without_an_approved_concept_or_for_the_animal_route():
    db = T._db()
    try:
        B.engine_draft_cir(db, "never-approved")
    except B.EngineDraftRefused as exc:
        assert "not an approved" in str(exc)
    else:
        raise AssertionError("an unapproved concept was drafted for a board")
    out = B.make_engine_board(db, "never-approved")
    assert out["board_image"] is None and CI.board_why_code(out) == "engine_draft_refused"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("OK")
