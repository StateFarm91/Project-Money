"""WS4 Stage A, part 1: the bounded public-activation authority (off in code).

Design §1.5, §5.4 (SP lineage), §7.3 G-LIMITED pace, §9 M1/M5/M6 item 11. No network: the
Etsy listing is a dict, and only `ops/standing_activation.py`, the policy ceilings, the grant
store's `consume` and the client's `OwnerGrant` door are exercised.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import update  # noqa: E402

from brambleloop.core.models import AuditLog, Job, Listing  # noqa: E402
from brambleloop.ops import activation_authority as AA  # noqa: E402
from brambleloop.ops import standing_activation as SA  # noqa: E402
from brambleloop.ops import standing_boundary as SB  # noqa: E402
from brambleloop.ops import standing_grants as SG  # noqa: E402
from brambleloop.ops import standing_policy as sp  # noqa: E402
from test_ws4_7_issuer import (NOW, REL, SLUG, VERSION, _effective_db, _InPolicy,  # noqa: E402
                               _reports, _reset)
from test_ws4_policy_object import content  # noqa: E402

LISTING = "4400123"


class _On:
    """Stage A switched on, as the reviewed code change would."""
    def __enter__(self):
        self.p = patch.object(SA, "STAGE_A_ENABLED", True)
        self.p.start()

    def __exit__(self, *a):
        self.p.stop()


def _refused(fn, exc, contains):
    try:
        fn()
    except exc as e:
        assert contains in str(e), (contains, str(e))
        return
    raise AssertionError(f"expected {exc.__name__} containing {contains!r}")


def _draft(db, *, listing_id=LISTING, state="draft"):
    with db.session() as s:
        s.execute(update(Listing).where(Listing.product_slug == SLUG, Listing.version == VERSION)
                  .values(etsy_listing_id=listing_id, state=state))


def _publish_grant(db, aid, *, job_id, action="store.publish", consumed=True):
    SG.ensure_tables(db)
    with db.session() as s:
        g = SG.StandingGrant(policy_row_id=aid, policy_version=1, scope=f"{SLUG}@{VERSION}",
                             release=REL, digest="d" * 64, detail_json={"action": action},
                             seal="00", issued_at=NOW, expires_at=NOW + timedelta(minutes=15),
                             consumed_at=NOW if consumed else None,
                             consumed_job_id=job_id if consumed else None)
        s.add(g)
        s.flush()
        return g.id


def _published(db, *, job_id, listing_id=LISTING):
    with db.session() as s:
        if s.get(Job, job_id) is None:
            s.add(Job(id=job_id, agent="store", job_type="store.publish", inputs={}))
            s.flush()
        s.add(AuditLog(actor="worker", action="store.published", artifact=f"{SLUG}@{VERSION}",
                       job_id=job_id, detail={"etsy_listing_id": listing_id,
                                              "files_sent": [{"name": "p.pdf", "size": 1}]}))


# ---- off in code ---------------------------------------------------------------------------

def test_the_power_is_off_in_code_everywhere():
    assert SA.STAGE_A_ENABLED is False
    c = content(actions=["store.publish", "store.activate"])
    assert SA.OFF in sp.ceiling_refusals(c)
    assert sp.ceiling_refusals(content()) == []
    try:
        db, _, a = _effective_db()
        _refused(lambda: SA.issue(db, slug=SLUG, version=VERSION, release=REL, job_id=1),
                 SA.ActivationRefused, "off in code")
        assert SA.decide(db, SLUG, VERSION, REL)["reasons"] == [SA.OFF]
        assert SA.use_refusal(db, "seg:1", slug=SLUG, version=VERSION, listing_id=LISTING,
                              release=REL, job_id=1, remote={"should_auto_renew": False}) == SA.OFF
    finally:
        _reset()


def test_switched_on_the_content_ceilings_hold():
    with _On():
        # Activation only of drafts the same policy created: publish must be named too.
        assert any("must also name store.publish" in r
                   for r in sp.ceiling_refusals(content(actions=["store.activate"])))
        c = content(actions=["store.publish", "store.activate"])
        c["spend"]["max_listing_fees_cad_per_30d"] = SA.MAX_ACTIVATION_FEES_CAD_PER_30D
        assert sp.ceiling_refusals(c) == []
        c["spend"]["max_listing_fees_cad_per_30d"] = SA.MAX_ACTIVATION_FEES_CAD_PER_30D + 0.01
        assert any("max_listing_fees" in r for r in sp.ceiling_refusals(c))
        # A draft-only policy still may not name a single cent of fees.
        p = content()
        p["spend"]["max_listing_fees_cad_per_30d"] = 0.01
        assert any("max_listing_fees" in r for r in sp.ceiling_refusals(p))
        # The text the owner signs says plainly that this one goes public, and the draft-only
        # text is unchanged (its digest is what existing approvals signed).
        live = sp.render_statement(c)
        assert "make those same drafts LIVE" in live and "cannot activate" not in live
        draft = sp.render_statement(content())
        assert "create Etsy DRAFT listings on shop" in draft
        assert "This policy cannot activate a listing, change a price" in draft


# ---- SP lineage ----------------------------------------------------------------------------

def test_only_a_draft_this_policy_created_is_in_lineage():
    try:
        db, _, aid = _effective_db()
        lin = lambda: SA.lineage(db, SLUG, VERSION, REL, aid)  # noqa: E731
        assert "no Etsy draft" in lin()["why"]
        _draft(db)
        assert "no store.publish grant of this policy" in lin()["why"]
        _publish_grant(db, aid, job_id=7, action="store.activate")     # wrong kind
        _publish_grant(db, aid + 1000, job_id=8)                        # another policy
        _publish_grant(db, aid, job_id=9, consumed=False)               # never used
        assert "no store.publish grant of this policy" in lin()["why"]
        _publish_grant(db, aid, job_id=11)
        assert "no verified store.published" in lin()["why"]
        _published(db, job_id=12)                     # the owner's own publish job
        assert "not by a job that consumed" in lin()["why"]
        _published(db, job_id=11)
        assert lin()["state"] == SB.PASS and lin()["value"]["publish_job"] == 11
        _draft(db, state="active")
        assert "already active" in lin()["why"]
    finally:
        _reset()


# ---- Stage A's own shadow gate -------------------------------------------------------------

def test_stage_a_shadow_needs_days_candidates_and_owner_agreement():
    try:
        db, _, aid = _effective_db()
        rec = lambda d, dec="ACTIVATE": SA.record_shadow(  # noqa: E731
            db, SLUG, VERSION, REL, approval_id=aid, decision=dec, now=NOW + timedelta(days=d))
        gate = lambda: SA.a_shadow(db, aid, approved_at=NOW - timedelta(days=1),  # noqa: E731
                                   now=NOW + timedelta(days=9))
        rec(0)
        rec(1)
        rec(3)
        why = gate()["why"]
        assert "3 of 7 shadow days" in why and "would-activate" not in why, why
        rec(8, "HOLD")
        why = gate()["why"]
        assert "shadow days" not in why and "3 of 3" not in why, why
        # Rows from before the approval do not count: from day 0.5 there are 7 days of rows
        # but only 2 would-activate decisions.
        why = SA.a_shadow(db, aid, approved_at=NOW + timedelta(hours=12),
                          now=NOW + timedelta(days=9))["why"]
        assert "2 of 3 would-activate" in why and "shadow days" not in why, why
        # 3 would-activate over 8 days, and the owner never approved this release.
        assert "never approved" in gate()["why"]
        with patch.object(SA, "_owner_approved_activation", lambda *a: True):
            assert gate()["state"] == SB.PASS
        # Another approval's rows, or rows from the future, do not count.
        assert SA.a_shadow(db, aid + 1, approved_at=None, now=NOW + timedelta(days=9))[
            "state"] == SB.FAIL
        assert SA.a_shadow(db, aid, approved_at=None, now=NOW + timedelta(days=2))[
            "state"] == SB.FAIL
    finally:
        _reset()


# ---- the decision and its ceilings ---------------------------------------------------------

class _Gates:
    """Every gate but the one under test passes."""
    def __init__(self, **over):
        self.over = over

    def __enter__(self):
        from brambleloop.ops import standing_shadow_gate as G

        aid = self.over.pop("aid")
        g = {"verdict": "MET", "approval_id": aid}
        self.p = [
            patch.object(G, "g_shadow", lambda *a, **k: dict(self.over.get("g", g))),
            patch.object(SA, "a_shadow", lambda *a, **k: self.over.get(
                "a", {"state": SB.PASS, "why": None})),
            patch.object(SA, "lineage", lambda *a, **k: self.over.get(
                "lin", {"state": SB.PASS, "value": {}, "why": None})),
        ]
        for p in self.p:
            p.start()
        self.inp = _InPolicy()
        self.inp.__enter__()

    def __exit__(self, *a):
        self.inp.__exit__()
        for p in self.p:
            p.stop()


def _activation_policy_db():
    db, c, aid = _effective_db()
    _reports(db)
    return db, aid


def _with_actions(eff):
    out = dict(eff)
    out["content"] = {**eff["content"], "actions": ["store.publish", "store.activate"],
                      "spend": {"max_listing_fees_cad_per_30d": 4.0, "ads": "NONE"}}
    return out


def _decide(db, aid, now=NOW, **over):
    real = sp.effective
    with _On(), _Gates(aid=aid, **over), patch.object(
            sp, "effective", lambda *a, **k: _with_actions(real(*a, **k))):
        return SA.decide(db, SLUG, VERSION, REL, now=now)


def test_every_gate_is_required_and_the_pace_and_fee_ceilings_hold():
    try:
        db, aid = _activation_policy_db()
        assert _decide(db, aid)["decision"] == "ACTIVATE", _decide(db, aid)
        assert "G-SHADOW" in " ".join(_decide(db, aid, g={"verdict": "NOT_MET",
                                                          "approval_id": aid})["reasons"])
        assert "G-SHADOW" in " ".join(_decide(db, aid, g={"verdict": "MET",
                                                          "approval_id": aid + 1})["reasons"])
        assert "Stage A shadow" in " ".join(_decide(
            db, aid, a={"state": SB.FAIL, "why": "x"})["reasons"])
        assert "lineage" in " ".join(_decide(
            db, aid, lin={"state": SB.FAIL, "why": "x"})["reasons"])
        # A publish-only effective policy cannot activate.
        with _On(), _Gates(aid=aid):
            assert "does not name store.activate" in " ".join(
                SA.decide(db, SLUG, VERSION, REL, now=NOW)["reasons"])
        # Pace: 1 per day, 3 per 7 days; fees inside the policy's own 30-day figure.
        SA.ensure_tables(db)
        with db.session() as s:
            s.add(SA.StandingActivationSlot(policy_row_id=aid, day=NOW.date().isoformat(),
                                            slot_no=1, at=NOW))
        assert "per day" in " ".join(_decide(db, aid)["reasons"])
        tomorrow = NOW + timedelta(days=1)
        _reports(db, now=tomorrow)                 # Mode T is read fresh at every decision
        assert _decide(db, aid, now=tomorrow)["decision"] == "ACTIVATE"
        with db.session() as s:
            for d in (1, 2):                       # with today's: 3 in 7 days
                s.add(SA.StandingActivationSlot(policy_row_id=aid, slot_no=1, at=NOW - timedelta(
                    days=d), day=(NOW - timedelta(days=d)).date().isoformat()))
        assert "per 7 days" in " ".join(_decide(db, aid, now=tomorrow)["reasons"])
        real = sp.effective
        tight = lambda *a, **k: {**_with_actions(real(*a, **k))}  # noqa: E731

        def fees(*a, **k):
            e = tight(*a, **k)
            e["content"] = {**e["content"], "spend": {"max_listing_fees_cad_per_30d": 0.5,
                                                      "ads": "NONE"}}
            return e
        _reports(db, now=NOW + timedelta(days=20))
        with _On(), _Gates(aid=aid), patch.object(sp, "effective", fees):
            r = SA.decide(db, SLUG, VERSION, REL, now=NOW + timedelta(days=20))
        assert "listing fees would pass CA$0.50" in " ".join(r["reasons"]), r
    finally:
        _reset()


def test_the_database_refuses_a_second_activation_slot_in_a_day():
    from sqlalchemy.exc import IntegrityError

    try:
        db, aid = _activation_policy_db()
        SA.ensure_tables(db)
        for slot in (1, 2):
            try:
                with db.session() as s:
                    s.add(SA.StandingActivationSlot(policy_row_id=aid, day="2026-11-20",
                                                    slot_no=slot, at=NOW))
                assert slot == 1, "slot 2 must be refused by the CHECK"
            except IntegrityError:
                assert slot == 2
        try:
            with db.session() as s:
                s.add(SA.StandingActivationSlot(policy_row_id=aid, day="2026-11-20",
                                                slot_no=1, at=NOW))
            raise AssertionError("a duplicate slot must be refused")
        except IntegrityError:
            pass
    finally:
        _reset()


# ---- issue, consume and use ----------------------------------------------------------------

def _aa_snapshot(db, slug, version, release=""):
    return {"action": "store.activate", "slug": slug, "version": version, "release": release,
            "listing_id": LISTING, "payload": {"title": "Shadow Coaster"}, "files": ["p.pdf"]}


def test_an_issued_activation_grant_is_single_use_job_and_listing_bound():
    try:
        db, aid = _activation_policy_db()
        real = sp.effective
        with _On(), _Gates(aid=aid), patch.object(AA, "snapshot", _aa_snapshot), \
                patch.object(sp, "effective", lambda *a, **k: _with_actions(real(*a, **k))):
            out = SA.issue(db, slug=SLUG, version=VERSION, release=REL, job_id=51,
                           now=NOW + timedelta(minutes=1))
            body = out["content"]
            assert body["action"] == "store.activate" and body["listing_id"] == LISTING
            assert body["budget"]["slot_no"] == 1 and body["fee_cad"] == SA.fee_cad()
            assert SG.verify(SA.DOMAIN, body, out["seal"])
            assert not SG.verify(SG.DOMAIN, body, out["seal"])    # never a publish grant
            # A second one today is refused by the pace ceiling.
            _refused(lambda: SA.issue(db, slug=SLUG, version=VERSION, release=REL, job_id=52,
                                      now=NOW + timedelta(minutes=2)),
                     SA.ActivationRefused, "per day")
            gid = out["grant_id"]
            seg = f"seg:{gid}"
            ok = {"should_auto_renew": False}
            use = lambda **k: SA.use_refusal(  # noqa: E731
                db, k.pop("aid", seg), slug=SLUG, version=VERSION,
                **{"release": REL, "listing_id": LISTING, "job_id": 51, "remote": ok, **k})
            assert "not consumed by this job" in use()
            # Consumed only as an activation, only by its own job.
            _refused(lambda: SG.consume(db, gid, job_id=51, now=NOW + timedelta(minutes=3)),
                     SG.GrantRefused, "not store.publish")
            _refused(lambda: SG.consume(db, gid, job_id=99, action="store.activate",
                                        now=NOW + timedelta(minutes=3)),
                     SG.GrantRefused, "issued for job 51")
            SG.consume(db, gid, job_id=51, action="store.activate",
                       now=NOW + timedelta(minutes=3))
            _refused(lambda: SG.consume(db, gid, job_id=51, action="store.activate",
                                        now=NOW + timedelta(minutes=4)),
                     SG.GrantRefused, "used, expired or gone")
            assert use() is None
            assert "not consumed by this job" in use(job_id=52)
            assert "another listing" in use(listing_id="999")
            assert "another release" in use(release="b" * 64)
            assert "should_auto_renew" in use(remote={"should_auto_renew": True})
            assert "should_auto_renew" in use(remote={})
            assert "not a standing activation grant" in use(aid=str(gid))
            with patch.object(AA, "snapshot", lambda *a, **k: {**_aa_snapshot(*a, **k),
                                                                "payload": {"title": "X"}}):
                assert "no longer matches" in use()
        # Off again (the shipped state): the same consumed grant authorises nothing.
        assert use() == SA.OFF
    finally:
        _reset()


def test_a_publish_grant_is_never_consumed_or_used_as_an_activation():
    try:
        db, aid = _activation_policy_db()
        gid = _publish_grant(db, aid, job_id=0, consumed=False)
        with db.session() as s:
            s.get(SG.StandingGrant, gid).detail_json = {"action": "store.publish", "job_id": 5}
        _refused(lambda: SG.consume(db, gid, job_id=5, action="store.activate", now=NOW),
                 SG.GrantRefused, "not store.activate")
        with _On():
            why = SA.use_refusal(db, f"seg:{gid}", slug=SLUG, version=VERSION,
                                 listing_id=LISTING, release=REL, job_id=5,
                                 remote={"should_auto_renew": False})
            assert why is not None and "does not verify" in why, why
    finally:
        _reset()


def test_the_client_door_routes_a_standing_grant_and_passes_the_read_back():
    from brambleloop.integrations import etsy as E

    seen = {}

    def spy(db, approval_id, **k):
        seen.update(k, approval_id=approval_id)
        return "spied"
    with patch.object(SA, "use_refusal", spy), \
            patch("brambleloop.core.phase.effective", lambda db: "limited_production"), \
            patch.object(E, "PHASES_THAT_MAY_PUBLISH", ("limited_production",)):
        g = E.OwnerGrant(object(), action=E.OwnerGrant.ACTIVATE, approval_id="seg:3",
                         slug=SLUG, version=VERSION, release=REL, listing_id=LISTING, job_id=51)
        assert E._grant_refusal(g, action=E.OwnerGrant.ACTIVATE, listing_id=LISTING,
                                remote={"should_auto_renew": False}) == "spied"
    assert seen["job_id"] == 51 and seen["remote"] == {"should_auto_renew": False}
    assert seen["approval_id"] == "seg:3" and seen["listing_id"] == LISTING


def test_the_client_hands_a_standing_grant_the_listing_as_etsy_holds_it():
    from brambleloop.integrations import etsy_probe
    from brambleloop.integrations.etsy import OwnerGrant
    from test_etsy_transport import (PAYLOAD, FakeEtsy, _client, _verified_activation_grant,
                                     build_payload)
    from test_etsy_transport import _verified_publication_grant

    seen = []

    class _Standing(OwnerGrant):
        def refusal(self, *, action, listing_id="", remote=None):
            seen.append(remote)
            return None if action == self.action else "no"

    with FakeEtsy() as fake:
        client = _client(fake, phase="production", owner=True, shadow_writes=False)
        lid = client.create_draft(build_payload(**PAYLOAD),
                                  grant=_verified_publication_grant())
        client.upload_image(lid, filename="cover.png", data=etsy_probe.one_pixel_png(),
                            grant=_verified_activation_grant(lid))
        g = _Standing(None, action=OwnerGrant.ACTIVATE, approval_id="seg:7", slug="s",
                      version="1", listing_id=lid, job_id=3)
        client.activate(lid, launch_authorisation="LAUNCH-0-TEST", grant=g)
    reads = [r for r in seen if r is not None]
    assert reads and str(reads[-1].get("listing_id")) == str(lid), seen


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
