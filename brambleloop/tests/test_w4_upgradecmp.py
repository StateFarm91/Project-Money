"""W4-UPGRADECMP: F-738 identity-preserving promotion comparator.

A challenger to Laura's visual system is proposed to the owner only when it is still Laura,
retains identity at least as well as the incumbent, and is strictly more real without losing
a check the incumbent passed. It never adopts anything. The row's named acceptance test:
"a realism win with identity loss is refused".

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_upgradecmp.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, OwnerAction  # noqa: E402
from brambleloop.visual import canonical, identity, photoreal  # noqa: E402
from brambleloop.visual import upgrade_compare as U  # noqa: E402

DIMS = list(identity.DRIFT_DIMENSIONS)


def _identity(drift=(), unread=()):
    return {d: identity.DRIFT if d in drift else identity.UNMEASURABLE if d in unread
            else identity.MATCH for d in DIMS}


def _realism(sound: int, failed=()):
    keys = list(photoreal.CHECKS)
    checks = {k: True for k in keys[:sound]}
    for k in failed:
        checks[k] = False
    return photoreal.gate({"judged": True, "checks": checks})


INCUMBENT = {"label": "laura-r2-a42aeac7", "identity": _identity(unread=DIMS[-2:]),
             "realism": _realism(6)}


def test_a_realism_win_with_identity_loss_is_refused():
    assert DIMS
    challenger = {"label": "challenger", "identity": _identity(drift=[DIMS[0]]),
                  "realism": _realism(10)}
    out = U.compare(INCUMBENT, challenger)
    assert out["verdict"] == "refuse"
    assert any("not Laura" in r for r in out["reasons"])
    lower = {"label": "challenger",
             "identity": _identity(unread=[d for d in DIMS[-4:]
                                           if d not in canonical.LOCKED_FACE_DIMENSIONS]),
             "realism": _realism(10)}
    out = U.compare(INCUMBENT, lower)
    assert out["verdict"] == "refuse", out
    assert any("retention fell" in r for r in out["reasons"]), out["reasons"]


def test_equal_identity_and_better_realism_is_proposed_and_adopts_nothing():
    challenger = {"label": "challenger", "identity": _identity(unread=DIMS[-2:]),
                  "realism": _realism(9)}
    out = U.compare(INCUMBENT, challenger)
    assert out["verdict"] == "propose", out["reasons"]
    assert "AUTHORISED_IDENTITY_CHANGES" in out["adopts_nothing"]


def test_no_improvement_or_a_lost_check_or_a_missing_reading_is_refused():
    same = {"label": "c", "identity": INCUMBENT["identity"], "realism": _realism(6)}
    assert U.compare(INCUMBENT, same)["verdict"] == "refuse"
    keys = list(photoreal.CHECKS)
    lost = {"label": "c", "identity": INCUMBENT["identity"],
            "realism": photoreal.gate({"judged": True, "checks": {
                **{k: True for k in keys[1:9]}, keys[0]: False}})}
    out = U.compare(INCUMBENT, lost)
    assert out["verdict"] == "refuse" and any("incumbent passed" in r for r in out["reasons"])
    assert U.compare(INCUMBENT, {"label": "c", "identity": None,
                                 "realism": _realism(9)})["verdict"] == "refuse"
    assert U.compare(INCUMBENT, {"label": "c", "identity": INCUMBENT["identity"],
                                 "realism": None})["verdict"] == "refuse"


def test_only_a_proposal_raises_one_owner_card():
    db = Database("sqlite://")
    db.create_all()
    refused = U.compare(INCUMBENT, {"label": "c", "identity": _identity(drift=[DIMS[0]]),
                                    "realism": _realism(10)})
    assert U.file_owner_card(db, refused)["card"] is False
    good = U.compare(INCUMBENT, {"label": "c2", "identity": INCUMBENT["identity"],
                                 "realism": _realism(9)})
    assert U.file_owner_card(db, good)["card"] is True
    assert U.file_owner_card(db, good)["card"] is False, "one open card, not one per run"
    with db.session() as s:
        cards = list(s.query(OwnerAction).filter_by(requirement_key=U.CARD_KEY))
        rows = list(s.query(AuditLog).filter_by(action=U.ACTION))
    assert len(cards) == 1 and len(rows) == 3


def test_the_comparator_never_touches_laura():
    before = canonical.verify()
    U.compare(INCUMBENT, {"label": "c", "identity": INCUMBENT["identity"],
                          "realism": _realism(9)})
    assert canonical.verify() == before and before["ok"] is True


if __name__ == "__main__":
    import time

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, test in tests:
        started = time.time()
        try:
            test()
            print("OK  ", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    sys.exit(bool(failures))
