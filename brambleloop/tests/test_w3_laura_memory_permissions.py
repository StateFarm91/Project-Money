"""W3-E: Laura's business memory -- the permission matrix (spec/07 item 5, D-FB-13).

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_laura_memory_permissions.py
"""
from __future__ import annotations

from w3_laura_memory_harness import check, finish, fresh_db, owner_session, raises

from brambleloop.autonomy import memory as company
from brambleloop.laura import memory as lm

TIERS = lm.TIERS
# Source that always resolves: a recorded owner ruling.
SRC = "decision:D-FB-13"


def _key(tier: str, who: str) -> str:
    return {"relationship": f"context/{who}-note"}.get(tier, f"{who}/note")


def _principals(db):
    return {"owner": lm.Principal.owner(owner_session(db)), "laura": lm.Principal.laura(),
            "department": lm.Principal.department("store_commerce"),
            "public": lm.Principal.public("store_preview"),
            "customer": lm.Principal.customer("support_draft")}


EXPECTED_READ = {
    "owner": set(TIERS), "laura": set(TIERS),
    "department": set(TIERS), "public": set(), "customer": set()}
EXPECTED_WRITE = {
    "owner": set(TIERS), "laura": {"brand", "operational", "experience", "relationship"},
    "department": {"operational", "experience"}, "public": set(), "customer": set()}


def test_tiers_are_exactly_the_five_business_tiers():
    assert TIERS == ("canonical", "brand", "operational", "experience", "relationship")


def test_write_matrix():
    db = fresh_db()
    ps = _principals(db)
    assert ps and TIERS
    for kind, p in ps.items():
        for tier in TIERS:
            key = _key(tier, kind)
            if tier in EXPECTED_WRITE[kind]:
                out = lm.write(db, tier, key, {"v": kind}, SRC, p)
                assert out["revision"] == 1 and out["sources"] == [SRC], out
            else:
                raises(lm.MemoryError_, lm.write, db, tier, key, {"v": kind}, SRC, p)


def test_read_matrix():
    db = fresh_db()
    ps = _principals(db)
    assert ps
    for tier in TIERS:
        k = "context/x" if tier == "relationship" else "x"
        lm.write(db, tier, k, "value", SRC, ps["owner"])
    for kind, p in ps.items():
        for tier in TIERS:
            if tier in EXPECTED_READ[kind]:
                assert isinstance(lm.read(db, tier, None, p), list)
            else:
                e = raises(lm.PermissionRefused, lm.read, db, tier, None, p)
                assert tier in str(e)
            assert lm.can_read(kind, tier) == (tier in EXPECTED_READ[kind])
            assert lm.can_write(kind, tier) == (tier in EXPECTED_WRITE[kind])


def test_public_and_customer_read_nothing_anywhere():
    db = fresh_db()
    pid = owner_session(db)
    lm.write(db, "brand", "palette", "secret-canary-brand", SRC, lm.Principal.owner(pid))
    blocked = [lm.Principal.public(), lm.Principal.customer()] + \
        [lm.principal_for_surface(n) for n in lm.SURFACES]
    assert len(blocked) > 2
    for p in blocked:
        assert p.kind in ("public", "customer"), p
        for tier in TIERS:
            raises(lm.PermissionRefused, lm.read, db, tier, None, p)
        raises(lm.PermissionRefused, lm.context, db, p)
        raises(lm.PermissionRefused, lm.history, db, "brand", "palette", p)
    assert lm.principal_for_surface("some-new-surface").kind == "public"


def test_no_private_tier_exists_in_this_api():
    db = fresh_db()
    owner = lm.Principal.owner(owner_session(db))
    for tier in ("private", "spouse", "owner_private", "relationship_private", ""):
        raises(lm.TierRefused, lm.write, db, tier, "k", "v", SRC, owner)
        raises(lm.TierRefused, lm.read, db, tier, None, owner)


def test_owner_principal_needs_a_live_owner_session():
    db = fresh_db()
    for pid in ("s_forged", owner_session(db, expired=True), owner_session(db, revoked=True)):
        p = lm.Principal.owner(pid)
        raises(lm.PermissionRefused, lm.write, db, "canonical", "identity/x", "v", SRC, p)
        raises(lm.PermissionRefused, lm.read, db, "brand", None, p)
    raises(lm.PermissionRefused, lm.Principal.owner, "")
    raises(lm.PermissionRefused, lm.read, db, "brand", None, None)
    raises(lm.PermissionRefused, lm.Principal, "admin", "x")


def test_departments_must_be_chartered_and_cannot_touch_others_entries():
    db = fresh_db()
    raises(lm.PermissionRefused, lm.Principal.department, "not_a_department")
    store = lm.Principal.department("store_commerce")
    growth = lm.Principal.department("growth")
    lm.write(db, "operational", "store/readiness", "ok", SRC, store)
    raises(lm.PermissionRefused, lm.write, db, "operational", "store/readiness", "x", SRC,
           growth)
    lm.write(db, "operational", "laura/priority", "launch", SRC, lm.Principal.laura())
    raises(lm.PermissionRefused, lm.write, db, "operational", "laura/priority", "x", SRC, store)
    assert lm.write(db, "operational", "store/readiness", "better", SRC, store)["revision"] == 2


def test_relationship_namespaces_policies_are_owner_approved():
    db = fresh_db()
    owner = lm.Principal.owner(owner_session(db))
    laura = lm.Principal.laura()
    store = lm.Principal.department("store_commerce")
    lm.write(db, "relationship", "policy/no-discount-theatre", "never", SRC, owner)
    lm.write(db, "relationship", "preference/launch-cadence", "weekly", SRC, owner)
    for k in ("policy/x", "preference/y"):
        raises(lm.PermissionRefused, lm.write, db, "relationship", k, "v", SRC, laura)
    raises(lm.PermissionRefused, lm.write, db, "relationship", "free-form", "v", SRC, laura)
    lm.write(db, "relationship", "department/store_commerce/working-style", "evidence-first",
             SRC, laura)
    lm.write(db, "relationship", "department/finance/working-style", "conservative", SRC,
             laura)
    seen = {e["key"] for e in lm.read(db, "relationship", None, store)}
    assert seen == {"policy/no-discount-theatre", "preference/launch-cadence",
                    "department/store_commerce/working-style"}, seen
    raises(lm.PermissionRefused, lm.history, db, "relationship",
           "department/finance/working-style", store)
    assert len(lm.read(db, "relationship", None, laura)) == 4


def test_refusals_are_audited_on_the_company_timeline_without_values():
    db = fresh_db()
    raises(lm.PermissionRefused, lm.read, db, "brand", None, lm.Principal.public("storefront"))
    raises(lm.CanonicalOverwriteRefused, lm.write, db, "canonical", "identity/name",
           "the-refused-value", SRC, lm.Principal.laura())
    ev = [e for e in company.events(db, limit=50) if e["kind"] == "laura.memory.refused"]
    assert len(ev) == 2, ev
    assert all("the-refused-value" not in e["summary"] for e in ev)
    assert {e["actor"] for e in ev} == {"public:storefront", "laura:laura"}


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)
finish()
