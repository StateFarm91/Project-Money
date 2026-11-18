"""WS4-0a (design ddde00cc §2.2, F-A): owner publication and activation grants are Ed25519.

The weakness closed here: grant rows were HMAC-SHA256 under the ops token, and verification
recomputed the HMAC, so any process able to VERIFY a grant (the worker) could MINT one. Now:

* a grant row verifies only under the owner-grant public key;
* a row "sealed" with the ops token (what a compromised worker could produce) is refused;
* approving or rebasing is signed only inside the Command Center owner request; a bearer call
  (the operator route) refuses; a revocation (tightening) does not need the owner request;
* a dedicated worker scrubs the signing key and refuses to sign; a process holding only the
  verify key cannot sign;
* each family signs under its own domain: a publication row never verifies as activation;
* a chain still holding rows sealed under the retired HMAC names that cause, and one owner
  rebase (signed, in the owner request) re-anchors it.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws4_0_owner_grant_keys.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702  (also gives this process its own grant key pair)
import hashlib
import hmac
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.core import owner_grant_keys as K  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.ops import activation_authority as act  # noqa: E402
from brambleloop.ops import publication_authority as pub  # noqa: E402

OPS_TOKEN = "ws4-0-test-operator-token-" + "q" * 20


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/g.sqlite", scratch=True)
    db.create_all()
    return db


def _grant_body(slug="p", version="1") -> dict:
    return {"principal": pub.PRINCIPAL, "action": pub.ACTION, "scope": f"{slug}@{version}",
            "release": "r" * 64, "content": {"x": 1}, "digest": "d" * 64, "reason": "test",
            "approved_at": "2026-11-12T00:00:00+00:00",
            "expires_at": "2026-11-13T00:00:00+00:00"}


def _owner():
    return K.owner_request("test-owner-session")


def test_an_owner_signed_row_verifies_and_an_edited_one_does_not():
    db = _db()
    with _owner():
        gid = pub.LEDGER.append(db, action=pub.APPROVED, artifact="p@1", detail=_grant_body())
    with db.session() as s:
        detail = dict(s.get(AuditLog, gid).detail)
    assert len(detail["seal"]) == 128                     # an Ed25519 signature, not an HMAC
    assert pub.LEDGER.verify_row(detail) is None
    assert pub.LEDGER.refusal(db, gid) is None
    edited = {**detail, "digest": "e" * 64}
    assert pub.LEDGER.verify_row(edited) is not None


def test_a_row_sealed_with_the_ops_token_is_refused_F_A():
    """What a compromised worker could forge before WS4-0: an HMAC under the ops token."""
    os.environ["BRAMBLELOOP_OPS_TOKEN"] = OPS_TOKEN
    body = {**_grant_body(), "event": pub.APPROVED, "seq": 1, "prev_id": None, "prev_seal": ""}
    forged = hmac.new(OPS_TOKEN.encode(), json.dumps(body, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=True, default=str).encode(),
                      hashlib.sha256).hexdigest()
    why = pub.LEDGER.verify_row({**body, "seal": forged})
    assert why and "retired ops-token HMAC" in why, why
    db = _db()
    with db.session() as s:
        s.add(AuditLog(actor=pub.PRINCIPAL, action=pub.APPROVED, artifact="p@1",
                       detail={**body, "seal": forged}))
    chain = pub.LEDGER.chain(db, record_incident=False)
    assert chain["valid"] is False and "retired ops-token HMAC" in chain["why"], chain


def test_approve_and_rebase_refuse_outside_the_owner_request_and_revoke_does_not():
    db = _db()
    for action in (pub.APPROVED, pub.REBASED):
        try:
            pub.LEDGER.append(db, action=action, artifact="p@1", detail=_grant_body())
        except ValueError as exc:
            assert "Command Center request" in str(exc), exc
        else:
            raise AssertionError(f"{action} was signed outside the owner request")
    try:
        pub.LEDGER.rebase(db, "no owner request")
    except ValueError as exc:
        assert "Command Center request" in str(exc), exc
    else:
        raise AssertionError("a rebase was signed outside the owner request")
    with _owner():
        gid = pub.LEDGER.append(db, action=pub.APPROVED, artifact="p@1", detail=_grant_body())
    rid = pub.LEDGER.revoke(db, gid)                      # tightening: no owner request needed
    assert rid and pub.LEDGER.refusal(db, gid) == "owner publication grant revoked"


def test_f2f_only_an_exact_revocation_body_signs_outside_the_owner_request():
    """Review 5060fcc7 F2f / INFO-4: outside the owner request a body signs only if it has
    EXACTLY the revocation keys (plus the optional rebase link) and an exact
    `owner.<family>.revoked` event -- an extra key, a missing key, or a suffix-only event is
    refused."""
    base = {"principal": pub.PRINCIPAL, "approval_id": 1, "grant_seal": "s" * 128,
            "revoked_at": "2026-11-12T09:00:00+00:00", "event": pub.REVOKED, "seq": 2,
            "prev_id": 1, "prev_seal": "p" * 128}
    assert K.is_signature(K.sign("brambleloop/test-domain/v1", base))
    assert K.is_signature(K.sign("brambleloop/test-domain/v1", {**base, "rebase": True}))
    bad = [
        {**base, "content": {"slug": "p"}},                       # an extra key
        {**base, "expires_at": "2099-01-01T00:00:00+00:00"},      # another extra key
        {k: v for k, v in base.items() if k != "grant_seal"},     # a missing key
        {**base, "event": "owner.publication.approved\n.revoked"},  # suffix only
        {**base, "event": "x.revoked"},
        {**base, "event": pub.APPROVED},
    ]
    assert len(bad) == 6
    for body in bad:
        try:
            K.sign("brambleloop/test-domain/v1", body)
        except ValueError as exc:
            assert "Command Center request" in str(exc), (body, exc)
        else:
            raise AssertionError(f"signed outside the owner request: {sorted(body)}")


def test_the_bearer_route_approve_refuses_with_the_reason():
    """`publication_authority.approve` / `activation_authority.approve` called the way the
    operator bearer route calls them (a valid ops token, no owner request) never sign."""
    os.environ["BRAMBLELOOP_OPS_TOKEN"] = OPS_TOKEN
    db = _db()
    from unittest.mock import patch

    for mod in (pub, act):
        with patch.object(mod, "snapshot", return_value={"x": 1}), \
                patch("brambleloop.visual.experiment.refuse_if_experiment", lambda *a, **k: None):
            try:
                mod.approve(db, authorization=f"Bearer {OPS_TOKEN}", slug="p", version="1",
                            release="r" * 64, expected_digest=mod.digest({"x": 1}),
                            reason="operator")
            except ValueError as exc:
                assert "Command Center request" in str(exc), (mod.__name__, exc)
            else:
                raise AssertionError(f"{mod.__name__}.approve signed on the bearer route")


def test_a_job_process_never_signs_and_its_key_is_scrubbed():
    saved = dict(os.environ)
    try:
        assert os.environ.get(K.SIGNING_KEY_VAR)
        assert K.mark_job_process() is True
        assert K.SIGNING_KEY_VAR not in os.environ
        assert K.signing_refusal() == "this process runs jobs, so it may never sign an owner grant"
        with _owner():
            try:
                K.sign(pub.DOMAIN, {"event": pub.APPROVED})
            except ValueError as exc:
                assert "runs jobs" in str(exc), exc
            else:
                raise AssertionError("a job process signed an owner grant")
    finally:
        K._JOB_PROCESS["is"] = False
        os.environ.clear()
        os.environ.update(saved)


def test_a_process_with_only_the_verify_key_cannot_sign_but_can_verify():
    db = _db()
    with _owner():
        gid = pub.LEDGER.append(db, action=pub.APPROVED, artifact="p@1", detail=_grant_body())
    signing = os.environ.pop(K.SIGNING_KEY_VAR)
    try:
        assert pub.LEDGER.refusal(db, gid) is None            # verifies with the public key
        with _owner():
            try:
                K.sign(pub.DOMAIN, {"event": pub.APPROVED})
            except ValueError as exc:
                assert "signing key unavailable" in str(exc), exc
            else:
                raise AssertionError("signed without the signing key")
    finally:
        os.environ[K.SIGNING_KEY_VAR] = signing


def test_each_family_signs_under_its_own_domain():
    body = {**_grant_body(), "event": pub.APPROVED}
    with _owner():
        sig = K.sign(pub.DOMAIN, body)
    assert K.verify(pub.DOMAIN, body, sig) is True
    assert K.verify(act.DOMAIN, body, sig) is False
    assert pub.DOMAIN != act.DOMAIN


def test_a_missing_verify_key_refuses_every_grant():
    db = _db()
    with _owner():
        gid = pub.LEDGER.append(db, action=pub.APPROVED, artifact="p@1", detail=_grant_body())
    verify = os.environ.pop(K.VERIFY_KEY_VAR)
    try:
        why = pub.LEDGER.refusal(db, gid)
        assert why and "does not verify" in why, why
    finally:
        os.environ[K.VERIFY_KEY_VAR] = verify


def test_a_legacy_hmac_chain_is_re_anchored_by_one_owner_rebase():
    """Deploy path: the family still holds pre-WS4-0 HMAC rows. The chain names the cause; the
    owner records one signed rebase in the Command Center; a new grant then works."""
    os.environ["BRAMBLELOOP_OPS_TOKEN"] = OPS_TOKEN
    db = _db()
    body = {**_grant_body(), "event": pub.APPROVED, "seq": 1, "prev_id": None, "prev_seal": ""}
    legacy = hmac.new(OPS_TOKEN.encode(), json.dumps(body, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=True, default=str).encode(),
                      hashlib.sha256).hexdigest()
    with db.session() as s:
        row = AuditLog(actor=pub.PRINCIPAL, action=pub.APPROVED, artifact="p@1",
                       detail={**body, "seal": legacy})
        s.add(row)
        s.flush()
        legacy_id = row.id
    try:
        with _owner():
            pub.LEDGER.append(db, action=pub.APPROVED, artifact="p@1", detail=_grant_body())
    except ValueError as exc:
        assert "rebase" in str(exc), exc
    else:
        raise AssertionError("a grant was appended to a chain that does not verify")
    with _owner():
        pub.LEDGER.rebase(db, "WS4-0a: re-anchor after the Ed25519 migration")
        gid = pub.LEDGER.append(db, action=pub.APPROVED, artifact="p@1", detail=_grant_body())
    assert pub.LEDGER.chain(db, record_incident=False)["valid"] is True
    assert pub.LEDGER.refusal(db, gid) is None
    assert "predates" in (pub.LEDGER.refusal(db, legacy_id) or ""), pub.LEDGER.refusal(
        db, legacy_id)


def test_the_activation_family_is_asymmetric_too():
    db = _db()
    body = {"principal": act.PRINCIPAL, "action": "store.activate", "content": {"x": 1},
            "digest": "d" * 64, "reason": "t", "approved_at": "2026-11-12T00:00:00+00:00",
            "expires_at": "2026-11-13T00:00:00+00:00"}
    with _owner():
        gid = act.LEDGER.append(db, action=act.APPROVED, artifact="p@1", detail=body)
    assert act.LEDGER.refusal(db, gid) is None
    with db.session() as s:
        detail = dict(s.get(AuditLog, gid).detail)
    assert len(detail["seal"]) == 128
    assert act.LEDGER.verify_row({**detail, "content": {"x": 2}}) is not None


def test_every_worker_entry_scrubs_the_owner_grant_key():
    src = ROOT / "src" / "brambleloop" / "app"
    for name in ("worker_entry.py", "hq_worker.py"):
        text = (src / name).read_text()
        # review 6817118202 F6 (R9): the OWNER-GRANT scrub specifically, not any
        # mark_job_process() (the storefront's satisfies a substring check)
        assert "_ogk.mark_job_process()" in text, name
    api = (src / "command_center" / "api.py").read_text()
    assert '_ogk.owner_request(auth.current_public_id(request) or "owner")' in api
    # F6 (R8): the route enters the owner request ONLY for the approve and rebase actions.
    from brambleloop.app.command_center import api as cc_api

    src_api = (src / "command_center" / "api.py").read_text()
    seg = src_api[src_api.index("OWNER_GRANT_SIGNING_ACTIONS = ("):]
    declared = seg[:seg.index(")") + 1]
    for action in ("publication.approve", "publication.rebase", "activation.approve",
                   "activation.rebase"):
        assert f'"{action}"' in declared, action
    for action in ("publication.preview", "publication.revoke", "activation.preview",
                   "activation.revoke"):
        assert f'"{action}"' not in declared, action
    assert "elif action in OWNER_GRANT_SIGNING_ACTIONS:" in src_api
    assert cc_api is not None


def test_ws4_0c_the_publication_snapshot_binds_the_shop():
    """WS4-0c: the content a publication grant binds names the Etsy shop; another shop is
    another digest, so a grant approved for one shop never creates in another."""
    from unittest.mock import patch

    db = _db()
    saved = os.environ.get("ETSY_SHOP_ID")
    try:
        os.environ["ETSY_SHOP_ID"] = "1111"
        assert pub._shop_id(db) == "1111"
        os.environ.pop("ETSY_SHOP_ID")
        with patch("brambleloop.integrations.etsy_shop_binding.bound_shop_id",
                   return_value="2222"):
            assert pub._shop_id(db) == "2222"
    finally:
        if saved is None:
            os.environ.pop("ETSY_SHOP_ID", None)
        else:
            os.environ["ETSY_SHOP_ID"] = saved
    src = (ROOT / "src/brambleloop/ops/publication_authority.py").read_text()
    snap = src[src.index("def snapshot("):src.index("# ---- F-704")]
    assert '"shop_id": _shop_id(db)' in snap

def test_review_f2_a_revocation_label_cannot_carry_a_grant_body():
    """Review 6817118202 F2 (exploit E3): outside the owner request, a full grant body labelled
    `event: owner.publication.revoked` is not signable; and a row whose signed event differs
    from its recorded action is refused by the chain and by the grant check."""
    body = {**_grant_body(), "event": pub.REVOKED, "seq": 1, "prev_id": None, "prev_seal": ""}
    try:
        K.sign(pub.DOMAIN, body)
    except ValueError as exc:
        assert "Command Center request" in str(exc), exc
    else:
        raise AssertionError("a grant body relabelled 'revoked' was signed outside the owner "
                             "request")
    # Even a correctly signed revocation-labelled body, filed as an approval, is refused.
    db = _db()
    with _owner():
        sig = K.sign(pub.DOMAIN, body)
    with db.session() as s:
        row = AuditLog(actor=pub.PRINCIPAL, action=pub.APPROVED, artifact="p@1",
                       detail={**body, "seal": sig})
        s.add(row)
        s.flush()
        rid = row.id
    chain = pub.LEDGER.chain(db, record_incident=False)
    assert chain["valid"] is False and "signed event" in chain["why"], chain
    assert pub.LEDGER.refusal(db, rid) is not None
    # an exact revocation body is still signable outside the request (it only tightens)
    exact = {"principal": pub.PRINCIPAL, "approval_id": 1, "grant_seal": "x",
             "revoked_at": "2026-11-12T00:00:00+00:00", "event": pub.REVOKED, "seq": 2,
             "prev_id": 1, "prev_seal": "y"}
    assert K.is_signature(K.sign(pub.DOMAIN, exact))


def test_review_f1_the_completion_verifier_verifies_outside_the_owner_request():
    """Review 6817118202 F1: `store.publish.complete`'s grant check runs in the WORKER, outside
    any owner request, and must verify with the public key -- never re-sign."""
    from types import SimpleNamespace

    from brambleloop.integrations.etsy import _completion_grant_row_refusal

    db = _db()
    body = _grant_body()
    body["approved_at"] = "2020-01-01T00:00:00+00:00"
    body["expires_at"] = "2999-01-01T00:00:00+00:00"
    with _owner():
        gid = pub.LEDGER.append(db, action=pub.APPROVED, artifact="p@1", detail=body)
    assert not K.in_owner_request()
    grant = SimpleNamespace(db=db, slug="p", version="1", release="r" * 64)
    assert _completion_grant_row_refusal(grant, pub, gid) is None
    signing = os.environ.pop(K.SIGNING_KEY_VAR)          # a worker holds only the verify key
    try:
        assert _completion_grant_row_refusal(grant, pub, gid) is None
    finally:
        os.environ[K.SIGNING_KEY_VAR] = signing
    src = (ROOT / "src/brambleloop/integrations/etsy.py").read_text()
    fn = src[src.index("def _completion_grant_row_refusal"):]
    fn = fn[:fn.index("\ndef ")]
    assert "pa._seal(" not in fn and "pa._verify(detail, seal)" in fn


def test_review_f5_a_signature_is_exactly_128_lowercase_hex():
    body = {**_grant_body(), "event": pub.APPROVED}
    with _owner():
        sig = K.sign(pub.DOMAIN, body)
    assert K.is_signature(sig) and K.verify(pub.DOMAIN, body, sig)
    for bad in (sig.upper(), sig + "0", sig[:-1], " " + sig[1:], ""):
        assert not K.is_signature(bad) and K.verify(pub.DOMAIN, body, bad) is False, bad


def test_new_rows_name_the_command_center():
    assert pub.PRINCIPAL == act.PRINCIPAL == "owner:command-center"
    assert "never on the worker" in K.deployment_note() or "never SET on the worker" in (
        K.deployment_note())

if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(e))
    print(f"PASS: {fails} failing" if not fails else f"FAILED: {fails} failing")
    sys.exit(1 if fails else 0)
