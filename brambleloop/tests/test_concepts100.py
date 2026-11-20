"""ENG-CONCEPTS-100: concept generation at scale from evidence (P0 item 4).

* Synthetic watchlist scan evidence (every listing and title here is a TEST FIXTURE, not an
  observation) yields 100+ evidence-backed ORIGINAL concepts, each with a premise, a #88
  storyboard, an honest #108 qualifier set DERIVED by `creative.intake.qualifiers_for`, its
  construction family by `construction_families.route`, a target size range and evidence
  refs that resolve to observed listing rows.
* Clones are refused (the novelty floor), copied titles are refused (whole or restated),
  held families stay visible with reasons and are never dropped, and admission is bounded
  by the monthly ceiling, open reservations and the pool's share.
* Admitted concepts are attached to the answered research task of their arena and
  `radar.intake` approves them on its own checks.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_concepts100.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, BenchmarkListing, CoverageGap  # noqa: E402
from brambleloop.creative import construction_families as CF  # noqa: E402
from brambleloop.creative.concept import distance  # noqa: E402
from brambleloop.creative.intake import qualifiers_for  # noqa: E402
from brambleloop.creative.preengineering import FAIL, _silhouette  # noqa: E402
from brambleloop.creative.prospecting import MIN_NOVELTY  # noqa: E402
from brambleloop.intel import research  # noqa: E402
from brambleloop.intel.pods import route as pod_route  # noqa: E402
from brambleloop.radar import concept_pool as P  # noqa: E402
from brambleloop.radar import intake  # noqa: E402

NOW = datetime.now(timezone.utc).replace(microsecond=0)
TODAY = NOW.date()

# Fixture competitor titles. Each word below is fixture-only and must never reach a concept.
FIXTURE = {
    "madeline_mae_co": ["Zephyrine Bunny Amigurumi Pattern", "Quorra Baby Blanket Pattern",
                        "Velloria Cushion Cover Pattern", "Zephyrine Stuffed Fox Pattern",
                        "Quorra Nursery Baby Cardigan", "Velloria Storage Basket Pattern",
                        "Marrowind Tapestry Basket Pattern", "Quorra Plush Whale Pattern"],
    "zkbdesigner": ["Thistlegarde Lumbar Pillow Pattern", "Thistlegarde Mosaic Blanket",
                    "Ombrevale Granny Throw Pattern", "Ombrevale Beanie Pattern",
                    "Ombrevale Shawl Pattern", "Thistlegarde Amigurumi Owl",
                    "Ombrevale Sweater Pattern"],
    "the_easy_design": ["Fennimore Dishcloth Pattern", "Fennimore Coaster Pattern",
                        "Fennimore Table Runner Pattern", "Fennimore Tote Bag Pattern",
                        "Fennimore Wall Hanging Pattern", "Fennimore Cardigan Pattern",
                        "Fennimore Ornament Pattern", "Fennimore Christmas Stocking",
                        "Fennimore Throw Blanket Pattern", "Fennimore Storage Bin"],
}
SECRET = ("zephyrine", "quorra", "velloria", "marrowind", "thistlegarde", "ombrevale",
          "fennimore")


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/pool.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


# A title that states a feeling becomes a comparable card (`blinded.from_listing`), so every
# fixture pod has observed cards and the design-copy check actually runs. A pod with no cards
# is the UNKNOWN case, tested on its own below.
CARD_FEELING = "Vintage "


def _scan(db, fixture=FIXTURE, *, seen=NOW, start=1000, feeling=CARD_FEELING) -> None:
    n = start
    with db.session() as s:
        for shop, titles in fixture.items():
            for t in titles:
                n += 1
                t = feeling + t
                s.add(BenchmarkListing(benchmark_key=shop, listing_ref=f"fx-{n}", title=t,
                                       pod=pod_route(t), price_cad=6.0 + (n % 5),
                                       last_seen=seen, first_seen=seen,
                                       detail={"num_favorers": n % 40}))


def _pool(db) -> list[P.ConceptPoolEntry]:
    P._ensure(db)
    with db.session() as s:
        rows = list(s.scalars(select(P.ConceptPoolEntry).order_by(P.ConceptPoolEntry.slug)))
        s.expunge_all()
        return rows


def _seeded():
    db = _db()
    _scan(db)
    out = P.replenish(db, now=NOW, unit_cad=0.12)
    return db, out


def _answered_task(db, pod: str) -> int:
    t = research.open_question(
        db, question=f"Is there durable buyer demand in the {pod} arena?",
        trigger=f"watchlist_gap:fixture-{pod}", decision_ref="radar.concept_pool:test",
        domain="competitor_positioning", query_terms=[pod],
        evidence_needed="fixture listing census", stop_condition="a fact answers it",
        if_unresolved="record it unresolved")
    tid = t["task"]
    research.add_source(db, tid, source="fixture census", citation="https://example.invalid/c",
                        retrieval="fetched", read_on=TODAY - timedelta(days=3))
    research.add_finding(db, tid, statement="fixture: the arena sells steadily",
                         claim_class="fact", rests_on=["S1"], confidence="high")
    research.answer(db, tid, outcome="fixture: durable", confidence="high",
                    effect={"kind": "constraint_established", "statement": "fixture"},
                    conclusion={"alternatives": [], "constraints": ["fixture"],
                                "unresolved": [], "next_test": {}, "applicability": None})
    with db.session() as s:
        s.add(CoverageGap(benchmark_key="watchlist", arena=f"watchlist:{pod}", pod=pod,
                          state="uncovered",
                          evidence={"research_task_id": tid,
                                    "corroborated_by": ["madeline_mae_co", "zkbdesigner"]}))
    return tid


# ---- generation -----------------------------------------------------------------------


def test_synthetic_scans_yield_100_evidence_backed_original_concepts():
    db, out = _seeded()
    c = out["health"]["counts"]
    assert c["evidence_backed"] >= P.TARGET_EVIDENCE_BACKED and c["target_met"], c
    rows = [r for r in _pool(db) if P.evidence_backed(r)]
    assert len(rows) >= P.TARGET_EVIDENCE_BACKED
    listing_ids = set()
    with db.session() as s:
        listing_ids = {f"benchmark_listing:{i}" for i in s.scalars(select(BenchmarkListing.id))}
    for r in rows:
        con = r.concept
        assert len(con["premise"].split()) >= 6, r.slug                  # #88 premise
        assert r.brief["thumbnail_storyboard"].strip(), r.slug            # #88 storyboard
        assert r.family and r.family_status, r.slug                       # construction family
        assert r.size_range.get("source"), r.slug                         # size range, sourced
        refs = [e["ref"] for e in r.evidence["refs"]]
        assert refs and set(refs) <= listing_ids, (r.slug, refs)          # evidence resolves
        assert r.evidence["listings"] >= P.MIN_SIGNAL_LISTINGS
    # Families with variation, across the construction spectrum.
    fams = {r.family for r in rows}
    assert {"panel_pair", "vessel", "tapestry", "flat_panel", "amigurumi"} <= fams
    # Garments now route to their named engines (ENG-GARMENT), so the family is the garment
    # construction (`garment_raglan`, `garment_drop_shoulder`, ...), never the bare word.
    assert any(f.startswith("garment_") for f in fams), fams
    assert "garment" not in fams, fams


def test_no_competitor_words_reach_a_concept():
    db, _ = _seeded()
    rows = _pool(db)
    assert rows
    for r in rows:
        text = " ".join([r.title, *map(str, r.concept.values()), *map(str, r.brief.values())])
        assert not any(w in text.lower() for w in SECRET), (r.slug, text)
        assert "title" not in str(r.evidence["refs"])


def test_108_is_derived_honestly_never_constant():
    db, _ = _seeded()
    seen = set()
    for r in _pool(db):
        if r.state == P.REFUSED:
            continue
        con = P.as_concept(r.slug, r.title, r.concept)
        assert r.brief["silhouette_qualifiers"] == qualifiers_for(con), r.slug
        assert not P.honesty_reasons(con), r.slug
        sil = _silhouette(con, r.brief)
        if sil["status"] == FAIL:
            assert r.state == P.HELD and any(x.startswith("#108") for x in r.reasons), r.slug
        seen.add(tuple(r.brief["silhouette_qualifiers"]))
    assert len(seen) >= 2, seen                    # not one constant qualifier for everyone
    assert () in seen                              # plain stripes honestly carry none
    # A generic flat form with no earned qualifier is HELD by #108, never relabelled.
    throws = [r for r in _pool(db) if r.lane == "throw" and r.state != P.REFUSED]
    assert throws and all(r.state == P.HELD and r.brief["silhouette_qualifiers"] == []
                          for r in throws)


def test_a_premise_claiming_an_unearned_qualifier_is_refused():
    lane = P.LANES_BY_KEY["cushion"]
    motif, use, options = next(P.variant_options(lane))
    bad = P.Motif(motif.key, motif.title, "a procession of motifs", motif.palette)
    cand = P.build(lane, "x", bad, options[0], use, {"refs": []}, None)
    assert any(r.startswith("#108 honesty") for r in cand["reasons"]), cand["reasons"]


def test_clones_are_rejected_and_kept_concepts_are_distinct():
    db, _ = _seeded()
    rows = _pool(db)
    clone = next(r for r in rows if r.slug.startswith("pool-tapestry-basket-geometric-"))
    assert clone.state == P.REFUSED and any(x.startswith("clone:") for x in clone.reasons)
    kept = [P.as_concept(r.slug, r.title, r.concept) for r in rows if r.state != P.REFUSED]
    assert len(kept) >= P.TARGET_EVIDENCE_BACKED
    for i, a in enumerate(kept):
        for b in kept[i + 1:]:  # vacuity-ok: the last concept has no later sibling
            assert distance(a, b) >= MIN_NOVELTY, (a.key, b.key, distance(a, b))


def test_copied_titles_are_refused():
    db = _db()
    _scan(db)
    first = {c["slug"]: c for c in P.generate(db, now=NOW)}
    ready = next(c for c in first.values() if c["state"] == P.READY and c["lane"] == "cushion")
    restated = next(c for c in first.values() if c["state"] == P.READY and c["lane"] == "basket")
    _scan(db, {"zkbdesigner": [ready["title"],                       # the exact title
                               f"{restated['title']} Crochet Pattern"]},  # restated
          start=9000, feeling="")
    again = {c["slug"]: c for c in P.generate(db, now=NOW)}
    for c in (ready, restated):
        got = again[c["slug"]]
        assert got["state"] == P.REFUSED, got["reasons"]
        assert any(r.startswith("copy:") for r in got["reasons"]), got["reasons"]


def test_held_families_are_visible_and_never_dropped():
    db, out = _seeded()
    h = out["health"]
    held_keys = {k for k, n in h["held_reasons"].items()
                 if k.startswith("construction_unsupported:") and n}
    assert held_keys, h["held_reasons"]
    # Families with no engine yet: each is held under its own key, with a count.
    for fam in ("amigurumi", "hat", "mosaic", "c2c", "cable"):
        assert f"construction_unsupported:{fam}" in held_keys, (fam, h["held_reasons"])
        assert h["by_family"][fam].get("held"), fam
    # Garments: held under the garment construction that refused them, never a bare
    # `garment` key (the engines exist now; the key names which construction held it).
    garment_keys = {k for k in held_keys if k.startswith("construction_unsupported:garment_")}
    assert garment_keys, h["held_reasons"]
    assert "construction_unsupported:garment" not in h["held_reasons"], h["held_reasons"]
    for k in garment_keys:
        assert h["by_family"][k.split(":", 1)[1]].get("held"), k
    # Every held construction key is visible per family too (nothing is dropped between them).
    for k in held_keys:
        assert h["by_family"][k.split(":", 1)[1]].get("held"), k
    assert h["held_reasons"].get("#108 silhouette")
    held = [r for r in _pool(db) if r.state == P.HELD]
    assert all(r.reasons for r in held)
    # Core families are present and held with their reason, not dropped.
    assert any(r.lane == "amigurumi" for r in held)
    assert any(r.lane == "baby-cardigan" for r in held)
    # Evidence disappears: everything stays, marked STALE with a reason.
    later = NOW + timedelta(days=P.SIGNAL_FRESH_DAYS + 2)
    before = {r.slug for r in _pool(db)}
    P.replenish(db, now=later, unit_cad=0.12)
    after = _pool(db)
    assert {r.slug for r in after} == before
    assert all(r.state == P.STALE and r.reasons[-1].startswith("stale:") for r in after
               if r.state != P.ADMITTED)


def test_replenish_is_idempotent():
    db, _ = _seeded()
    again = P.replenish(db, now=NOW + timedelta(hours=6), unit_cad=0.12)
    assert again["new"] == [] and again["changed"] == [] and again["stale"] == []


# ---- owner weighting ---------------------------------------------------------------------


def test_owner_weighting_madeline_and_core_families():
    sig = {"listings": 4, "shops": {"zkbdesigner": 4}, "favourites": 10}
    mmc = {**sig, "shops": {"madeline_mae_co": 4}}
    lane_core = P.LANES_BY_KEY["amigurumi"]
    lane_plain = P.LANES_BY_KEY["runner"]
    assert P.priority_of(lane_core, mmc) > P.priority_of(lane_core, sig)
    assert P.priority_of(lane_core, sig) > P.priority_of(lane_plain, sig)
    assert P.priority_of(P.LANES_BY_KEY["basket"], sig) > P.priority_of(lane_plain, sig)
    db, out = _seeded()
    reqs = out["health"]["research_requests"]
    assert reqs and reqs[0]["priority_shop"], reqs



def test_core_families_outrank_plain_lanes_at_equal_demand_and_demand_still_leads():
    """Amigurumi, baby, pillows and garments are favoured; demand (listings, shops) still
    decides within that, so a weight never invents demand a lane does not have."""
    sig = {"listings": 4, "shops": {"zkbdesigner": 4}, "favourites": 10}
    plain = P.priority_of(P.LANES_BY_KEY["runner"], sig)
    for key in ("amigurumi", "baby-blanket", "baby-cardigan", "cushion", "animal-cushion",
                "cardigan", "yoke-sweater"):
        assert P.priority_of(P.LANES_BY_KEY[key], sig) > plain, key
    core = P.LANES_BY_KEY["amigurumi"]
    thin = {"listings": 1, "shops": {"zkbdesigner": 1}, "favourites": 0}
    strong = {"listings": 12, "shops": {"zkbdesigner": 6, "the_easy_design": 6},
              "favourites": 80}
    assert P.priority_of(core, strong) > P.priority_of(core, thin)
    assert P.priority_of(P.LANES_BY_KEY["runner"], strong) > P.priority_of(core, thin)

# ---- spend bound and admission ------------------------------------------------------------


def test_spend_is_bounded():
    from brambleloop.finance import reservations

    db = _db()
    a = P.admission_allowance(db, now=NOW, unit_cad=0.12)
    assert 0 < a["units"] <= P.ADMIT_PER_RUN and a["binding"] == "per_run", a
    assert P.admission_allowance(db, now=NOW, unit_cad=0)["units"] == 0
    # A unit cost the month cannot fit admits nothing.
    huge = P.admission_allowance(db, now=NOW, unit_cad=500.0)
    assert huge["units"] == 0 and huge["binding"] in ("monthly_ceiling", "pool_share"), huge
    # Open reservations count against the month.
    reservations.reserve(db, amount_cad=99.95, agent="test")
    held = P.admission_allowance(db, now=NOW, unit_cad=0.12)
    assert held["units"] == 0 and held["binding"] == "monthly_ceiling", held


def test_pool_share_caps_monthly_admissions():
    db, _ = _seeded()
    _answered_task(db, "home_decor")
    unit = 4.0
    out = P.replenish(db, now=NOW + timedelta(hours=1), unit_cad=unit)
    # CA$10 pool share / CA$4 per concept: two admissions, then the share binds.
    assert len(out["admitted"]) == 2, out["allowance"]
    nxt = P.replenish(db, now=NOW + timedelta(hours=2), unit_cad=unit)
    assert nxt["admitted"] == [] and nxt["allowance"]["binding"] == "pool_share"


def test_admitted_concepts_are_approved_by_intake_on_its_own_checks():
    db, _ = _seeded()
    tid = _answered_task(db, "home_decor")
    out = P.replenish(db, now=NOW + timedelta(hours=1), unit_cad=0.12)
    assert out["admitted"] and len(out["admitted"]) <= P.ADMIT_PER_RUN
    with db.session() as s:
        t = s.get(research.ResearchTask, tid)
        props = list((t.detail or {}).get("concept_proposals") or [])
    assert {p["slug"] for p in props} == set(out["admitted"])
    for p in props:
        assert not any(w in str(p).lower() for w in SECRET + ("madeline", "zkb"))
    actions = []
    res = intake.run(db, audit=lambda a, **k: actions.append(a),
                     enqueue=lambda *a, **k: None, today=TODAY)
    assert set(res["approved"]) == set(out["admitted"]), res
    h = P.health(db, now=NOW)
    assert h["counts"]["admitted"] == len(out["admitted"])
    assert h["counts"]["intake_approved"] == len(out["admitted"])


def test_mission_control_counts():
    db, out = _seeded()
    c = out["health"]["counts"]
    for k in ("evidence_backed", "ready", "admitted", "held", "engineered",
              "refused_clone_or_copy", "section_33_pool"):
        assert isinstance(c[k], int), k
    assert set(out["health"]["by_shop"]) >= {"MadelineMaeCo", "ZKBDESIGNER", "TheEasyDesign"}
    assert "ArtLoveDesing" in out["health"]["shops_without_signal"]


def test_generation_is_free():
    db, out = _seeded()
    assert out["spend_cad"] == 0.0 and out["network_calls"] == 0
    with db.session() as s:
        assert s.scalar(select(AuditLog.id).where(AuditLog.action.like("paid%"))) is None


# ---- C2: the design-copy check is load-bearing, and UNKNOWN is never READY ----------------


def test_a_concept_matching_an_observed_listing_card_is_refused_as_a_copy():
    """Kill the mutant `twin = ""`: a listing whose card states everything the concept states
    must refuse the concept, even though the titles share no words."""
    from brambleloop.creative import blinded

    db = _db()
    _scan(db)
    first = P.generate(db, now=NOW)
    # A title that `from_listing` reads back to exactly a READY concept's card (brute force
    # over the reader's own vocabulary; no competitor text is involved).
    from itertools import product

    from brambleloop.creative.blinded import (_FEELING_WORDS, _FORM_WORDS, _OCCASION_WORDS,
                                              _RECIPIENT_WORDS)

    def words(table, value, default=None):
        out = [w for w, v in table if v == value]
        return ([""] + out) if value == default else out

    def title_for_card(mine, pod):
        for fw, ew, ow, rw in product(words(_FORM_WORDS, mine.form),
                                      words(_FEELING_WORDS, mine.feeling),
                                      words(_OCCASION_WORDS, mine.occasion, "everyday"),
                                      words(_RECIPIENT_WORDS, mine.recipient, "self")):
            t = " ".join(x for x in (ow, ew, fw, rw) if x)
            try:
                card = blinded.from_listing({"title": t, "listing_ref": "probe", "pod": pod})
            except (blinded.Unreadable, blinded.NotComparable):
                continue
            if card.presented() == mine.presented():
                return t
        return None

    c = title = None
    for cand in first:
        if cand["state"] != P.READY or cand["_concept"] is None:
            continue
        try:
            mine = blinded.from_concept(cand["_concept"])
        except Exception:  # noqa: BLE001 - not every concept maps to a card
            continue
        title = title_for_card(mine, cand["pod"])
        if title:
            c = cand
            break
    assert title, "the fixture must yield a READY concept a listing title can match"
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key="zkbdesigner", listing_ref="fx-twin", title=title,
                               pod=c["pod"], price_cad=7.0, last_seen=NOW, first_seen=NOW,
                               detail={"num_favorers": 1}))
    got = {x["slug"]: x for x in P.generate(db, now=NOW)}[c["slug"]]
    assert got["state"] == P.REFUSED, (got["state"], got["reasons"])
    assert any(r.startswith("copy: indistinguishable from observed listing") for r in
               got["reasons"]), got["reasons"]


def test_a_pod_with_no_benchmark_cards_is_held_not_ready():
    """No observed cards for a pod: originality is UNKNOWN, so nothing in it is READY."""
    db = _db()
    _scan(db, feeling="")      # titles state no feeling, so no listing becomes a card
    out = P.generate(db, now=NOW)
    no_cards = [c for c in out if c["originality"].get("benchmark_cards") == 0]
    assert no_cards, "the fixture must leave at least one pod without cards"
    for c in no_cards:
        assert c["state"] != P.READY, (c["slug"], c["reasons"])
        if c["state"] == P.HELD:
            assert P.HELD_NO_CARDS in c["reasons"], c["reasons"]
    assert any(P.HELD_NO_CARDS in c["reasons"] for c in no_cards)
    # And the cards, once observed, lift the hold (the gate is not a constant).
    db2 = _db()
    _scan(db2)
    out2 = P.generate(db2, now=NOW)
    assert any(c["state"] == P.READY for c in out2)
    assert not any(P.HELD_NO_CARDS in c["reasons"] for c in out2
                   if c["originality"].get("benchmark_cards"))


def test_classify_holds_on_unknown_originality():
    cand = {"reasons": []}
    assert P.classify(cand, [], [P.HELD_NO_CARDS]) == (P.HELD, [P.HELD_NO_CARDS])
    assert P.classify(cand, [], []) == (P.READY, [])
    assert P.classify(cand, ["copy: x"], [P.HELD_NO_CARDS])[0] == P.REFUSED


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
