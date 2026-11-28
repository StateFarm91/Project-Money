"""VERIFY-REFS (19i31): why both hexagon-coaster-set@1.2.1 runs stop at verification.

Production 19i30 (15f809bfb, evidence 2026-11-26T01:31Z): both coaster runs passed product
fidelity, went through lifestyle generation (6 Laura frames, identity UNKNOWN) and are blocked
`verification:references:exhausted`, `redrive_eligibility` kind none, refused `final_block`.
`fidelity_unknowns.by_check` adds `region_palette` 9 (was 2 at 00:16Z; `coaster:palette` 10 is
three superseded 19i26-era anchor frames, unchanged since 18:41Z).

Two causes, both reproduced here (the production rows and pixels were NOT read):

1. The block itself. `verification` blocks, exhausted, on a STRUCTURAL failure: the LIFESTYLE
   frame's Product Truth applies `compose.lifestyle_evidence`, which FAILs a frame made from
   pattern-derived references ("chart", informational) whatever the image shows (W5-V1), and
   the block text names "references", which `production_evidence.block_family` files as
   `references`. That reading is policy -- test_v6_gallery_e2e REMAINING_GATES
   "LIFESTYLE-EVIDENCE": a photographic reference of a made sample, or an owner decision -- and
   is unchanged. It is not caused by region_palette, and the repair loop never ran: a
   structural FAIL buys no repair.
2. region_palette UNKNOWN on every generated non-anchor frame. The product region is located by
   a vision question; `RealJudges.product_truth` asked it of the identity adapters'
   `GatewayVisionJudge` (`image_vision` only), while craft texture and anchor consistency go to
   the routed fidelity judge. Production has openai-vision activated and Anthropic vision not,
   so the region question was never sent: "no product region is declared". Fix: the region is
   located through the routed fidelity judge (`fidelity.LIFESTYLE_REGION_ROUTE`
   "lifestyle-region/2"). A faithful coaster frame then reads region_palette PASS; a wrong
   colour FAILs; no route, or a frame where the item is not clearly visible, stays UNKNOWN.

The redrive: a run blocked at verification on a structural reading is re-verified ONCE per
(judge, checks, region route) version -- stored frames only, nothing generated -- and only
when today's policy no longer reads a stored frame as structural. While the policy holds the
readback says `structural_reference` (the named owner gate) instead of `final_block`, and no
vision call is spent on a reading that cannot change.

Every provider answer here is a TEST FIXTURE. There is no network and no paid call.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_verify_refs.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from PIL import Image  # noqa: E402

import test_image_fidelity_route as R  # noqa: E402  (its harness refuses the network)
import test_image_fidelity_3 as H  # noqa: E402  (deterministic photographic coasters)
import test_w4_ownerimg as O  # noqa: E402
import test_w5_v1_visual_correctness as V  # noqa: E402

from brambleloop.ops import production_evidence as PE  # noqa: E402
from brambleloop.visual import candidate_gates as CG  # noqa: E402
from brambleloop.visual import fidelity as F  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402

REL = "a" * 64


# ---- harness ---------------------------------------------------------------------------------

def _boxes(canvas=1400, inset=0.28):
    """Interior fabric rectangles of `H.scene`'s coasters (one per coaster, its centre), as
    fractions of the image: what a judge that "leaves out anything not only fabric" returns."""
    n = H._ctx()["make"]
    size = int(0.8 * canvas / (n * 1.1))
    x, out = (canvas - n * size * 1.1) / 2, []
    for _ in range(n):
        cx, cy, s = int(x) + size // 2, (canvas - size) // 2 + size // 2, size * inset
        out.append([round((cx - s) / canvas, 4), round((cy - s) / canvas, 4),
                    round((cx + s) / canvas, 4), round((cy + s) / canvas, 4)])
        x += size * 1.1
    return out


def _region_answer(boxes=None, visible="yes"):
    return {"item_visible": visible, "patches": _boxes() if boxes is None else boxes}


def _lifestyle(data, region):
    """`fidelity.verify_lifestyle` on a coaster frame, anchor PASS, with these pixel patches."""
    return F.verify_lifestyle(data, H._ctx()["cir"], release_hash=REL,
                              anchor={"status": "PASS", "release_hash": REL},
                              product_region=region or None)


def _region_check(v):
    return [c for c in v["checks"] if c["check"] == "region_palette"][0]


def _captured_locate(db):
    """`RealJudges.product_truth`'s locate callable (the region detector it hands to
    `fidelity_reading`), with the production judges' configuration."""
    seen = {}
    saved = CG.fidelity_reading

    def capture(_db, cand, bind, *, judge=None, consistency=None, locate=None):
        seen.update(judge=judge, locate=locate)
        return {"status": "UNKNOWN", "why": "captured", "codes": [], "failed": [],
                "unknown": ["fidelity"]}

    CG.fidelity_reading = capture
    try:
        j = CG.RealJudges(db, second_vision=None, embedder=None)
        j.product_truth({"slug": H.COASTERS, "version": "1.2.1", "role": "detail",
                         "sha256": "0" * 64}, {})
    finally:
        CG.fidelity_reading = saved
    return j, seen


def _structural_run():
    """The W5-V1 harness run: real Product Truth, fidelity stubbed PASS, so the run reaches
    verification and blocks on the LIFESTYLE frame's lifestyle_evidence reading."""
    db, cir, rel = V._basket_db()
    gen = O.StubGenerator()
    judges = V._judges(db)
    # the rows production made under 19i30/19i31's policy (W5-V1), reproduced as a fixture
    with V._FidelityPass(), V.LegacyLifestylePolicy():
        follow, _ = O.drain(db, generator=gen, judges=judges)
        assert IP.trigger(follow, slug=cir.slug, version=cir.version, release=rel)["enqueued"]
        O.drain(db, generator=gen, judges=judges)
    key = IP.run_key(cir.slug, cir.version, rel)
    return db, key, gen, judges


def _readback(db, key):
    with db.session() as s:
        return IP.redrive_readback(s)["runs"][key]


def _follow(calls):
    def follow(inputs, key, *, session=None):
        calls.append((inputs, key))
        return object()
    return follow


class _Lifted:
    """Simulate a changed Product Truth policy (as an owner decision would make it): the
    lifestyle_evidence scope no longer covers the frame. Test-only."""

    def __enter__(self):
        self.saved = CG.applies_lifestyle_evidence
        CG.applies_lifestyle_evidence = lambda cand: False
        return self

    def __exit__(self, *exc):
        CG.applies_lifestyle_evidence = self.saved
        return False


class _VisionOk:
    """The sweep's read-only vision pre-checks answer "usable, headroom" (fixture)."""

    def __enter__(self):
        self.saved = IP._vision_route_usable_read, IP._vision_headroom
        IP._vision_route_usable_read = lambda db: True
        IP._vision_headroom = lambda db, frames: (True, "")
        return self

    def __exit__(self, *exc):
        IP._vision_route_usable_read, IP._vision_headroom = self.saved
        return False


# ---- 1. the block, reproduced ------------------------------------------------------------------

def test_1_the_verification_references_block_is_the_structural_lifestyle_evidence_reading():
    db, key, gen, _ = _structural_run()
    run = IP.get_run(db, key)
    assert run["state"] == "blocked" and run["stage"] == "verification", run
    assert run["attempts_exhausted"] is True
    reason = run["blocked_reason"]
    assert IP.structural_verification_block(reason), reason
    assert "lifestyle_evidence: chart reference" in reason, reason
    # the production readback's grouping of exactly this reason
    assert PE.block_family(reason) == "references", PE.block_family(reason)
    grouped = PE._vp_runs(db)["blocked_reasons_grouped"]
    assert grouped == {"verification:references:exhausted": 1}, grouped
    # no repair was bought: one lifestyle call, and the reading is the policy's, not a misread
    assert [r for r, _k, _o in gen.seen if r == "lifestyle"] == ["lifestyle"], gen.seen
    best = IP._best(db, listing=V.BASKET_LISTING, role="lifestyle", run=key)
    assert best["structural"] == "lifestyle_evidence: chart reference"
    with V.LegacyLifestylePolicy():
        assert CG.lifestyle_structural({"role": "lifestyle", "references": [
            {"kind": "pattern_derived"}]}, {}) == "lifestyle_evidence: chart reference"
    # D-OWNER-LIFESTYLE-GENERATED (19i32): today's policy reads no structural reason
    assert CG.lifestyle_structural({"role": "lifestyle", "references": [
        {"kind": "pattern_derived"}]}, {}) is None
    print("OK 1 verification:references:exhausted is the structural lifestyle_evidence FAIL")


def test_2_while_the_policy_holds_the_readback_names_it_and_nothing_is_restarted():
    db, key, gen, _ = _structural_run()
    with V.LegacyLifestylePolicy():
        _test_2_body(db, key)


def _test_2_body(db, key):
    v = _readback(db, key)
    assert v["kind"] == "verification_reverify" and v["refused"] == "structural_reference", v
    assert not v["eligible"]
    calls: list = []
    with _VisionOk():
        out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert calls == [] and out["restarted"] == [], out
    assert any(r.get("kind") == "verification_reverify" and "structural" in r["why"]
               for r in out["refused"]), out["refused"]
    with db.session() as s:
        assert IP.redrive_due(s, None) is None
    can = IP.restartable(db, key, reverify_only=True)
    assert can["restartable"] is False and can["code"] == "structural_reference", can
    # an ordinary restart request is still refused as before (no regeneration bought)
    assert IP.restartable(db, key)["restartable"] is False
    print("OK 2 policy in force: refused structural_reference, no restart, no spend")


# ---- 2. region_palette: the region question went to the closed judge -------------------------

def test_3_before_the_fix_the_region_question_never_reaches_the_activated_route():
    db = R._db()
    R._production_vision(db)
    data = H.scene()
    t = R._Transport(_region_answer())
    with R._Patched(t):
        # the 19i30 locate callable on the 19i30 adapters' judge (image_vision only; since
        # VISION-GATE-ROUTE the adapters ask the routed judge by default)
        j = CG.RealJudges(db, vision=F.GatewayVisionJudge(db), second_vision=None,
                          embedder=None)
        old = j.adapters().product_region({"data": data})
    assert t.calls == 0 and old["patches"] == [], (t.calls, old)
    assert "image_vision" in old["why"], old
    v = _lifestyle(data, old["patches"])
    rc = _region_check(v)
    assert rc["status"] == "UNKNOWN" and "no product region" in rc["why"], rc
    print("OK 3 reproduced: region_palette UNKNOWN, no product region declared")


def test_4_product_truth_locates_the_region_through_the_routed_judge_and_a_faithful_frame_passes():
    db = R._db()
    R._production_vision(db)
    j, seen = _captured_locate(db)
    assert isinstance(seen["judge"], F.RoutedVisionJudge), seen
    data = H.scene()
    t = R._Transport(_region_answer())
    with R._Patched(t):
        got = seen["locate"]({"data": data})
    assert t.calls == 1 and len(got["patches"]) == H._ctx()["make"], (t.calls, got)
    rc = _region_check(_lifestyle(data, got["patches"]))
    assert rc["status"] == "PASS", rc
    # VISION-GATE-ROUTE (19i35): the adapters ask the same routed judge (the route in use)
    assert type(j._vision_judge()) is F.RoutedVisionJudge
    assert F.LIFESTYLE_REGION_ROUTE == "lifestyle-region/2"
    # light oak and the eyelets' shade read PASS too
    for table in (H.LIGHT_OAK, H.HONEY):
        rc = _region_check(_lifestyle(H.scene(table=table), got["patches"]))
        assert rc["status"] == "PASS", (table, rc)
    print("OK 4 region located through the routed judge; faithful frame region_palette PASS")


def test_5_a_wrong_colour_fails_a_missing_round_fails_and_unreadable_stays_unknown():
    db = R._db()
    R._production_vision(db)
    _j, seen = _captured_locate(db)
    data = H.scene()
    with R._Patched(R._Transport(_region_answer())):
        patches = seen["locate"]({"data": data})["patches"]
    # a wrong main colour inside the located fabric FAILs on the colour check itself
    mustard = H.scene(src=H.recoloured(H.CREAM, (238, 205, 120)))
    rc = _region_check(_lifestyle(mustard, patches))
    assert rc["status"] == "FAIL" and rc.get("code") == "OFF_PALETTE_COLOUR", rc
    # a wrong or missing wine round lies outside the interior patches (round 6 of 7): the
    # colour check does not claim it; the anchor-consistency reading does, and the frame
    # never PASSes. (On the product frame both FAIL deterministically: test_image_fidelity_3.)

    class Differs:
        name = "fixture"

        def read(self, prompt, images, **kw):
            return {"answered": True, "reading": {"same_item": "false",
                                                  "differences": ["no dark red round"]}}

    for wrong in (H.recoloured(H.WINE, (31, 42, 110)), H.recoloured(H.WINE,
                                                                    F._hex_rgb(H.CREAM))):
        v = F.verify_lifestyle(H.scene(src=wrong), H._ctx()["cir"], release_hash=REL,
                               anchor={"status": "PASS", "release_hash": REL},
                               anchor_data=data, product_region=patches, judge=Differs())
        assert v["status"] == "FAIL" and "anchor_consistency" in v["failed"], v["failed"]
    # unreadable: the item is not clearly visible, patches too small, or no route at all
    for answer in (_region_answer(visible="unclear"), _region_answer(boxes=[[0.1, 0.1, 0.11,
                                                                             0.11]])):
        dbx = R._db()            # a fresh store: the route keeps one answer per bytes
        R._production_vision(dbx)
        _jx, seenx = _captured_locate(dbx)
        with R._Patched(R._Transport(answer)):
            got = seenx["locate"]({"data": data})
        assert got["patches"] == [], got
        assert _region_check(_lifestyle(data, got["patches"]))["status"] == "UNKNOWN"
    db2 = R._db()
    R._no_vision()
    _j2, seen2 = _captured_locate(db2)
    t = R._Transport(_region_answer())
    with R._Patched(t):
        got = seen2["locate"]({"data": data})
    assert t.calls == 0 and got["patches"] == [], got
    assert _region_check(_lifestyle(data, got["patches"]))["status"] == "UNKNOWN"
    print("OK 5 wrong colour FAIL, missing round FAIL, unreadable UNKNOWN")


# ---- 3. the bounded redrive ---------------------------------------------------------------------

def test_6_when_the_policy_no_longer_reads_structural_the_stored_frames_are_reverified_once():
    db, key, gen, judges = _structural_run()
    calls_before = gen.calls
    with _Lifted():
        v = _readback(db, key)
        assert v["kind"] == "verification_reverify" and v["eligible"], v
        with db.session() as s:
            due = IP.redrive_due(s, None)
        assert due and due["kind"] == "verification_reverify" and due["run_key"] == key, due
        calls: list = []
        with _VisionOk():
            out = IP.redrive_capability_blocked(db, follow=_follow(calls))
        assert len(calls) == 1, (calls, out)
        inputs, _k = calls[0]
        assert inputs["stage"] == "verification" and inputs.get("reverify") is True, inputs
        assert out["restarted"][0]["resume_at"] == "verification", out
        from sqlalchemy import select

        from brambleloop.visual.image_records import ImageProductionRun

        with db.session() as s:
            r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
            hist = (r.stages or {})[IP.RESTART_KEY]["history"]
        rec = [h for h in hist if h.get("by") == IP.VERIFY_REDRIVE_BY]
        assert len(rec) == 1 and rec[0]["verify_version"] == IP.verify_redrive_version(), rec
        assert rec[0]["reverify"] is True and rec[0]["resume_at"] == "verification", rec
        # the re-verification job itself, on the real queue: stored frames only
        from brambleloop.queue.durable import JobQueue

        q = JobQueue(db)
        inputs, k = calls[0]
        q.enqueue(IP.AGENT, IP.JOB_TYPE, inputs, idempotency_key=k)
        with V._FidelityPass():
            O.drain(db, generator=gen, judges=judges)
        after = IP.get_run(db, key)
        assert not (after["state"] == "blocked" and after["stage"] == "verification"
                    and IP.structural_verification_block(after["blocked_reason"])), after
    # nothing was generated by the redrive or its re-verification
    assert gen.calls == calls_before, (gen.calls, calls_before)
    print("OK 6 policy lifted: re-verified once at verification, nothing generated")


def test_7_once_per_version_and_the_restart_cap_binds():
    db, key, gen, judges = _structural_run()
    with _Lifted(), _VisionOk():
        # the job the restart enqueued never ran here: re-block the run as it was
        calls: list = []
        IP.redrive_capability_blocked(db, follow=_follow(calls))
        assert len(calls) == 1
        from sqlalchemy import select
        from sqlalchemy.orm.attributes import flag_modified

        from brambleloop.visual.image_records import ImageProductionRun

        with db.session() as s:
            r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
            hist = (r.stages or {})[IP.RESTART_KEY]["history"]
            reason = hist[-1]["blocked_reason"]
            r.status, r.stage, r.blocked_reason, r.attempts_exhausted = (
                "blocked", "verification", reason, True)
            flag_modified(r, "stages")
        v = _readback(db, key)
        assert v["refused"] == "already_redriven", v
        again: list = []
        out = IP.redrive_capability_blocked(db, follow=_follow(again))
        assert again == [] and out["restarted"] == [], out
        # at the restart cap the run is refused before anything is asked
        saved = IP.restart_counts

        def at_cap(session, row, current=None):
            got = saved(session, row, current=current)
            return {**got, "current": IP.MAX_RESTARTS, "total": IP.MAX_RESTARTS}

        IP.restart_counts = at_cap
        try:
            assert _readback(db, key)["refused"] == "max_restarts"
        finally:
            IP.restart_counts = saved
    print("OK 7 once per version; MAX_RESTARTS binds")


def test_9_owner_1a_makes_the_stored_coaster_runs_due_once_and_generates_nothing():
    """D-OWNER-LIFESTYLE-GENERATED (19i32), no test patch of the policy: the stored structural
    rows (W5-V1) are no longer structural under today's policy, so the run is due for one
    verification_reverify; the policy version is part of the redrive key."""
    db, key, gen, judges = _structural_run()
    calls_before = gen.calls
    assert CG.LIFESTYLE_POLICY_VERSION in IP.verify_redrive_version()
    v = _readback(db, key)
    assert v["kind"] == "verification_reverify" and v["eligible"], v
    with db.session() as s:
        due = IP.redrive_due(s, None)
    assert due and due["kind"] == "verification_reverify" and due["run_key"] == key, due
    calls: list = []
    with _VisionOk():
        out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert len(calls) == 1 and out["restarted"][0]["resume_at"] == "verification", out
    assert calls[0][0].get("reverify") is True
    # it is running again (no longer blocked), and the same version is recorded
    with db.session() as s:
        assert key not in IP.redrive_readback(s)["runs"]
    assert gen.calls == calls_before
    print("OK 9 owner 1A: due once, re-verified at verification, nothing generated")


def test_8_the_readback_vocabulary_carries_the_new_kind_and_refusal():
    assert "verification_reverify" in IP.REDRIVE_KINDS
    assert "structural_reference" in IP.REDRIVE_REFUSALS
    assert IP._redrive_kind("x (structural: the references are pattern-derived, so ...)",
                            "verification") == "verification_reverify"
    assert IP._redrive_kind("lifestyle: something else", "verification") == "none"
    print("OK 8 readback vocabulary")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    tests.sort(key=lambda f: int(f.__name__.split("_")[1]))
    for t in tests:
        t()
    print(f"ALL {len(tests)} OK")
