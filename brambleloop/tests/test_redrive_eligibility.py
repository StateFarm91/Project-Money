"""REDRIVE-ELIGIBILITY (19i28): why the IMAGE-FIDELITY-3 re-judgement never fired.

Production 19i27 (211745f9d, deployed ~11:50Z 2026-11-25; evidence 12:59Z): `chain.successors`
ran at 12:00:37Z and finished, yet the two hexagon-coaster-set@1.2.1 runs parked UNKNOWN at
`fidelity_gate` (`fidelity_unknowns` 5 frames, `coaster:palette` 18) were not restarted and
`redrive_due` read None. FLUX had CA$4.95 of its CA$5.00 day spent (3 provider_daily_ceiling
refusals) and 3 runs were `product_generation:budget:exhausted`.

Root cause, from the code and the evidence timeline (06:16Z `fidelity_unknown` due under 19i25;
07:24Z both runs `fidelity_gate:product_truth:exhausted`; 10:16Z both UNKNOWN again):

1. 19i25 re-drove them under `fidelity-judge-route/1` (restart 1; the repair loop then made
   frames 3-5). 19i26's rejudge redrive re-read their FAILed frames under `fidelity-judge/2`
   (restart 2, no generation) and they re-blocked UNKNOWN. The next hourly sweep then re-drove
   them AGAIN under `fidelity-judge/2` through the UNKNOWN redrive (restart 3): its "already
   re-driven" test read `fidelity_unknown_redrive` entries only, so the rejudge it had just made
   under the same verifier did not count. That restart could read nothing differently.
2. Three restarts is `MAX_RESTARTS`. Under 19i27, `redrive_due` skipped a run at the cap with a
   silent `continue` (None), and the sweep's restart was refused "already restarted 3 times
   (cap 3)", recorded only inside the run's own stages. Nothing in the evidence said so.

Not the cause (each reproduced here): the FLUX daily ceiling (a re-judgement generates
nothing and no generation ceiling is consulted); the legacy refusal hold under the old key
(it does not hold under `fidelity-checks/2`); the UNKNOWN reason prefix (unchanged by
IMAGE-FIDELITY-2); scheduler backoff (the sweep ran at 12:00Z).

Fix: a re-judgement under (judge version, check version) by EITHER fidelity redrive, or a run
whose every stored anchor frame already carries a verdict under those versions, is not
re-driven again (no restart is spent on a reading that cannot change); the vision route's own
daily ceiling (openai-vision CA$2.00) is read before a re-judgement restart and the sweep waits
for the UTC day when it cannot cover it; and `redrive_readback` puts every blocked run's
eligibility and a fixed-vocabulary refusal ("max_restarts", ...) in the evidence. MAX_RESTARTS,
the attempt cap, the call cap and every spend ceiling are unchanged: the two production runs at
the cap stay refused, visibly.

Every provider answer and paid-call row here is a TEST FIXTURE. There is no network.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_redrive_eligibility.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_image_fidelity_route as R  # noqa: E402  (its harness refuses the network)
import _paid_activation as paid  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.gateway import paid_provider_gate as G  # noqa: E402
from brambleloop.ops import production_evidence as PE  # noqa: E402
from brambleloop.visual import fidelity as F  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402
from brambleloop.visual.image_records import ImageCandidate, ImageProductionRun  # noqa: E402

COASTERS = "hexagon-coaster-set"
RELEASE = f"{COASTERS}-83b5db1f2cb4"
JUDGE2 = "fidelity-judge/2"
UNKNOWN_PALETTE = ("product fidelity cannot be verified: the fidelity verifier (visual.fidelity) "
                   "reads UNKNOWN on ['coaster:palette']. Unknown: ['product_truth']")
DAILY = ("budget stop: paid provider gate refused before sending (provider_daily_ceiling): "
         "flux-3-image has CA$4.9500 reserved or billed today against the owner's CA$5.00 "
         "daily ceiling; this call is CA$0.0700")
FORBIDDEN_TEXT = ("already restarted", "cannot be verified", "budget stop", "CA$")


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _fid(judge: str, check: str | None) -> dict:
    fid = {"status": "UNKNOWN", "judge_version": judge, "unknown": ["coaster:palette"],
           "checks": [{"check": "coaster:palette", "status": "UNKNOWN"}]}
    if check:
        fid["check_version"] = check
    return {"product_truth": {"status": "UNKNOWN", "fidelity": fid}}


def _hex_run(db, *, route: bool, history: list[dict], frames: int = 5,
             judge: str = JUDGE2, check: str | None = None, calls: int = 5,
             spent: float = 0.35, extra: dict | None = None) -> str:
    """A hexagon-coaster run parked UNKNOWN at fidelity_gate, as production 19i27 holds it."""
    key = IP.run_key(COASTERS, "1.2.1", RELEASE, route=IP.SP.FLUX_ROUTE if route else "")
    stages = {IP.RESTART_KEY: {"epoch": len(history), "history": history}} if history else {}
    stages.update(extra or {})
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug=COASTERS, version="1.2.1", release=RELEASE,
                                 listing=COASTERS, stage="fidelity_gate", status="blocked",
                                 blocked_reason=UNKNOWN_PALETTE, stages=stages,
                                 generation_calls=calls, spent_cad=spent,
                                 attempts_exhausted=False))
        for i in range(frames):
            s.add(ImageCandidate(sha256=f"{(i + 1) + (100 if route else 0):064x}", run_key=key,
                                 method="autonomous", provenance_kind="ai_generated_autonomous",
                                 slug=COASTERS, version="1.2.1", release=RELEASE,
                                 listing=COASTERS, role=IP.ANCHOR_ROLE,
                                 stage="product_generation", attempt=i + 1,
                                 checks=_fid(judge, check), technical_status="UNKNOWN",
                                 outcome="unverified"))
    return key


def _h(epoch: int, by: str, at: str, calls: int, **kw) -> dict:
    return {"epoch": epoch, "by": by, "at": at, "reason": "fixture", "generation_calls": calls,
            "spent_cad": 0.0, "blocked_reason": kw.pop("blocked_reason", UNKNOWN_PALETTE), **kw}


def _production_history(day: str) -> list[dict]:
    """19i25 UNKNOWN redrive (then repairs made frames 3-5), 19i26 rejudge, and 19i26's
    duplicate UNKNOWN redrive under the same judge: three restarts, MAX_RESTARTS."""
    return [_h(1, IP.FIDELITY_REDRIVE_BY, f"{day}T06:10:00+00:00", 2,
               judge_version="fidelity-judge-route/1", reverify=True),
            _h(2, IP.FIDELITY_REJUDGE_BY, f"{day}T09:00:40+00:00", 5,
               judge_version=JUDGE2, reverify=True,
               blocked_reason="product fidelity FAIL after 3 attempts: ['craft_texture']"),
            _h(3, IP.FIDELITY_REDRIVE_BY, f"{day}T10:00:40+00:00", 5,
               judge_version=JUDGE2, reverify=True)]


def _flux_ceiling_hit(db):
    """FLUX activated at CA$5.00/day with CA$4.95 billed today: the 12:59Z state."""
    paid.activate(db, "flux-3-image", G.GENERATION, daily=5.0, monthly=20.0, per_gallery=2.5)
    _bill(db, "flux-3-image", G.GENERATION, [0.99] * 5)


def _bill(db, provider: str, scope: str, amounts: list[float]):
    from brambleloop.gateway.paid_provider_gate import PaidProviderActivation, PaidProviderCall

    with db.session() as s:
        act = s.scalar(select(PaidProviderActivation).where(
            PaidProviderActivation.provider == provider,
            PaidProviderActivation.scope == scope).order_by(PaidProviderActivation.id.desc()))
        for i, amt in enumerate(amounts):
            s.add(PaidProviderCall(activation_id=act.id, provider=provider, scope=scope,
                                   gallery="shared", run_key="fixture", idem_key=f"fx-{provider}-{i}",
                                   fingerprint="fixture", purpose="fixture", estimate_cad=amt,
                                   actual_cad=amt, status=G.BILLED, at=_now_utc(),
                                   settled_at=_now_utc()))


def _evidence_runs(db) -> dict:
    return PE._vp_runs(db)["redrive_eligibility"]


def _vocabulary_only(ev: dict):
    text = json.dumps(ev)
    for bad in FORBIDDEN_TEXT:
        assert bad not in text, (bad, text)
    for k, v in ev["runs"].items():
        assert set(v) == {"kind", "eligible", "refused", "restarts_spent", "max_restarts"}, v
        assert v["kind"] in IP.REDRIVE_KINDS, v
        assert v["refused"] is None or v["refused"] in IP.REDRIVE_REFUSALS, v


# ---- 1. production 19i27, reproduced --------------------------------------------------------

def test_1_production_state_both_runs_sit_at_max_restarts_and_the_readback_says_so():
    db = R._db()
    R._production_vision(db)
    _flux_ceiling_hit(db)
    day = str(_now_utc().date())
    hist = _production_history(day)
    a = _hex_run(db, route=True, history=hist)
    # the second run: the 19i26 sweep's refusal recorded under the OLD key (no check version)
    b = _hex_run(db, route=False, history=hist, extra={IP.FIDELITY_REDRIVE_KEY: {
        "judge_version": JUDGE2, "day": None, "why": "already restarted 3 times (cap 3)",
        "at": f"{day}T11:00:41+00:00"}})
    with db.session() as s:
        for key in (a, b):
            r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
            assert IP.restarts_spent(s, r) == IP.MAX_RESTARTS, "reverify epochs count"
    # the state 19i27 read: nothing due, and nothing fires
    assert R._due(db) is None
    calls = []
    out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
    assert calls == [] and out["restarted"] == [], out
    whys = {r["run_key"]: r["why"] for r in out["refused"]}
    assert set(whys) == {a, b} and all("cap 3" in w for w in whys.values()), out
    for key in (a, b):
        row = R._row(db, key)
        assert row["status"] == "blocked" and row["calls"] == 5, "no cap is reset or raised"
    # now visible: per run key, the cap is named; counts in a fixed vocabulary
    ev = _evidence_runs(db)
    assert ev["readable"] is True, ev
    for key in (a, b):
        v = ev["runs"][key]
        assert v == {"kind": "fidelity_unknown", "eligible": False, "refused": "max_restarts",
                     "restarts_spent": 3, "max_restarts": 3}, v
    assert ev["counts"]["at_max_restarts"] == 2 and ev["counts"]["eligible"] == 0, ev
    assert ev["counts"]["by_refusal"] == {"max_restarts": 2}, ev
    _vocabulary_only(ev)


def test_2_the_third_restart_was_a_duplicate_judgement_and_is_no_longer_made():
    """The 19i26 step that spent the third restart: a run the rejudge redrive had just re-read
    under fidelity-judge/2 re-blocked UNKNOWN; the UNKNOWN redrive re-drove it again under the
    same verifier. Under the fix, a re-judgement under (judge, checks) by either redrive counts."""
    db = R._db()
    R._production_vision(db)
    day = str(_now_utc().date())
    hist = _production_history(day)[:2]
    # 19i26 shape: the rejudge entry names no check version; the frames were judged by checks/1
    saved = IP.fidelity_check_version
    IP.fidelity_check_version = lambda: IP.LEGACY_CHECK_VERSION   # replay the 19i26 world
    try:
        key = _hex_run(db, route=True, history=hist, judge=JUDGE2, check=None)
        assert R._due(db) is None, "already re-judged under (judge/2, checks/1)"
        calls = []
        out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
        assert calls == [] and out["restarted"] == [], out
        assert any("already re-driven" in r["why"] for r in out["refused"]), out
    finally:
        IP.fidelity_check_version = saved
    row = R._row(db, key)
    assert row["stages"][IP.RESTART_KEY]["epoch"] == 2, "no restart spent on the same reading"
    # under 19i27's check version the same run IS due once: the reading can change
    assert (R._due(db) or {}).get("kind") == "fidelity_unknown"


def test_3_frames_already_judged_under_the_current_versions_spend_no_restart():
    db = R._db()
    R._production_vision(db)
    day = str(_now_utc().date())
    key = _hex_run(db, route=True, history=_production_history(day)[:1],
                   check=F.FIDELITY_CHECK_VERSION)
    assert R._due(db) is None
    with db.session() as s:
        rb = IP.redrive_readback(s)
    assert rb["runs"][key]["refused"] == "already_judged_now", rb
    calls = []
    out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
    assert calls == [] and out["restarted"] == [], out
    rec = R._row(db, key)["stages"][IP.FIDELITY_REDRIVE_KEY]
    assert rec["check_version"] == F.FIDELITY_CHECK_VERSION and rec["day"] is None, rec
    assert R._row(db, key)["stages"][IP.RESTART_KEY]["epoch"] == 1


def test_4_under_the_cap_the_flux_ceiling_and_the_old_key_do_not_hold_it():
    """Two restarts spent (19i25 UNKNOWN redrive, 19i26 rejudge), the FLUX daily ceiling hit,
    and a refusal recorded today under the old key: the checks/2 re-judgement fires once,
    generates nothing and leaves calls and spend as they were."""
    db = R._db()
    R._production_vision(db)
    _flux_ceiling_hit(db)
    day = str(_now_utc().date())
    key = _hex_run(db, route=True, history=_production_history(day)[:2], extra={
        IP.FIDELITY_REDRIVE_KEY: {"judge_version": JUDGE2, "day": day,
                                  "why": "fixture refusal under the old key"}})
    assert G.daily_headroom_cad(db, "flux-3-image", G.GENERATION) < 0.07, "FLUX is spent"
    with db.session() as s:
        rb = IP.redrive_readback(s)
    assert rb["runs"][key]["eligible"] is True and rb["runs"][key]["refused"] is None, rb
    assert R._due(db)["kind"] == "fidelity_unknown"
    calls = []
    out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
    assert [r["run_key"] for r in out["restarted"]] == [key], out
    assert len(calls) == 1 and calls[0][0]["stage"] == "fidelity_gate" \
        and calls[0][0]["reverify"] is True, calls
    row = R._row(db, key)
    assert row["calls"] == 5 and abs(row["spent"] - 0.35) < 1e-9, "nothing generated"
    hist = row["stages"][IP.RESTART_KEY]["history"][-1]
    assert hist["check_version"] == F.FIDELITY_CHECK_VERSION, hist
    R._reblock(db, key)
    with db.session() as s:
        assert IP.redrive_readback(s)["runs"][key]["refused"] == "max_restarts"
    assert R._due(db) is None


def test_5_the_vision_routes_own_daily_ceiling_is_respected():
    """openai-vision CA$2.00/day with CA$1.9999 billed: the sweep waits for the UTC day (no
    restart spent on a reading that would come back UNKNOWN); the hold is read back."""
    db = R._db()
    R._production_vision(db)
    _bill(db, G.OPENAI_VISION, G.VISION, [0.9999, 1.0])
    day = str(_now_utc().date())
    key = _hex_run(db, route=True, history=_production_history(day)[:1])
    ok, why = IP._vision_headroom(db, 1)
    assert not ok and "openai-vision daily ceiling" in why, why
    calls = []
    out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
    assert calls == [] and [w["run_key"] for w in out["waiting"]] == [key], out
    rec = R._row(db, key)["stages"][IP.FIDELITY_REDRIVE_KEY]
    assert rec["day"] == day, "held for today only"
    assert R._row(db, key)["stages"][IP.RESTART_KEY]["epoch"] == 1
    assert R._due(db) is None
    with db.session() as s:
        assert IP.redrive_readback(s)["runs"][key]["refused"] == "refusal_held"
    # the hold is for the UTC day: tomorrow it is due again
    saved = IP._now
    IP._now = lambda: saved() + timedelta(days=1)
    try:
        assert (R._due(db) or {}).get("kind") == "fidelity_unknown"
    finally:
        IP._now = saved


def test_6_rejudge_records_its_check_version_and_waits_on_vision_headroom():
    db = R._db()
    R._production_vision(db)
    _bill(db, G.OPENAI_VISION, G.VISION, [1.9999])
    key = R._blocked(db, "basket-fail", reason="product fidelity FAIL after 3 attempts: x",
                     anchor_status="FAIL")
    with db.session() as s:
        c = s.scalar(select(ImageCandidate).where(ImageCandidate.run_key == key))
        c.checks = {"product_truth": {"status": "FAIL", "fidelity": {
            "status": "FAIL", "judge_version": "fidelity-judge-route/1",
            "failed": ["craft_texture"]}}}
    assert IP.rejudge_candidate_ids(db, key), "a frame the current judge would re-read"
    calls = []
    out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
    assert calls == [] and [w["run_key"] for w in out["waiting"]] == [key], out
    rec = R._row(db, key)["stages"][IP.FIDELITY_REJUDGE_KEY]
    assert rec["day"] == str(_now_utc().date()) and "daily ceiling" in rec["why"], rec
    # with headroom, the rejudge restart records (judge, checks), which the UNKNOWN redrive reads
    db2 = R._db()
    R._production_vision(db2)
    key2 = R._blocked(db2, "basket-fail", reason="product fidelity FAIL after 3 attempts: x",
                      anchor_status="FAIL")
    with db2.session() as s:
        c = s.scalar(select(ImageCandidate).where(ImageCandidate.run_key == key2))
        c.checks = {"product_truth": {"status": "FAIL", "fidelity": {
            "status": "FAIL", "judge_version": "fidelity-judge-route/1",
            "failed": ["craft_texture"]}}}
    out = IP.redrive_capability_blocked(db2, follow=R._follow(calls))
    assert [r["run_key"] for r in out["restarted"]] == [key2], out
    hist = R._row(db2, key2)["stages"][IP.RESTART_KEY]["history"][-1]
    assert hist["by"] == IP.FIDELITY_REJUDGE_BY and hist["check_version"] == \
        F.FIDELITY_CHECK_VERSION, hist
    with db2.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key2))
        assert IP._fidelity_redriven(dict(r.stages), F.FIDELITY_JUDGE_VERSION)


# ---- 2. the three product_generation:budget:exhausted runs ----------------------------------

T0 = datetime(2026, 11, 25, 12, 59, 22, tzinfo=timezone.utc)


def _daily_run(db, slug: str, *, history: list[dict], calls: int, legacy_403: list[datetime],
               blocked_at: datetime) -> str:
    key = IP.run_key(slug, "1.3.0", f"{slug}-release", route=IP.SP.FLUX_ROUTE)
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug=slug, version="1.3.0",
                                 release=f"{slug}-release", listing=slug,
                                 stage="product_generation", status="blocked",
                                 blocked_reason=DAILY, generation_calls=calls, spent_cad=0.42,
                                 attempts_exhausted=True, updated_at=blocked_at,
                                 stages={IP.RESTART_KEY: {"epoch": len(history),
                                                          "history": history}}
                                 if history else {}))
        for i, at in enumerate(legacy_403):
            s.add(ImageCandidate(sha256="", run_key=key, method="autonomous",
                                 provenance_kind="ai_generated_autonomous", slug=slug,
                                 version="1.3.0", release=f"{slug}-release", listing=slug,
                                 role=IP.ANCHOR_ROLE, stage="product_generation", attempt=i + 1,
                                 provider="flux-3-image", technical_status="UNKNOWN",
                                 outcome="provider_error", failure_categories=["provider_error"],
                                 created_at=at, checks={"provider": {
                                     "status": "FAIL", "why": "TransientError: flux-3-image 403: "
                                                              "{\"detail\":\"not_authenticated\"}"}}))
    return key


def test_7_daily_ceiling_runs_restart_after_midnight_and_refused_calls_burn_no_restart():
    db = R._db()
    d0 = T0 - timedelta(days=3)
    # 403 era: two submits refused before a task id; then a daily-ceiling refusal; then a
    # restart that billed three calls and met the ceiling again today
    hist = [_h(1, IP.PROVIDER_REDRIVE_BY, _iso(d0 + timedelta(hours=1)), 2,
               blocked_reason="provider error: TransientError: flux-3-image 503"),
            _h(2, IP.DAILY_REDRIVE_BY, _iso(d0 + timedelta(days=1, hours=1)), 4,
               blocked_reason="provider error: TransientError: flux-3-image 403: x"),
            _h(3, IP.DAILY_REDRIVE_BY, _iso(d0 + timedelta(days=2, hours=1)), 5,
               blocked_reason=DAILY)]
    four03 = [d0 + timedelta(hours=1, minutes=5), d0 + timedelta(hours=1, minutes=6)]
    blocked = T0 - timedelta(minutes=30)
    d1 = _daily_run(db, "market-basket-small", history=hist, calls=9, legacy_403=four03,
                    blocked_at=blocked)
    billed = [_h(i + 1, IP.DAILY_REDRIVE_BY, _iso(d0 + timedelta(hours=i)), 2 + 3 * i,
                 blocked_reason=DAILY) for i in range(3)]
    d2 = _daily_run(db, "housewarming-key-basket", history=billed, calls=12, legacy_403=[],
                    blocked_at=blocked)
    d3 = _daily_run(db, "hexagon-coaster-set", history=[], calls=3, legacy_403=[],
                    blocked_at=blocked)
    with db.session() as s:
        spent = {r.run_key: IP.restarts_spent(s, r) for r in s.scalars(
            select(ImageProductionRun))}
    assert spent[d1] == 1, ("the 403 epoch and the refused daily epoch are free", spent)
    assert spent[d2] == 3 and spent[d3] == 0, spent
    assert IP._attempts(db, d1, IP.ANCHOR_ROLE) == 0, "a never-accepted call is no attempt"
    saved = IP._now
    try:
        IP._now = lambda: T0
        with db.session() as s:
            assert IP.redrive_due(s, None) is None
            rb = IP.redrive_readback(s)
        assert rb["runs"][d1]["refused"] == "waiting_daily_reset", rb
        assert rb["runs"][d3]["refused"] == "waiting_daily_reset", rb
        assert rb["runs"][d2]["refused"] == "max_restarts", "visible, not skipped"
        calls = []
        out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
        assert calls == [] and out["restarted"] == [], out
        # after 00:00Z the reset is due, and the sweep restarts the two under the cap
        IP._now = lambda: datetime(2026, 11, 26, 0, 30, tzinfo=timezone.utc)
        with db.session() as s:
            due = IP.redrive_due(s, T0)
            rb = IP.redrive_readback(s)
        assert due and due["kind"] == "daily_ceiling_reset" and \
            due["at"] == "2026-11-26T00:00:00+00:00", due
        assert rb["runs"][d1]["eligible"] and rb["runs"][d3]["eligible"], rb
        assert rb["runs"][d2]["refused"] == "max_restarts", rb
        out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
        assert sorted(r["run_key"] for r in out["restarted"]) == sorted([d1, d3]), out
        assert any(r["run_key"] == d2 and "cap 3" in r["why"] for r in out["refused"]), out
        for key, n in ((d1, 9), (d3, 3)):
            row = R._row(db, key)
            assert row["calls"] == n and abs(row["spent"] - 0.42) < 1e-9, "nothing reset"
            assert row["stages"][IP.RESTART_KEY]["history"][-1]["by"] == IP.DAILY_REDRIVE_BY
        with db.session() as s:
            assert IP.redrive_due(s, T0) is None, "once per UTC day"
    finally:
        IP._now = saved


def test_8_the_readback_is_fixed_vocabulary_and_unreadable_is_not_empty():
    db = R._db()
    ev = _evidence_runs(db)
    assert ev == {"readable": True, "runs": {}, "counts": {
        "blocked": 0, "eligible": 0, "at_max_restarts": 0, "by_refusal": {}}}, ev
    saved = IP.redrive_readback
    IP.redrive_readback = lambda *_a, **_k: 1 / 0
    try:
        ev = _evidence_runs(db)
    finally:
        IP.redrive_readback = saved
    assert ev == {"readable": False, "error_class": "ZeroDivisionError"}, ev
    # an experiment key is one-shot and its key is not echoed
    R._production_vision(db)
    xp = R._blocked(db, "coaster-xp", ns="xp1")
    ev = _evidence_runs(db)
    assert xp not in ev["runs"] and list(ev["runs"].values())[0]["refused"] == \
        "experiment_one_shot", ev
    _vocabulary_only(ev)


if __name__ == "__main__":
    failed = 0
    tests = [v for k, v in sorted(globals().items(), key=lambda kv: (
        int(kv[0].split("_")[1]) if kv[0].startswith("test_") else 0, kv[0]))
        if k.startswith("test_") and callable(v)]
    for fn in tests:
        try:
            fn()
            print(f"OK   {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            traceback.print_exc()
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
