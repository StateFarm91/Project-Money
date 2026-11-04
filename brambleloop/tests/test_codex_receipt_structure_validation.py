"""Malformed receipt evidence is reported, never omitted or mistaken for a pass."""
import pytest
from brambleloop.commerce import deliverables as d
from test_w4_firstsale_deliverables import _db


@pytest.mark.parametrize("receipt,mapping,why", [
    ([], {}, "receipt is not an object"),
    ({"is_paid": True, "transactions": {}}, {}, "transactions is not a list"),
    ({"is_paid": True, "transactions": ["bad"]}, {}, "transaction is not an object"),
    ({"is_paid": True, "transactions": []}, [], "listing mappings are not an object"),
    ({"is_paid": True, "transactions": [{"is_digital": True, "listing_id": 1}]}, {"1": ["item"]}, "the line maps to no valid release"),
    ({"is_paid": True, "transactions": [{"is_digital": True, "listing_id": 1}]}, {"1": ["item@other", "1"]}, "the line maps to no valid release"),
    ({"is_paid": True, "transactions": [{"is_digital": True, "listing_id": None}]}, {"None": ["item", "1"]}, "the line has no valid listing id"),
])
def test_bad_receipt_structure_is_a_reported_failure(receipt, mapping, why):
    out = d.rehearse_purchase(_db(), receipt, mapping)
    assert out["state"] == d.FAIL and out["files"][0]["why"] == why
