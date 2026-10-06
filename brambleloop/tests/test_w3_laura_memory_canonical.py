"""W3-E: canonical identity is owner-controlled; generated summaries never replace facts.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_laura_memory_canonical.py
"""
from __future__ import annotations

from w3_laura_memory_harness import check, finish, fresh_db, owner_session, raises

from brambleloop.autonomy import memory as company
from brambleloop.laura import memory as lm

SRC = "decision:D-FB-13"
AGENTS = (lm.Principal.laura(), lm.Principal.department("executive"),
          lm.Principal.department("visual"), lm.Principal.public(), lm.Principal.customer())


def test_seed_writes_the_recorded_rulings_once_and_never_overwrites():
    db = fresh_db()
    keys = lm.ensure_canonical_seed(db)
    assert keys == [k for k, _, _ in lm.CANONICAL_SEED] and len(keys) == 6
    assert lm.ensure_canonical_seed(db) == []
    got = {e["key"]: e for e in lm.read(db, "canonical", None, lm.Principal.laura())}
    assert got["identity/visual_identity_id"]["value"] == "laura-v15-a42aeac7"
    assert got["identity/role"]["value"].startswith("Founder/CEO")
    assert all(e["sources"][0].startswith("decision:D-FB-") for e in got.values())
    assert all(e["actor"].startswith("owner_ruling:") for e in got.values())
    ev = [e for e in company.events(db) if e["kind"] == "laura.memory.canonical"]
    assert len(ev) == 1


def test_agents_cannot_write_or_overwrite_canonical():
    db = fresh_db()
    lm.ensure_canonical_seed(db)
    assert len(AGENTS) == 5
    for p in AGENTS:
        for key in ("identity/visual_identity_id", "identity/new-fact"):
            raises(lm.MemoryError_, lm.write, db, "canonical", key, "laura-v99-other", SRC, p,
                   supersede=True)
    v = lm.read(db, "canonical", "identity/visual_identity_id", lm.Principal.laura())
    assert v and v[0]["value"] == "laura-v15-a42aeac7" and v[0]["revision"] == 1
    e = raises(lm.CanonicalOverwriteRefused, lm.write, db, "canonical",
               "identity/visual_identity_id", "x", SRC, lm.Principal.laura())
    assert "owner-controlled" in str(e)


def test_owner_must_explicitly_supersede_and_history_keeps_every_revision():
    db = fresh_db()
    lm.ensure_canonical_seed(db)
    owner = lm.Principal.owner(owner_session(db))
    raises(lm.CanonicalOverwriteRefused, lm.write, db, "canonical", "identity/name", "Laura B",
           "owner_statement:typed in CC", owner)
    out = lm.write(db, "canonical", "identity/name", "Laura", "owner_statement:reconfirmed",
                   owner, supersede=True)
    assert out["revision"] == 2 and out["sources"][0].startswith(
        f"owner_statement:{owner.id}:"), out
    h = lm.history(db, "canonical", "identity/name", lm.Principal.laura())
    assert [r["revision"] for r in h] == [1, 2]
    assert h[0]["actor"] == "owner_ruling:D-FB-11" and h[1]["actor"] == owner.label
    assert any(e["kind"] == "laura.memory.canonical" and "identity/name" in e["summary"]
               for e in company.events(db))


def test_generated_summary_can_never_be_a_canonical_fact():
    db = fresh_db()
    owner = lm.Principal.owner(owner_session(db))
    e = raises(lm.SummaryOverwriteRefused, lm.write, db, "canonical", "identity/summary",
               "a model's summary", SRC, owner, generated=True)
    assert "canonical" in str(e)
    lm.ensure_canonical_seed(db)
    raises(lm.SummaryOverwriteRefused, lm.write, db, "canonical", "identity/role",
           "summarised role", SRC, owner, generated=True, supersede=True)


def test_generated_summary_cannot_replace_a_recorded_fact_in_any_tier():
    db = fresh_db()
    laura = lm.Principal.laura()
    lm.write(db, "brand", "voice/register", "warm, concise, never robotic", SRC, laura)
    raises(lm.SummaryOverwriteRefused, lm.write, db, "brand", "voice/register",
           "summary: cheerful", "laura_memory:brand:voice/register", laura, generated=True)
    s = lm.write(db, "brand", "voice/register.summary", "warm and concise",
                 "laura_memory:brand:voice/register", laura, generated=True)
    assert s["authority"] == "summary"
    s2 = lm.write(db, "brand", "voice/register.summary", "warm, concise",
                  "laura_memory:brand:voice/register", laura, generated=True)
    assert s2["revision"] == 2
    lm.write(db, "brand", "voice/register.summary", "owner-confirmed fact", SRC, laura)
    raises(lm.SummaryOverwriteRefused, lm.write, db, "brand", "voice/register.summary",
           "regenerated", "laura_memory:brand:voice/register", laura, generated=True)


def test_context_answers_with_canonical_facts_and_shadows_lower_tier_collisions():
    db = fresh_db()
    lm.ensure_canonical_seed(db)
    laura = lm.Principal.laura()
    # A summary in another tier that tries to restate a canonical key with a drifted value.
    lm.write(db, "operational", "identity/visual_identity_id", "laura-v16-drift",
             "laura_memory:canonical:identity/visual_identity_id", laura, generated=True)
    ctx = lm.context(db, laura, "identity/visual_identity_id")
    assert ctx["canonical"]["identity/visual_identity_id"]["value"] == "laura-v15-a42aeac7"
    assert ctx["tiers"]["operational"] == []
    assert [e["value"] for e in ctx["shadowed"]] == ["laura-v16-drift"]
    dept = lm.context(db, lm.Principal.department("visual"), "identity/visual_identity_id")
    assert dept["canonical"]["identity/visual_identity_id"]["authority"] == "canonical"


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)
finish()
