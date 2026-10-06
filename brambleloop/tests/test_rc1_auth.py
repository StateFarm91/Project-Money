"""rc1-AUTH: the independent audit's authority findings A1, D1-D4, kept as regressions.

Each test is the audit's reproduction turned into an assertion. Hermetic: synthetic local
evidence, a fake Etsy and a temporary SQLite database; no provider, model or network call.

* A1  store.activate honoured only the worker's boot-time phase: an owner rollback to shadow
      recorded after boot did not stop activation.
* D1  a copy of an old sealed phase-transition row appended after a rollback restored
      production (the seal bound content, not position).
* D2  revocation rows were unsealed: deleting one revived the grant; inserting one was
      accepted silently.
* D3  EtsyClient.activate/publish accepted any non-empty string / no grant at all.
* D4  upward phase transitions accepted arbitrary evidence strings.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import copy
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core import phase as P  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident, Phase  # noqa: E402
from phase_fixture import (record_phase_path, synthetic_evidence,  # noqa: E402
                           synthetic_readiness)

TOKEN = "rc1-auth-synthetic-owner-credential-not-a-secret"


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/rc1auth.sqlite")
    db.create_all()
    return db


def _open_incidents(db, signature: str) -> list:
    with db.session() as s:
        return [i for i in s.scalars(select(Incident).where(Incident.signature == signature))
                if not i.resolved]


# ---- A1 ------------------------------------------------------------------------------------


def test_A1_owner_rollback_recorded_after_boot_stops_store_activate():
    """auth1.py: grant approved, owner records rollback to shadow, worker still believes
    limited_production and the env flag is set. Before: activated=True, state active."""
    import test_etsy_readback_observe as f
    from brambleloop.ops import activation_authority as a

    db = f._db()
    orig = f._gates_pass()
    try:
        with patch.dict(os.environ, {"BRAMBLELOOP_PUBLISH_AUTHORISED": "1",
                                     "BRAMBLELOOP_OPS_TOKEN": TOKEN,
                                     "BRAMBLELOOP_PHASE": "limited_production"}):
            with f.FakeEtsy() as fake:
                product, lid = f._published(db, fake)
                record_phase_path(db, TOKEN, "limited_production")
                content = a.snapshot(db, product["slug"], product["version"])
                ident = a.approve(db, authorization=TOKEN, slug=product["slug"],
                                  version=product["version"],
                                  expected_digest=a.digest(content), reason="r")["approval_id"]
                P.record_transition(db, authorization=TOKEN, to="shadow",
                                    reason="owner rollback", env=os.environ)
                assert P.effective(db) == "shadow"
                with f._Patched(fake):
                    job = f._run(db, "store.activate",
                                 {"slug": product["slug"], "version": product["version"],
                                  "owner_activation_approval_id": ident},
                                 agent="store_operator", phase=Phase.LIMITED_PRODUCTION)
                assert fake.listings[lid]["state"] == "draft", fake.listings[lid]["state"]
                assert not (job.outputs or {}).get("activated"), job.outputs
                assert not [r for r in fake.requests if r["operation"] == "updateListing"]
                with db.session() as s:
                    refused = [r.detail for r in s.scalars(select(AuditLog).where(
                        AuditLog.action == "store.activate_refused"))]
                assert any(d.get("effective_phase") == "shadow" for d in refused), refused
    finally:
        f._restore(orig)


def test_A1_rollback_between_reservation_and_request_is_honoured_at_the_effect_boundary():
    """The phase is re-read at every effect boundary, not only at the top of the handler."""
    import test_etsy_readback_observe as f
    from brambleloop.finance import listing_costs
    from brambleloop.ops import activation_authority as a

    db = f._db()
    orig = f._gates_pass()
    try:
        with patch.dict(os.environ, {"BRAMBLELOOP_PUBLISH_AUTHORISED": "1",
                                     "BRAMBLELOOP_OPS_TOKEN": TOKEN,
                                     "BRAMBLELOOP_PHASE": "limited_production"}):
            with f.FakeEtsy() as fake:
                product, lid = f._published(db, fake)
                record_phase_path(db, TOKEN, "limited_production")
                content = a.snapshot(db, product["slug"], product["version"])
                ident = a.approve(db, authorization=TOKEN, slug=product["slug"],
                                  version=product["version"],
                                  expected_digest=a.digest(content), reason="r")["approval_id"]
                original = listing_costs.reserve

                def reserve_then_rollback(*args, **kw):
                    out = original(*args, **kw)
                    P.record_transition(db, authorization=TOKEN, to="shadow",
                                        reason="owner rollback mid-flight")
                    return out

                with f._Patched(fake), patch.object(listing_costs, "reserve",
                                                    reserve_then_rollback):
                    job = f._run(db, "store.activate",
                                 {"slug": product["slug"], "version": product["version"],
                                  "owner_activation_approval_id": ident},
                                 agent="store_operator", phase=Phase.LIMITED_PRODUCTION)
                assert fake.listings[lid]["state"] == "draft"
                assert job.outputs["activated"] is False, job.outputs
                assert "phase" in " ".join(job.outputs["reasons"]), job.outputs
    finally:
        f._restore(orig)


def test_A1_live_worker_reresolves_the_phase_per_job_and_protected_phase_is_restrictive():
    from brambleloop.agents.registry import Registry
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import HandlerRegistry, Worker, protected_phase

    db = _db()
    Registry(db).seed_defaults()
    seen: list[tuple[str, str]] = []
    reg = HandlerRegistry()

    @reg.register("ops.queue_check")
    def _probe(ctx):
        seen.append((ctx.phase.value, protected_phase(ctx).value))
        return {}

    with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": TOKEN,
                                 "BRAMBLELOOP_PHASE": "limited_production"}):
        record_phase_path(db, TOKEN, "limited_production")
        assert P.effective(db) == "limited_production"
        worker = Worker(db, "live", phase=P.effective_phase(db), registry=reg, live_phase=True)
        boot = Worker(db, "boot", phase=Phase.LIMITED_PRODUCTION, registry=reg)
        q = JobQueue(db)
        q.enqueue("orchestrator", "ops.queue_check", {}, idempotency_key="j1")
        assert worker.run_once()
        P.record_transition(db, authorization=TOKEN, to="shadow", reason="owner rollback")
        q.enqueue("orchestrator", "ops.queue_check", {}, idempotency_key="j2")
        assert worker.run_once()
        q.enqueue("orchestrator", "ops.queue_check", {}, idempotency_key="j3")
        assert boot.run_once()
    assert seen[0] == ("limited_production", "limited_production"), seen
    assert seen[1] == ("shadow", "shadow"), seen          # live worker: next job is shadow
    assert seen[2] == ("limited_production", "shadow"), seen  # boot-phase worker: effect
    # boundaries still resolve the owner's rollback through protected_phase


def test_A1_deployed_workers_are_built_live():
    entry = (ROOT / "src/brambleloop/app/worker_entry.py").read_text()
    runner = (ROOT / "src/brambleloop/app/runner.py").read_text()
    assert "live_phase=True" in entry and "live_phase=True" in runner


# ---- D1 ------------------------------------------------------------------------------------


def _record_up_to_production(db):
    for t in P.ORDER[1:]:
        P.record_transition(db, authorization=TOKEN, to=t, reason="up",
                            evidence_refs=synthetic_evidence(db), env={P.ENV_VAR: t},
                            readiness_verdict=synthetic_readiness)


def test_D1_replayed_old_sealed_production_row_does_not_restore_production():
    """auth2.py part 1. Before: 'after replay of old sealed row: production True'."""
    db = _db()
    env = {P.ENV_VAR: "production"}
    with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": TOKEN}):
        _record_up_to_production(db)
        assert P.resolve(db, env)["phase"] == "production"
        P.record_transition(db, authorization=TOKEN, to="shadow", reason="incident rollback",
                            env=env)
        assert P.resolve(db, env)["phase"] == "shadow"
        with db.session() as s:
            old = [r for r in s.scalars(select(AuditLog).where(AuditLog.action == P.TRANSITION)
                                        .order_by(AuditLog.id)) if r.detail["to"] == "production"][0]
            s.add(AuditLog(actor=old.actor, action=old.action, artifact=old.artifact,
                           detail=copy.deepcopy(old.detail)))
        r = P.resolve(db, env)
        assert r["phase"] == "shadow" and r["mismatch"] and r["record"]["valid"] is False, r
        assert "chain" in r["record"]["why"], r["record"]
        # restrictive phase AND an incident
        assert P.effective(db, env) == "shadow"
        assert _open_incidents(db, P.INCIDENT_SIGNATURE)
        # nothing but a rebase down to shadow may be recorded over the broken chain
        try:
            P.record_transition(db, authorization=TOKEN, to="staging", reason="x",
                                evidence_refs=synthetic_evidence(db))
            raise AssertionError("moved up over a broken chain")
        except ValueError:
            pass
        out = P.record_transition(db, authorization=TOKEN, to="shadow", reason="rebase")
        assert out["rebase"] is True and out["seq"] == 1
        assert P.resolve(db, {P.ENV_VAR: "shadow"})["agree"] is True
        # and the chain then continues normally
        record_phase_path(db, TOKEN, "staging")
        assert P.resolve(db, {P.ENV_VAR: "staging"})["phase"] == "staging"


def test_D1_deleted_inserted_and_copied_rows_break_the_chain():
    env = {P.ENV_VAR: "production"}
    with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": TOKEN}):
        # deleting a middle row (e.g. the rollback that preceded a later reaffirm)
        db = _db()
        _record_up_to_production(db)
        with db.session() as s:
            rows = list(s.scalars(select(AuditLog).where(AuditLog.action == P.TRANSITION)
                                  .order_by(AuditLog.id)))
            assert [r.detail["seq"] for r in rows] == [1, 2, 3]
            s.delete(rows[1])
        assert P.resolve(db, env)["phase"] == "shadow"
        # a copied genesis row appended later is not a genesis
        db = _db()
        P.record_transition(db, authorization=TOKEN, to="staging", reason="up",
                            evidence_refs=synthetic_evidence(db),
                            readiness_verdict=synthetic_readiness)
        P.record_transition(db, authorization=TOKEN, to="shadow", reason="down")
        with db.session() as s:
            first = s.scalar(select(AuditLog).where(AuditLog.action == P.TRANSITION)
                             .order_by(AuditLog.id).limit(1))
            s.add(AuditLog(actor=first.actor, action=first.action, artifact=first.artifact,
                           detail=copy.deepcopy(first.detail)))
        assert P.resolve(db, {P.ENV_VAR: "staging"})["phase"] == "shadow"
        # history marks the replayed row invalid while the genuine rows stay valid
        hist = P.history(db)
        assert hist[0]["valid"] is False and all(h["valid"] for h in hist[1:]), hist


# ---- D2 ------------------------------------------------------------------------------------


def _sealed_publication_grant(db, pa, scope="s@1"):
    """auth2.py's grant: written through the ledger so it is a genuine chain link."""
    now = pa._now()
    detail = {"principal": pa.PRINCIPAL, "action": pa.ACTION, "scope": scope, "release": "r",
              "content": {}, "digest": pa.digest({}), "reason": "x",
              "approved_at": now.isoformat(),
              "expires_at": (now + timedelta(hours=pa.GRANT_HOURS)).isoformat()}
    return pa.LEDGER.append(db, action=pa.APPROVED, artifact=scope, detail=detail)


def test_D2_deleting_a_revocation_does_not_revive_the_grant_and_opens_an_incident():
    """auth2.py part 2. Before: 'after deleting revocation row: refusal= None'."""
    from brambleloop.ops import publication_authority as pa

    db = _db()
    with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": TOKEN}):
        gid = _sealed_publication_grant(db, pa)
        check = lambda: pa._check_one(db, gid, slug="s", version="1", release="r",  # noqa: E731
                                      current={})
        assert check() is None
        pa.revoke(db, authorization=TOKEN, approval_id=gid)
        assert "revoked" in check()
        with db.session() as s:
            rev = s.scalar(select(AuditLog).where(AuditLog.action == pa.REVOKED))
            assert rev.detail["seal"] and rev.detail["grant_seal"]  # sealed, bound to grant
        # a later chain row (another grant) makes the deletion a broken link
        _sealed_publication_grant(db, pa, scope="t@1")
        with db.session() as s:
            for r in s.scalars(select(AuditLog).where(AuditLog.action == pa.REVOKED)):
                s.delete(r)
        why = check()
        assert why is not None and "chain does not verify" in why, why
        assert _open_incidents(db, f"authority_chain_tamper:{pa.ACTION}")
        # the owner re-anchors; every earlier grant stays void
        pa.rebase(db, authorization=TOKEN, reason="revocation row deleted")
        assert "rebase" in check()
        assert not _open_incidents(db, f"authority_chain_tamper:{pa.ACTION}")
        fresh = _sealed_publication_grant(db, pa)
        assert pa._check_one(db, fresh, slug="s", version="1", release="r", current={}) is None


def test_D2_an_unsealed_inserted_revocation_revokes_and_is_reported_as_tampering():
    from brambleloop.ops import activation_authority as aa
    from brambleloop.ops import publication_authority as pa

    db = _db()
    with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": TOKEN}):
        gid = _sealed_publication_grant(db, pa)
        with db.session() as s:
            s.add(AuditLog(actor=pa.PRINCIPAL, action=pa.REVOKED, artifact=str(gid),
                           detail={"approval_id": gid}))
        why = pa._check_one(db, gid, slug="s", version="1", release="r", current={})
        assert why is not None and "revoked" in why and "tamper" in why, why
        assert _open_incidents(db, f"authority_chain_tamper:{pa.ACTION}")
        # the same ledger guards activation grants
        content = {"action": "store.activate", "listing_id": "9"}
        with patch.object(aa, "snapshot", return_value=content):
            ident = aa.approve(db, authorization=TOKEN, slug="x", version="1",
                               expected_digest=aa.digest(content), reason="r")["approval_id"]
            assert aa.validate(db, ident, slug="x", version="1", listing_id="9") is None
            aa.revoke(db, authorization=TOKEN, approval_id=ident)
            aa.approve(db, authorization=TOKEN, slug="x", version="1",
                       expected_digest=aa.digest(content), reason="r2")
            with db.session() as s:
                for r in s.scalars(select(AuditLog).where(AuditLog.action == aa.REVOKED)):
                    s.delete(r)
            why = aa.validate(db, ident, slug="x", version="1", listing_id="9")
            assert why is not None, "deleting an activation revocation revived the grant"
            assert _open_incidents(db, "authority_chain_tamper:store.activate")


def test_D2_chain_rows_are_protected_from_retention():
    from brambleloop.ops import retention
    from brambleloop.ops import activation_authority as aa
    from brambleloop.ops import publication_authority as pa

    for action in (P.TRANSITION, pa.APPROVED, pa.REVOKED, pa.REBASED, aa.APPROVED, aa.REVOKED,
                   aa.REBASED):
        assert action in retention.PROTECTED_ACTIONS, action


# ---- D3 ------------------------------------------------------------------------------------


def test_D3_client_activate_requires_a_validated_grant_object():
    from test_etsy_transport import (FakeEtsy, PAYLOAD, _client, _verified_activation_grant,
                                     _verified_publication_grant)
    from brambleloop.integrations import etsy_probe
    from brambleloop.integrations.etsy import EtsyNotPermitted, OwnerGrant, build_payload

    db = _db()
    with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": TOKEN,
                                 "BRAMBLELOOP_PHASE": "production"}):
        record_phase_path(db, TOKEN, "production")
        with FakeEtsy() as fake:
            client = _client(fake, phase="production", owner=True, shadow_writes=False)
            lid = client.create_draft(build_payload(**PAYLOAD),
                                      grant=_verified_publication_grant())
            client.upload_image(lid, filename="cover.png", data=etsy_probe.one_pixel_png(),
                                grant=_verified_activation_grant(lid))
            client.attach_file(lid, filename="pattern.pdf", data=b"%PDF-1.7 bytes",
                               grant=_verified_activation_grant(lid))
            # the audit's read-only repro: any non-empty string used to pass
            for grant in (None, "x", 1):
                try:
                    client.activate(lid, launch_authorisation="x", grant=grant)
                    raise AssertionError(f"activated with grant={grant!r}")
                except EtsyNotPermitted as e:
                    assert "OwnerGrant" in str(e), e
            # an OwnerGrant naming no recorded grant is refused before updateListing
            bogus = OwnerGrant(db, action=OwnerGrant.ACTIVATE, approval_id=424242,
                               slug="s", version="1", listing_id=lid)
            try:
                client.activate(lid, launch_authorisation="x", grant=bogus)
                raise AssertionError("activated on a grant id that names nothing")
            except EtsyNotPermitted as e:
                assert "refused at the client" in str(e), e
            # a grant for publication does not authorise activation
            wrong = OwnerGrant(db, action=OwnerGrant.PUBLISH, approval_id=1, slug="s",
                               version="1")
            try:
                client.activate(lid, launch_authorisation="x", grant=wrong)
                raise AssertionError("a publication grant activated a listing")
            except EtsyNotPermitted:
                pass
            assert not [r for r in fake.requests if r["operation"] == "updateListing"]
            assert client.get_listing(lid)["state"] == "draft"
        # the client also re-reads the live phase: shadow recorded -> refused
        P.record_transition(db, authorization=TOKEN, to="shadow", reason="rollback")
        g = OwnerGrant(db, action=OwnerGrant.ACTIVATE, approval_id=1, slug="s", version="1",
                       listing_id="1")
        assert "phase" in g.refusal(action=OwnerGrant.ACTIVATE, listing_id="1")


# ---- D4 ------------------------------------------------------------------------------------


def test_D4_upward_evidence_refs_must_resolve_to_real_recent_passing_records():
    db = _db()
    with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": TOKEN}):
        def up(to, refs):
            return P.record_transition(db, authorization=TOKEN, to=to, reason="up",
                                       evidence_refs=refs,
                                       readiness_verdict=synthetic_readiness)

        def refused(to, refs, needle):
            try:
                up(to, refs)
            except ValueError as e:
                assert needle in str(e), e
                return
            raise AssertionError(f"accepted {refs}")

        refused("staging", {"readiness": "r", "rollback": "b"}, "must be the id")
        refused("staging", {"readiness": "999999", "rollback": "999998"}, "does not resolve")
        with db.session() as s:
            other = AuditLog(actor="x", action="something.else", detail={"ready": True})
            s.add(other)
            s.flush()
            other_id = str(other.id)
        good = synthetic_evidence(db)
        refused("staging", {**good, "readiness": other_id}, "does not resolve")
        # a real but failing assessment is enough for staging, not for limited_production
        with db.session() as s:
            failing = AuditLog(actor="orchestrator", action="launch.assessed",
                               detail={"ready": False})
            s.add(failing)
            s.flush()
            failing_id = str(failing.id)
        out = up("staging", {**good, "readiness": failing_id})
        assert out["evidence"]["readiness"]["passing"] is False
        refused("limited_production", {**good, "readiness": failing_id}, "does not pass")
        # stale evidence
        with db.session() as s:
            row = s.get(AuditLog, int(good["rollback"]))
            row.at = row.at - timedelta(days=P.EVIDENCE_MAX_AGE_DAYS["rollback"] + 1)
        refused("limited_production", good, "days old")
        out = up("limited_production", synthetic_evidence(db))
        assert out["evidence"]["rollback"]["passing"] is True


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    for fn in TESTS:
        try:
            fn()
            print("OK  ", fn.__name__)
        except Exception as exc:  # noqa: BLE001
            import traceback

            failed += 1
            traceback.print_exc()
            print("FAIL", fn.__name__, repr(exc))
    print(f"{len(TESTS) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
