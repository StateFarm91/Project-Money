"""The approve-all-3 readback names what stays by card kind, never by slug or free text."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from brambleloop.ops import approve_all_directive as AD  # noqa: E402


def test_kind_keeps_only_code_identifiers():
    items = [{"requirement_key": "etsy.oauth:cloudline-baby-blanket", "bucket": "outside"},
             {"requirement_key": "etsy.oauth:another", "bucket": "outside"},
             {"requirement_key": "Payout Setup for Jake!", "bucket": "outside"},
             {"card": "publication:hexagon-coaster-set@1.0.0", "bucket": "owner_grant_signature"},
             {"bucket": "spend_over_cap"}]
    got = AD._by_kind(items)
    assert got == {"outside/etsy.oauth": 2, "outside/other": 1,
                   "owner_grant_signature/publication": 1, "spend_over_cap/other": 1}, got
    assert not any("cloudline" in k or "Jake" in k for k in got)


if __name__ == "__main__":
    test_kind_keeps_only_code_identifiers()
    print("ok test_kind_keeps_only_code_identifiers")
    print("OK 1 passed")
