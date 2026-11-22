"""eng/halt-380-redeploy: an attempt-cap hold filed under an earlier build is re-armed once by
a new deploy; under the build that filed it the hold stands; a parked, refused, DEAD-attempt,
child-safety or owner hold is never re-armed by a deploy."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core import build  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident  # noqa: E402
from brambleloop.ops import rebuild_graph as RG  # noqa: E402

NOW = datetime(2026, 11, 21, 23, 0, tzinfo=timezone.utc)
CAP_HELD = ("3 rebuild attempts at this change left 20 artefact(s) stale (chart, pdf); "
            "no refusal was recorded -- the stage ran and did not rewrite them")


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/r.db")
    db.create_all()
    return db


def _boot(db, commit, at):
    with db.session() as s:
        s.add(AuditLog(at=at, actor="orchestrator", action="runtime.started",
                       detail={"commit": commit}))


def _running(commit):
    real = build.identity
    build.identity = lambda: {"commit": commit}
    return real


def _detail(**extra):
    d = {"held": CAP_HELD, "attempts": 3, "max_attempts": 3, "refused_by": [],
         "stale": ["chart:x", "pdf:y"], "fingerprints": {"cir:a": {"old": "1", "new": "2"}}}
    d.update(extra)
    return d


def test_cap_hold_from_an_earlier_build_is_rearmed_once():
    db = _db()
    real = _running("newsha")
    try:
        _boot(db, "oldsha", NOW - timedelta(hours=6))
        _boot(db, "newsha", NOW - timedelta(minutes=10))
        with db.session() as s:
            inc = Incident(signature="rebuild-incomplete:p", product_slug="p",
                           halts_publication=True, report_count=3,
                           detail=_detail(held_commit="oldsha"))
            s.add(inc)
            s.flush()
            got = RG.held_before_deploy(s, inc.detail)
            assert got is not None and got["deploy"] == "newsha", got
            assert got["reason"] == RG.REDEPLOY_REARM_REASON
            rec = RG.release_cleared_hold(inc, got, now=NOW)
            assert "held" not in inc.detail and inc.detail["attempts"] == 0
            assert inc.report_count == 1 and not inc.resolved      # still open and halting
            assert inc.halts_publication
            assert rec["deploy"] == "newsha" and rec["reason"] == RG.REDEPLOY_REARM_REASON
            # a hold re-reached under the same build is not re-armed again
            inc.detail = dict(inc.detail, held=CAP_HELD, held_commit="newsha")
            assert RG.held_before_deploy(s, inc.detail) is None
            # nor is a hold whose release already records this deploy
            inc.detail = dict(inc.detail, held_commit="oldsha")
            assert RG.held_before_deploy(s, inc.detail) is None
    finally:
        build.identity = real


def test_legacy_hold_without_a_recorded_build_is_rearmed():
    db = _db()
    real = _running("newsha")
    try:
        _boot(db, "newsha", NOW - timedelta(minutes=10))
        with db.session() as s:
            got = RG.held_before_deploy(s, _detail())
            assert got is not None and got["previous_held_commit"] == "unrecorded", got
    finally:
        build.identity = real


def test_a_hold_refused_only_by_the_publication_halt_is_rearmed():
    """Production 2026-11-21: all 12 holds were 'refused by: halted (#173)' -- the halt these
    rows feed. That is the symptom, so a deploy re-arms it; any other refusal does not."""
    db = _db()
    real = _running("newsha")
    try:
        _boot(db, "newsha", NOW - timedelta(minutes=10))
        halted = ["halted (#173): 11 open publication-halting incident(s): stale-artefact:x"]
        with db.session() as s:
            d = _detail(held=CAP_HELD.replace("no refusal was recorded -- the stage ran and "
                                              "did not rewrite them",
                                              "refused by: " + halted[0]),
                        refused_by=halted, held_commit="oldsha")
            assert RG.held_before_deploy(s, d) is not None, d
            mixed = dict(d, refused_by=halted + ["#39 unreviewed policy change"])
            assert RG.held_before_deploy(s, mixed) is None
    finally:
        build.identity = real


def test_hold_under_the_running_build_stands():
    db = _db()
    real = _running("newsha")
    try:
        _boot(db, "newsha", NOW - timedelta(minutes=10))
        with db.session() as s:
            assert RG.held_before_deploy(s, _detail(held_commit="newsha")) is None
    finally:
        build.identity = real


def test_other_holds_are_never_rearmed_by_a_deploy():
    db = _db()
    real = _running("newsha")
    try:
        _boot(db, "newsha", NOW - timedelta(minutes=10))
        with db.session() as s:
            for d in (_detail(parked={"gate": "listing.seo", "reasons": ["blocked"]}),
                      _detail(refused_by=["listing.seo_blocked"]),
                      _detail(failed_attempts=[{"why": "chain.rebuild went dead: X"}]),
                      _detail(held="3 attempts; child safety hold: toy eyes"),
                      _detail(held="3 attempts; owner hold pending approval"),
                      dict(_detail(), held="")):
                assert RG.held_before_deploy(s, dict(d, held_commit="oldsha")) is None, d
    finally:
        build.identity = real


def test_the_verdict_vocabulary_matches_the_decision():
    db = _db()
    real = _running("newsha")
    try:
        _boot(db, "newsha", NOW - timedelta(minutes=10))
        from brambleloop.ops import production_evidence as PE
        cases = {"rearmed": _detail(held_commit="oldsha"),
                 "same_build": _detail(held_commit="newsha"),
                 "parked": _detail(parked={"gate": "g"}),
                 "other_refusal": _detail(refused_by=["#39 policy"]),
                 "not_held": dict(_detail(), held="")}
        assert len(cases) == 5
        with db.session() as s:
            for want, d in cases.items():
                assert RG.rearm_verdict(s, d) == want, (want, d)
                assert (RG.held_before_deploy(s, d) is not None) == (want == "rearmed")
        assert set(RG.REARM_VERDICTS) | {"unreadable"} == set(PE._REARM_VOCAB)
    finally:
        build.identity = real


def test_unknown_deploy_rearms_nothing():
    db = _db()
    real = _running("dev")
    try:
        with db.session() as s:
            assert RG.held_before_deploy(s, _detail(held_commit="oldsha")) is None
    finally:
        build.identity = real


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(exc))
                traceback.print_exc()
    sys.exit(1 if fails else 0)
