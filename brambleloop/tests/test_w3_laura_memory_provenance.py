"""W3-E: no invented history -- every memory entry's source resolves to a real record.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_laura_memory_provenance.py
"""
from __future__ import annotations

from w3_laura_memory_harness import check, finish, fresh_db, owner_session, raises

from brambleloop.autonomy import memory as company
from brambleloop.core.models import Lesson
from brambleloop.laura import memory as lm

LAURA = lm.Principal.laura()
INVENTED = (
    "",                                   # nothing
    "learned crochet from her grandmother",  # prose, not a record
    "jobs:999999",                        # a table, but no such row
    "no_such_table:1",                    # not a table
    "decision:D-FB-99",                   # a ruling nobody made
    "doc:../../etc/passwd",               # traversal
    "doc:spec/does_not_exist.md",
    "laura_memory:brand:never-written",
    "laura_memory:private:anything",      # there is no private tier to cite
    "owner_statement:the owner said so",  # only the owner may cite the owner
)


def test_invented_sources_are_refused():
    db = fresh_db()
    assert len(INVENTED) == 10
    for src in INVENTED:
        raises(lm.ProvenanceRefused, lm.write, db, "experience", "history/first-launch",
               "Laura launched the autumn range in 2019", src, LAURA)
    raises(lm.ProvenanceRefused, lm.write, db, "experience", "history/x", "v", [], LAURA)
    raises(lm.ProvenanceRefused, lm.write, db, "experience", "history/x", "v",
           ["decision:D-FB-13", "jobs:424242"], LAURA)
    assert lm.read(db, "experience", "history/first-launch", LAURA) == []


def test_real_records_resolve():
    db = fresh_db()
    company.remember(db, "mission:store:1", kind="mission", department="store_commerce",
                     subject="audit the storefront")
    company.record_event(db, "ev:1", kind="mission.done", summary="storefront audited")
    with db.session() as s:
        s.add(Lesson(origin_cell="quality", subject="instruction_clarity",
                     statement="buyers stall at round 7 when the stitch count is omitted"))
        s.flush()
        lid = s.scalar(__import__("sqlalchemy").select(Lesson.id))
    ok = ["company_memory:mission:store:1", "company_timeline:ev:1", f"lessons:{lid}",
          "decision:D-FB-11", "doc:spec/07_Laura_Owner_Ruling_2026-10-06.md"]
    out = lm.write(db, "operational", "store/audit", {"state": "done"}, ok, LAURA)
    assert out["sources"] == ok
    out2 = lm.write(db, "operational", "store/audit.followup", "re-check after banner",
                    "laura_memory:operational:store/audit", LAURA)
    assert out2["sources"] == ["laura_memory:operational:store/audit"]


def test_an_entry_cannot_cite_itself_into_existence():
    db = fresh_db()
    raises(lm.ProvenanceRefused, lm.write, db, "brand", "tagline", "x",
           "laura_memory:brand:tagline", LAURA)
    lm.write(db, "brand", "tagline", "x", "decision:D-FB-13", LAURA)
    raises(lm.ProvenanceRefused, lm.write, db, "brand", "tagline", "y",
           "laura_memory:brand:tagline", LAURA)


def test_owner_statements_are_attributed_to_the_verified_session():
    db = fresh_db()
    owner = lm.Principal.owner(owner_session(db))
    out = lm.write(db, "relationship", "preference/briefing-time", "07:30 local",
                   "owner_statement:said in Command Center", owner)
    assert out["sources"] == [f"owner_statement:{owner.id}:said in Command Center"]
    raises(lm.ProvenanceRefused, lm.write, db, "brand", "x", "v", "owner_statement:", owner)


def test_every_entry_and_revision_is_source_linked():
    db = fresh_db()
    lm.ensure_canonical_seed(db)
    lm.write(db, "brand", "palette", ["bramble", "oat"], "decision:D-FB-13", LAURA)
    lm.write(db, "brand", "palette", ["bramble", "oat", "moss"], "decision:D-FB-11", LAURA)
    entries = [e for t in lm.TIERS for e in lm.read(db, t, None, LAURA)]
    assert len(entries) >= 7
    assert all(e["sources"] and e["actor"] for e in entries)
    h = lm.history(db, "brand", "palette", LAURA)
    assert [(r["revision"], r["sources"]) for r in h] == [
        (1, ["decision:D-FB-13"]), (2, ["decision:D-FB-11"])]


def test_experience_tier_reuses_existing_lessons_read_only():
    db = fresh_db()
    with db.session() as s:
        s.add(Lesson(origin_cell="customer_experience", subject="sizing",
                     statement="buyers want finished measurements before the materials list",
                     evidence_ref="incidents:7"))
    got = lm.read(db, "experience", "~finished measurements", LAURA)
    assert len(got) == 1 and got[0]["authority"] == "projection", got
    assert got[0]["sources"][0].startswith("lessons:") and "incidents:7" in got[0]["sources"]
    lm.write(db, "experience", "lesson-cite", "lead with measurements", got[0]["ref"], LAURA)
    raises(lm.PermissionRefused, lm.read, db, "experience", None, lm.Principal.customer())


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)
finish()
