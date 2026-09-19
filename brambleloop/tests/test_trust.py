"""What must be true before a new shop buys traffic, and how fast it answers when it does.

v1.4.3 requirements 17 and 18. Both are sequences that get run backwards. Ads before the
About page, because the ads are the exciting part; and a support department that has believed
for a year that fast answers reduce refunds without anybody checking.

The tests hold the two lines that make these gates rather than checklists: unmeasured is not
passed, and proof has a row behind it or it is not proof.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.commerce import trust  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.support import service  # noqa: E402

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/trust.sqlite")
    db.create_all()
    return db


def _passing_test(db, n: int = 1) -> list[int]:
    from brambleloop.core.models import PhysicalTest

    ids = []
    with db.session() as s:
        for i in range(n):
            row = PhysicalTest(product_slug=f"p{i}", version="1.0.0", tester_ref=f"t{i}",
                               passed=True)
            s.add(row)
            s.flush()
            ids.append(row.id)
    return ids


def _case(db, *, escalated: bool = False) -> int:
    from brambleloop.core.models import SupportCase

    with db.session() as s:
        row = SupportCase(customer_ref="buyer-1", product_slug="p0", version="1.0.0",
                          question="how many stitches should row 12 have?",
                          escalated=escalated)
        s.add(row)
        s.flush()
        return row.id


# ---- #17: the sequence ----------------------------------------------------


def test_an_unmeasured_rung_is_not_a_cleared_one():
    """A rung nobody has looked at and a rung this shop has cleared are opposite situations
    wearing the same colour."""
    db = _db()

    state = trust.accelerator(db)

    assert state["cleared"] is False
    assert "thumbnail_coherence" in state["unmeasured"]
    assert "Unmeasured is not passed" in state["note"]


def test_paid_traffic_is_blocked_by_the_shop_rather_than_by_the_budget():
    db = _db()

    decision = trust.may_scale_ads(db)

    assert decision["may_scale"] is False
    assert "legitimate_proof" in decision["blocking"]
    assert "converts better and costs the same" in decision["note"]


def test_a_finished_shop_with_counted_proof_clears_the_sequence():
    db = _db()
    _passing_test(db, trust.PROOF_FLOOR)

    decision = trust.may_scale_ads(db, disclosure_ok=True, claims_ok=True,
                                   thumbnails_coherent=True, support_meets_target=True)

    assert decision["may_scale"] is True
    assert decision["blocking"] == []
    assert "separate owner approval" in decision["note"]


def test_proof_is_counted_from_rows_rather_than_claimed():
    db = _db()
    assert trust.proof_count(db)["total"] == 0
    _passing_test(db, 2)
    assert trust.proof_count(db)["physical_test"] == 2


def test_a_testimonial_with_no_row_behind_it_is_refused():
    """The standing rule against manufactured reviews, in its mechanical form."""
    db = _db()
    try:
        trust.record_proof(db, origin="a lovely email", row_id=1, summary="they loved it")
    except trust.TrustRefused as e:
        assert "somebody saying a nice thing happened" in str(e)
    else:
        raise AssertionError("free-standing proof was accepted")


def test_proof_pointing_at_a_row_that_does_not_exist_is_refused():
    db = _db()
    try:
        trust.record_proof(db, origin="physical_test", row_id=404, summary="finished it")
    except trust.TrustRefused as e:
        assert "points at nothing" in str(e)
    else:
        raise AssertionError("proof was attached to a row that does not exist")


def test_real_proof_records_what_it_points_at():
    db = _db()
    test_id = _passing_test(db)[0]

    record = trust.record_proof(db, origin="physical_test", row_id=test_id,
                                summary="finished the throw and photographed it")

    assert record["origin"] == "physical_test"
    assert record["row_id"] == test_id


# ---- #18: speed, and the claim it does not get to make --------------------


def test_no_timed_case_is_no_service_level_rather_than_a_bad_one():
    report = service.service_level(_db(), now=NOW)
    assert report["meets_target"] is None
    assert "different from a bad one" in report["note"]


def test_an_untimed_case_is_counted_as_untimed_rather_than_dropped():
    """Dropping it measures the cases somebody remembered to time."""
    db = _db()
    _case(db)
    timed = _case(db)
    service.record_response(db, timed, minutes=2, from_canonical=True)

    report = service.service_level(db, now=NOW)

    assert report["cases"] == 2
    assert report["timed"] == 1
    assert report["untimed"] == 1


def test_canonical_and_escalated_targets_are_kept_apart():
    """One average over both lets a fast automated majority bury the slow escalated
    minority, and the escalated minority is where the unhappy buyers are."""
    db = _db()
    for _ in range(9):
        service.record_response(db, _case(db), minutes=2, from_canonical=True)
    slow = _case(db, escalated=True)
    service.record_response(db, slow, minutes=60 * 72, from_canonical=False)

    report = service.service_level(db, now=NOW)

    assert report["canonical"]["within_target"] == 1.0
    assert report["escalated"]["within_target"] == 0.0
    assert report["meets_target"] is False, "a slow escalation was buried by a fast majority"


def test_a_response_time_cannot_be_revised():
    db = _db()
    case = _case(db)
    service.record_response(db, case, minutes=3, from_canonical=True)
    try:
        service.record_response(db, case, minutes=1, from_canonical=True)
    except service.ServiceRefused as e:
        assert "always goes the same way" in str(e)
    else:
        raise AssertionError("a response time was revised downward")


def test_the_refund_claim_is_reported_unmeasurable_rather_than_assumed():
    """Plausible, widely believed and unchecked is exactly the shape of a claim that needs a
    measurement rather than a sentence."""
    report = service.refund_impact(_db())

    assert report["measurable"] is False
    assert report["orders"] == 0
    assert "not zero and it is not assumed" in report["reason"]


def _run() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
