"""Independent security review of claude/w4-ADOPT @ af042099: adversarial cases.

Each test asserts the SAFE behaviour. A failing test is a finding (see
research/final_build/w4/INDEPENDENT_SECREVIEW_ADOPT_af04209.md).

Ported verbatim from the review's Appendix A into the branch suite (W-ADOPT, fixes F-1..F-4);
only this docstring, the temp sandbox line and the non-zero exit on failure were added, and
one fixture value changed: `test_after_acceptance_policy_fields_still_drift` built its listing
with `materials=[]`, which the fix now (correctly) reports as drift against the CIR's
materials before any change is made; it uses the certified `["dk cotton"]` instead.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_secreview_adopt_adversarial.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit

import os
import traceback
import uuid
from unittest.mock import patch

import test_w4_adopt_manual_listing as T  # sets up env, sockets refused, shared DB
from fastapi.testclient import TestClient
from sqlalchemy import select

from brambleloop.app import main, verify_checks
from brambleloop.core.models import Listing
from brambleloop.publish import manual_adoption as MA

DB = T.DB
BODY = {"slug": "hexagon-coaster-set", "version": "1.2.0"}


def _adopt_and_accept(lid, live, t):
    release = T.seed(DB)
    T.adopt(DB, t, lid, release)
    with patch.dict(os.environ, T.ETSY_ENV), patch.object(MA, "_transport", lambda: t):
        shown = MA.baseline_preview(DB, etsy_listing_id=lid, **BODY)
        assert shown["acceptable"], shown["refusals"]
        MA.accept_baseline(DB, etsy_listing_id=lid, expected_digest=shown["digest"],
                           actor="owner:review", reason="review", **BODY)
    return release


def test_after_acceptance_policy_fields_still_drift():
    """Q4: accepting a baseline must not silence later drift the certified census caught."""
    lid = "7101"
    base = T.remote_listing(lid, description=T.EDITED, who_made="i_did",
                            when_made="made_to_order", is_supply=True, type="download",
                            quantity=999, materials=["dk cotton"])
    live = {lid: dict(base)}
    t = T.transport(live)
    _adopt_and_accept(lid, live, t)
    assert lid not in T.run_census(t)["field_drift"]
    # The owner (or anyone with Shop Manager access) changes who-made and the listing type.
    live[lid] = {**base, "who_made": "someone_else", "type": "physical", "quantity": 1,
                 "is_supply": False}
    found = lid in T.run_census(t)["field_drift"]
    assert found, ("who_made/type/quantity/is_supply changed after the baseline was accepted "
                   "and the census reported no drift")


def test_baseline_narrows_the_fields_the_census_compares():
    """Q4 (unit, deterministic): with a certified payload the census compares who_made,
    when_made, is_supply, type, quantity and materials; once a baseline exists it compares
    only title/description/tags/price/taxonomy."""
    from brambleloop.integrations.etsy import ListingPayload
    from brambleloop.runtime import etsy_ops

    lid = "7111"
    payload = ListingPayload(title=T.TITLE, description=T.EDITED, price=4.0, tags=list(T.TAGS),
                             materials=["yarn"], taxonomy_id=2856)
    good = T.remote_listing(lid, description=T.EDITED, materials=["yarn"], quantity=999,
                            who_made="i_did", when_made="made_to_order", is_supply=True,
                            type="download")
    bad = {**good, "who_made": "someone_else", "type": "physical", "is_supply": False}
    known = {"slug": "hexagon-coaster-set", "version": "1.2.0"}
    baseline = {"snapshot": MA.snapshot(good), "digest": MA.digest_of(MA.snapshot(good))}
    with patch.object(etsy_ops, "certified_payload", lambda db, s, v: payload):
        certified = etsy_ops._field_drift(DB, known, bad)
        with_base = etsy_ops._field_drift(DB, {**known, "accepted_baseline": baseline}, bad)
    assert any("who_made" in d for d in certified), certified   # control: caught without one
    assert any("who_made" in d for d in with_base), (
        f"who_made/type/is_supply drift silenced by the accepted baseline; certified census "
        f"reports {certified}, baseline census reports {with_base}")


def test_live_phase_verify_does_not_prove_a_mismatched_manual_listing():
    """Q5: in live phases a VERIFIED adoption counts as 'read back verified' even when the
    live copy differs from the certified copy and drops the AI disclosure."""
    lid = "7201"
    stripped = T.DESCRIPTION.split(" How this pattern was made")[0]
    t = T.transport({lid: T.remote_listing(lid, description=stripped,
                                           title="Anything At All")})
    release = T.seed(DB)
    res = T.adopt(DB, t, lid, release)
    assert res["verification"] == MA.VERIFIED and res["differences"]
    proven = verify_checks._published_rows_proven(DB)
    mine = [u for u in proven["unproven"] if u["etsy_listing_id"] == lid]
    assert mine, ("everything_published_is_certified_granted_and_read_back passes for an "
                  f"adopted listing whose copy differs from the certificate: {res['differences']}")


def test_one_etsy_id_cannot_be_linked_to_two_releases_concurrently():
    """Q3: the 'already linked elsewhere' check runs before the Etsy read, outside the write
    transaction, and Listing.etsy_listing_id has no unique constraint."""
    lid = "7301"
    t = T.transport({lid: T.remote_listing(lid)})
    rel_a = T.seed(DB)
    rel_b = T.seed(DB, slug="hexagon-coaster-twin", version="1.0.0")
    real_read = MA.read_listing
    fired = []

    def racing_read(db, listing_id, *, transport=None):
        if not fired:
            fired.append(1)  # a second owner tab adopts the same id for the other release
            T.adopt(DB, t, lid, rel_b, slug="hexagon-coaster-twin", version="1.0.0")
        return real_read(db, listing_id, transport=transport)

    try:
        with patch.object(MA, "read_listing", racing_read):
            T.adopt(DB, t, lid, rel_a)
    except MA.AdoptionRefused:
        pass
    with DB.session() as s:
        linked = [f"{r.product_slug}@{r.version}" for r in s.scalars(
            select(Listing).where(Listing.etsy_listing_id == lid))]
    assert len(linked) <= 1, f"Etsy listing {lid} linked to two releases: {linked}"


def test_store_publish_and_claim_blocked_after_adoption():
    """Q3: both duplicate guards hold for an UNVERIFIED adoption too."""
    from brambleloop.publish import draft_intent

    lid = "7401"
    release = T.seed(DB)
    t = T.transport({}, fail=503)
    assert T.adopt(DB, t, lid, release)["verification"] == MA.UNVERIFIED
    with DB.session() as s:
        intent = s.get(draft_intent.DraftIntent,
                       draft_intent.key_for("hexagon-coaster-set", "1.2.0"))
        assert intent.state == MA.INTENT_STATE and intent.remote_id == lid
    assert T.listing_row(DB)["etsy_listing_id"] == lid


def test_anonymous_catalogue_sees_only_published():
    """Q6."""
    lid = "7501"
    release = T.seed(DB)
    T.adopt(DB, T.transport({lid: T.remote_listing(lid)}), lid, release)
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = anon.get("/api/catalogue")
    assert r.status_code == 200 and r.json() == {"published": True}, r.text


def test_accept_baseline_refuses_bearer_and_replayed_nonce():
    """Q2."""
    lid = "7601"
    t = T.transport({lid: T.remote_listing(lid, description=T.EDITED)})
    release = T.seed(DB)
    T.adopt(DB, t, lid, release)
    with patch.dict(os.environ, T.ETSY_ENV), patch.object(MA, "_transport", lambda: t):
        digest = MA.baseline_preview(DB, etsy_listing_id=lid, **BODY)["digest"]
        body = {**BODY, "etsy_listing_id": lid, "expected_digest": digest, "reason": "x"}
        anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
        for action in ("listing.accept_baseline", "listing.baseline_preview",
                       "listing.adopt_manual"):
            r = anon.post(f"/api/cc/actions/{action}", json={**body, "release": release},
                          headers={"Authorization": f"Bearer {T.OPS}"})
            assert r.status_code in (401, 403), (action, r.status_code, r.text)
        c, csrf = T.session()
        h = T.fresh(csrf)
        r1 = c.post("/api/cc/actions/listing.baseline_preview", json=body, headers=h)
        assert r1.status_code == 200, r1.text
        r2 = c.post("/api/cc/actions/listing.accept_baseline", json=body, headers=h)
        assert r2.status_code in (401, 403, 409), ("replayed nonce accepted", r2.text)
    assert T.baseline_of(lid) is None


if __name__ == "__main__":
    failed = 0
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            try:
                fn()
                print("OK  ", n)
            except AssertionError as e:
                failed += 1
                print("FAIL", n, "--", str(e)[:400])
            except Exception:  # noqa: BLE001
                failed += 1
                print("ERR ", n)
                traceback.print_exc()
    print("failed:", failed)
    raise SystemExit(1 if failed else 0)
