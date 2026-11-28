"""D-RESTART-PER-METHOD (19i29): MAX_RESTARTS binds per generation-method version; the coaster's
UNKNOWN reverify no longer waits on a hold recorded under a cap that no longer binds.

Production 19i28 (563da3bed), evidence 2026-11-25T16:37Z, `galleries.redrive_eligibility`:

- market-basket-small@1.3.0 (main and ~gallery) and housewarming-key-basket@0.1.0~gallery:
  `daily_ceiling_reset`, refused `max_restarts`, 3/3. Their restarts were spent by system
  recovery after code fixes (stale references 19i24, the fidelity route 19i25, the method
  redrive / rejudge 19i26, the daily reset), all under generation methods older than the one
  production now runs (prompt builder 2.4.0, pattern-refs 3.1.6, since 19i27 at 11:42Z).
  Problem A: the cap counted them all, so the runs were dead for good.
- hexagon-coaster-set@1.2.1: `fidelity_unknown`, refused `refusal_held`, 2/3. Problem B: the
  hold was recorded by 19i27's 12:00Z sweep, whose restart was refused "already restarted 3
  times (cap 3)" under (fidelity-judge/2, fidelity-checks/2), a hold for good. 19i28's
  duplicate credit then counted 2, but the hold outlived the count it was made from (19i28's
  own test recorded that legacy hold WITHOUT a check version, so it never held there). It was
  not the openai-vision headroom: CA$0.7635 of CA$2.00 spent (unchanged 12:59Z -> 16:37Z, 46
  billed calls), and one re-judgement reserves about CA$0.022.
- hexagon-coaster-set@1.2.1~gallery: `method_redrive`, eligible, 2/3. With FLUX at CA$4.9539
  of its CA$5.00 day it would have spent its first restart under the current method on a call
  the daily ceiling refuses, while its sibling was being re-judged.

Fix: `restart_counts` attributes each restart to the generation-method version it was made
under (stamped from 19i29; older entries by their method redrive's version or the production
timeline) and only the current version's count toward MAX_RESTARTS; the readback shows the
current count and the total. A refusal recorded because MAX_RESTARTS bound holds only while
the cap binds; every other hold is unchanged (a vision headroom shortfall still waits for
00:00Z). A method redrive waits (day-scoped, no restart spent) while the generation provider's
daily ceiling cannot cover one attempt, and while a sibling run of its release is re-judged.
MAX_RESTARTS (3), the attempt cap, the call cap and every spend ceiling are unchanged.

Every provider answer and paid-call row here is a TEST FIXTURE. There is no network.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_restart_per_method.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
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

# Production's method now (19i27 onward) and the two before it.
PROD = "flux3-prompt-builder/2.4.0|pattern-refs/3.1.6|pdf-page-refs/1.0.0|owner_two_step/1"
M_19I26 = "flux3-prompt-builder/2.4.0|pattern-refs/3.1.5|pdf-page-refs/1.0.0|owner_two_step/1"
OLD_STAMP = {"version": "flux3-prompt-builder/2.3.0|pattern-refs/3.1.4|pdf-page-refs/1.0.0|"
                        "owner_two_step/1"}
JUDGE2 = "fidelity-judge/2"
CHECKS2 = "fidelity-checks/2"
DAILY = ("budget stop: paid provider gate refused before sending (provider_daily_ceiling): "
         "flux-3-image has CA$4.9539 reserved or billed today against the owner's CA$5.00 "
         "daily ceiling; this call is CA$0.0700")
UNKNOWN = ("product fidelity cannot be verified: the fidelity verifier (visual.fidelity) "
           "reads UNKNOWN on ['coaster:palette']. Unknown: ['product_truth']")
FAIL = "product fidelity FAIL after 3 attempts: {'product_truth': 'wrong bands'}"
# the ~gallery's block: a FAILed anchor under an older method, with no frame the current judge
# reads differently (the evidence's kind `method_redrive`)
GALLERY_BLOCK = "fidelity_gate: product_truth FAIL on the anchor under an older method"
CAP_WHY_19I27 = "already restarted 3 times (cap 3)"
LEGACY_DAY = "2026-11-25"     # the production history's own timestamps (unstamped entries)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today_blocked() -> datetime:
    """A moment earlier today (UTC), so 'blocked today' holds whenever the suite runs."""
    now = _now()
    return max(now.replace(hour=0, minute=1, second=0, microsecond=0), now - timedelta(hours=4))


def _next_day(at: datetime) -> datetime:
    return datetime(at.year, at.month, at.day, 0, 30, tzinfo=timezone.utc) + timedelta(days=1)


class _Clock:
    """Patch `image_production._now` (the sweep's clock) for a block."""

    def __init__(self, at: datetime):
        self.at, self.saved = at, None

    def __enter__(self):
        self.saved = IP._now
        IP._now = lambda: self.at
        return self

    def __exit__(self, *exc):
        IP._now = self.saved


class _Method:
    """Pin the current generation-method version to production's (19i27/19i28)."""

    def __init__(self, version: str = PROD):
        self.version, self.saved = version, None

    def __enter__(self):
        self.saved = IP.current_method_version
        IP.current_method_version = lambda: self.version
        return self

    def __exit__(self, *exc):
        IP.current_method_version = self.saved


def _h(epoch: int, by: str, at: str, calls: int, **kw) -> dict:
    """An entry as written before 19i29: no `generation_method` stamp."""
    return {"epoch": epoch, "by": by, "at": at, "reason": "fixture", "generation_calls": calls,
            "spent_cad": 0.0, "blocked_reason": kw.pop("blocked_reason", DAILY), **kw}


def _basket_history() -> list[dict]:
    """Three restarts spent by recovery after code fixes, all before 19i27 (11:42Z): the
    daily reset at 00:40Z, the stale-references redrive (19i24) and the method redrive (19i26).
    Each billed calls, so each counts under its own method version."""
    return [_h(1, IP.DAILY_REDRIVE_BY, f"{LEGACY_DAY}T00:40:00+00:00", 2),
            _h(2, IP.STALE_REFS_REDRIVE_BY, f"{LEGACY_DAY}T05:10:00+00:00", 4,
               blocked_reason="vessel side view could not be rendered: GeneratorRefused: the "
                              "product references handed in are not the bytes this release "
                              "renders; refused"),
            _h(3, IP.METHOD_REDRIVE_BY, f"{LEGACY_DAY}T09:30:00+00:00", 6,
               method_version=M_19I26, blocked_reason=FAIL)]


def _basket(db, slug: str, version: str, *, route: bool, history: list[dict],
            blocked_at: datetime, calls: int = 9) -> str:
    key = IP.run_key(slug, version, f"{slug}-release", route=IP.SP.FLUX_ROUTE if route else "")
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug=slug, version=version,
                                 release=f"{slug}-release", listing=slug,
                                 stage="product_generation", status="blocked",
                                 blocked_reason=DAILY, generation_calls=calls, spent_cad=0.63,
                                 attempts_exhausted=True, updated_at=blocked_at,
                                 stages={IP.RESTART_KEY: {"epoch": len(history),
                                                          "history": history}}))
    return key


def _fid(judge: str, check: str) -> dict:
    return {"product_truth": {"status": "UNKNOWN", "fidelity": {
        "status": "UNKNOWN", "judge_version": judge, "check_version": check,
        "unknown": ["coaster:palette"],
        "checks": [{"check": "coaster:palette", "status": "UNKNOWN"}]}}}


def _coaster_history() -> list[dict]:
    """19i25 UNKNOWN redrive, 19i26 rejudge, and 19i26's duplicate UNKNOWN redrive."""
    return [_h(1, IP.FIDELITY_REDRIVE_BY, f"{LEGACY_DAY}T06:10:00+00:00", 2,
               judge_version="fidelity-judge-route/1", reverify=True, blocked_reason=UNKNOWN),
            _h(2, IP.FIDELITY_REJUDGE_BY, f"{LEGACY_DAY}T09:00:40+00:00", 5,
               judge_version=JUDGE2, reverify=True, blocked_reason=FAIL),
            _h(3, IP.FIDELITY_REDRIVE_BY, f"{LEGACY_DAY}T10:00:40+00:00", 5,
               judge_version=JUDGE2, reverify=True, blocked_reason=UNKNOWN)]


def _coaster(db, *, hold: dict | None, blocked_at: datetime) -> str:
    """hexagon-coaster-set@1.2.1 (main route) parked UNKNOWN at fidelity_gate, with the hold
    19i27's 12:00Z sweep recorded when MAX_RESTARTS refused its checks/2 reverify."""
    key = IP.run_key("hexagon-coaster-set", "1.2.1", "hexagon-coaster-set-83b5db1f2cb4")
    stages = {IP.RESTART_KEY: {"epoch": 3, "history": _coaster_history()}}
    if hold is not None:
        stages[IP.FIDELITY_REDRIVE_KEY] = hold
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug="hexagon-coaster-set", version="1.2.1",
                                 release="hexagon-coaster-set-83b5db1f2cb4",
                                 listing="hexagon-coaster-set", stage="fidelity_gate",
                                 status="blocked", blocked_reason=UNKNOWN, stages=stages,
                                 generation_calls=5, spent_cad=0.35, attempts_exhausted=False,
                                 updated_at=blocked_at))
        for i in range(5):
            s.add(ImageCandidate(sha256=f"{i + 1:064x}", run_key=key, method="autonomous",
                                 provenance_kind="ai_generated_autonomous",
                                 slug="hexagon-coaster-set", version="1.2.1",
                                 release="hexagon-coaster-set-83b5db1f2cb4",
                                 listing="hexagon-coaster-set", role=IP.ANCHOR_ROLE,
                                 stage="product_generation", attempt=i + 1,
                                 checks=_fid(JUDGE2, "fidelity-checks/1"),
                                 technical_status="UNKNOWN", outcome="unverified"))
    return key


def _coaster_gallery(db, *, blocked_at: datetime) -> str:
    """hexagon-coaster-set@1.2.1~gallery: blocked at fidelity_gate on FAILs made under an older
    method (the method redrive owns it), 2 restarts spent under older methods."""
    key = IP.run_key("hexagon-coaster-set", "1.2.1", "hexagon-coaster-set-83b5db1f2cb4",
                     route=IP.SP.FLUX_ROUTE)
    hist = [_h(1, IP.FIDELITY_REDRIVE_BY, f"{LEGACY_DAY}T06:10:00+00:00", 2,
               judge_version="fidelity-judge-route/1", reverify=True, blocked_reason=UNKNOWN),
            _h(2, IP.FIDELITY_REJUDGE_BY, f"{LEGACY_DAY}T09:00:40+00:00", 3,
               judge_version=JUDGE2, reverify=True, blocked_reason=FAIL)]
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug="hexagon-coaster-set", version="1.2.1",
                                 release="hexagon-coaster-set-83b5db1f2cb4",
                                 listing="hexagon-coaster-set", stage="fidelity_gate",
                                 status="blocked", blocked_reason=GALLERY_BLOCK,
                                 stages={IP.RESTART_KEY: {"epoch": 2, "history": hist}},
                                 generation_calls=3, spent_cad=0.21, attempts_exhausted=True,
                                 updated_at=blocked_at))
        for i in range(3):
            s.add(ImageCandidate(sha256=f"{i + 50:064x}", run_key=key, method="autonomous",
                                 provenance_kind="ai_generated_autonomous",
                                 slug="hexagon-coaster-set", version="1.2.1",
                                 release="hexagon-coaster-set-83b5db1f2cb4",
                                 listing="hexagon-coaster-set", role=IP.ANCHOR_ROLE,
                                 stage="product_generation", attempt=i + 1,
                                 checks={"product_truth": {"status": "FAIL",
                                                           "why": "bands disagree"},
                                         IP.METHOD_KEY: dict(OLD_STAMP)},
                                 technical_status="FAIL", outcome="rejected"))
    return key


def _bill(db, provider: str, scope: str, amounts: list[float], at: datetime):
    from brambleloop.gateway.paid_provider_gate import PaidProviderActivation, PaidProviderCall

    with db.session() as s:
        act = s.scalar(select(PaidProviderActivation).where(
            PaidProviderActivation.provider == provider,
            PaidProviderActivation.scope == scope).order_by(PaidProviderActivation.id.desc()))
        for i, amt in enumerate(amounts):
            s.add(PaidProviderCall(activation_id=act.id, provider=provider, scope=scope,
                                   gallery="shared", run_key="fixture",
                                   idem_key=f"fx-{provider}-{at.isoformat()}-{i}",
                                   fingerprint="fixture", purpose="fixture", estimate_cad=amt,
                                   actual_cad=amt, status=G.BILLED, at=at, settled_at=at))


def _production_spend(db, at: datetime):
    """16:37Z: FLUX CA$4.9539 of CA$5.00 today; openai-vision CA$0.7635 of CA$2.00 today."""
    R._production_vision(db)
    paid.activate(db, "flux-3-image", G.GENERATION, daily=5.0, monthly=100.0, per_gallery=2.5)
    _bill(db, "flux-3-image", G.GENERATION, [0.9539, 1.0, 1.0, 1.0, 1.0], at)
    _bill(db, G.OPENAI_VISION, G.VISION, [0.7635], at)


def _readback(db) -> dict:
    return PE._vp_runs(db)["redrive_eligibility"]


def _count(db, key) -> dict:
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        return IP.restart_counts(s, r)


# ---- Problem A: the baskets ---------------------------------------------------------------

def test_1_unstamped_history_is_attributed_to_the_method_production_ran_then():
    assert IP.entry_method_version({"at": f"{LEGACY_DAY}T12:00:41+00:00"}) == PROD
    assert IP.entry_method_version({"at": f"{LEGACY_DAY}T11:42:00+00:00"}) == PROD
    assert IP.entry_method_version({"at": f"{LEGACY_DAY}T09:00:40+00:00"}) == M_19I26
    assert IP.entry_method_version({"at": f"{LEGACY_DAY}T05:10:00+00:00"}) == \
        IP.LEGACY_METHOD_BEFORE_19I26
    # a method redrive's entry names its own version; a 19i29 entry carries its stamp
    assert IP.entry_method_version({"at": f"{LEGACY_DAY}T05:00:00+00:00",
                                    "method_version": "m/x"}) == "m/x"
    assert IP.entry_method_version({"at": f"{LEGACY_DAY}T05:00:00+00:00",
                                    IP.HISTORY_METHOD_KEY: "m/y",
                                    "method_version": "m/x"}) == "m/y"
    # unreadable time: cannot be shown to be older, so it counts under the current version
    assert IP.entry_method_version({}, "cur") == "cur"
    assert IP.entry_method_version({"at": "not a time"}, "cur") == "cur"


def test_2_production_baskets_were_capped_and_restart_after_midnight():
    db = R._db()
    blocked = _today_blocked()
    _production_spend(db, blocked)
    with _Method():
        keys = [_basket(db, "market-basket-small", "1.3.0", route=False,
                        history=_basket_history(), blocked_at=blocked),
                _basket(db, "market-basket-small", "1.3.0", route=True,
                        history=_basket_history(), blocked_at=blocked),
                _basket(db, "housewarming-key-basket", "0.1.0", route=True,
                        history=_basket_history(), blocked_at=blocked)]
        # 19i28 counted every restart, whatever method it was made under
        for key in keys:
            c = _count(db, key)
            assert c["total"] == 3 and c["current"] == 0 and c["method_version"] == PROD, c
            assert c["by_method"] == {IP.LEGACY_METHOD_BEFORE_19I26: 2, M_19I26: 1}, c
        # the 19i28 count, replayed: every entry counted against one cap whatever its method
        saved = IP.entry_method_version
        try:
            IP.entry_method_version = lambda h, current=None: current or PROD
            with db.session() as s:
                rb = {k: IP._redrive_verdict(s, s.scalar(select(ImageProductionRun).where(
                    ImageProductionRun.run_key == k)), None, _now(), {}) for k in keys}
        finally:
            IP.entry_method_version = saved
        # today (before 00:00Z): not capped, waiting for the FLUX day to change
        with _Clock(_now()):
            ev = _readback(db)
            for key in keys:
                assert ev["runs"][key] == {"kind": "daily_ceiling_reset", "eligible": False,
                                           "refused": "waiting_daily_reset",
                                           "restarts_spent": 0, "restarts_total": 3,
                                           "max_restarts": 3, "hold": None}, ev
            assert "max_restarts" not in ev["counts"]["by_refusal"], ev
            calls: list = []
            out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
            assert calls == [] and out["restarted"] == [], out
        # after 00:00Z: the daily reset (the path the code already prefers) restarts all three
        with _Clock(_next_day(blocked)):
            with db.session() as s:
                due = IP.redrive_due(s, None)
            assert due and due["kind"] == "daily_ceiling_reset", due
            ev = _readback(db)
            assert all(ev["runs"][k]["eligible"] for k in keys), ev
            out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
            assert sorted(r["run_key"] for r in out["restarted"]) == sorted(keys), out
            assert len(calls) == 3, calls
            for key in keys:
                row = R._row(db, key)
                assert row["calls"] == 9 and abs(row["spent"] - 0.63) < 1e-9, "nothing reset"
                h = row["stages"][IP.RESTART_KEY]["history"]
                assert len(h) == 4 and h[-1]["by"] == IP.DAILY_REDRIVE_BY, h
                assert h[-1][IP.HISTORY_METHOD_KEY] == PROD, "19i29 stamps every restart"
                assert h[0] == _basket_history()[0], "older restarts stay in history"
                c = _count(db, key)
                assert c["current"] == 1 and c["total"] == 4, c
    # (the 19i28 count, for the record: every basket read max_restarts)
    assert all(v["refused"] == "max_restarts" for v in rb.values()), rb


def test_3_within_one_method_version_the_cap_binds_exactly_as_before():
    """The thrash bound: three restarts under the current version still cap the run, after
    midnight too. Unstamped restarts after 19i27's deploy (11:42Z) are the current version."""
    db = R._db()
    blocked = _today_blocked()
    _production_spend(db, blocked)
    with _Method():
        stamped = [dict(h, **{IP.HISTORY_METHOD_KEY: PROD}) for h in _basket_history()]
        a = _basket(db, "basket-a", "1.0.0", route=True, history=stamped, blocked_at=blocked)
        late = [_h(i + 1, IP.PROVIDER_REDRIVE_BY, f"{LEGACY_DAY}T{12 + i:02d}:05:00+00:00",
                   2 + 2 * i) for i in range(3)]
        b = _basket(db, "basket-b", "1.0.0", route=True, history=late, blocked_at=blocked)
        mixed = _basket_history()[:2] + [dict(_basket_history()[2],
                                              **{IP.HISTORY_METHOD_KEY: PROD})]
        c = _basket(db, "basket-c", "1.0.0", route=True, history=mixed, blocked_at=blocked)
        for key, cur in ((a, 3), (b, 3), (c, 1)):
            assert _count(db, key)["current"] == cur, (key, _count(db, key))
        with _Clock(_next_day(blocked)):
            ev = _readback(db)
            assert ev["runs"][a]["refused"] == "max_restarts", ev
            assert ev["runs"][b]["refused"] == "max_restarts", ev
            assert ev["runs"][c]["eligible"], ev
            assert ev["counts"]["at_max_restarts"] == 2, ev
            calls: list = []
            out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
            assert [r["run_key"] for r in out["restarted"]] == [c], out
            why = [r["why"] for r in out["refused"] if r["run_key"] == a][0]
            assert "cap 3" in why and PROD in why and "3 in all" in why, why
        # a method change starts a fresh budget for the same run (D-RESTART-PER-METHOD)
    with _Method("flux3-prompt-builder/2.5.0|pattern-refs/3.1.6|pdf-page-refs/1.0.0|"
                 "owner_two_step/1"):
        assert _count(db, a)["current"] == 0 and _count(db, a)["total"] == 3
        assert IP._run_counts(db, a)["restarts_spent"] == 0


# ---- Problem B: the coaster's reverify ----------------------------------------------------

def _cap_hold() -> dict:
    """What 19i27's 12:00:37Z sweep recorded (it stamped the check version; no code)."""
    return {"judge_version": JUDGE2, "check_version": CHECKS2, "day": None,
            "why": CAP_WHY_19I27, "at": f"{LEGACY_DAY}T12:00:41+00:00"}


def test_4_the_coaster_hold_was_the_19i27_cap_refusal_not_vision_headroom():
    db = R._db()
    blocked = _today_blocked()
    _production_spend(db, blocked)
    # Replays the 19i27..19i29 world, whose deterministic checks were CHECKS2
    # (ENG-COASTER-SIDES moved the current version on; the redrive reads it from here).
    assert F.FIDELITY_JUDGE_VERSION == JUDGE2
    saved_checks = IP.fidelity_check_version
    IP.fidelity_check_version = lambda: CHECKS2
    try:
        _test_4_body(db, blocked)
    finally:
        IP.fidelity_check_version = saved_checks


def _test_4_body(db, blocked):
    with _Method():
        key = _coaster(db, hold=_cap_hold(), blocked_at=blocked)
        # the openai-vision headroom covers a re-judgement comfortably
        ok, why = IP._vision_headroom(db, 1)
        assert ok, why
        left = G.daily_headroom_cad(db, G.OPENAI_VISION, G.VISION)
        assert abs(left - (2.0 - 0.7635)) < 1e-6, left
        # 19i28: the hold outlived the count it was made from
        saved = IP._cap_hold_lifted
        IP._cap_hold_lifted = lambda *_a, **_k: False
        try:
            ev = _readback(db)
            assert ev["runs"][key]["refused"] == "refusal_held", ev
            assert ev["runs"][key]["hold"] == IP.RESTART_CAP_CODE, ev
        finally:
            IP._cap_hold_lifted = saved
        assert IP.hold_code(_cap_hold()) == IP.RESTART_CAP_CODE
        # 19i29: the cap no longer binds (0 under the current method; 2 in all after the
        # duplicate credit), so the hold lifts and the reverify is due now
        c = _count(db, key)
        assert c["current"] == 0 and c["total"] == 2, c
        ev = _readback(db)
        assert ev["runs"][key] == {"kind": "fidelity_unknown", "eligible": True,
                                   "refused": None, "restarts_spent": 0,
                                   "restarts_total": 2, "max_restarts": 3, "hold": None}, ev
        calls: list = []
        out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
        assert [r["run_key"] for r in out["restarted"]] == [key], out
        assert len(calls) == 1 and calls[0][0]["stage"] == "fidelity_gate" \
            and calls[0][0]["reverify"], calls
        row = R._row(db, key)
        assert row["calls"] == 5 and abs(row["spent"] - 0.35) < 1e-9, "nothing generated"
        h = row["stages"][IP.RESTART_KEY]["history"][-1]
        assert h["check_version"] == CHECKS2 and h[IP.HISTORY_METHOD_KEY] == PROD, h
        # once under (judge/2, checks/2): re-blocked, it is not re-driven again
        R._reblock(db, key)
        out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
        assert len(calls) == 1 and out["restarted"] == [], out


def test_5_a_real_cap_hold_and_a_vision_headroom_hold_still_hold():
    db = R._db()
    blocked = _today_blocked()
    _production_spend(db, blocked)
    with _Method():
        key = _coaster(db, hold=_cap_hold(), blocked_at=blocked)
        # the same hold, with three restarts under the current method: the cap binds
        with db.session() as s:
            r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
            st = dict(r.stages)
            st[IP.RESTART_KEY] = {"epoch": 3, "history": [
                dict(h, **{IP.HISTORY_METHOD_KEY: PROD}, generation_calls=i)
                for i, h in enumerate(_coaster_history())]}
            r.stages = st
        ev = _readback(db)
        assert ev["runs"][key]["refused"] == "max_restarts", ev
    db = R._db()
    _production_spend(db, blocked)
    # openai-vision nearly spent today: the hold waits for 00:00Z and then lifts
    _bill(db, G.OPENAI_VISION, G.VISION, [1.2300], blocked)
    with _Method():
        key = _coaster(db, hold=None, blocked_at=blocked)
        with _Clock(_now()):
            calls: list = []
            out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
            assert calls == [] and [w["run_key"] for w in out["waiting"]] == [key], out
            assert "waits for the next UTC day" in out["waiting"][0]["why"], out
            ev = _readback(db)
            assert ev["runs"][key]["refused"] == "refusal_held", ev
            assert ev["runs"][key]["hold"] == "vision_headroom", ev
        with _Clock(_next_day(blocked)):
            ev = _readback(db)
            assert ev["runs"][key]["eligible"], "the vision day changed"


# ---- the coaster ~gallery's method redrive ------------------------------------------------

def test_6_the_gallery_method_redrive_never_races_the_reverify_or_the_flux_day():
    db = R._db()
    blocked = _today_blocked()
    _production_spend(db, blocked)
    with _Method():
        main = _coaster(db, hold=_cap_hold(), blocked_at=blocked)
        gal = _coaster_gallery(db, blocked_at=blocked)
        with _Clock(_now()):
            ev = _readback(db)
            assert ev["runs"][gal]["kind"] == "method_redrive" and \
                ev["runs"][gal]["eligible"], ev
            assert ev["runs"][gal]["restarts_spent"] == 0 and \
                ev["runs"][gal]["restarts_total"] == 2, ev
            calls: list = []
            out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
            # the free re-judgement goes first; the paid regeneration waits for it
            assert [r["run_key"] for r in out["restarted"]] == [main], out
            assert [c[0]["stage"] for c in calls] == ["fidelity_gate"], calls
            w = [x for x in out["waiting"] if x["run_key"] == gal]
            assert w and w[0]["code"] == IP.METHOD_REDRIVE_SIBLING, out
            ev = _readback(db)
            assert ev["runs"][gal]["refused"] == "sibling_rejudging", ev
            assert R._row(db, gal)["calls"] == 3, "no restart spent"
            # the reverify finished (UNKNOWN again): FLUX has CA$0.0461 left, one attempt
            # costs more, so the method redrive waits for 00:00Z (no restart spent)
            R._reblock(db, main)
            out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
            assert len(calls) == 1 and out["restarted"] == [], out
            w = [x for x in out["waiting"] if x["run_key"] == gal]
            assert w and w[0]["code"] == IP.METHOD_REDRIVE_WAIT_DAILY, out
            row = R._row(db, gal)
            assert row["status"] == "blocked" and \
                len(row["stages"][IP.RESTART_KEY]["history"]) == 2, row
            ev = _readback(db)
            assert ev["runs"][gal]["refused"] == "refusal_held" and \
                ev["runs"][gal]["hold"] == "generation_headroom", ev
            with db.session() as s:
                due = IP.redrive_due(s, None)
            assert due is None or due["run_key"] != gal, due
        with _Clock(_next_day(blocked)):
            ev = _readback(db)
            assert ev["runs"][gal]["eligible"], ev
            out = IP.redrive_capability_blocked(db, follow=R._follow(calls))
            assert [r["run_key"] for r in out["restarted"]] == [gal], out
            assert calls[-1][0]["stage"] == "product_generation", calls
            row = R._row(db, gal)
            h = row["stages"][IP.RESTART_KEY]["history"][-1]
            assert h["method_version"] == PROD and h[IP.HISTORY_METHOD_KEY] == PROD, h
            assert row["calls"] == 3 and abs(row["spent"] - 0.21) < 1e-9, "nothing reset"
            assert _count(db, gal)["current"] == 1


def test_7_the_vocabulary_is_fixed():
    assert IP.MAX_RESTARTS == 3, "the cap itself is unchanged"
    assert set(IP.HOLD_CODES) >= {IP.RESTART_CAP_CODE, "vision_headroom",
                                  "generation_headroom"}
    assert "sibling_rejudging" in IP.REDRIVE_REFUSALS
    assert IP.hold_code({"why": "a role FAILed: x"}) == "role_failed"
    assert IP.hold_code({"why": "openai-vision daily ceiling: CA$0.0100 left today, a "
                                "re-judgement needs up to CA$0.0222; waits"}) == "vision_headroom"
    assert IP.hold_code({"why": "free text"}) == "other"
    assert IP.hold_code({}) is None


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert len(tests) == 7, len(tests)
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL {name}: {exc}"[:600])
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
