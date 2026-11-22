"""Audit F-04 (2026-11-22): every audit action the production code reads has a retention
decision, and the rows a reader still needs survive `retention.audit_plan`.

On f9011cf94 `unknown_read_actions()` named six actions with no decision and five read sites
the scan could not resolve, so the retention guard was red and a retention run could delete
the owner's bulk-approval record, or a paid-call idempotency row, with nothing to stop it.
"""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="arc_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/r.db"

from brambleloop.ops import read_actions, retention  # noqa: E402

SIX = {
    "owner_queue.approve_everything": "lifetime_total",
    "concept.judge_attempt": "windowed",
    "asset_inspection.openai_attempt": "windowed",
    "asset_inspection.openai_answer": "windowed",
    "paid_provider.refused": "windowed",
    "creative.regate": "latest",
}
FIVE = ("ops/production_evidence.py::_credential_health",
        "ops/production_evidence.py::after_admission",
        "ops/production_evidence.py::rebuild_outcomes",
        "runtime/release.py::_attempt_gate_refusal",
        "runtime/release_recovery.py::_halted_releases")


def _db():
    from brambleloop.core.db import Database

    db = Database(os.environ["BRAMBLELOOP_DATABASE_URL"])
    db.create_all()
    return db


def test_each_of_the_six_actions_has_an_explicit_decision():
    for action, how in SIX.items():
        assert action in retention.KNOWN_READ_ACTIONS, action
        got, why = retention.KNOWN_READ_ACTIONS[action]
        assert got == how and why.strip(), (action, got, why)
    # The owner's stepped-up bulk approval record is kept for life.
    assert "owner_queue.approve_everything" in retention.PROTECTED_ACTIONS


def test_a_windowed_paid_call_guard_reads_far_inside_the_horizon():
    # Windowed is only safe while each guard's window is inside the horizon; if RETRY_AFTER
    # ever grows toward it, these actions must be protected instead.
    from brambleloop.creative import concept_judge as CJ
    from brambleloop.visual import vision_route as VR

    horizon = timedelta(days=retention.AUDIT_RETENTION_DAYS)
    for mod, actions in ((CJ, (CJ.ATTEMPT_ACTION,)),
                         (VR, (VR.ATTEMPT_ACTION, VR.ANSWER_ACTION))):
        for a in actions:
            assert (mod.RETRY_AFTER * 2 < horizon
                    or a in retention.PROTECTED_ACTIONS), (a, mod.RETRY_AFTER)


def test_old_approval_records_and_live_paid_call_guards_survive_the_plan():
    from brambleloop.core.models import AuditLog
    from brambleloop.creative import concept_judge as CJ
    from brambleloop.visual import vision_route as VR

    db = _db()
    now = datetime.now(timezone.utc)
    old, recent = now - timedelta(days=400), now - timedelta(hours=2)
    n = retention.KEEP_PER_ACTION + 3   # more than keep-per-action alone would save
    with db.session() as s:
        for i in range(n):
            s.add(AuditLog(actor="owner", action="owner_queue.approve_everything",
                           artifact=f"approve_everything:b{i}", at=old,
                           detail={"batch": f"b{i}", "acted": 1}))
            s.add(AuditLog(actor="t", action="plain.noise", artifact=f"n{i}", at=old))
        # Rows the paid-call guards are still reading (inside RETRY_AFTER) ...
        s.add(AuditLog(actor="t", action=CJ.ATTEMPT_ACTION, artifact="slug-a", at=recent,
                       detail={"board_sha256": "sha-a", "provider": "openai"}))
        s.add(AuditLog(actor="t", action=VR.ANSWER_ACTION, artifact="k" * 64, at=recent,
                       detail={"text": "kept", "model": "m"}))
        # ... buried under newer rows of the same actions, so keep-per-action cannot be what
        # saves them.
        for i in range(n):
            s.add(AuditLog(actor="t", action=CJ.ATTEMPT_ACTION, artifact=f"other{i}",
                           at=now - timedelta(minutes=5), detail={}))
            s.add(AuditLog(actor="t", action=VR.ANSWER_ACTION, artifact=f"o{i}",
                           at=now - timedelta(minutes=5), detail={"text": "x"}))
    plan = retention.audit_plan(db, now=now)
    with db.session() as s:
        ids = {r.id: (r.action, r.artifact) for r in s.query(AuditLog)}
    doomed = [ids[i] for i in plan["deletable_ids"]]
    assert ("plain.noise" in {a for a, _ in doomed}), plan   # the plan is not vacuous
    assert not [d for d in doomed if d[0] == "owner_queue.approve_everything"], doomed
    assert not [d for d in doomed if d[0] in (CJ.ATTEMPT_ACTION, VR.ANSWER_ACTION,
                                              VR.ATTEMPT_ACTION)], doomed
    # Apply the plan and ask the guards themselves: they still refuse the repeat paid call.
    with db.session() as s:
        s.query(AuditLog).filter(AuditLog.id.in_(plan["deletable_ids"])).delete(
            synchronize_session=False)
    assert CJ.attempted(db, "sha-a", "openai", slug="slug-a", now=now)

    class _P:
        name, model = "openai-vision", "m"
    got = VR.kept_answer(db, _P(), "k" * 64, now=now)
    assert got is not None and got.text == "kept" and got.replayed, got
    with db.session() as s:
        left = s.query(AuditLog).filter(
            AuditLog.action == "owner_queue.approve_everything").count()
    assert left == n, left


def test_the_five_read_sites_are_resolved_and_their_actions_classified():
    s = read_actions.scan()
    unresolved = {u["key"] for u in s.unresolved}
    for site in FIVE:
        assert site not in unresolved or site in retention.UNRESOLVED_READ_SITES, site
        assert site not in unresolved, f"{site} should be resolved, not allow-listed"
    for a in ("provider.credential_health", "concept.intake_approved",
              "chain.rebuild_verified", "launch.pivot_queued", "gate.halted",
              "gate.certified", "childrens.decision_required"):
        assert a in s.exact and a in retention.KNOWN_READ_ACTIONS, a
    assert retention.unknown_read_actions() == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
