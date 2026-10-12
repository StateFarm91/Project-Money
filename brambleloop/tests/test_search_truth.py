"""Listing search truth: category, attributes, tags, copy and the search certificate.

Wave FB-1 cluster A. Every listing was filed under one taxonomy integer nobody had read back
from Etsy, attributes never became Etsy properties, nine or ten of thirteen tag slots were
used, stuffed titles were only audited, and a tag or category edit did not touch the
certificate. These tests pin the replacement: the deepest truthful node from a stored
snapshot (UNKNOWN without one, never 66), properties decided per node, 13 truthful tags, a
blocking search-copy gate, and a holistic search certificate bound to the listing's content.

The taxonomy responses are recorded shapes (`fixtures_etsy_taxonomy`); no test makes a
network call.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

_ART = tempfile.TemporaryDirectory()
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", _ART.name)

from sqlalchemy import select  # noqa: E402

import fixtures_etsy_taxonomy as FX  # noqa: E402
from brambleloop.commerce import category as C  # noqa: E402
from brambleloop.commerce import search, seo  # noqa: E402
from brambleloop.commerce.search import Query  # noqa: E402

_TMP = tempfile.mkdtemp()


def _facts(category="coaster", **kw):
    base = dict(category=category, difficulty="beginner",
                colors=[("cream", "#FAF6EB"), ("forest", "#244A3A")], season=None)
    base.update(kw)
    return C.Facts(**base)


# ---- F-005: the deepest truthful category ------------------------------------------------


def test_no_snapshot_is_unknown_and_never_taxonomy_66():
    choice = C.choose(None, "basket")
    assert choice.status == C.UNKNOWN and choice.taxonomy_id is None
    assert "66" in choice.why and "never" in choice.why


def test_the_deepest_crochet_pattern_node_is_chosen_per_product():
    snap = FX.snapshot()
    got = {cat: C.choose(snap, cat).taxonomy_id
           for cat in ("coaster", "basket", "amigurumi", "mosaic_blanket", "ornament", "hat")}
    assert got == {"coaster": 2114, "basket": 2115, "amigurumi": 2111,
                   "mosaic_blanket": 2112, "ornament": 2116, "hat": 2110}, got
    # Never the finished-goods "Blankets & Throws" node, which is outside the pattern subtree.
    assert 1001 not in got.values()
    assert C.choose(snap, "coaster").path_names[-2:] == ["Home Decor", "Coasters"]


def test_a_parent_of_a_valid_deeper_node_is_refused():
    snap = FX.snapshot()
    assert "parent of the deeper valid node" in C.refuse_broad(snap, 2110, "coaster")
    assert "parent of the deeper valid node" in C.refuse_broad(snap, 2113, "coaster")
    assert "not in the stored Etsy tree" in C.refuse_broad(snap, 66, "coaster")
    assert C.refuse_broad(snap, 2114, "coaster") is None
    assert "UNKNOWN" in C.refuse_broad(None, 2114, "coaster")


def test_a_tree_with_no_crochet_pattern_node_is_unknown():
    snap = {"id": 9, "nodes": [n for n in FX.snapshot()["nodes"]
                               if "Crochet" not in n["path_names"]], "properties": {}}
    assert C.choose(snap, "coaster").status == C.UNKNOWN


# ---- F-006 / F-014: inheritance and structured-field deduplication ----------------------


def test_parent_category_phrases_count_as_covered_by_the_category_field():
    choice = C.choose(FX.snapshot(), "amigurumi")
    q = Query("crochet amigurumi", 0.3, 0.3)
    report = search.score_coverage([q], title="Fox | Crochet Pattern PDF", tags=[],
                                   description="", category_path=choice.path_names)
    assert report.where == {"crochet amigurumi": "category"}
    assert report.matrix[0]["field"] == "category"


def test_tags_never_repeat_a_phrase_the_structured_fields_supply():
    queries = search.build_query_set("coaster", ["hexie"], None, ["texture"], "beginner")
    free = search.choose_tags(queries)
    assert "coaster crochet" in free
    tags = search.choose_tags(queries, exclude=["coaster crochet"])
    assert "coaster crochet" not in tags and len(tags) == len(free), (free, tags)
    assert search.structured_duplicates(["crochet", "home decor"], ["Home Decor"]) == \
        ["home decor"]


# ---- F-007 / F-008 / F-009: properties, truth, filters ----------------------------------


def test_every_property_of_the_node_is_set_or_explicitly_not_applicable():
    snap = FX.snapshot()
    choice = C.choose(snap, "coaster")
    props = C.properties_for(snap, choice, _facts())
    by = {d["name"]: d for d in props["decisions"]}
    assert props["complete"] is True, props["gaps"]
    assert by["Primary color"]["values"] == ["Beige"]
    assert by["Secondary color"]["values"] == ["Green"]
    assert by["Craft type"]["values"] == ["Crochet"]
    assert by["Skill level"]["values"] == ["Beginner"]
    for na in ("Holiday", "Occasion", "Recipient", "Subject"):
        assert by[na]["status"] == C.NOT_APPLICABLE and by[na]["why"], na
    # The payload is shaped for updateListingProperty.
    first = props["payload"][0]
    assert set(first) == {"property_id", "value_ids", "values", "scale_id", "name"}
    assert first["property_id"] == 200 and first["value_ids"] == [5000]


def test_an_unruled_property_leaves_the_attributes_incomplete():
    snap = FX.snapshot()
    snap["properties"]["2114"] = snap["properties"]["2114"] + [FX.prop(9999, "Glitter level")]
    props = C.properties_for(snap, C.choose(snap, "coaster"), _facts())
    assert props["complete"] is False
    assert any("UNDECIDED: Glitter level" in g for g in props["gaps"])


def test_a_seasonal_product_sets_its_holiday_and_an_evergreen_one_does_not():
    snap = FX.snapshot()
    choice = C.choose(snap, "ornament")
    xmas = {d["name"]: d for d in C.properties_for(
        snap, choice, _facts("ornament", season="Christmas"))["decisions"]}
    assert xmas["Holiday"]["values"] == ["Christmas"]
    assert xmas["Occasion"]["status"] == C.NOT_APPLICABLE
    plain = {d["name"]: d for d in C.properties_for(
        snap, choice, _facts("ornament", season=None))["decisions"]}
    assert plain["Holiday"]["status"] == C.NOT_APPLICABLE


def test_the_filter_audit_shows_the_filters_entered_and_lost():
    snap = FX.snapshot()
    one_colour = _facts(colors=[("zzz-unnamed", None)])
    props = C.properties_for(snap, C.choose(snap, "coaster"), one_colour)
    f = props["filters"]
    assert {"Craft type", "Skill level"} <= {x["filter"] for x in f["entered"]}
    assert "Primary color" in f["lost_to_missing_data"], f
    assert props["complete"] is False


def test_attribute_truth_rejects_irrelevant_occasion_foreign_colour_and_wrong_skill():
    attrs = search.listing_attributes(category="coaster", difficulty="beginner",
                                      colors=["cream"], season="Christmas")
    assert search.attribute_truth(attrs, difficulty="beginner", colors=["cream"],
                                  season="Christmas") == []
    bad = dict(attrs, primary_color="neon", skill_level="advanced", recipient="babies")
    problems = search.attribute_truth(bad, difficulty="beginner", colors=["cream"], season=None)
    joined = " ".join(problems)
    assert "neon" in joined and "skill_level" in joined and "recipient" in joined
    assert "no seasonal premise" in joined


def test_easy_is_never_tagged_on_an_intermediate_pattern_nor_finished_item_phrasing():
    for diff in ("intermediate", None):
        queries = search.build_query_set("basket", ["market"], None, None, diff)
        assert not any("easy" in q.phrase or "beginner" in q.phrase for q in queries), diff
    beginner = search.build_query_set("basket", ["market"], None, None, "beginner")
    assert any("easy" in q.phrase for q in beginner)
    assert search.tag_truth("handmade gift", difficulty="beginner")
    assert search.tag_truth("crochet christmas gift", difficulty="beginner") is None
    assert search.tag_truth("christmas gift", difficulty="beginner")
    assert search.tags_truth(["easy basket", "diy basket"], difficulty="intermediate") == \
        [search.tag_truth("easy basket", difficulty="intermediate")]


# ---- F-011: all thirteen slots -----------------------------------------------------------


def test_every_catalogue_seed_gets_thirteen_truthful_tags():
    from brambleloop.radar.opportunity import POOL
    from brambleloop.runtime.release import _motifs_for

    for seed in POOL:
        tech = ["mosaic"] if "mosaic" in (seed.category + " " + seed.slug) else ["texture"]
        for diff in ("beginner", "confident beginner", "intermediate"):
            q = search.build_query_set(seed.category, _motifs_for(seed.slug), seed.season,
                                       tech, diff)
            tags = search.choose_tags(q)
            assert len(tags) == 13, (seed.slug, diff, tags)
            assert search.tags_truth(tags, difficulty=diff) == [], (seed.slug, tags)


def _copy(title="Market Basket | Crochet Pattern PDF | US and UK Terms", tags=None,
          description=None):
    tags = tags if tags is not None else [f"tag{i} word{i}" for i in range(13)]
    description = description or ("A crochet pattern, not a finished item. " * 12)
    return seo.ListingCopy(title=title, tags=tags, description=description,
                           materials=[], price_cad=5.0)


def test_fewer_than_thirteen_tags_block_unless_a_limitation_is_recorded():
    short = _copy(tags=[f"tag{i} word{i}" for i in range(10)])
    gate = seo.check_search_copy(short)
    assert any(p.startswith("LISTING_TAG_SLOTS_UNUSED") for p in gate["blocking"])
    limited = seo.check_search_copy(short, tag_limitation="Etsy refuses tags for this node")
    assert not any("TAG_SLOTS" in p for p in limited["blocking"])
    assert any("recorded limitation" in p for p in limited["soft"])
    assert seo.check_search_copy(_copy())["ok"] is True


# ---- F-021 / F-245 / F-298 / F-023 / F-024: titles ---------------------------------------


def test_a_stuffed_title_is_refused_and_build_title_never_repeats_a_word():
    from brambleloop.commerce import portfolio
    from brambleloop.radar.opportunity import POOL
    from brambleloop.runtime.release import _motifs_for

    gate = seo.check_search_copy(_copy(title="Crochet Pattern Crochet Blanket Crochet Throw"))
    assert any(p.startswith("LISTING_STUFFED") for p in gate["blocking"])
    for seed in POOL:
        title = seo.build_title(seed.title, seed.category, _motifs_for(seed.slug),
                                seed.season)
        assert not portfolio.stuffing(title, ["a b"])["repeated_in_title"], title
        assert "crochet pattern" in title.lower(), title
        assert len(seo._title_words(title)) <= seo.TITLE_WORD_TARGET, title


def test_a_long_title_is_a_soft_readability_finding_not_a_block():
    long = _copy(title="Market Basket Trio Crochet Pattern PDF With Three Sizes Written "
                       "Instructions Chart Photo Tutorial Stitch Guide Extra")
    gate = seo.check_search_copy(long)
    assert any(p.startswith("LISTING_TITLE_LONG") for p in gate["soft"])
    assert not any("LONG" in p for p in gate["blocking"])


def test_subjective_words_move_out_of_the_title():
    title = seo.build_title("Adorable Fox Friend", "amigurumi", ["fox"])
    assert "adorable" not in title.lower() and title.startswith("Fox Friend"), title
    gate = seo.check_search_copy(_copy(title="Beautiful Basket | Crochet Pattern PDF"))
    assert any(p.startswith("LISTING_SUBJECTIVE_IN_TITLE") for p in gate["blocking"])


# ---- F-025 / F-026: the description -------------------------------------------------------


def test_the_description_opens_with_key_phrases_without_copying_the_title():
    title = seo.build_title("Market Basket Trio", "basket", ["market"])
    desc = seo.build_description(
        "Market Basket Trio", size_label=None, yardage_lines=[], tolerance_pct=10,
        difficulty="beginner", colors=["cream"], terminology="US", gauge_line=None,
        stitches=["sc"], key_phrases=["market basket", "crochet basket", "diy basket"])
    head = "\n".join(desc.splitlines()[:2])
    for phrase in ("market basket", "crochet basket", "diy basket"):
        assert phrase in head, head
    assert title not in desc


def test_a_keyword_dump_description_is_refused():
    dump = ("Great pattern.\ncrochet basket, market basket, diy basket, basket crochet, "
            "storage basket\n" + "More text. " * 40)
    gate = seo.check_search_copy(_copy(description=dump),
                                 phrases=["crochet basket", "market basket", "diy basket",
                                          "basket crochet", "storage basket"])
    assert any(p.startswith("DESCRIPTION_KEYWORD_LIST") for p in gate["blocking"])
    repeat = "diy basket pattern. " * 6 + "Plain text. " * 30
    assert any(p.startswith("DESCRIPTION_KEYWORD_REPEAT")
               for p in seo.keyword_dump(repeat, ["diy basket"]))


# ---- F-020 / F-015 / F-002: provenance and the coverage matrix ---------------------------


def test_assumed_phrases_are_labelled_and_excluded_from_the_evidence_share():
    assumed = search.build_query_set("basket", ["market"], None, None, "beginner")
    assert all(q.provenance == search.ASSUMED for q in assumed)
    tags = search.choose_tags(assumed)
    report = search.score_coverage(assumed, title="Market Basket | Crochet Pattern PDF",
                                   tags=tags, description="")
    assert report.evidence_share is None
    assert report.to_dict()["evidence_share"] == "UNMEASURED"
    observed = Query("storage basket idea", 0.4, 0.3, provenance="observed:serp",
                     read_at="2026-09-28")
    report = search.score_coverage(assumed + [observed], title="x", description="",
                                   tags=tags + ["storage basket idea"])
    assert report.evidence_share == 1.0
    sources = search.tag_provenance(tags[:2] + ["storage basket idea"],
                                    assumed + [observed], observed_tags=[])
    assert [s["evidence"] for s in sources] == [False, False, True]
    assert sources[2]["read_at"] == "2026-09-28"


def test_the_coverage_matrix_names_the_supplying_field_for_every_query():
    queries = search.build_query_set("basket", ["market"], None, None, "beginner")
    tags = search.choose_tags(queries)
    report = search.score_coverage(queries, title="Market Basket | Crochet Pattern PDF",
                                   tags=tags, description="a diy gift crochet pattern")
    matrix = report.to_dict()["matrix"]
    assert len(matrix) == len(queries)
    fields = {row["phrase"]: row["field"] for row in matrix}
    exact = [t for t in tags if t in fields]
    assert exact and all(fields[t] == "tag_exact" for t in exact)
    assert all({"phrase", "family", "provenance", "field"} <= set(r) for r in matrix)


# ---- F-004 / F-251 / F-250 ---------------------------------------------------------------


def test_the_search_certificate_refuses_an_unknown_category_and_pends_on_the_hero():
    ok_copy = {"ok": True, "blocking": []}
    snap = FX.snapshot()
    choice = C.choose(snap, "coaster")
    props = C.properties_for(snap, choice, _facts())
    passing = search.search_certificate(category=choice.to_dict(), properties=props,
                                        attribute_problems=[], copy_gate=ok_copy,
                                        tag_problems=[], description_problems=[])
    assert passing["verdict"] == "PENDING" and passing["pending"] == ["hero"]
    done = search.search_certificate(category=choice.to_dict(), properties=props,
                                     attribute_problems=[], copy_gate=ok_copy,
                                     tag_problems=[], description_problems=[],
                                     hero={"ok": True})
    assert done["verdict"] == search.PASS
    unknown = C.choose(None, "coaster")
    refused = search.search_certificate(
        category=unknown.to_dict(), properties=C.properties_for(None, unknown, _facts()),
        attribute_problems=[], copy_gate=ok_copy, tag_problems=[], description_problems=[],
        hero={"ok": True})
    assert refused["verdict"] == search.REFUSED
    assert set(refused["failed"]) == {"category", "attributes"}


def test_a_non_english_tag_is_refused_without_a_translation_record():
    tags = [f"tag{i} word{i}" for i in range(12)] + ["häkelanleitung decke"]
    gate = seo.check_search_copy(_copy(tags=tags))
    assert any(p.startswith("LISTING_LANGUAGE") for p in gate["blocking"])
    assert seo.check_search_copy(_copy(tags=tags),
                                 translation_record="DE market test 2026-10")["ok"]


def test_a_recency_only_renewal_is_refused():
    from brambleloop.publish.release_gates import renewal_decision

    assert renewal_decision(reason="recency")["allowed"] is False
    assert renewal_decision(reason="expired", listing_state="active")["allowed"] is False
    assert renewal_decision(reason="expired", listing_state="expired")["allowed"] is True
    assert renewal_decision(reason="material_change",
                            material_change="added a second size")["allowed"] is True


# ---- F-294: tags, taxonomy and attributes are claims ------------------------------------


def test_a_tag_or_taxonomy_edit_changes_the_claims_the_certificate_is_bound_to():
    from types import SimpleNamespace

    from brambleloop.publish import listing_set as ls
    from brambleloop.publish.release_gates import claims_of

    listing = SimpleNamespace(title="T", description="D", tags=["a b", "c d"])
    profile = SimpleNamespace(taxonomy_id=2114, attributes={"skill_level": "beginner"},
                              properties=[{"property_id": 200, "values": ["Beige"]}])
    base = ls.fingerprint(claims_of(listing, [], profile))
    edited_tags = SimpleNamespace(title="T", description="D", tags=["a b", "e f"])
    assert ls.fingerprint(claims_of(edited_tags, [], profile)) != base
    moved = SimpleNamespace(**{**vars(profile), "taxonomy_id": 2113})
    assert ls.fingerprint(claims_of(listing, [], moved)) != base
    attr = SimpleNamespace(**{**vars(profile), "properties": []})
    assert ls.fingerprint(claims_of(listing, [], attr)) != base


# ---- the live path: cadence, snapshot, listing.seo, publish verdict ---------------------


def _db(name: str):
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/{name}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _run(db, agent: str, job_type: str, inputs: dict, *, key: str):
    from brambleloop.core.models import Job, Phase
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import Worker

    JobQueue(db).enqueue(agent, job_type, inputs, priority=0, idempotency_key=key)
    w = Worker(db, f"fb1a-{job_type}", phase=Phase.SHADOW, job_types=[job_type])
    for _ in range(5):
        if not w.run_once():
            break
    with db.session() as s:
        job = s.scalar(select(Job).where(Job.idempotency_key == key))
        s.expunge(job)
        return job


def _probe_ok(db) -> None:
    from brambleloop.core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="market_radar", action="etsy.probe", artifact="fixture",
                       detail={"ok": True, "application_id": "fixture"}))


def test_the_taxonomy_cadence_is_scheduled_handled_and_permitted():
    from brambleloop.agents.registry import DEFAULT_AGENTS
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime.worker import CADENCES, handlers

    assert ("etsy_taxonomy", "listing", "listing.taxonomy_refresh", 86400) in CADENCES
    assert handlers.get("listing.taxonomy_refresh") is not None
    listing = next(a for a in DEFAULT_AGENTS if a["name"] == "listing")
    assert "listing.taxonomy_refresh" in listing["allowed_job_types"]


def test_the_refresh_is_an_honest_noop_while_the_etsy_api_gate_is_closed():
    from brambleloop.core.models import EtsyTaxonomySnapshot
    from brambleloop.integrations import etsy_taxonomy as T

    db = _db("closed")

    def never(_db):
        raise AssertionError("a client was built while the gate was closed")

    T.client_factory = never
    try:
        job = _run(db, "listing", "listing.taxonomy_refresh", {}, key="tax-closed")
    finally:
        T.client_factory = None
    out = job.outputs
    assert out["ran"] is False and out["reading"] == "UNMEASURED"
    assert out["network_calls"] == 0 and out["gate_missing"]
    with db.session() as s:
        assert s.scalar(select(EtsyTaxonomySnapshot)) is None


def test_the_refresh_stores_a_snapshot_from_recorded_responses_and_confirms_it_after():
    from brambleloop.integrations import etsy_taxonomy as T

    db = _db("open")
    _probe_ok(db)
    client = FX.RecordedTaxonomyClient()
    T.client_factory = lambda _db: client
    try:
        first = _run(db, "listing", "listing.taxonomy_refresh", {}, key="tax-1").outputs
        second = _run(db, "listing", "listing.taxonomy_refresh", {}, key="tax-2").outputs
    finally:
        T.client_factory = None
    assert first["ran"] and first["new_snapshot"] is True, first
    # The tree, then one property read per crochet-pattern node -- not the knitting node,
    # and not the finished-goods tree.
    assert client.calls.count("getSellerTaxonomyNodes") == 2
    assert first["properties_read"] == 7 and first["network_calls"] == 8, first
    assert second["new_snapshot"] is False and second["snapshot_id"] == first["snapshot_id"]
    snap = T.latest(db)
    assert C.choose(snap, "basket").taxonomy_id == 2115


_CHAIN: dict = {}


def _chain_db():
    """One certified product through the post-certification chain, copied per test."""
    import sqlite3
    from datetime import datetime

    from brambleloop.core.db import Database

    if not _CHAIN:
        from brambleloop.products.vessels import build_hexagon_coaster
        from brambleloop.queue.durable import JobQueue
        from brambleloop.runtime import pipeline  # noqa: F401
        from brambleloop.runtime.worker import Worker

        db = _db("chain")
        JobQueue(db).enqueue("quality_director", "gate.certify",
                             {"cir": build_hexagon_coaster().to_dict()})
        w = Worker(db, "fb1a-chain")
        for _ in range(100):
            if not w.run_once():
                break
        _CHAIN["path"] = f"{_TMP}/chain.sqlite"
    dst = f"{_TMP}/copy-{datetime.now().timestamp()}.sqlite"
    with sqlite3.connect(_CHAIN["path"]) as src, sqlite3.connect(dst) as out:
        src.backup(out)
    return Database(f"sqlite:///{dst}")


def _seo_job(db):
    from brambleloop.core.models import Job, JobStatus

    with db.session() as s:
        job = s.scalar(select(Job).where(Job.job_type == "listing.seo",
                                         Job.status == JobStatus.DONE))
        s.expunge(job)
        return job


def _profile(db, slug):
    from brambleloop.core.models import ListingSearchProfile

    with db.session() as s:
        row = s.scalar(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == slug))
        s.expunge(row)
        return row


def test_listing_seo_drafts_thirteen_tags_and_records_an_unknown_category_without_a_snapshot():
    db = _chain_db()
    job = _seo_job(db)
    out = job.outputs
    assert out["ok"] is True
    assert len(out["listing"]["tags"]) == 13, out["listing"]["tags"]
    slug, version = out["slug"], out["version"]
    row = _profile(db, slug)
    assert row.category_status == C.UNKNOWN and row.taxonomy_id is None
    assert row.verdict == "REFUSED" and "category" in row.certificate["failed"]
    assert row.coverage_matrix and all("field" in r for r in row.coverage_matrix)
    assert all(t["provenance"] for t in row.tag_provenance)
    assert C.publish_inputs(db, slug=slug, version=version)["taxonomy_id"] is None


def test_publish_refuses_when_search_is_not_certified():
    from brambleloop.publish import release_gates as RG

    db = _chain_db()
    out = _seo_job(db).outputs
    verdict = RG.for_publish(db, slug=out["slug"], version=out["version"])
    assert verdict["blocks_release"] is True
    assert verdict["search"]["ok"] is False
    assert any("category UNKNOWN" in r for r in verdict["search"]["reasons"])
    assert any(r.startswith("search certificate") for r in verdict["reasons"])


def test_with_a_snapshot_listing_seo_chooses_the_node_and_writes_the_property_payload():
    from brambleloop.core.models import EtsyTaxonomySnapshot
    from brambleloop.runtime.release import _seed_for

    db = _chain_db()
    snap = FX.snapshot()
    with db.session() as s:
        s.add(EtsyTaxonomySnapshot(sha256="fixture", node_count=len(snap["nodes"]),
                                   nodes=snap["nodes"], properties=snap["properties"]))
    inputs = dict(_seo_job(db).inputs)
    job = _run(db, "listing", "listing.seo", inputs, key="fb1a-seo-with-snapshot")
    assert job.outputs["ok"] is True, job.outputs.get("blocking")
    seed = _seed_for(inputs["slug"])
    category = inputs.get("category") or (seed.category if seed else "mosaic_blanket")
    expected = C.choose(dict(snap, id=1), category)
    row = _profile(db, inputs["slug"])
    assert row.category_status == C.CHOSEN and row.taxonomy_id == expected.taxonomy_id
    assert row.taxonomy_path == expected.path_names
    assert any(p["property_id"] == 3001 and p["values"] == ["Crochet"]
               for p in row.properties), row.properties
    assert row.certificate["checks"]["category"]["ok"] is True
    got = C.publish_inputs(db, slug=inputs["slug"], version=inputs["version"])
    assert got["taxonomy_id"] == expected.taxonomy_id and got["properties"] == row.properties
    assert job.outputs["listing"]["tags"] and len(job.outputs["listing"]["tags"]) == 13


def test_a_tag_edit_after_certification_makes_the_search_gate_refuse():
    from brambleloop.core.models import Listing
    from brambleloop.publish import release_gates as RG

    db = _chain_db()
    out = _seo_job(db).outputs
    slug, version = out["slug"], out["version"]
    before = RG.search_gate(db, slug=slug, version=version)
    assert not any("changed after certification" in r for r in before["reasons"])
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug))
        row.tags = list(row.tags[:-1]) + ["edited by hand"]
    after = RG.search_gate(db, slug=slug, version=version)
    assert any("changed after certification" in r for r in after["reasons"])


if __name__ == "__main__":
    fails = passes = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                passes += 1
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback

                traceback.print_exc()
                print("FAIL", name, repr(e))
    print(f"\n  {passes} passing, {fails} failing")
    sys.exit(1 if fails else 0)
