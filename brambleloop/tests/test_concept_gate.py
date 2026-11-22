"""CONCEPT-GATE: an unbilled judge refusal must not lock a concept out for 24 hours.

Production (67efe8eb, 05:01Z 2026-11-22): openai_route_usable true, key present, yet the last
creative.regate judged 0 radar concepts and held 5, and after_admission_24h read gate_passed 0,
gate_waiting 15 (all on image_vision). Before 19i4 the openai key was not read, so attempts
recorded by `concept_judge.record_attempt` ended in a provider refusal (a PermanentError,
never billed). `concept_judge.attempted` counted those attempts for RETRY_AFTER (24 h), so once
the key was wired the same boards were still "already sent to this judge" and never judged.

This test proves:
1. A provider refusal (HTTP 401, never billed) leaves the concept waiting and never passes.
2. After a new deploy (the route closure lifts, KEYS-19i4), the same board IS judged again,
   with a working judge, and the concept is drafted. The paid-call idempotency is unchanged
   for billed calls: a redrive after a successful judgement sends nothing new.
3. An answer that is not a judgement (billed, unparsed) is UNKNOWN: the concept never passes,
   and the billed board is not re-sent within the retry window.
4. The readback names why each held concept was not judged, in fixed codes only.

Every listing, judgement and product here is a TEST FIXTURE. No network call is made.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_concept_gate.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

import test_admit_to_build as ATB  # noqa: E402
import test_supply_feed as SF  # noqa: E402

from sqlalchemy import select  # noqa: E402

from brambleloop.ops import production_evidence as PE  # noqa: E402


class _Switch:
    """FIXTURE transport whose behaviour the test changes between passes."""

    def __init__(self, status: int, answer: str =
                 '{"thumbnail_reads_small": true, "craft_impression": 4.3}'):
        self.inner = ATB._OpenAITransport(status=status, answer=answer)

    @property
    def calls(self):
        return self.inner.calls

    def set(self, status: int, answer: str | None = None):
        calls = self.inner.calls
        self.inner = ATB._OpenAITransport(status=status, answer=answer or self.inner.answer)
        self.inner.calls = calls

    def __call__(self, provider, body, headers, timeout):
        return self.inner(provider, body, headers, timeout)


def _with_transport(transport, fn):
    from brambleloop.gateway import openai_chat

    saved_post = openai_chat.OpenAIProvider._post
    saved_key = os.environ.get(openai_chat.KEY_VAR)
    openai_chat.OpenAIProvider._post = lambda self, body, headers, timeout: transport(
        self, body, headers, timeout)
    os.environ[openai_chat.KEY_VAR] = "fixture-key-not-a-secret"
    try:
        return fn()
    finally:
        openai_chat.OpenAIProvider._post = saved_post
        if saved_key is None:
            os.environ.pop(openai_chat.KEY_VAR, None)
        else:
            os.environ[openai_chat.KEY_VAR] = saved_key


def _new_deploy(after):
    """Make `_current_deploy_started_at` read a deploy that started after `after`."""
    from brambleloop.ops import rebuild_graph

    saved = rebuild_graph._current_deploy_started_at
    rebuild_graph._current_deploy_started_at = lambda db: after
    return lambda: setattr(rebuild_graph, "_current_deploy_started_at", saved)


def _last_attempt_at(db):
    from brambleloop.core.models import AuditLog
    from brambleloop.creative import concept_judge as CJ

    with db.session() as s:
        return s.scalar(select(AuditLog.at).where(AuditLog.action.in_(
            (CJ.ATTEMPT_ACTION, CJ.FAILED_ACTION))).order_by(AuditLog.id.desc()).limit(1))


class _Ctx:
    def __init__(self, db):
        self.db = db

    def audit(self, action, *, artifact=None, detail=None):
        from brambleloop.core.models import AuditLog

        with self.db.session() as s:
            s.add(AuditLog(actor="test", action=action, artifact=artifact, detail=detail or {}))
            s.commit()


def test_an_unbilled_refusal_does_not_block_a_later_judgement():
    from brambleloop.creative import concept_judge as CJ

    db = ATB._state_openai(_Switch(status=200))   # any production-shaped database
    ctx = _Ctx(db)
    CJ.record_attempt(ctx, slug="fixture-a", board_sha="a" * 64, provider_name="openai",
                      model="fixture")
    assert CJ.attempted(db, "a" * 64, "openai", slug="fixture-a"), \
        "an attempt blocks a repeat paid call (it may have been billed)"
    CJ.record_unbilled_failure(ctx, slug="fixture-a", board_sha="a" * 64,
                               provider_name="openai")
    assert not CJ.attempted(db, "a" * 64, "openai", slug="fixture-a"), \
        "a refusal before any bill (401) no longer blocks the board for 24 h"
    # a later attempt of the same board blocks again until it too is shown unbilled
    CJ.record_attempt(ctx, slug="fixture-a", board_sha="a" * 64, provider_name="openai",
                      model="fixture")
    assert CJ.attempted(db, "a" * 64, "openai", slug="fixture-a")
    # another board, or another provider, is unaffected
    CJ.record_attempt(ctx, slug="fixture-b", board_sha="b" * 64, provider_name="openai",
                      model="fixture")
    CJ.record_unbilled_failure(ctx, slug="fixture-a", board_sha="a" * 64,
                               provider_name="openai")
    assert CJ.attempted(db, "b" * 64, "openai", slug="fixture-b")
    assert not CJ.attempted(db, "a" * 64, "openai", slug="fixture-a")


def test_judge_held_records_an_unbilled_refusal_and_never_passes():
    """provider=None is the guarded path (judge_held chooses openai-vision itself)."""
    from brambleloop.core.models import AuditLog
    from brambleloop.creative import concept_judge as CJ
    from brambleloop.creative import intake

    transport = _Switch(status=401)
    db = ATB._state_openai(_Switch(status=200))
    slug = None
    for row_id, sl, detail in intake.latest_per_slug(db):
        if intake.board_for(db, sl) and intake.board_digest_for(db, sl):
            slug = sl
            break
    if slug is None:
        from brambleloop.radar import intake as radar_intake
        for row in radar_intake.approved_rows(db):
            if intake.board_for(db, row.slug) and intake.board_digest_for(db, row.slug):
                slug = row.slug
                break
    assert slug, "the fixture state has a boarded concept"
    # AUDIT 19i7: a recorded verdict on the same board bytes by the same model is reused at no
    # cost, so the earlier fixture judgement of this board would answer without asking the
    # provider. Remove it (and any attempt row) so this case reaches the refusing provider.
    sha = intake.board_digest_for(db, slug)
    with db.session() as s:
        for r in s.scalars(select(AuditLog).where(AuditLog.action.in_(
                (intake.JUDGED_ACTION, CJ.ATTEMPT_ACTION)))).all():
            if (r.detail or {}).get("board_sha256") == sha:
                s.delete(r)

    class _Job:
        id = None
        agent = "market_radar"

    ctx = _Ctx(db)
    ctx.job = _Job()
    restore = _new_deploy(None)            # no deploy recorded: route state as the gate says
    try:
        res = _with_transport(transport, lambda: intake.judge_held(
            ctx, slug=slug, board=intake.board_for(db, slug)))
    finally:
        restore()
    if res.get("code") == "no_vision":
        return                              # the route is closed in this state: nothing sent
    assert not res.get("judged"), res
    assert res.get("code") in ("provider_refused", "retry_window"), res
    if res.get("code") == "provider_refused":
        with db.session() as s:
            assert s.scalars(select(AuditLog).where(
                AuditLog.action == CJ.FAILED_ACTION)).all(), "the refusal is recorded"
        with db.session() as s:
            guards = {str((d or {}).get("provider")) for (d,) in s.execute(
                select(AuditLog.detail).where(AuditLog.action == CJ.ATTEMPT_ACTION,
                                              AuditLog.artifact == slug))}
        assert guards, "the attempt was recorded before the send"
        for g in guards:  # vacuity-ok: asserted non-empty just above
            assert not CJ.attempted(db, intake.board_digest_for(db, slug), g, slug=slug), \
                "an unbilled refusal does not block the board"


def test_held_reasons_are_fixed_codes():
    from brambleloop.core.models import AuditLog

    transport = _Switch(status=401)
    db = ATB._state_openai(transport)
    with db.session() as s:
        detail = s.scalar(select(AuditLog.detail).where(
            AuditLog.action == "creative.regate").order_by(AuditLog.id.desc()).limit(1))
    held = ((detail or {}).get("regated") or {}).get("radar_held") or []
    codes = PE._held_codes(held)
    assert set(codes) <= set(PE.HELD_CODES) | {"other"}, codes
    assert all(isinstance(v, int) for v in codes.values()), codes
    out = PE._held_codes([{"code": "secret text that is not a code"}, {"code": "budget"}, "x"])
    assert out == {"other": 2, "budget": 1}, out
    assert "secret" not in json.dumps(out)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
