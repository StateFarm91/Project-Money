"""AUDIT 19i7: the openai concept judge billed the same request twice in one regate job.

Production readback (b829caf7, 2026-11-22T05:40Z): `paid_call_dedupe.repeated_billed_requests`
was 1 -- effect openai.vision, job creative.regate, one request fingerprint billed twice.
Two causes, both in `creative.intake.judge_held`:

1. `regate_held` passes the openai provider it chose, and the once-per-board guard ran only
   when judge_held chose the provider itself. A passed provider skipped it entirely.
2. The guard was keyed per concept slug, so two held concepts sharing one board image sent
   the identical request (constant prompt, same bytes), which `paid_calls.guarded` counts as
   a second occurrence inside the job, billed again.

The fix: the guard runs for any openai provider, passed or chosen; it is keyed on the board
BYTES; and this model's recorded verdict on the same bytes is reused at no cost.

Every concept, board and provider here is a TEST FIXTURE; no network call is made.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_concept_judge_dedupe.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.creative import intake as I  # noqa: E402

BOARD_SHA = "f" * 64


class _Provider:
    """FIXTURE openai-vision provider: counts paid sends; never touches the network."""
    name = "openai"
    model = "fixture-vision-model"
    cost_per_1k_input_cad = 0.001
    cost_per_1k_output_cad = 0.002

    def __init__(self, answer='{"thumbnail_reads_small": true, "craft_impression": 4.1}'):
        self.sends, self.answer = 0, answer

    def see(self, system, prompt, images, max_tokens):
        self.sends += 1
        return SimpleNamespace(text=self.answer, input_tokens=900, output_tokens=30)


class _Ctx:
    def __init__(self, db):
        self.db = db
        self.job = SimpleNamespace(agent="market_radar", id=4242)

    def audit(self, action, *, artifact=None, detail=None, **_kw):
        from brambleloop.core.models import AuditLog
        with self.db.session() as s:
            s.add(AuditLog(actor="market_radar", action=action, artifact=artifact,
                           job_id=None, detail=detail or {}))


def _patched(fn):
    """Run `fn(ctx, provider)` with the board, bytes, budget and spend ledger as fixtures."""
    from brambleloop.creative import blinded
    from brambleloop.finance import spend_report
    from brambleloop.gateway import providers as gw

    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='cjdedupe-')}/t.sqlite")
    db.create_all()
    saved = (I.board_digest_for, blinded.resolve_image, gw.check_budget,
             gw.release_reservation, spend_report.record)
    I.board_digest_for = lambda _db, _slug: BOARD_SHA
    blinded.resolve_image = lambda _db, _ref: ("data:image/png;base64,AAAA", None)
    gw.check_budget = lambda *a, **k: {"reservation_id": None}
    gw.release_reservation = lambda *a, **k: None
    spend_report.record = lambda *a, **k: None
    try:
        provider = _Provider()
        return fn(_Ctx(db), provider), provider
    finally:
        (I.board_digest_for, blinded.resolve_image, gw.check_budget,
         gw.release_reservation, spend_report.record) = saved


def test_two_concepts_sharing_one_board_pay_once():
    def run(ctx, provider):
        first = I.judge_held(ctx, slug="fixture-concept-a", board="boards/a.png",
                             provider=provider)
        second = I.judge_held(ctx, slug="fixture-concept-b", board="boards/b.png",
                              provider=provider)
        return first, second
    (first, second), provider = _patched(run)
    assert first["judged"] and second["judged"], (first, second)
    assert provider.sends == 1, f"the identical request was sent {provider.sends} times"
    assert second["cost_cad"] == 0.0 and second.get("reused_from"), second
    assert (first["thumbnail_reads_small"], first["craft_impression"]) == \
        (second["thumbnail_reads_small"], second["craft_impression"])


def test_a_passed_provider_is_guarded_on_a_redrive():
    """The same concept asked twice (a redrive) with the provider passed in: one send."""
    def run(ctx, provider):
        I.judge_held(ctx, slug="fixture-concept-a", board="boards/a.png", provider=provider)
        return I.judge_held(ctx, slug="fixture-concept-a", board="boards/a.png",
                            provider=provider)
    again, provider = _patched(run)
    assert provider.sends == 1, provider.sends
    assert again["judged"], again


def test_a_failed_attempt_blocks_a_repeat_for_another_concept():
    """A refused answer records no judgement; the bytes were still sent, so a second concept
    showing them waits instead of paying again within the retry window."""
    def run(ctx, provider):
        provider.answer = "not json"
        first = I.judge_held(ctx, slug="fixture-concept-a", board="boards/a.png",
                             provider=provider)
        second = I.judge_held(ctx, slug="fixture-concept-b", board="boards/b.png",
                              provider=provider)
        return first, second
    (first, second), provider = _patched(run)
    assert not first["judged"] and not second["judged"], (first, second)
    assert provider.sends == 1, provider.sends
    assert "not sent again" in second["why"], second


def test_another_model_is_not_reused():
    """A verdict is reused only from the same model on the same bytes."""
    def run(ctx, provider):
        I.judge_held(ctx, slug="fixture-concept-a", board="boards/a.png", provider=provider)
        other = _Provider()
        other.model = "fixture-other-model"
        out = I._reuse_judgement(ctx, slug="fixture-concept-b", board="boards/b.png",
                                 board_sha=BOARD_SHA, model=other.model)
        return out
    out, _provider = _patched(run)
    assert out is None, out


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
