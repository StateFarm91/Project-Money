"""AUDIT F-07: a publication-gate waiver needs a standing owner grant, not just a heading.

`publish.sample_photo.publish_with_renders` used to read only the shipped decision index, so any
commit that added a `D-OWNER-PUBLISH-WITH-RENDERS` heading waived SAMPLE_PHOTO_REQUIRED. It now
also requires the fixed `ops.owner_directives.WAIVERS` table, which names the owner decision,
when it was given and the directive that gives it standing (D-OWNER-AUDIT-APPROVALS), recorded
as owner_directed_without_attestation.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_audit_waiver_grant.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core import decision_index  # noqa: E402
from brambleloop.ops import owner_directives as OD  # noqa: E402
from brambleloop.publish import sample_photo as SP  # noqa: E402


def test_the_owner_waiver_stands_with_both_records():
    assert SP.publish_with_renders() is True
    w = OD.WAIVERS[SP.PUBLISH_WITH_RENDERS]
    assert w["gate"] == SP.CODE and w["evidence"] == "owner_directed_without_attestation"
    assert w["granted_under"] == "D-OWNER-AUDIT-APPROVALS"


def test_a_heading_alone_no_longer_waives_the_gate():
    saved = dict(OD.WAIVERS)
    OD.WAIVERS.clear()
    try:
        assert decision_index.recorded(SP.PUBLISH_WITH_RENDERS), "the heading is still there"
        assert SP.publish_with_renders() is False, "a heading without the grant waives nothing"
    finally:
        OD.WAIVERS.update(saved)


def test_the_grant_alone_without_the_heading_waives_nothing():
    real = decision_index.recorded
    decision_index.recorded = lambda _id: False
    try:
        assert SP.publish_with_renders() is False
    finally:
        decision_index.recorded = real


def test_the_grant_covers_exactly_its_gate_and_time():
    assert not OD.waiver_granted(SP.PUBLISH_WITH_RENDERS, "SOME_OTHER_GATE")
    assert not OD.waiver_granted("D-SOMETHING-ELSE", SP.CODE)
    before = datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)
    assert not OD.waiver_granted(SP.PUBLISH_WITH_RENDERS, SP.CODE, now=before)


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
