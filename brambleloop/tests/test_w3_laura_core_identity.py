"""W3 lane D: Laura's canonical identity is durable, verified and owner-controlled (D-FB-13).

Identity immutability: agents (Laura included) cannot alter it or expand her authority; the
owner can only with an authorised decision recorded in DECISION_LOG; the history is
append-only and a tampered row stops everything that depends on her.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import text  # noqa: E402

from brambleloop.agents.registry import (DEFAULT_AGENTS, FORBIDDEN_COMBINATIONS,  # noqa: E402
                                         Registry)
from brambleloop.autonomy import charters  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.laura import identity  # noqa: E402
from brambleloop.laura.core import identity as core_identity  # noqa: E402
from brambleloop.laura.core.models import (ImmutableRecordError,  # noqa: E402
                                           LauraIdentityVersion)
from brambleloop.visual import canonical  # noqa: E402


def boot() -> Database:
    tmp = tempfile.mkdtemp(prefix="w3d-id-")
    db = Database(f"sqlite:///{tmp}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _refused(fn, exc=identity.IdentityRefused) -> str:
    try:
        fn()
    except exc as e:
        return str(e)
    raise AssertionError(f"{fn} was not refused")


def test_genesis_record_is_pinned_and_carries_the_ruled_identity():
    g = identity.genesis()
    assert identity.sha256_of(g) == identity.GENESIS_SHA256
    assert g["name"] == "Laura" and g["role"] == "Founder/CEO"
    assert g["kind"] == "persistent AI person"
    assert g["visual_identity"]["identity_id"] == canonical.IDENTITY_ID == "laura-v15-a42aeac7"
    assert identity.VISUAL_IDENTITY_ID == "laura-v15-a42aeac7"
    assert g["visual_identity"]["publication_approved"] is False
    assert set(("D-FB-11", "D-FB-12", "D-FB-13")) <= set(g["rulings"])
    assert g["authority"]["spend_ceiling_cad"] == 0.0
    assert g["authority"]["own_job_types"] == ["laura.executive_tick"]
    assert set(g["constitution"]["may_block_her"]) == {"finance", "product_truth", "security"}
    assert g["voice"]["register"] == "public_business"
    assert "never claimed to be biologically human" in " ".join(g["voice"]["truth"])
    # a copy: mutating it does not touch the canonical record
    g["name"] = "Someone else"
    assert identity.genesis()["name"] == "Laura"


def test_public_record_holds_nothing_from_the_private_register():
    blob = core_identity.canonical_json(identity.genesis()).lower()
    for word in ("spouse's", "sexual", "flirtatious", "intimate", "husband", "wife",
                 "relationship memory"):
        assert word not in blob, word
    prof = identity.public_profile()
    assert prof["portrait_publication_approved"] is False
    assert prof["public_identity"] == "Brambleloop's AI founder"


def test_genesis_is_written_once_and_verified_on_every_load():
    db = boot()
    a = identity.current(db)
    b = identity.current(db)
    assert a["version"] == b["version"] == 1
    assert a["sha256"] == identity.GENESIS_SHA256
    with db.session() as s:
        assert s.query(LauraIdentityVersion).count() == 1
    assert identity.summary(db)["status"] == "OK"


def test_agents_and_laura_herself_cannot_change_her_identity_or_authority():
    db = boot()
    identity.ensure(db)
    for actor in ("laura", "coo", "orchestrator", "learn", "claude", "finance"):
        why = _refused(lambda a=actor: identity.amend(
            db, {"authority": {**identity.genesis()["authority"], "spend_ceiling_cad": 500.0}},
            owner_decision_id="D-FB-13", actor=a, reason="expand authority"))
        assert "owner-controlled" in why, why
    # the owner without an authorised decision is refused too
    why = _refused(lambda: identity.amend(db, {"role": "COO"}, owner_decision_id="",
                                          actor="owner", reason="change role"))
    assert "AUTHORISED_IDENTITY_AMENDMENTS" in why
    why = _refused(lambda: identity.amend(db, {"role": "COO"}, owner_decision_id="D-FB-13",
                                          actor="owner", reason="change role"))
    assert "AUTHORISED_IDENTITY_AMENDMENTS" in why
    assert identity.AUTHORISED_IDENTITY_AMENDMENTS == ()
    assert identity.current(db)["version"] == 1
    assert identity.load(db)["authority"]["spend_ceiling_cad"] == 0.0


def test_an_authorised_owner_amendment_is_a_new_chained_version():
    db = boot()
    identity.ensure(db)
    saved = core_identity.AUTHORISED_IDENTITY_AMENDMENTS
    try:
        # a decision id that IS recorded in DECISION_LOG.md, authorised for this test only
        core_identity.AUTHORISED_IDENTITY_AMENDMENTS = ("D-FB-13",)
        assert identity.decision_recorded("D-FB-13")
        assert not identity.decision_recorded("D-NOPE-99")
        core_identity.AUTHORISED_IDENTITY_AMENDMENTS = ("D-NOPE-99",)
        why = _refused(lambda: identity.amend(db, {"history_policy": "x"},
                                              owner_decision_id="D-NOPE-99", actor="owner",
                                              reason="unrecorded decision"))
        assert "not recorded in DECISION_LOG" in why
        core_identity.AUTHORISED_IDENTITY_AMENDMENTS = ("D-FB-13",)
        # the face is additionally held by visual.canonical's own (empty) authorisation list
        why = _refused(lambda: identity.amend(
            db, {"visual_identity": {"identity_id": "laura-v99-deadbeef"}},
            owner_decision_id="D-FB-13", actor="owner", reason="new face"),
            exc=canonical.CanonRefused)
        assert "canonical face" in why
        cur = identity.amend(db, {"history_policy": "amended by the owner"},
                             owner_decision_id="D-FB-13", actor="owner", reason="test")
        assert cur["version"] == 2 and cur["sha256"] != identity.GENESIS_SHA256
        assert identity.load(db)["history_policy"] == "amended by the owner"
        assert identity.load(db)["visual_identity"]["identity_id"] == "laura-v15-a42aeac7"
    finally:
        core_identity.AUTHORISED_IDENTITY_AMENDMENTS = saved
    # once the authorisation is withdrawn, the version it wrote no longer verifies
    _refused(lambda: identity.ensure(db), exc=identity.IdentityTampered)


def test_identity_history_is_append_only_and_tampering_is_detected():
    db = boot()
    identity.ensure(db)
    try:
        with db.session() as s:
            row = s.query(LauraIdentityVersion).first()
            row.reason = "rewritten"
        raise AssertionError("ORM update was allowed")
    except ImmutableRecordError:
        pass
    try:
        with db.session() as s:
            s.delete(s.query(LauraIdentityVersion).first())
        raise AssertionError("ORM delete was allowed")
    except ImmutableRecordError:
        pass
    # bypass the ORM: rewrite the stored record directly
    with db.engine.begin() as c:
        c.execute(text("UPDATE laura_identity_versions SET record = :r WHERE version = 1"),
                  {"r": '{"name": "Not Laura"}'})
    why = _refused(lambda: identity.ensure(db), exc=identity.IdentityTampered)
    assert "does not match its sha256" in why
    assert identity.summary(db)["status"] == "BLOCKED"
    # nothing of hers proceeds on an unverified identity
    from brambleloop.laura.core import constitution

    v = constitution.review(db, {"department": "platform", "job_type": "ops.slo"})
    assert not v["allowed"] and "authority" in v["blocked_by"], v
    from brambleloop.laura import executive

    _refused(lambda: executive.tick(db), exc=identity.IdentityTampered)


def test_code_drift_of_the_genesis_record_is_refused():
    db = boot()
    saved = core_identity._GENESIS["role"]
    try:
        core_identity._GENESIS["role"] = "Chief Executive (drifted)"
        why = _refused(lambda: identity.ensure(db), exc=identity.IdentityTampered)
        assert "pinned hash" in why
    finally:
        core_identity._GENESIS["role"] = saved
    assert identity.ensure(db)["version"] == 1


def test_laura_agent_is_green_zero_ceiling_and_structurally_bounded():
    a = [x for x in DEFAULT_AGENTS if x["name"] == "laura"]
    assert len(a) == 1, a
    a = a[0]
    assert a["allowed_job_types"] == ["laura.executive_tick"]
    assert a["daily_cost_ceiling_cad"] == 0.0 and str(a["authority"].value) == "green"
    forbidden = FORBIDDEN_COMBINATIONS["laura"]
    assert charters.PROTECTED_JOB_TYPES <= forbidden
    assert {"gate.certify", "cir.draft", "cir.revise"} <= forbidden
    assert charters.department_of("laura.executive_tick") == "executive"


def test_public_voice_lint_holds_the_register():
    bad = ("Laura, our founder, crocheted this herself!! As an AI I'd be happy to help, "
           "darling \U0001F60D\U0001F60D")
    rules = {f["rule"] for f in identity.voice_lint(bad)}
    assert {"TRUTH_LAURA_HUMAN_CLAIM", "VOICE_GENERIC_AI", "VOICE_PRIVATE_REGISTER",
            "VOICE_EMOJI"} <= rules, rules
    good = ("Laura, Brambleloop's AI founder, chose this basket for its calm texture. The "
            "chart and written rows agree, so you can relax into the making.")
    findings = [f for f in identity.voice_lint(good)
                if f["source"] == "laura.voice"
                or (f.get("detail") or {}).get("severity") == "fail"]
    assert findings == [], findings
    arch = identity.voice_lint("Our compiler and autonomous agents check every row.")
    assert "VOICE_ARCHITECTURE" in {f["rule"] for f in arch}


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
