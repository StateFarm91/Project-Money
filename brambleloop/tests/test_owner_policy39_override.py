"""D-OWNER-POLICY39-OVERRIDE: the owner directed proceeding without review of the pending
listing_image_rules change. The override is recorded as exactly that -- never "reviewed" --
covers only changes read on or before its date, and nothing else."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import PolicySnapshot  # noqa: E402
from brambleloop.gates import platform_policy as pp  # noqa: E402

_TMP = tempfile.mkdtemp()
_N = [0]


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/o{_N[0]}.db")
    db.create_all()
    return db


def _change(db, source, checked_on, digest):
    with db.session() as s:
        s.add(PolicySnapshot(source=source, material_change=True, affects=["publishing"],
                             digest=digest * 64, checked_on=checked_on))


def test_the_pending_image_rule_change_is_released_and_reported_as_an_override():
    db = _db()
    _change(db, "listing_image_rules", "2026-10-22", "a")
    assert [c["source"] for c in pp.unreviewed_changes(db)] == []
    (o,) = pp.overridden_changes(db)
    assert o["source"] == "listing_image_rules" and o["reviewed"] is False
    assert o["override"]["basis"] == "owner directed proceeding without review"
    assert o["override"]["decision"] == "D-OWNER-POLICY39-OVERRIDE"


def test_a_later_image_rule_change_holds_again():
    db = _db()
    _change(db, "listing_image_rules", "2026-10-22", "a")
    _change(db, "listing_image_rules", "2026-11-21", "b")
    assert [c["source"] for c in pp.unreviewed_changes(db)] == ["listing_image_rules"]
    assert pp.overridden_changes(db) == []


def test_an_undated_change_is_never_assumed_covered():
    db = _db()
    _change(db, "listing_image_rules", "", "c")
    assert [c["source"] for c in pp.unreviewed_changes(db)] == ["listing_image_rules"]


def test_no_other_policy_source_is_released():
    db = _db()
    _change(db, "seller_policy", "2026-10-22", "d")
    assert [c["source"] for c in pp.unreviewed_changes(db)] == ["seller_policy"]
    assert pp.overridden_changes(db) == []


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as exc:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(exc))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
