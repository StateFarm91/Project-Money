"""D5 (CATALOGUE-UNBLOCK, 2026-11-22): the #88 judge was shown a swatch, not the concept.

clay-lumbar-envelope-cushion-cover and larchwood-kids-beanie were refused at the
pre-engineering gate: "#88 premise_thumbnail: judged not to read at mobile-grid size". The
judge receives the board at 570 px (Etsy's grid thumbnail width), unscaled by the provider, so
size and resolution were right. The picture was not: `creative.board.make_board` drew a
research concept's prototype with `fabric_raster` at 26 px per stitch, kept the first 40 rows
and 40 stitches, cropped the TOP-LEFT square of that and resized it -- a close-up swatch in
`fabric_raster`'s default pink, whatever the CIR's colours, with no outline of the object.
Version 2 ("twin-board/2") draws the whole piece in the CIR's own colours, letterboxed, never
cropped (`products.moment_candidates.board_png`). A concept judged False on an older board
is redrawn and sent back to `radar.score`; its old verdict stays bound to the old bytes.

Every concept, board and judgement here is a TEST FIXTURE. No network, no model call.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_d5_concept_board.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job  # noqa: E402
from brambleloop.creative import intake as creative_intake  # noqa: E402
from brambleloop.creative.board import BOARD_PX, BOARD_RENDERER, make_board  # noqa: E402
from brambleloop.creative.preengineering import concept_from  # noqa: E402
from brambleloop.creative.prototype import author  # noqa: E402
from brambleloop.products.moment_candidates import BOARD_ACTION  # noqa: E402
from brambleloop.radar import demand_originals as DO  # noqa: E402
from brambleloop.radar import intake as radar_intake  # noqa: E402

SLUG = "clay-lumbar-envelope-cushion-cover"
PINK = (201, 139, 155)   # visual.render.fabric_raster's default yarn colour


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='d5board_')}/d.sqlite")
    db.create_all()
    return db


def _proposal(slug: str = SLUG) -> dict:
    o = next(x for x in DO.CATALOGUE if x.slug == slug)
    return DO.proposal_for(o, {"cluster": "fixture", "score": 1.0, "status": "MEASURED",
                               "confidence": "high"}, {"finding": "F1", "source": "S1"})


def _concept(slug: str = SLUG):
    p = _proposal(slug)
    c, _brief, problem = concept_from({"concept": {**p["concept"], "slug": slug,
                                                   "title": p["title"], "make_lane": "SHORT"},
                                       "brief": p["brief"]})
    assert c is not None, problem
    return c


def _image(db, ref: str) -> Image.Image:
    from brambleloop.core.artifacts import ArtifactStore

    sha = ref.split(":", 1)[1]
    return Image.open(io.BytesIO(ArtifactStore().get(sha, db=db))).convert("RGB")


def _near(a, b, tol=40) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_board_draws_the_whole_piece_in_the_cirs_own_colours():
    for slug in (SLUG, "larchwood-kids-beanie"):
        db = _db()
        concept = _concept(slug)
        cir = author(concept)
        made = make_board(db, concept)
        assert made["source"] == "prototype" and made["renderer"] == BOARD_RENDERER, made
        img = _image(db, made["board_image"])
        assert img.size == (BOARD_PX, BOARD_PX)
        palette = [tuple(int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
                   for h in cir.colors.values()]
        colours = img.getcolors(BOARD_PX * BOARD_PX)
        total = sum(n for n, _ in colours)
        pink = sum(n for n, c in colours if c[0] > c[1] + 35 and c[2] > c[1] + 5)  # pink hue
        assert pink / total < 0.01, f"{slug}: board drawn in the renderer's default pink"
        main = sum(n for n, c in colours if any(_near(c, p) for p in palette))
        assert main / total > 0.15, f"{slug}: the CIR's own colours are not on the board"
        # Letterboxed, never cropped: the piece is wider than tall, so the top and bottom
        # rows are the ground and the whole width carries fabric.
        ground = img.getpixel((BOARD_PX // 2, 2))
        assert _near(img.getpixel((BOARD_PX // 2, BOARD_PX - 3)), ground, 6)
        mid = BOARD_PX // 2
        band = [img.getpixel((x, mid)) for x in range(BOARD_PX)]
        fabric = sum(1 for p in band if not _near(p, ground, 12))
        assert fabric / BOARD_PX > 0.8, f"{slug}: the piece does not span the board"


def _approve(db) -> None:
    p = _proposal()
    radar_intake._ensure(db)
    with db.session() as s:
        s.add(radar_intake.RadarConcept(
            slug=SLUG, state=radar_intake.APPROVED, source=radar_intake.SOURCE_FAMILY,
            source_ref="family:fixture", fingerprint="d5" * 32,
            seed={"title": p["title"], "category": p["category"], "risk_class": "A",
                  "price_cad": p["price_cad"], "maker_hours": p["maker_hours"],
                  "design_hours": p["design_hours"], "whitespace": 0.6,
                  "rationale": p["rationale"], "evergreen": True},
            concept={**p["concept"], "make_lane": "SHORT"}, brief=p["brief"]))


class _Ctx:
    def __init__(self, db):
        self.db = db
        self.enqueued: list[tuple] = []

    def enqueue(self, agent, job_type, inputs, idempotency_key=None, **_kw):
        self.enqueued.append((job_type, idempotency_key))
        return object()

    def audit(self, action, artifact=None, detail=None):
        with self.db.session() as s:
            s.add(AuditLog(actor="test", action=action, artifact=artifact, detail=detail or {}))


def _old_board_judged(db, reads_small: bool, renderer: str | None = None) -> str:
    """A v1-style board on file (no renderer field) and a named judge's verdict on it."""
    from brambleloop.core.artifacts import ArtifactStore

    buf = io.BytesIO()
    Image.new("RGB", (BOARD_PX, BOARD_PX), PINK).save(buf, format="PNG")
    sha = ArtifactStore().put(f"board/{SLUG}-v1.png", buf.getvalue(), "image/png", db=db,
                              keep="fixture v1 board").sha256
    record = {"slug": SLUG, "image": {"sha256": sha}, "image_ref": f"sha256:{sha}",
              "source": creative_intake.RADAR_BOARD_SOURCE, "board_source": "prototype"}
    if renderer:
        record["renderer"] = renderer
    with db.session() as s:
        s.add(AuditLog(actor="creative", action=BOARD_ACTION, artifact=SLUG, detail=record))
        s.add(AuditLog(actor="creative", action=creative_intake.JUDGED_ACTION, artifact=SLUG,
                       detail={"thumbnail_reads_small": reads_small, "craft_impression": 3.0,
                               "judge": "fixture-judge", "board_sha256": sha}))
    return sha


def test_a_verdict_on_the_old_swatch_board_is_redrawn_and_rescored():
    db = _db()
    _approve(db)
    old = _old_board_judged(db, reads_small=False)
    assert creative_intake.judgement_for(db, SLUG)["thumbnail_reads_small"] is False
    ctx = _Ctx(db)
    assert creative_intake.reboard_stale_radar(ctx) == [SLUG]
    new = creative_intake.board_digest_for(db, SLUG)
    assert new and new != old
    # The old verdict is bound to the old bytes: nobody has judged the new board yet.
    assert creative_intake.judgement_for(db, SLUG) is None
    assert ctx.enqueued == [("radar.score", f"score-reboard:{SLUG}:{new[:16]}")]
    # Idempotent: the new board is the current renderer's, so nothing is redrawn again.
    assert creative_intake.reboard_stale_radar(_Ctx(db)) == []


def test_current_boards_passing_verdicts_and_drafted_concepts_are_left_alone():
    for case in ("current", "passed", "drafted"):
        db = _db()
        _approve(db)
        _old_board_judged(db, reads_small=(case == "passed"),
                          renderer=BOARD_RENDERER if case == "current" else None)
        if case == "drafted":
            with db.session() as s:
                s.add(Job(agent="crochet_engineer", job_type="cir.draft",
                          inputs={"slug": SLUG}, idempotency_key=f"draft:{SLUG}"))
        before = creative_intake.board_digest_for(db, SLUG)
        assert creative_intake.reboard_stale_radar(_Ctx(db)) == [], case
        assert creative_intake.board_digest_for(db, SLUG) == before, case
        with db.session() as s:
            assert s.scalar(select(AuditLog.id).where(
                AuditLog.action == "creative.board_redrawn")) is None, case


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK  ", name)
