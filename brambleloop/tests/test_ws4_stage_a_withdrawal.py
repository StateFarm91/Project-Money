"""WS4 Stage A, part 2: `EtsyClient.deactivate`, `OwnerGrant.WITHDRAW` and the rollback plan.

Design §5.3 v2 and §5.4. Etsy is `tests/fake_etsy.py`; nothing reaches a real shop.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
from datetime import timedelta
from unittest.mock import patch

# run_tests.sh sets no PYTHONPATH (verdict 6985175377): src before any brambleloop import.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select, update  # noqa: E402

from brambleloop.core.models import AuditLog, Listing  # noqa: E402
from brambleloop.integrations import etsy as E  # noqa: E402
from brambleloop.ops import standing_grants as SG  # noqa: E402
from brambleloop.ops import standing_policy as sp  # noqa: E402
from brambleloop.ops import standing_withdrawal as SW  # noqa: E402
from test_ws4_7_issuer import NOW, REL, SLUG, VERSION, _effective_db, _reset  # noqa: E402
from test_ws4_stage_a_activation import _draft, _publish_grant, _published  # noqa: E402

LISTING = "4400123"


def _activation_grant(db, aid, *, listing_id=LISTING, job_id=61, consumed=True):
    SG.ensure_tables(db)
    with db.session() as s:
        g = SG.StandingGrant(policy_row_id=aid, policy_version=1, scope=f"{SLUG}@{VERSION}",
                             release=REL, digest="e" * 64,
                             detail_json={"action": "store.activate", "listing_id": listing_id},
                             seal="00", issued_at=NOW, expires_at=NOW + timedelta(minutes=15),
                             consumed_at=NOW if consumed else None,
                             consumed_job_id=job_id if consumed else None)
        s.add(g)
        s.flush()
        return g.id


def _stopped(state=sp.SUSPENDED_STATE):
    real = sp.effective
    return patch.object(sp, "effective",
                        lambda *a, **k: {**real(*a, **k), "state": state, "why": "drill"})


ACTIVE = {"listing_id": LISTING, "state": "active"}


def test_only_a_listing_a_standing_activation_made_live_is_in_lineage():
    try:
        db, _, aid = _effective_db()
        assert SW.lineage_of_live(db, LISTING) is None
        _publish_grant(db, aid, job_id=5,                          # a publish grant: no,
                       detail={"action": "store.publish",          # even naming the listing
                               "listing_id": LISTING})             # (write-once: built so)
        _activation_grant(db, aid, consumed=False)                 # never used: no
        _activation_grant(db, aid, listing_id="999", job_id=62)    # another listing: no
        assert SW.lineage_of_live(db, LISTING) is None
        gid = _activation_grant(db, aid)
        assert SW.lineage_of_live(db, LISTING)["grant_id"] == gid
    finally:
        _reset()


def test_a_withdrawal_needs_lineage_a_stopped_policy_a_rate_and_an_active_read_back():
    try:
        db, _, aid = _effective_db()
        why = lambda remote=ACTIVE: SW.withdraw_refusal(db, LISTING, remote=remote)  # noqa
        assert "not in SP lineage" in why()
        _activation_grant(db, aid)
        assert "still in effect" in why()                    # EFFECTIVE or not, it is not stopped
        for state in (sp.ISSUE_PAUSED, sp.NOT_YET):
            with _stopped(state):
                assert "still in effect" in why(), state
        for state in sorted(SW.STOPPED_STATES):
            with _stopped(state):
                assert why() is None, state
        with _stopped():
            assert "not this listing" in why({"listing_id": "999", "state": "active"})
            assert "not this listing" in why(None)
            assert "'draft'" in why({"listing_id": LISTING, "state": "draft"})
            with db.session() as s:
                for _ in range(SW.MAX_PER_HOUR):
                    s.add(AuditLog(actor=SW.ACTOR, action=SW.WITHDRAWN, artifact="x",
                                   at=NOW - timedelta(minutes=5)))
            assert "per hour" in SW.withdraw_refusal(db, LISTING, remote=ACTIVE, now=NOW)
            assert SW.withdraw_refusal(db, LISTING, remote=ACTIVE,
                                       now=NOW + timedelta(hours=2)) is None
    finally:
        _reset()


def test_the_withdrawal_grant_is_listing_bound_and_not_gated_on_the_phase():
    seen = {}

    def spy(db, listing_id, *, remote=None):
        seen.update(listing_id=listing_id, remote=remote)
        return None
    with patch.object(SW, "withdraw_refusal", spy), \
            patch("brambleloop.core.phase.effective", lambda db: "shadow"):
        g = E.OwnerGrant(object(), action=E.OwnerGrant.WITHDRAW, approval_id="policy-stopped",
                         slug=SLUG, version=VERSION, listing_id=LISTING)
        assert g.refusal(action=E.OwnerGrant.WITHDRAW, listing_id=LISTING, remote=ACTIVE) is None
        assert seen == {"listing_id": LISTING, "remote": ACTIVE}
        assert "another listing" in g.refusal(action=E.OwnerGrant.WITHDRAW, listing_id="999")
        # A withdrawal grant never covers going live or publishing.
        assert "not store.activate" in g.refusal(action=E.OwnerGrant.ACTIVATE,
                                                 listing_id=LISTING)
        assert "not store.publish" in g.refusal(action=E.OwnerGrant.PUBLISH)


def _fake_live(fake):
    from test_etsy_transport import (PAYLOAD, _client, _verified_activation_grant,
                                     _verified_publication_grant, build_payload)
    from brambleloop.integrations import etsy_probe

    live = _client(fake, phase="production", owner=True, shadow_writes=False)
    lid = live.create_draft(build_payload(**PAYLOAD), grant=_verified_publication_grant())
    live.upload_image(lid, filename="cover.png", data=etsy_probe.one_pixel_png(),
                      grant=_verified_activation_grant(lid))
    live.activate(lid, launch_authorisation="LAUNCH-0-TEST", grant=_verified_activation_grant(lid))
    assert live.get_listing(lid)["state"] == "active"
    return lid, _client(fake, phase="shadow", owner=False, shadow_writes=False)


def _updates(fake):
    return [r for r in fake.requests if r["operation"] == "updateListing"]


def test_deactivate_takes_a_stopped_policys_listing_down_and_records_it_even_in_shadow():
    from fake_etsy import FakeEtsy

    try:
        db, _, aid = _effective_db()
        with FakeEtsy() as fake:
            lid, shadow = _fake_live(fake)
            _draft(db, listing_id=lid, state="active")
            _activation_grant(db, aid, listing_id=lid)
            n = len(_updates(fake))
            # No grant, or a grant of another kind: refused before anything is sent.
            for bad in (None, E.OwnerGrant(db, action=E.OwnerGrant.ACTIVATE, approval_id=1,
                                           listing_id=lid)):
                try:
                    shadow.deactivate(lid, grant=bad)
                    raise AssertionError("deactivated without a withdrawal grant")
                except E.EtsyNotPermitted as exc:
                    assert "OwnerGrant.WITHDRAW" in str(exc), exc
            # The policy is still in effect: the grant refuses, nothing is sent.
            try:
                SW.withdraw(db, shadow, slug=SLUG, version=VERSION, listing_id=lid)
                raise AssertionError("withdrew while the policy is in effect")
            except E.EtsyNotPermitted as exc:
                assert "still in effect" in str(exc)
            assert len(_updates(fake)) == n
            with _stopped():
                out = SW.withdraw(db, shadow, slug=SLUG, version=VERSION, listing_id=lid)
            assert out == {"listing_id": lid, "before": "active", "after": "inactive"}
            assert shadow.get_listing(lid)["state"] == "inactive"
            assert len(_updates(fake)) == n + 1                 # exactly one request sent
            with db.session() as s:
                assert s.scalar(select(Listing.state).where(
                    Listing.product_slug == SLUG)) == "withdrawn"
                row = s.scalar(select(AuditLog).where(AuditLog.action == SW.WITHDRAWN))
                assert row.detail["before"] == "active" and row.detail["after"] == "inactive"
            # Again: the read-back says it is no longer active, so it is refused.
            with _stopped():
                try:
                    SW.withdraw(db, shadow, slug=SLUG, version=VERSION, listing_id=lid)
                    raise AssertionError("withdrew an inactive listing")
                except E.EtsyNotPermitted as exc:
                    assert "'inactive'" in str(exc)
    finally:
        _reset()


def test_deactivate_raises_when_etsy_does_not_report_inactive():
    from fake_etsy import FakeEtsy

    with FakeEtsy() as fake:
        lid, shadow = _fake_live(fake)

        class _Ok(E.OwnerGrant):
            def refusal(self, **k):
                return None
        g = _Ok(None, action=E.OwnerGrant.WITHDRAW, approval_id="x", listing_id=lid)
        real = shadow.get_listing
        reads = []

        def stuck(listing_id, **k):
            reads.append(1)
            return {**real(listing_id, **k), "state": "active"}
        with patch.object(shadow, "get_listing", stuck):
            try:
                shadow.deactivate(lid, grant=g)
                raise AssertionError("an unconfirmed deactivation was reported done")
            except E.EtsyRejected as exc:
                assert "after deactivation" in str(exc)
        assert len(reads) == 2                                  # read before and after


def test_the_rollback_plans_and_executes_nothing():
    try:
        db, _, aid = _effective_db()
        assert SW.plan(db)["planned"] is False
        _draft(db, state="active")
        _activation_grant(db, aid)
        with _stopped():
            first = SW.plan(db)
            again = SW.plan(db)
        assert first["planned"] and first["recorded"] and not again["recorded"]
        assert [x["listing_id"] for x in first["live"]] == [LISTING]
        assert first["executes"].startswith("nothing")
        # A draft this policy published is planned too; one it did not is not.
        with db.session() as s:
            s.execute(update(Listing).where(Listing.product_slug == SLUG).values(state="draft"))
        _publish_grant(db, aid, job_id=11)
        _published(db, job_id=12)                  # published by a job outside lineage
        with _stopped(sp.NONE):
            assert SW.plan(db)["drafts"] == []
        _published(db, job_id=11)
        with _stopped(sp.NONE):
            p = SW.plan(db)
        assert [x["listing_id"] for x in p["drafts"]] == [LISTING] and p["live"] == []
        with db.session() as s:
            assert s.scalar(select(Listing.state).where(Listing.product_slug == SLUG)) == "draft"
            assert not list(s.scalars(select(AuditLog).where(AuditLog.action == SW.WITHDRAWN)))
    finally:
        _reset()


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:600])
                import traceback

                traceback.print_exc()
    print(f"{failed} failed")
    # run_tests.sh reads the exit code: a failing test must fail the suite.
    sys.exit(1 if failed else 0)
