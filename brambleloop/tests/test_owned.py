"""#20: an audience this company owns, and the law that governs writing to it.

CASL governs every commercial electronic message this company will ever send.
`growth/content.py` already carried the right sentence -- express consent required before
this is ever sent -- in a detail dictionary, where it is a comment. These tests are about the
difference between a comment and a control.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.growth import owned as O  # noqa: E402

TODAY = date(2026, 9, 20)
GOOD_MESSAGE = {
    "sender_name": "Brambleloop Studio",
    "mailing_address": "a real postal address",
    "contact": "hello@example.invalid",
    "unsubscribe_url": "https://example.invalid/unsubscribe/abc",
}


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def test_a_consent_without_a_named_basis_is_refused():
    """A send with no named basis is a send with no basis."""
    for kwargs, fragment in (
            ({"basis": "because they seemed interested"}, "not a consent basis"),
            ({"source": "  "}, "record rather than an assertion")):
        base = {"address_ref": "s1", "basis": O.EXPRESS, "obtained_on": TODAY,
                "source": "signup form"}
        base.update(kwargs)
        raised = None
        try:
            O.Consent(**base)
        except O.ConsentRefused as e:
            raised = e
        assert raised is not None, kwargs
        assert fragment in str(raised), str(raised)


def test_implied_consent_expires_on_its_own_and_a_list_cannot_keep_it_alive():
    """The part that catches careful senders out.

    Nothing about an address changes on the day implied consent runs out, so a list that is
    not checking simply carries on. Two years from a purchase, six months from an enquiry.
    """
    purchase = O.Consent("s1", O.IMPLIED_PURCHASE, date(2024, 1, 1), "order 1234")
    assert purchase.expires_on() == date(2025, 12, 31)
    assert O.may_send(purchase, date(2025, 6, 1))["may_send"] is True
    lapsed = O.may_send(purchase, TODAY)
    assert lapsed["may_send"] is False
    assert "expires on its own" in lapsed["why"]

    enquiry = O.Consent("s2", O.IMPLIED_ENQUIRY, date(2026, 1, 1), "contact form")
    assert enquiry.expires_on() == date(2026, 6, 30)
    assert O.may_send(enquiry, date(2026, 3, 1))["may_send"] is True
    assert O.may_send(enquiry, TODAY)["may_send"] is False


def test_express_consent_lasts_until_it_is_withdrawn_and_withdrawal_is_final():
    express = O.Consent("s3", O.EXPRESS, date(2020, 1, 1), "signup form")
    allowed = O.may_send(express, TODAY)
    assert allowed["may_send"] is True
    assert allowed["expires_on"] is None

    withdrawn = O.Consent("s3", O.EXPRESS, date(2020, 1, 1), "signup form",
                          withdrawn_on=date(2026, 1, 1))
    refused = O.may_send(withdrawn, TODAY)
    assert refused["may_send"] is False
    assert "does not need a reason" in refused["why"]


def test_identification_and_unsubscribe_are_conditions_of_sending():
    """Not good manners. A message missing either is refused before it arrives in an inbox."""
    assert O.check_message(GOOD_MESSAGE) == []
    for field in O.REQUIRED_IN_EVERY_MESSAGE:
        partial = {k: v for k, v in GOOD_MESSAGE.items() if k != field}
        problems = O.check_message(partial)
        assert any(field in p for p in problems), (field, problems)


def test_the_gate_refuses_a_valid_message_to_an_expired_consent_and_says_which_half():
    express = O.Consent("s1", O.EXPRESS, date(2024, 1, 1), "signup form")
    lapsed = O.Consent("s2", O.IMPLIED_ENQUIRY, date(2026, 1, 1), "contact form")

    ok = O.send_gate(express, GOOD_MESSAGE, TODAY)
    assert ok["sendable"] is True
    assert ok["missing_from_message"] == []

    no_consent = O.send_gate(lapsed, GOOD_MESSAGE, TODAY)
    assert no_consent["sendable"] is False
    assert no_consent["consent"]["may_send"] is False
    assert no_consent["missing_from_message"] == []

    bad_message = O.send_gate(express, {"sender_name": "Brambleloop"}, TODAY)
    assert bad_message["sendable"] is False
    assert bad_message["consent"]["may_send"] is True
    assert bad_message["missing_from_message"]


def test_the_screen_says_it_is_not_clearance():
    """The same wording culture/rights.py uses, for the same reason."""
    gate = O.send_gate(O.Consent("s1", O.EXPRESS, TODAY, "form"), GOOD_MESSAGE, TODAY)
    assert "not legal advice and is not clearance" in gate["screen_not_clearance"]


def test_an_empty_coverage_report_is_not_full_coverage():
    """The useful half of a counterpart report is what is missing, not what exists."""
    empty = O.counterparts(_db())
    assert empty["measurable"] is False
    assert empty["flagships"] == 0
    assert "not full coverage" in empty["why"]


def test_a_certified_product_with_no_owned_channel_is_the_finding():
    from brambleloop.core.models import ContentPiece, PatternVersion, Product

    db = _db()
    with db.session() as s:
        bare = Product(slug="bare", title="Bare")
        covered = Product(slug="covered", title="Covered")
        s.add_all([bare, covered])
        s.flush()
        for product in (bare, covered):
            s.add(PatternVersion(product_id=product.id, version="1.0.0", cir_json={},
                                 certified=True))
        for channel in O.OWNED_CHANNELS:
            s.add(ContentPiece(product_slug="covered", channel=channel, title="t", body="b"))

    report = O.counterparts(db)
    assert report["flagships"] == 2
    assert report["without_a_full_counterpart"] == ["bare"], report
    assert report["covered"] == 1
    bare_row = next(r for r in report["products"] if r["slug"] == "bare")
    assert set(bare_row["missing"]) == set(O.OWNED_CHANNELS)


def test_owned_share_is_unmeasurable_rather_than_zero_with_no_traffic():
    """A company with no traffic has no marketplace dependence either, and that is not the
    finding anybody wants recorded."""
    share = O.owned_share(_db())
    assert share["measurable"] is False
    assert "not the same finding" in share["reason"]
    assert "#29" in share["feeds"]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
