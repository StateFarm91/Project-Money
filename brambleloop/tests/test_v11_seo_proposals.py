"""Lane G: title/tag/attribute proposals for Launch-0 drafts.

Etsy's field limits, as this repository already records them (cited, not restated):
`commerce/seo.py` TITLE_MAX = 140, TAG_MAX_CHARS = 20, TAG_MAX_COUNT = 13;
`commerce/search.py` TAG_SLOTS = 13, TAG_MAX_CHARS = 20, TITLE_MAX = 140;
`publish/listing_schema.py` docstring: "140-character title, 13 tags of 20 characters".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.seo._testkit import ROOT, fresh_db, launch0_facts, run  # noqa: E402

from brambleloop.seo import proposals


def _all(db, rows=None):
    facts = launch0_facts()
    assert len(facts) >= 3, [f.slug for f in facts]
    return [proposals.propose(db, f, evidence_rows=rows if rows is not None else [])
            for f in facts]


def test_the_limits_cited_are_the_ones_the_repo_records():
    from brambleloop.commerce import search, seo
    from brambleloop.publish import listing_schema

    assert (seo.TITLE_MAX, seo.TAG_MAX_CHARS, seo.TAG_MAX_COUNT) == (140, 20, 13)
    assert (search.TITLE_MAX, search.TAG_MAX_CHARS, search.TAG_SLOTS) == (140, 20, 13)
    assert "140-character title, 13 tags of 20" in listing_schema.__doc__.replace("\n", " ")


def test_every_launch0_proposal_passes_etsy_field_limits():
    from brambleloop.commerce import seo

    props = _all(fresh_db())
    assert props
    for p in props:
        assert len(p["title"]) <= seo.TITLE_MAX, (p["slug"], len(p["title"]))
        assert len(p["tags"]) == seo.TAG_MAX_COUNT, (p["slug"], p["tags"])
        assert all(len(t) <= seo.TAG_MAX_CHARS for t in p["tags"]), p["tags"]
        assert len(set(p["tags"])) == len(p["tags"])
        assert "pattern" in p["title"].lower()


def test_every_proposal_is_truthful_and_traceable():
    props = _all(fresh_db())
    assert props
    for p in props:
        assert p["ok"], (p["slug"], p["validation"]["blocking"], p["attribute_problems"])
        assert p["validation"]["blocking"] == []
        assert p["tag_provenance"], p["slug"]
        for row in p["tag_provenance"]:
            assert all(w["source"] for w in row["trace"]), row


def test_proposals_never_write_to_etsy():
    props = _all(fresh_db())
    assert props and all(p["writes_to_etsy"] is False for p in props)
    src = "\n".join(path.read_text() for path in (ROOT / "src/brambleloop/seo").glob("*.py"))
    for forbidden in ("EtsyClient", "integrations.etsy import", "createDraftListing",
                      "updateListing", "store.publish"):
        assert forbidden not in src, forbidden


def test_with_no_measured_evidence_every_tag_is_labelled_modelled():
    props = _all(fresh_db())
    assert props
    for p in props:
        assert set(p["tag_basis_counts"]) <= {"modelled", "unknown"}, p["tag_basis_counts"]


def _stats_rows(terms):
    from brambleloop.seo.evidence import _row

    out = []
    for term, imp, visits, orders in terms:
        for metric, v in (("stats_impressions", imp), ("stats_visits", visits),
                          ("stats_orders", orders)):
            out.append(_row(term, metric, v, "measured", "shop_level_term_outcome",
                            "etsy_stats_export", "operating_readings:1:2026-10-01", None))
    return out


def test_measured_evidence_moves_slots_but_never_overrides_truth():
    f = [x for x in launch0_facts() if x.slug == "hexagon-coaster-set"]
    assert f
    f = f[0]
    rows = _stats_rows([
        ("cream coaster", 400, 60, 3),          # earning and true -> earns a slot
        ("hanjan coasters", 900, 120, 9),       # earning but a competitor -> rejected
        ("digital download", 5000, 40, 0),      # vanity -> withheld
    ])
    p = proposals.propose(fresh_db(), f, evidence_rows=rows)
    assert "cream coaster" in p["tags"], p["tags"]
    assert "hanjan coasters" not in p["tags"]
    assert any(r["phrase"] == "hanjan coasters" for r in p["rejected_candidates"])
    assert "digital download" not in p["tags"] and "digital download" in p["withheld_vanity_terms"]
    prov = {r["tag"]: r for r in p["tag_provenance"]}
    assert prov["cream coaster"]["basis"] == "measured"
    assert prov["cream coaster"]["origin"] == "etsy_stats_export:earning"
    assert p["ok"], p["validation"]["blocking"]


def test_a_proposal_diffs_against_the_current_draft_and_audits_it():
    from brambleloop.core.models import Listing

    db = fresh_db()
    f = [x for x in launch0_facts() if x.slug == "market-basket-small"]
    assert f
    with db.session() as s:
        s.add(Listing(product_slug="market-basket-small", version="1.0.0",
                      title="Market Mosaic Blanket | Crochet Pattern PDF",
                      description="x" * 400, tags=["mosaic blanket", "basket crochet"]))
    p = proposals.propose(db, f[0], evidence_rows=[])
    assert p["current_draft"]["title"].startswith("Market Mosaic Blanket")
    assert p["diff"]["title_changed"] is True
    assert "mosaic blanket" in p["diff"]["tags_removed"]
    assert p["current_validation"]["ok"] is False   # the PT-01 basket-as-blanket draft
    # Proposal only: the draft row is untouched.
    with db.session() as s:
        from sqlalchemy import select

        row = s.scalar(select(Listing).where(Listing.product_slug == "market-basket-small"))
        assert row.title.startswith("Market Mosaic Blanket")


def test_attributes_are_true_of_the_pattern():
    props = _all(fresh_db())
    assert props
    for p in props:
        a = p["attributes"]
        assert a["skill_level"] == p["facts"]["difficulty"]
        assert a["primary_color"] in p["facts"]["colors"]
        assert a["occasion"] is None and p["attribute_problems"] == []


if __name__ == "__main__":
    run(globals())
