"""Final Build 2, worker I: reproductions of Codex build-2 defects, each now fixed.

Every test was written to fail on 0f3f5d1 with the defect the reconciliation records
(research/final_build/codex_reconciliation/build2_assist_reconciliation.json) and to pass
with the repair. No network, no model calls.

- CB2-D01: a concept judgement is bound to the board's content digest.
- CB2-I01: a repeated unreviewed policy change stays unreviewed until reviewed.
- CB2-I04: a physical photo needs its bytes in the artefact store, not only a digest.
- CB2-I05: the upgrade impact clock starts when the frame is approved, not when planned.
- CB2-I07: an UNMEASURED drift series never resolves a publication-halting incident.
- CB2-I10: unquoted catchphrases are declared as slogan tokens.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", tempfile.mkdtemp(prefix="fb2_i_art_"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Incident, ListingAsset, ListingOutcome, PhysicalPhoto,
)


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='fb2_i_')}/t.sqlite")
    db.create_all()
    return db


# ---- CB2-D01 ------------------------------------------------------------------------------


def _file_board(db, slug: str, payload: bytes) -> str:
    from brambleloop.publish import owned_photography

    sha = hashlib.sha256(payload).hexdigest()
    with db.session() as s:
        s.add(AuditLog(actor="publishing", action=owned_photography.ACTION, detail={
            "made": True, "slug": slug, "method_version": owned_photography.METHOD_VERSION,
            "image_ref": f"/gone/{sha[:8]}.png", "image": {"sha256": sha}}))
    return sha


def _judged(db, slug: str, **extra) -> None:
    from brambleloop.creative import intake

    with db.session() as s:
        s.add(AuditLog(actor="t", action=intake.JUDGED_ACTION, artifact=slug, detail={
            "judge": "model-m", "thumbnail_reads_small": True, "craft_impression": 4.5,
            "board": "/old/board_v1.png", **extra}))


def test_d01_a_judgement_is_bound_to_the_board_bytes_it_saw():
    from brambleloop.creative import intake

    db = _db()
    # The Codex reproduction: a judged row naming only a board path, no digest.
    _judged(db, "winner-x")
    assert intake.judgement_for(db, "winner-x") is None, \
        "a judgement that never recorded which bytes it saw counted"

    v1 = _file_board(db, "winner-y", b"board v1")
    _judged(db, "winner-y", board_sha256=v1)
    got = intake.judgement_for(db, "winner-y")
    assert got and got["craft_impression"] == 4.5 and got["thumbnail_reads_small"] is True

    # The board is re-rendered: the old verdict is about a picture no longer on file.
    _file_board(db, "winner-y", b"board v2 -- different bytes")
    assert intake.judgement_for(db, "winner-y") is None, "a changed board kept its judgement"


def test_d01_a_board_with_no_identifiable_bytes_is_not_judged():
    from types import SimpleNamespace

    from brambleloop.creative import intake
    from brambleloop.publish import owned_photography

    db = _db()
    with db.session() as s:
        s.add(AuditLog(actor="publishing", action=owned_photography.ACTION, detail={
            "made": True, "slug": "w", "method_version": owned_photography.METHOD_VERSION,
            "image_ref": "https://example.invalid/board.png"}))
    assert intake.board_digest_for(db, "w") == ""

    class NeverCalled:
        model = "m"

        def see(self, *a, **k):
            raise AssertionError("a board with no digest was sent to the judge")

    out = intake.judge_held(SimpleNamespace(db=db), slug="w",
                            board="https://example.invalid/board.png", provider=NeverCalled())
    assert out["judged"] is False and "digest" in out["why"]


# ---- CB2-I01 ------------------------------------------------------------------------------


def test_i01_reading_a_changed_policy_again_does_not_review_it():
    from brambleloop.gates import platform_policy as pp

    db = _db()
    src = "advertising_rules"
    pp.record_snapshot(db, src, text="policy A")
    b = pp.record_snapshot(db, src, text="policy B")
    assert b["material_change"]
    assert [c["source"] for c in pp.unreviewed_changes(db)] == [src]
    again = pp.record_snapshot(db, src, text="policy B")
    assert again["material_change"] is False
    assert [c["source"] for c in pp.unreviewed_changes(db)] == [src], \
        "an unchanged second reading erased an unreviewed change"
    # Only a review clears it, and the review lands on the change, not the later reading.
    out = pp.review_change(db, src, reviewed_by="owner", tested="ads flow re-run")
    assert out["snapshot_id"] == b["id"]
    assert pp.unreviewed_changes(db) == []
    try:
        pp.review_change(db, src, reviewed_by="owner", tested="again")
    except pp.PolicyRefused:
        pass
    else:
        raise AssertionError("an already-reviewed change was reviewed again")
    # A later change reopens the block.
    pp.record_snapshot(db, src, text="policy C")
    assert [c["source"] for c in pp.unreviewed_changes(db)] == [src]


# ---- CB2-I04 / CB2-I05 --------------------------------------------------------------------


def test_i04_a_digest_and_a_rights_label_are_not_a_photograph():
    from brambleloop.publish import physical_upgrade as pu

    db = _db()
    r = pu.intake(db, slug="any-slug", source="tester", sha256="a" * 64,
                  rights_basis="tester_agreement")
    assert r["may_use"] is False and r["state"] == pu.HELD_NO_BYTES, r
    plan = pu.plan_upgrade(db, r["photo_id"])
    assert plan["upgraded"] is False
    with db.session() as s:
        assert s.scalar(select(ListingAsset)) is None

    # Bytes that hash to the digest arrive: the same photo becomes usable.
    from brambleloop.core.artifacts import ArtifactStore

    sha = ArtifactStore().put("p.jpg", b"real photo bytes", "image/jpeg").sha256
    held = pu.intake(db, slug="any-slug", source="tester", sha256=sha,
                     rights_basis="tester_agreement")
    assert held["may_use"] is True and held["state"] == "received", held


def test_i05_the_impact_clock_starts_only_when_the_frame_is_approved():
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.publish import physical_upgrade as pu

    db = _db()
    sha = ArtifactStore().put("q.jpg", b"another real photo", "image/jpeg").sha256
    r = pu.intake(db, slug="cable", version="1.0.0", source="tester", sha256=sha,
                  rights_basis="tester_agreement")
    plan = pu.plan_upgrade(db, r["photo_id"], today=date(2026, 9, 1))
    assert plan["upgraded"]
    with db.session() as s:
        photo = s.get(PhysicalPhoto, r["photo_id"])
        assert "upgraded_on" not in photo.detail and "live_since" not in photo.detail
        s.add(ListingOutcome(product_slug="cable", period_start="2026-09-05",
                             period_end="2026-09-12", visits=100, first_frame_views=1000,
                             first_frame_engagements=30, orders=3, source="fixture"))
    out = pu.measure_impact(db, today=date(2026, 9, 20))
    assert out["readings"][0]["impact"] == "UNMEASURED"
    assert "not approved" in out["readings"][0]["why"]
    with db.session() as s:
        assert "live_since" not in s.get(PhysicalPhoto, r["photo_id"]).detail
        s.scalar(select(ListingAsset).where(ListingAsset.sha256 == sha)).approved = True
    pu.measure_impact(db, today=date(2026, 9, 21))
    with db.session() as s:
        detail = s.get(PhysicalPhoto, r["photo_id"]).detail
    assert detail["live_since"] == "2026-09-21"
    # The period between planning and approval is the baseline, not the "after".
    assert detail["baseline"]["ctr"] == 0.03


# ---- CB2-I07 ------------------------------------------------------------------------------


def test_i07_an_unmeasured_series_does_not_resolve_a_drift_incident():
    from brambleloop.visual import drift_series as ds

    db = _db()
    with db.session() as s:
        s.add(Incident(severity="P2", signature=ds.SIGNATURE + "face", summary="drift",
                       halts_publication=True, resolved=False))
    out = ds.run(db)
    assert out["batches"] == 0 and out["measurable"] is False
    assert out["incidents_resolved"] == []
    with db.session() as s:
        inc = s.scalar(select(Incident).where(Incident.signature == ds.SIGNATURE + "face"))
        assert inc.resolved is False and inc.halts_publication


# ---- CB2-I10 ------------------------------------------------------------------------------


def test_i10_unquoted_catchphrases_are_declared():
    from brambleloop.culture import rights
    from brambleloop.culture.engine import file_topic, quote_tokens

    for topic, domain in (("Keep calm and crochet on", "meme"),
                          ("I am the danger", "internet_moment"),
                          ("Keep Calm and Carry On", "film"),
                          ("May the Force be with you", "film"),
                          ("This is fine", "meme"),
                          ("You had one job", "internet_moment")):
        toks = quote_tokens(topic, domain)
        assert toks and all(t.asset_class == rights.SLOGAN for t in toks), (topic, toks)
    filed = file_topic("Keep calm and crochet on", "meme")
    assert any(t.asset_class == rights.SLOGAN for t in filed["tokens"])
    # Not a false-positive surge: ordinary titles stay clear of the slogan class.
    for topic, domain in (("Distracted boyfriend", "meme"), ("Grumpy Cat", "meme"),
                          ("Christmas Eve", "holiday"), ("Cottagecore", "viral_aesthetic"),
                          ("Winter solstice", "season"), ("Breaking Bad", "television"),
                          ("Coquette bows", "viral_aesthetic"), ("Taylor Swift", "music")):
        assert quote_tokens(topic, domain) == [], topic


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
