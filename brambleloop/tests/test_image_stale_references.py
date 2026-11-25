"""IMAGE-STALE-REFS (19i24): a gallery never hands FLUX references from an older render.

Production 19i23 (2026-11-25): four basket galleries (market-basket-small@1.3.0 and
housewarming-key-basket@0.1.0, both routes) blocked at product_generation with

    vessel side view could not be rendered: GeneratorRefused: the product references
    handed in are not the bytes this release renders; refused

Root cause: `prepare_references` stores the pattern references (layout, texture, detail,
rules) once per run and every later stage reads them back from the run record. Batch 19i16
(b9718dc73, pattern-refs 3.1.3 -> 3.1.4) changed what a vessel's layout and rules
references render. Runs that had prepared under 3.1.3 were later restarted (the method
redrive and the provider redrive both resume at product_generation), so they handed the
3.1.3 bytes to a generator whose binding check renders 3.1.4. The check is right to refuse;
the stored references were stale. Fixed here:

  1. the prepared references carry the reference-renderer version and the epoch they were
     made in; a stage that would hand them to the generator re-prepares them (deterministic,
     free) when either differs, and records what it superseded;
  2. a refusal for stale references is raised before anything is sent: its hold is released
     and the call counts toward no call, attempt or restart cap (legacy rows too);
  3. runs already blocked on it are re-driven by the hourly sweep (kind `stale_references`),
     once per reference version, under every other cap.

The binding check itself is unchanged and still refuses references that are not this
release's render.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_image_stale_references.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import hashlib
import io
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

from brambleloop.visual import image_production as IP  # noqa: E402

LEGACY = ("vessel side view could not be rendered: GeneratorRefused: the product references "
          "handed in are not the bytes this release renders; refused")
NOW = datetime.now(timezone.utc)
_S: dict = {}


def _older_render(raw: bytes) -> bytes:
    """The same reference as an older renderer drew it: a valid PNG, different bytes."""
    from PIL import Image

    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.putpixel((0, 0), tuple(255 - c for c in im.getpixel((0, 0))))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _make_references_stale(db, key) -> dict | None:
    """Rewrite the run's stored references the way a run prepared under pattern-refs 3.1.3
    looks to 3.1.4 code: the layout and rules images are other bytes, and no stamp."""
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.visual.image_records import ImageProductionRun

    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        if r is None or "prepare_references" not in (r.stages or {}):
            return None
        st = dict(r.stages)
        rec = dict(st["prepare_references"])
        outs = dict(rec.get("outputs") or {})
        refs = [dict(x) for x in outs.get("references") or []]
    old = []
    for x in refs:
        role = str(x.get("label") or "").split("|", 1)[0]
        if role in ("product_layout", "product_rules"):
            raw = _older_render(ArtifactStore().get(x["sha256"], db=db))
            x["sha256"] = IP.store_bytes(db, raw, key=f"{key}/ref", why="test: older render")
            old.append(x["sha256"])
    assert len(old) == 2, refs
    outs = {k: v for k, v in outs.items() if k not in ("references_version", "epoch")}
    outs["references"] = refs
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        st = dict(r.stages)
        st["prepare_references"] = {**rec, "outputs": outs}
        r.stages = st
        flag_modified(r, "stages")
    return {"refs": refs, "old": old}


def stale_run():
    """The basket's FLUX gallery whose references are made stale right after they were
    prepared, before product_generation reads them."""
    if "stale" in _S:
        return _S["stale"]
    import test_image_ad as AD

    seen: dict = {}

    def after(db_, _bfl):
        if seen:
            return
        from sqlalchemy import select

        from brambleloop.visual.image_records import ImageProductionRun

        with db_.session() as s:
            keys = [r.run_key for r in s.scalars(select(ImageProductionRun))
                    if "prepare_references" in (r.stages or {})
                    and r.stage == "prepare_references"]
        for k in keys:
            got = _make_references_stale(db_, k)
            if got:
                seen[k] = got

    db, version, rh, jobs, bfl = AD.basket_run(after=after)
    _S["stale"] = (db, version, rh, jobs, bfl, seen)
    return _S["stale"]


def test_1_a_run_with_references_from_an_older_render_is_not_refused():
    db, _v, _rh, _jobs, bfl, seen = stale_run()
    assert seen, "the references were never made stale (the hook did not run)"
    for key in seen:
        run = IP.get_run(db, key)
        assert "not the bytes this release renders" not in (run.get("blocked_reason") or ""), run
        sides = [c for c in _cands(db, key) if c["role"] == IP.ANCHOR_SIDE_ROLE]
        assert any(c["sha256"] for c in sides), (sides, run)
        assert not any("not the bytes this release renders" in c["why"]
                       for c in _cands(db, key)), _cands(db, key)


def test_2_the_references_were_re_prepared_from_this_release_and_the_old_ones_recorded():
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.creative import flux3_generator as FG

    db, _v, _rh, _jobs, _bfl, seen = stale_run()
    assert seen, "the references were never made stale (the hook did not run)"
    for key, got in seen.items():
        rec = IP._stage_data(db, key)["prepare_references"]["outputs"]
        assert rec["references_version"] == IP.references_version(), rec
        shas = [r["sha256"] for r in rec["references"]]
        assert not set(got["old"]) & set(shas), (got["old"], shas)
        sup = rec.get("superseded") or []
        assert sup and set(got["old"]) <= set(sup[-1]["sha256s"]), sup
        assert sup[-1]["why"] and sup[-1]["references_version"] is None, sup
        # what is stored now is exactly what the generator's own binding renders
        run = IP.get_run(db, key)
        gen = FG.Flux3Generator(db) if hasattr(FG, "Flux3Generator") else None
        if gen is not None:
            refs = [{**r, "data": ArtifactStore().get(r["sha256"], db=db)}
                    for r in rec["references"]]
            with gen._scratch():
                rel, *_ = gen._bind(refs)
            assert rel.release_hash == run["release"]


def test_3_the_binding_check_still_refuses_references_that_are_not_this_release():
    """The fix re-prepares; it never relaxes. Old bytes handed straight to the generator are
    refused exactly as before, and the refusal says nothing was sent."""
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.creative import flux3_generator as FG

    db, _v, _rh, _jobs, _bfl, seen = stale_run()
    key, got = next(iter(seen.items()))
    refs = [{**r, "data": ArtifactStore().get(r["sha256"], db=db)} for r in got["refs"]]
    gen = FG.Flux3Generator(db)
    try:
        with gen._scratch():
            gen._bind(refs)
        raise AssertionError("stale references must be refused")
    except FG.GeneratorRefused as exc:
        assert "not the bytes this release renders" in str(exc), exc
        assert isinstance(exc, FG.StaleReferences) and exc.sent_nothing is True
    # unlabelled data with a claimed hash is still checked against the render
    forged = [{**r, "sha256": hashlib.sha256(b"x").hexdigest()} for r in refs]
    try:
        with gen._scratch():
            gen._bind(forged)
        raise AssertionError("a forged hash must be refused")
    except FG.GeneratorRefused:
        pass


def _cands(db, key):
    from sqlalchemy import select

    from brambleloop.visual.image_records import ImageCandidate

    with db.session() as s:
        return [{"role": c.role, "sha256": c.sha256, "outcome": c.outcome,
                 "why": str(((c.checks or {}).get("provider") or {}).get("why") or "")}
                for c in s.scalars(select(ImageCandidate).where(ImageCandidate.run_key == key))]


# ---- runs already blocked in production -------------------------------------------------

def _prod_blocked(db, slug, *, when, pending=True, reason=LEGACY):
    """A run as production holds it: blocked at product_generation on the stale-reference
    refusal, the refused side-view call's provider-error row (no marker: written before
    one existed), and the paid hold `_begin_generation` left behind."""
    from brambleloop.visual.image_records import ImageCandidate, ImageProductionRun

    key = IP.run_key(slug, "1.0.0", f"{slug}-release")
    hold_at = when - timedelta(seconds=5)
    stages = {"prepare_references": {"outputs": {"references": []},
                                     "at": (when - timedelta(hours=2)).isoformat()}}
    if pending:
        stages["_pending_paid_call"] = {"token": "t" * 32, "stage": "product_generation",
                                        "maximum_cad": 0.14, "at": hold_at.isoformat()}
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug=slug, version="1.0.0",
                                 release=f"{slug}-release", listing=slug,
                                 stage="product_generation", status="blocked",
                                 blocked_reason=reason, stages=stages, updated_at=when,
                                 generation_calls=1))
        s.add(ImageCandidate(sha256="", run_key=key, method="autonomous",
                             provenance_kind="ai_generated_autonomous", slug=slug,
                             version="1.0.0", release=f"{slug}-release", listing=slug,
                             role=IP.ANCHOR_SIDE_ROLE, stage="product_generation", attempt=1,
                             provider="flux3", technical_status="UNKNOWN",
                             outcome="provider_error", failure_categories=["provider_error"],
                             checks={"provider": {"status": "FAIL", "why": reason.split(
                                 "rendered: ", 1)[1]}},
                             created_at=when - timedelta(seconds=2)))
    return key


def test_4_stale_reference_blocks_are_recognised_and_nothing_else_is():
    assert IP.stale_references_block(LEGACY)
    assert IP.stale_references_block(
        "generator refused: GeneratorRefused: the certified-PDF page references handed in "
        "are not the pages of this release's certified PDF; refused")
    assert IP.stale_references_block(LEGACY.replace("GeneratorRefused", "StaleReferences"))
    for other in ("budget stop: per-gallery cap CA$2.00 reached",
                  "vessel side view could not be rendered: TransientError: flux-3-image 503",
                  "generator refused: GeneratorRefused: the product references do not name "
                  "one release",
                  "product fidelity FAIL after 3 attempts: bands"):
        assert not IP.stale_references_block(other), other


def test_5_a_blocked_run_is_redriven_once_per_reference_version_and_its_hold_released():
    from test_image_daily_ceiling_redrive import _db, _follow

    db = _db()
    key = _prod_blocked(db, "basket-stale", when=NOW - timedelta(hours=1))
    with db.session() as s:
        due = IP.redrive_due(s, None, now=NOW)
    assert due and due["kind"] == "stale_references" and due["run_key"] == key, due
    calls: list = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert [r["run_key"] for r in out["restarted"]] == [key], out
    assert len(calls) == 1 and calls[0][0]["stage"] == "product_generation", calls
    assert not calls[0][0].get("reverify"), calls
    run = IP.get_run(db, key)
    assert run["state"] != "blocked", run
    st = IP._stage_data(db, key)
    # the refused call sent nothing: its hold is gone and it is not a counted call
    assert "_pending_paid_call" not in st, st
    counts = IP._run_counts(db, key)
    assert counts["counted_calls"] == 0 and counts["unbilled_calls"] == 1, counts
    hist = st[IP.RESTART_KEY]["history"]
    assert hist[-1]["by"] == IP.STALE_REFS_REDRIVE_BY, hist
    assert hist[-1]["references_version"] == IP.references_version(), hist
    # blocked the same way again under the same reference version: not redriven twice
    from sqlalchemy import select

    from brambleloop.visual.image_records import ImageProductionRun
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        r.status, r.blocked_reason = "blocked", LEGACY
        r.updated_at = NOW - timedelta(hours=1)
    with db.session() as s:
        assert IP.redrive_due(s, None, now=NOW) is None
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert key not in [r["run_key"] for r in out["restarted"]], out
    assert len(calls) == 1


def test_6_a_hold_that_is_not_the_refused_call_is_never_released():
    """Only the hold of the refused call is released: a hold with a recorded receipt (a call
    that was sent) keeps the run blocked for review, exactly as before."""
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from brambleloop.visual.image_records import ImageProductionRun
    from test_image_daily_ceiling_redrive import _db, _follow

    db = _db()
    key = _prod_blocked(db, "basket-sent", when=NOW - timedelta(hours=1))
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        st = dict(r.stages)
        st["_pending_paid_call"] = {**st["_pending_paid_call"], "state": "receipt_recorded",
                                    "actual_cad": 0.14}
        r.stages = st
        flag_modified(r, "stages")
    calls: list = []
    IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert IP._stage_data(db, key)["_pending_paid_call"]["state"] == "receipt_recorded"


def test_7_a_new_stale_refusal_releases_its_hold_and_costs_no_call():
    """A refusal raised by the binding check (before any send) is not a paid call."""
    from brambleloop.creative import flux3_generator as FG
    from test_image_daily_ceiling_redrive import _db

    db = _db()
    from brambleloop.visual.image_records import ImageProductionRun
    key = IP.run_key("basket-new", "1.0.0", "basket-new-release")
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug="basket-new", version="1.0.0",
                                 release="basket-new-release", listing="basket-new",
                                 stage="product_generation", status="product_generation",
                                 stages={}))

    class Refusing:
        name, paid, max_cost_cad_per_call = "flux3", True, 0.14

        def generate(self, **kw):
            raise FG.StaleReferences("the product references handed in are not the bytes "
                                     "this release renders; refused")

    from brambleloop.visual import gallery as GL
    saved = GL.gates_now
    GL.gates_now = lambda db_, keys=(): {k: True for k in keys}
    try:
        out = IP._generate(db, key, Refusing(), slug="basket-new", version="1.0.0",
                           release="basket-new-release", role=IP.ANCHOR_SIDE_ROLE,
                           stage="product_generation", brief="side", refs=[], outfit=None,
                           laura=False, judges=None, plan_attempt=1, operation="op-1")
    finally:
        GL.gates_now = saved
    assert "StaleReferences" in out["provider_error"], out
    assert "_pending_paid_call" not in IP._stage_data(db, key)
    counts = IP._run_counts(db, key)
    assert counts["counted_calls"] == 0 and counts["unbilled_calls"] == 1, counts
    assert IP._attempts(db, key, IP.ANCHOR_SIDE_ROLE) == 0


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            traceback.print_exc()
            print(f"FAIL {t.__name__} {exc!r}")
    print(f"PASS: {failed} failing" if not failed else f"FAIL: {failed} failing")
    sys.exit(1 if failed else 0)
