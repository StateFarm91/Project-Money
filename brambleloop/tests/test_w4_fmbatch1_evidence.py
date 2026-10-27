"""F-407: one source hierarchy (retrieval class + authority tier) shared by learning
observations and platform-policy readings; unknown hosts are never promoted to primary."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1ev_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/e.db"

from brambleloop.intel import childrens, evidence as E  # noqa: E402


def test_tiers():
    assert E.tier_for("https://www.cpsc.gov/x") == E.PRIMARY
    assert E.tier_for("https://help.etsy.com/hc/en-us/articles/1") == E.PRIMARY
    assert E.tier_for("https://www.law.cornell.edu/cfr/text/16/1500.19") == E.SECONDARY
    assert E.tier_for("https://www.reddit.com/r/crochet/x") == E.COMMUNITY
    assert E.tier_for("https://community.etsy.com/t5/x") == E.COMMUNITY  # longer suffix wins
    assert E.tier_for("https://some-blog.example/x") == E.UNCLASSIFIED
    assert E.tier_for("notaurl") == E.UNCLASSIFIED
    assert E.tier_for("db:listing_outcomes") == E.PRIMARY


def test_retrieval_vocabulary_is_the_childrens_one_and_validated():
    for c in (childrens.FETCHED, childrens.SEARCH_SUMMARY, childrens.REPOSITORY,
              childrens.RENDERED_IMAGE):
        assert c in E.RETRIEVAL_CLASSES
    try:
        E.Source("https://x.gov", "guessed")
    except E.EvidenceRefused:
        pass
    else:
        raise AssertionError("unknown retrieval accepted")


def test_rank_and_conflict():
    gov = E.Source("https://x.gov/a", E.FETCHED)
    quote = E.Source("https://x.gov/b", E.SEARCH_SUMMARY)
    forum = E.Source("https://reddit.com/r", E.FETCHED)
    assert [s.ref for s in E.rank([forum, quote, gov])] == [gov.ref, quote.ref, forum.ref]
    assert E.conflict(forum, gov)["governs"] == gov.ref
    assert E.conflict(gov, quote)["governs"] is None


def test_learning_record_carries_tier_and_retrieval():
    from brambleloop.core.db import Database
    from brambleloop.core.models import LearningObservation
    from brambleloop.intel import learning

    db = Database(os.environ["BRAMBLELOOP_DATABASE_URL"])
    db.create_all()
    domain = sorted(learning.DOMAIN_BY_KEY)[0]
    rid = learning.record(db, domain=domain, source="reddit", citation="https://reddit.com/r/x",
                          summary="makers in the thread report hooks slipping in cotton",
                          observed_on=date(2026, 10, 1), retrieval=E.FETCHED)
    with db.session() as s:
        d = s.get(LearningObservation, rid).detail
    assert d["source_tier"] == E.COMMUNITY and d["retrieval"] == E.FETCHED
    try:
        learning.record(db, domain=domain, source="x", citation="https://x.gov/a",
                        summary="a regulator says something specific here", retrieval="vibes",
                        observed_on=date(2026, 10, 1))
    except learning.LearningRefused:
        pass
    else:
        raise AssertionError("unknown retrieval accepted")


def test_policy_readings_expose_tiers_without_changing_digests():
    from brambleloop.gates import policy_knowledge as P

    readings = P.all_readings()
    assert readings
    for r in readings.values():
        d = r.to_dict()
        assert set(d["source_tiers"]) == set(r.urls)
        assert d["digest"] == r.digest() and "source_tiers" not in r.canonical_text()


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
