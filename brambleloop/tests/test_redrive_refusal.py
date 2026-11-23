"""REDRIVE-REFUSAL: calls the provider never accepted do not spend a run's call, attempt or
restart budget, so a daily-ceiling stop restarts after the UTC reset.

Production 19i19 (2026-11-23 04:08Z): redrive_due read "daily_ceiling_reset" every hour and the
chain.successors sweep restarted nothing. The runs it was due for had spent their counters in
the 403 era (a rejected BFL key: refused on the submit, before any task id, never billed) and on
paid-gate refusals (refused before sending), and held an earlier FAILed candidate the stopped
repair was answering. `restartable` read that FAIL as "attempts were spent on a failure" and the
counters as spent; a refusal recorded nothing, so the run stayed "due" forever.

Billed (and uncertain) calls still count in full; spend and the money caps are untouched.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_redrive_refusal.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import io
import sys
import tempfile
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402
from brambleloop.visual import spend_plan  # noqa: E402
from brambleloop.visual.image_records import (ImageCandidate, ImageProductionRun,  # noqa: E402
                                              ensure_tables)

DAILY = ("budget stop: paid provider gate refused before sending (provider_daily_ceiling): "
         "the provider's daily ceiling is reached")
LEGACY_403 = ("GeneratorRefused: flux-3-image 403: {\"detail\":\"Not authenticated - "
              "Invalid Authentication\"}")
NOW = datetime.now(timezone.utc)
YESTERDAY = NOW - timedelta(days=1)


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='rr_')}/rr.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    ensure_tables(db)
    return db


def _cand(s, key, slug, *, role, at, billed, status="UNKNOWN", why=LEGACY_403):
    s.add(ImageCandidate(
        sha256=("ab" * 32) if billed else "", run_key=key, method="autonomous",
        provenance_kind="ai_generated_autonomous", slug=slug, version="1.0.0",
        release=f"{slug}-release", listing=slug, role=role, stage="product_generation",
        provider="flux-3-image", technical_status=status,
        outcome={"FAIL": "rejected"}.get(status, "unverified" if billed else "provider_error"),
        failure_categories=[] if billed else ["provider_error"],
        cost_cad=0.07 if billed else None,
        checks={} if billed else {"provider": {"status": "FAIL", "why": why}},
        created_at=at))


def _run(db, slug, *, epochs_billed=(False, False, False)):
    """A run blocked yesterday on the daily ceiling at 12 counted calls: 2 billed calls (one
    FAILed product frame the repair was answering), then three restarted epochs of 3, 3 and 4
    calls. An unbilled epoch's calls are 403s on the submit (and the last one ends with the
    gate's refusal); a billed epoch's calls were accepted and billed."""
    key = IP.run_key(slug, "1.0.0", f"{slug}-release")
    t0 = YESTERDAY - timedelta(hours=6)
    marks = [t0 + timedelta(hours=1), t0 + timedelta(hours=2), t0 + timedelta(hours=3)]
    history = [{"epoch": i + 1, "at": m.isoformat(), "by": "capability_redrive",
                "reason": "image_generation opened", "blocked_at": "product_generation",
                "blocked_reason": "image_generation gate closed", "resume_at":
                "product_generation", "reverify": False, "generation_calls": c,
                "spent_cad": 0.14}
               for i, (m, c) in enumerate(zip(marks, (2, 5, 8)))]
    with db.session() as s:
        s.add(ImageProductionRun(
            run_key=key, slug=slug, version="1.0.0", release=f"{slug}-release", listing=slug,
            stage="product_generation", status="blocked", blocked_reason=DAILY,
            stages={IP.RESTART_KEY: {"epoch": 3, "history": history}}, updated_at=YESTERDAY,
            attempts_exhausted=True, generation_calls=12, spent_cad=0.14))
        _cand(s, key, slug, role="hero_flat", at=t0, billed=True, status="FAIL")
        _cand(s, key, slug, role="hero_flat", at=t0 + timedelta(minutes=5), billed=True,
              status="FAIL")
        for i, (start, n) in enumerate(zip(marks, (3, 3, 3))):
            for j in range(n):
                _cand(s, key, slug, role="detail", at=start + timedelta(minutes=j + 1),
                      billed=epochs_billed[i])
    return key


def _follow(calls):
    def follow(inputs, key, *, session=None):
        calls.append((inputs, key))
        return object()
    return follow


def _counts(db, key):
    return IP._run_counts(db, key)


def test_403_era_unbilled_attempts_then_daily_reset_restarts():
    db = _db()
    key = _run(db, "hexagon-coaster-set")
    counts = _counts(db, key)
    # 9 submits refused with 403 + the gate's refusal that blocked the run: 10 unbilled.
    assert counts == {"counted_calls": 2, "restarts_spent": 0, "unbilled_calls": 10}, counts
    assert IP._attempts(db, key, "detail") == 0
    assert IP._attempts(db, key, "hero_flat") == 2
    got = IP.restartable(db, key)
    assert got["restartable"] is True, got
    calls = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert [r["run_key"] for r in out["restarted"]] == [key], out
    assert len(calls) == 1, calls
    run = IP.get_run(db, key)
    assert run["state"] != "blocked" and run["restarts"] == 4, run
    # nothing is reset: generation_calls keeps the audit count, spend is untouched
    assert run["generation_calls"] == 12 and run["spent_cad"] == 0.14, run
    # the call cap reads the counted calls: room for the remaining 10 of 12
    spend_plan.guard(IP._spend_plan(key, db), spent_cad=0.14, calls_made=_counts(db, key)[
        "counted_calls"], next_cost_cad=0.07)


def test_billed_calls_still_count():
    db = _db()
    key = _run(db, "market-basket-small", epochs_billed=(True, True, True))
    counts = _counts(db, key)
    # only the gate's refusal was unbilled; every accepted call counts
    assert counts == {"counted_calls": 11, "restarts_spent": 3, "unbilled_calls": 1}, counts
    assert IP._attempts(db, key, "detail") == 9
    got = IP.restartable(db, key)
    assert got["restartable"] is False and "already restarted 3" in got["why"], got
    calls = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert out["restarted"] == [] and calls == [], out
    # a refused daily redrive is judged once for the day: no longer reported as due
    with db.session() as s:
        assert IP.redrive_due(s, None) is None


def test_one_billed_epoch_spends_one_restart():
    db = _db()
    key = _run(db, "housewarming-key-basket", epochs_billed=(False, True, False))
    counts = _counts(db, key)
    assert counts["restarts_spent"] == 1 and counts["counted_calls"] == 5, counts
    assert IP.restartable(db, key)["restartable"] is True


def test_poll_errors_after_acceptance_still_count():
    db = _db()
    key = IP.run_key("poll-x", "1.0.0", "poll-x-release")
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug="poll-x", version="1.0.0",
                                 release="poll-x-release", listing="poll-x",
                                 stage="product_generation", status="blocked",
                                 blocked_reason="provider error", stages={},
                                 updated_at=NOW, generation_calls=1))
        _cand(s, key, "poll-x", role="detail", at=NOW, billed=False,
              why="TransientError: flux-3-image poll 403")
    assert _counts(db, key)["counted_calls"] == 1
    assert IP._attempts(db, key, "detail") == 1


def test_submit_4xx_is_marked_never_accepted():
    from brambleloop.gateway import images

    def opener(code):
        class O:
            def open(self, request, timeout=None):
                raise urllib.error.HTTPError(request.full_url, code, "x", {},
                                             io.BytesIO(b'{"detail":"no"}'))
        return lambda: O()

    seen = {}
    real = images._no_redirect
    try:
        for code in (401, 403, 422, 500):
            images._no_redirect = opener(code)
            try:
                images._post("https://api.us.bfl.ai/v1/x", {}, b"{}", label="flux-3-image",
                             timeout=1)
            except Exception as exc:  # noqa: BLE001
                try:
                    raise RuntimeError("wrapped") from exc
                except RuntimeError as outer:
                    seen[code] = IP.never_accepted_status(outer)
    finally:
        images._no_redirect = real
    assert seen == {401: 401, 403: 403, 422: 422, 500: None}, seen
    assert IP.candidate_unaccepted("provider_error", "", {
        IP.UNACCEPTED_KEY: {"accepted": False, "http_status": 422}})
    assert not IP.candidate_unaccepted("provider_error", "ab", {
        IP.UNACCEPTED_KEY: {"accepted": False}})
    assert not IP.candidate_unaccepted("rejected", "", {"provider": {"why": LEGACY_403}})


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                import traceback

                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
