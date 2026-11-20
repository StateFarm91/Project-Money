"""Lane G wave 3: Etsy field constraints are recorded with evidence and honest status.

VERIFIED only from a primary Etsy source with a quoted sentence; the familiar 140/13/20 and
shop limits stay UNVERIFIED (Etsy help pages refused automated reads on 2026-10-06) and say how
the owner closes them. The working numbers agree with what the repo enforces.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.seo._testkit import fresh_db, run  # noqa: E402
from brambleloop.seo import constraints as C  # noqa: E402


def test_every_row_cites_url_and_date_and_has_a_known_status():
    assert C.CONSTRAINTS
    for c in C.CONSTRAINTS:
        assert c.url.startswith("https://"), c.key
        assert c.retrieved_on == "2026-10-06", c.key
        assert c.status in (C.VERIFIED, C.UNVERIFIED), c.key


def test_verified_rows_are_primary_and_quoted():
    verified = [c for c in C.CONSTRAINTS if c.status == C.VERIFIED]
    assert verified
    for c in verified:
        assert c.method.startswith("primary:"), c.key
        assert c.quote.strip(), c.key
        assert "etsy.com" in c.url, c.key


def test_secondary_evidence_is_never_verified_and_says_how_to_close():
    unverified = [c for c in C.CONSTRAINTS if c.status == C.UNVERIFIED]
    assert unverified
    for c in unverified:
        assert c.owner_check.strip(), c.key
    for key in ("title_max_chars", "tag_max_count", "tag_max_chars", "shop_title_max_chars",
                "sections_max_count", "section_name_max_chars", "ai_disclosure"):
        assert C.get(key).status == C.UNVERIFIED, key
        assert C.get(key).method == C.SECONDARY_SEARCH, key


def test_constructor_refuses_a_secondary_source_labelled_verified():
    try:
        C.Constraint("x", "listing", "r", 1, C.VERIFIED, C.SECONDARY_SEARCH,
                     "https://help.etsy.com/x", "2026-10-06", "summary")
    except ValueError:
        pass
    else:
        raise AssertionError("a secondary source was accepted as VERIFIED")
    try:
        C.Constraint("y", "listing", "r", 1, C.VERIFIED, C.PRIMARY_API_DOC, C.OPENAPI_URL,
                     "2026-10-06", "")
    except ValueError:
        pass
    else:
        raise AssertionError("VERIFIED without a quote was accepted")


def test_openapi_facts_recorded():
    assert C.get("styles").value == {"max_count": 2, "max_chars": 45}
    assert C.get("image_count").value == 20
    assert C.get("title_length_not_in_api").value == C.NOT_STATED
    assert C.get("seller_taxonomy_read_needs_api_key_only").status == C.VERIFIED
    assert len(C.OPENAPI_SHA256) == 64


def test_working_limits_agree_with_repo_constants():
    assert C.consistency_with_repo() == []
    w = C.working_limits()
    assert w["title_max_chars"]["value"] == 140 and w["tag_max_count"]["value"] == 13
    assert w["tag_max_chars"]["value"] == 20


def test_no_numeric_taxonomy_id_is_asserted():
    blob = json.dumps(C.snapshot())
    for fixture_id in ("2112", "2114", "2115"):
        assert fixture_id not in blob
    assert C.get("crochet_pattern_buyer_path").status == C.UNVERIFIED


def test_status_exposes_constraints_and_owner_item():
    from brambleloop.seo import jobs, status

    db = fresh_db()
    s = status.summary(db)
    w3 = s["w3"]
    assert w3["constraints"]["counts"]["VERIFIED"] >= 10
    assert "tag_max_chars" in w3["constraints"]["unverified_keys"]
    jobs.run_cycle(db)
    work = {w["key"]: w for w in status.next_work(db)}
    assert work["seo.verify_limits"]["kind"] == "owner"
    assert work["seo.verify_limits"]["external_effect"] is False
    json.dumps(s)


if __name__ == "__main__":
    run(globals())
