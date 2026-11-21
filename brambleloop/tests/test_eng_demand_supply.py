"""ENG-DEMAND-SUPPLY: demand from stored evidence, demand-led admission, engine demand, and
original core-family concepts.

Real code throughout: the score is pure arithmetic over fixture rows, admission runs the real
`products.supply` controller and durable queue on SQLite, and the originals run through the
real `radar.concept_intake` handler with every intake gate. Every listing, slug and title in a
fixture here is a TEST FIXTURE, not market data.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

_TMP = tempfile.mkdtemp(prefix="eng_demand_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, BenchmarkListing, Job, JobStatus, Phase  # noqa: E402
from brambleloop.products import demand as D  # noqa: E402
from brambleloop.products import supply  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import JobContext  # noqa: E402

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
_N = [0]


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _ctx(db, key="holder"):
    job = JobQueue(db).enqueue("orchestrator", "supply.admit", {}, idempotency_key=key)
    return JobContext(job=job, db=db, queue=JobQueue(db), registry=Registry(db),
                      phase=Phase.SHADOW)


def _row(title, fav=None, *, shop="fx_shop", pod="", hist=None, age_days=1, **extra):
    detail = dict(extra)
    if fav is not None:
        detail["num_favorers"] = fav
    if hist is not None:
        detail["favorers_history"] = hist
    return {"benchmark_key": shop, "title": title, "pod": pod, "audit_state": "audited",
            "last_seen": NOW - timedelta(days=age_days), "detail": detail}


def _hist(start, end, days=10):
    return [{"at": (NOW - timedelta(days=days)).isoformat(), "n": start},
            {"at": NOW.isoformat(), "n": end}]


def _same_evidence(title_by_family: dict) -> list[dict]:
    """Identical readings for each family's fixture title: three listings, three shops."""
    rows = []
    for fam, title in title_by_family.items():
        for i in range(3):
            rows.append(_row(title, 400, shop=f"fx{i}", hist=_hist(300, 400)))
    return rows


# ---- 1. the deterministic score ------------------------------------------------------------


def test_the_score_is_deterministic_and_pinned():
    rows = [_row("Fixture Amigurumi Frog Pattern", 500, shop="a", hist=_hist(400, 500)),
            _row("Fixture Amigurumi Frog Pattern", 120, shop="b", hist=_hist(100, 120)),
            _row("Fixture Amigurumi Frog Pattern", 80, shop="c")]
    serp = [{"query": "amigurumi frog pattern", "captured_at": NOW - timedelta(days=2),
             "rank_list": [{"rank": 1, "pod": "amigurumi", "favourites": 300},
                           {"rank": 4, "pod": "amigurumi", "favourites": None}]}]
    a = D.build_index(rows, serp, now=NOW, teardowns=())
    b = D.build_index(list(reversed(rows)), serp, now=NOW, teardowns=())
    sa = a.score("Frog Amigurumi")
    assert sa == b.score("Frog Amigurumi"), "the order rows are read in changes nothing"
    assert sa["cluster"] == "amigurumi/standard/frog" and sa["level"] == "cluster", sa
    # Five readings with no reviews, bestseller or baskets stored: PARTIAL, not MEASURED.
    assert sa["observations"] == 5 and sa["status"] == D.PARTIAL, sa
    # Pinned arithmetic: any change to a weight, a saturation point, the prior, the boost or
    # the recency rule moves these numbers.
    assert (sa["score"], sa["confidence"], sa["value"], sa["boost"]) == (
        0.4796, 0.2004, 0.6966, 0.1801), sa
    assert sa["signals"]["favourites_velocity"]["status"] == D.MEASURED
    assert sa["signals"]["reviews"]["status"] == D.UNKNOWN          # never stored here
    assert sa["signals"]["serp_rank"]["value"] == round((1 + 0.5) / 2, 4)


def test_velocity_needs_two_dated_readings_a_day_apart():
    assert D.velocity([]) is None
    assert D.velocity([{"at": NOW.isoformat(), "n": 5}]) is None
    assert D.velocity([{"at": NOW.isoformat(), "n": 5},
                       {"at": (NOW + timedelta(hours=3)).isoformat(), "n": 9}]) is None
    assert D.velocity(_hist(100, 200, days=10)) == 10.0
    assert D.velocity(_hist(200, 100, days=10)) == 0.0, "favourites removed are not negative"


def test_old_readings_count_less_and_stale_ones_not_at_all():
    assert D.recency_weight(NOW, NOW) == 1.0
    assert D.recency_weight(NOW - timedelta(days=D.HALF_LIFE_DAYS), NOW) == 0.5
    assert D.recency_weight(NOW - timedelta(days=D.MAX_AGE_DAYS + 1), NOW) == 0.0
    ix = D.build_index([_row("Fixture Cushion Pattern", 900, age_days=D.MAX_AGE_DAYS + 5)
                        for _ in range(3)], (), now=NOW, teardowns=())
    assert ix.score("Fixture Cushion")["status"] == D.UNKNOWN


# ---- 2. the owner core-family boost --------------------------------------------------------


CORE_TITLES = {"amigurumi": "Fixture Plush Toy", "baby": "Fixture Baby Blanket",
               "pillow_cushion": "Fixture Cushion Cover", "garment": "Fixture Cardigan",
               "home_decor": "Fixture Coaster Set", "seasonal_decor": "Fixture Garland"}


def test_on_equal_evidence_the_core_families_lead_in_the_owners_order():
    ix = D.build_index(_same_evidence(CORE_TITLES), (), now=NOW, teardowns=())
    got = [ix.score(t)["cluster"].split("/")[0] for t in CORE_TITLES.values()]
    assert got == list(CORE_TITLES), got
    order = sorted(CORE_TITLES, key=lambda f: -ix.score(CORE_TITLES[f])["score"])
    assert order[:4] == ["amigurumi", "baby", "pillow_cushion", "garment"], order
    flat = {ix.score(CORE_TITLES[f])["score"] for f in ("home_decor", "seasonal_decor")}
    assert len(flat) == 1, "flat décor and seasonal get no boost: equal evidence, equal score"
    assert max(flat) < ix.score(CORE_TITLES["garment"])["score"]


def test_flat_decor_leads_only_when_the_evidence_ranks_it():
    rows = [_row("Fixture Coaster Set", 2000, shop=f"s{i}", hist=_hist(1000, 2000, 5),
                 is_bestseller=True, review_count=300, in_baskets=20) for i in range(6)]
    rows += [_row("Fixture Plush Toy", 2, shop=f"t{i}", hist=_hist(2, 2, 5),
                  is_bestseller=False, review_count=0, in_baskets=0) for i in range(6)]
    ix = D.build_index(rows, (), now=NOW, teardowns=())
    assert ix.score("Fixture Coaster Set")["score"] > ix.score("Fixture Plush Toy")["score"]


# ---- 3. UNKNOWN is never zero, and never high -----------------------------------------------


def test_unknown_is_never_zero_and_never_scores_high():
    ix = D.build_index((), (), now=NOW, teardowns=())
    u = ix.score("Fixture Coaster Set")
    assert u["status"] == D.UNKNOWN and u["confidence"] == 0.0
    assert u["score"] == D.PRIOR and u["score"] > 0, "UNKNOWN reads the prior, not 0"
    core = ix.score("Fixture Plush Toy")
    assert core["status"] == D.UNKNOWN
    assert core["score"] == round(D.PRIOR + D.CORE_BOOST["amigurumi"] * 0.5, 4)
    measured = D.build_index(_same_evidence({"home_decor": "Fixture Coaster Set"}), (),
                             now=NOW, teardowns=()).score("Fixture Coaster Set")
    strong = D.build_index([_row("Fixture Coaster Set", 2000, shop=f"s{i}",
                                 hist=_hist(1000, 2000, 5), is_bestseller=True,
                                 review_count=300, in_baskets=20) for i in range(6)], (),
                           now=NOW, teardowns=()).score("Fixture Coaster Set")
    assert strong["score"] > core["score"], "an unobserved core cluster cannot outrank a " \
                                            "strongly measured one"
    assert measured["confidence"] > 0


def test_a_missing_signal_lowers_confidence_while_a_measured_zero_lowers_the_value():
    none = [_row("Fixture Cushion Cover", None, shop=f"n{i}") for i in range(3)]
    zero = [_row("Fixture Cushion Cover", 0, shop=f"z{i}") for i in range(3)]
    a = D.build_index(none, (), now=NOW, teardowns=()).score("Fixture Cushion Cover")
    b = D.build_index(zero, (), now=NOW, teardowns=()).score("Fixture Cushion Cover")
    assert a["status"] == D.UNKNOWN and a["observations"] == 0, a
    assert b["observations"] == 3 and b["value"] == 0.0 and b["confidence"] > 0, b
    assert b["evidence_score"] < a["evidence_score"], "measured 0 is evidence; None is not"


# ---- 4. engines and the engine-demand list --------------------------------------------------


def test_engine_verdicts_name_the_engine_a_concept_needs():
    v = D.engine_verdict("fx-bear", {"title": "Ball Bear Amigurumi", "category": "amigurumi"})
    assert v["certified"] is True and v["family"] == "amigurumi", v
    v = D.engine_verdict("fx-fox", {"title": "Woodland Fox Amigurumi", "category": "amigurumi"})
    assert v["known"] and not v["certified"] and v["family"] == "amigurumi", v
    assert v["reason"].startswith("construction_unsupported:amigurumi"), v
    v = D.engine_verdict("nordic-forest-mosaic-throw", {"title": "x", "category": "y"})
    assert v["certified"] and v["family"] == "engineered", "an engineered design is buildable"
    assert D.engine_verdict("fx", {"title": "No Category"})["known"] is False


def test_the_engine_demand_list_ranks_by_demand_then_by_count():
    ranked = D.engine_demand([
        {"slug": "a", "family": "hat", "demand": 0.30},
        {"slug": "b", "family": "hat", "demand": 0.29},
        {"slug": "c", "family": "amigurumi", "demand": {"score": 0.61, "cluster": "x"}},
        {"slug": "d", "family": "seasonal_decor", "demand": 0.30},
        {"slug": "e", "family": "ornament", "demand": None},     # UNKNOWN -> the prior
    ])
    assert [e["engine"] for e in ranked] == ["amigurumi", "hat", "seasonal_decor", "ornament"]
    assert [e["rank"] for e in ranked] == [1, 2, 3, 4]
    assert ranked[1]["count"] == 2 and ranked[1]["concepts"][0]["slug"] == "a"
    assert ranked[3]["top_demand"] == D.PRIOR
    assert ranked[0]["build"].startswith("amigurumi shape library")


def test_every_held_pool_concept_is_reclassified_with_the_engine_it_needs():
    rows = D.pool_reclassification(D.build_index((), (), now=NOW))
    assert len(rows) == 34
    held = [r for r in rows if not r["buildable"]]
    assert len(held) >= 18, len(held)
    assert all(r["engine"] and r["needs"] for r in held)
    by = {r["slug"]: r for r in rows}
    assert by["woodland-fox-amigurumi"]["engine"] == "amigurumi"
    assert by["spooky-garland"]["engine"] == "seasonal_decor"
    assert by["cropped-cardigan"]["engine"] == "garment"
    assert by["nordic-forest-mosaic-throw"]["buildable"] is True        # engineered design
    # core-family concepts rank above flat décor and seasonal pieces on equal (no) evidence
    assert rows[0]["cluster"].split("/")[0] in D.CORE_FAMILIES, rows[0]
    assert by["spooky-garland"]["demand"] < by["woodland-fox-amigurumi"]["demand"]


# ---- 5. demand-led admission -----------------------------------------------------------------


def _offer(ctx, slug, title, category, *, research=True, demand=0.6):
    return supply.offer(ctx, slug=slug, key=f"draft:{slug}", source="radar.score",
                        payload={"slug": slug, "title": title, "category": category},
                        family=slug, demand=demand, research=research)


def _fill(db, *slugs):
    for s in slugs:
        j = JobQueue(db).enqueue("quality_director", "gate.certify", {"slug": s},
                                 idempotency_key=f"chain:{s}")
        assert j is not None


def _finish(db, *slugs):
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.job_type == "gate.certify")):
            if j.inputs.get("slug") in slugs:
                j.status = JobStatus.DONE


def test_admission_orders_by_market_demand_and_records_engine_demand():
    db = _db()
    ctx = _ctx(db)
    with db.session() as s:                      # stored market evidence (fixtures)
        for i in range(4):
            s.add(BenchmarkListing(benchmark_key=f"fx{i}", listing_ref=f"r{i}",
                                   title="Fixture Amigurumi Bear Pattern", pod="amigurumi",
                                   audit_state="audited", last_seen=NOW,
                                   detail={"num_favorers": 800,
                                           "favorers_history": _hist(500, 800)}))
    _fill(db, "busy-one", "busy-two")
    _offer(ctx, "fx-coaster-mat", "Tide Line Placemat", "placemat", demand=0.99)
    _offer(ctx, "fx-ball-bear", "Ball Bear Amigurumi", "amigurumi", demand=0.10)
    _offer(ctx, "fx-fox", "Woodland Fox Amigurumi", "amigurumi", demand=0.95)
    order = [o["slug"] for o in supply.offers(db)]
    assert order.index("fx-ball-bear") < order.index("fx-coaster-mat"), order
    _finish(db, "busy-one", "busy-two")
    out = supply.admit(ctx, per_run=2)
    assert [a["slug"] for a in out["admitted"]] == ["fx-ball-bear", "fx-coaster-mat"], out
    assert out["engine_demand"] == ["fx-fox"], out
    assert out["refused"]["draft:fx-fox"].startswith("engine_demand:amigurumi"), out
    # recorded once, and shown on the ranked list
    supply.admit(ctx)
    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(
            AuditLog.action == D.ENGINE_DEMAND_ACTION)))
    assert len(rows) == 1 and rows[0].artifact == "fx-fox"
    panel = D.panel(db, now=NOW)
    top = next(e for e in panel["engines"] if e["engine"] == "amigurumi")
    assert any(c["slug"] == "fx-fox" for c in top["concepts"]), top
    rb = D.readback(db, now=NOW)
    assert rb["engines_needed"] == len(panel["engines"]) and rb["top_engines"], rb


def test_a_waiting_engine_demand_concept_is_admitted_once_its_engine_certifies():
    from brambleloop.creative import construction_families as CF

    db = _db()
    ctx = _ctx(db)
    _offer(ctx, "fx-tote", "Everyday Market Tote", "bag")
    assert supply.offers(db) and not D.engine_verdict(
        "fx-tote", {"title": "Everyday Market Tote", "category": "bag"})["certified"]
    old = CF.FAMILIES["tote"]
    CF.FAMILIES["tote"] = CF.Family(old.key, old.engine, CF.VERIFIED, "fx", old.sizes,
                                    old.size_source, old.gaps)
    try:
        out = supply.admit(ctx)
    finally:
        CF.FAMILIES["tote"] = old
    assert [a["slug"] for a in out["admitted"]] == ["fx-tote"], out
    assert D.recorded_engine_demand(db) == [], "admitted: no longer engine demand"


def test_intake_evaluates_the_highest_demand_candidate_first():
    from brambleloop.radar import intake

    db = _db()
    cands = [{"proposal": {"title": t, "category": c}} for t, c in (
        ("Tide Line Placemat", "placemat"), ("Hush Baby Cardigan", "baby"),
        ("Ball Bear Amigurumi", "amigurumi"), ("Spooky Garland", "seasonal_decor"))]
    got = [c["proposal"]["title"] for c in intake.order_by_demand(db, cands)]
    assert got == ["Ball Bear Amigurumi", "Hush Baby Cardigan", "Tide Line Placemat",
                   "Spooky Garland"], got
    assert all("market_demand" in c for c in cands)


# ---- 6. original concepts from the top demand clusters ---------------------------------------


def test_the_originals_catalogue_is_core_heavy_and_original():
    from brambleloop.creative.concept import Concept, distance
    from brambleloop.radar import demand_originals as O
    from brambleloop.radar.ideation import originality_reasons
    from brambleloop.radar.opportunity import POOL

    cat = O.CATALOGUE
    assert len(cat) >= 20
    assert all(o.family in D.BOOSTED_FAMILIES for o in cat)
    assert {o.family for o in cat} == set(D.BOOSTED_FAMILIES)
    assert sum(o.family in D.CORE_FAMILIES for o in cat) > len(cat) // 2   # core-heavy
    assert sum(o.family == D.GARMENT for o in cat) >= 4
    pool = {p.title.lower() for p in POOL}
    assert not [o for o in cat if o.title.lower() in pool]
    cs = [Concept(key=o.slug, title=o.title, premise=o.premise, pod=O._pod(o), form=o.form,
                  construction=o.construction, motif=o.motif, palette_story=o.palette,
                  recipient=o.recipient, occasion=o.occasion, feeling=o.feeling,
                  function=o.function, make_lane="SHORT", provenance="t") for o in cat]
    gaps = [distance(a, b) for i, a in enumerate(cs) for b in cs[i + 1:]]
    assert gaps and min(gaps) >= 0.45, "no original is a near-clone of another"
    # The run-time guard: a title overlapping an observed listing is never proposed.
    assert originality_reasons("Riverbank Capybara Amigurumi", "Riverbank Capybara",
                               [("fx", "Riverbank Capybara Amigurumi Pattern")])
    db = _db()
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key="fx", listing_ref="cap1", audit_state="audited",
                               title="Riverbank Capybara Amigurumi Pattern", pod="amigurumi",
                               last_seen=datetime.now(timezone.utc),
                               detail={"num_favorers": 50}))
    proposed: list[str] = []
    skipped: set[str] = set()
    for _ in range(8):
        got = O.run(db, audit=lambda *a, **k: None)
        assert len(got["proposed"]) <= O.MAX_PER_RUN
        proposed += [x["slug"] for x in got["proposed"]]
        skipped |= {x["slug"] for x in got["skipped"]}
    assert "riverbank-capybara-amigurumi" in skipped, skipped
    assert "riverbank-capybara-amigurumi" not in proposed
    # only the amigurumi family was scanned here: nothing else is proposed (UNKNOWN)
    assert sorted(proposed) == sorted(o.slug for o in cat if o.family == D.AMIGURUMI
                                      and o.slug != "riverbank-capybara-amigurumi"), proposed


def test_no_scanned_market_reading_proposes_nothing():
    from brambleloop.radar import demand_originals as O

    db = _db()                       # teardown facts exist; no scan has observed anything
    got = O.run(db, audit=lambda *a, **k: None)
    assert got["proposed"] == [] and len(got["skipped"]) == len(O.CATALOGUE), got


def test_originals_run_through_intake_gates_into_buildable_work_and_engine_demand():
    import test_eng_families as T
    from brambleloop.radar import demand_originals as O

    db = T._db()
    with db.session() as s:
        for i, (title, pod) in enumerate((("Fixture Amigurumi Toy Pattern", "amigurumi"),
                                          ("Fixture Cardigan Pattern", "garments"),
                                          ("Fixture Baby Blanket Pattern", "home_decor"),
                                          ("Fixture Cushion Cover Pattern", "home_decor"))):
            for k in range(3):
                s.add(BenchmarkListing(
                    benchmark_key=f"fx{k}", listing_ref=f"o{i}-{k}", title=title, pod=pod,
                    audit_state="audited", last_seen=datetime.now(timezone.utc),
                    detail={"num_favorers": 300,
                            "favorers_history": [
                                {"at": (datetime.now(timezone.utc)
                                        - timedelta(days=10)).isoformat(), "n": 200},
                                {"at": datetime.now(timezone.utc).isoformat(), "n": 300}]}))
    approved, refused, proposed = [], {}, 0
    for k in range(8):
        out = T._run(db, "radar.concept_intake", {"pass": k})
        assert out["originals_proposed"] <= O.MAX_PER_RUN, out
        proposed += out["originals_proposed"]
        approved += out["approved"]
        refused.update({r["slug"]: r["reasons"] for r in out["refused"]})
    assert proposed == len(O.CATALOGUE), proposed
    assert len(approved) + len(refused) == len(O.CATALOGUE), (approved, refused)
    for slug in ("cosy-round-bear-amigurumi", "cosy-bunny-lovey", "hearthstone-raglan-cardigan",
                 "stoneware-envelope-cushion-cover", "kite-day-kids-sweater"):
        assert slug in approved, (slug, refused.get(slug))
    held = {s: r for s, r in refused.items()
            if any(str(x).startswith("construction_unsupported:") for x in r)}
    assert set(held) == set(refused), "every refusal is engine demand, none a copy or dupe"
    assert "riverbank-capybara-amigurumi" in held
    panel = D.panel(db)
    listed = {c["slug"] for e in panel["engines"] for c in e["concepts"]}
    assert set(held) <= listed, set(held) - listed
    # idempotent: the next pass proposes nothing new
    again = T._run(db, "radar.concept_intake", {"pass": "again"})
    assert again["originals_proposed"] == 0 and again["approved"] == [], again


# ---- 7. mutations that must be killed --------------------------------------------------------


def _unknown_contract_holds() -> bool:
    ix = D.build_index([_row("Fixture Cushion Cover", None, shop=f"n{i}") for i in range(3)],
                       (), now=NOW, teardowns=())
    r = ix.score("Fixture Cushion Cover")
    return r["status"] == D.UNKNOWN and r["score"] > 0 and r["score"] < 0.5


def _boost_order_holds() -> bool:
    ix = D.build_index(_same_evidence(CORE_TITLES), (), now=NOW, teardowns=())
    s = [ix.score(CORE_TITLES[f])["score"] for f in
         ("amigurumi", "baby", "pillow_cushion", "garment", "home_decor")]
    return all(a > b for a, b in zip(s, s[1:]))


def test_only_the_owners_three_families_are_core_and_garments_are_secondary():
    """Review b18-a B-1: D-OWNER-CORE-FAMILIES names three core families. Garments keep a
    smaller, separately named routine weighting and are labelled `core: False`."""
    assert D.CORE_FAMILIES == ("amigurumi", "baby", "pillow_cushion")
    assert set(D.CORE_BOOST) == set(D.CORE_FAMILIES) and D.GARMENT not in D.CORE_BOOST
    assert D.SECONDARY_BOOST == {D.GARMENT: 0.18}
    assert max(D.SECONDARY_BOOST.values()) < min(D.CORE_BOOST.values())
    ix = D.build_index(_same_evidence(CORE_TITLES), (), now=NOW, teardowns=())
    assert ix.score("Fixture Cardigan")["core"] is False
    assert ix.score("Fixture Plush Toy")["core"] is True
    fams = {r["family"]: r["core"] for r in ix.families()}
    assert fams.get(D.GARMENT) is not True, fams
    assert all(fams[f] is True for f in D.CORE_FAMILIES), fams


def test_a_missing_market_score_orders_as_the_prior_not_zero():
    """Review b18-a B-2: `supply.offers` reads a missing market score as demand.PRIOR."""
    db = _db()
    ctx = _ctx(db)
    _fill(db, "busy-one", "busy-two")            # no free slot: both offers wait
    _offer(ctx, "fx-a", "Tide Line Placemat", "placemat", demand=0.5)
    _offer(ctx, "fx-b", "Shore Line Placemat", "placemat", demand=0.4)
    real = supply._market_demand
    supply._market_demand = lambda ix, o: (
        {"score": None} if o["slug"] == "fx-a" else {**real(ix, o), "score": D.PRIOR - 0.01})
    try:
        order = [o["slug"] for o in supply.offers(db)]
    finally:
        supply._market_demand = real
    # read as 0.0 the missing score would sort last; read as PRIOR it leads PRIOR - 0.01
    assert order == ["fx-a", "fx-b"], order


def test_mutation_unknown_read_as_zero_is_killed():
    assert _unknown_contract_holds()
    real = D.listing_signals

    def mutant(detail):
        out = real(detail)
        return {k: (0.0 if v is None else v) for k, v in out.items()}   # UNKNOWN -> 0
    D.listing_signals = mutant
    try:
        assert not _unknown_contract_holds(), "the UNKNOWN-as-0 mutant survived"
    finally:
        D.listing_signals = real
    assert _unknown_contract_holds()


def test_mutation_flattened_core_boost_is_killed():
    assert _boost_order_holds()
    real = dict(D.CORE_BOOST)
    D.CORE_BOOST.update({k: 0.2 for k in real})                          # order erased
    try:
        assert not _boost_order_holds(), "the flattened-boost mutant survived"
    finally:
        D.CORE_BOOST.clear()
        D.CORE_BOOST.update(real)
    assert _boost_order_holds()


def test_mutation_engine_gate_removed_is_killed():
    db = _db()
    ctx = _ctx(db)
    real = D.engine_verdict
    D.engine_verdict = lambda slug, payload=None, **kw: {
        "known": True, "certified": True, "family": "x", "status": "verified", "reason": ""}
    try:
        out = _offer(ctx, "fx-fox-m", "Woodland Fox Amigurumi", "amigurumi")
        assert out["admitted"] is True, "the mutant admits an engine-less concept"
    finally:
        D.engine_verdict = real
    db2 = _db()
    out = _offer(_ctx(db2), "fx-fox-r", "Woodland Fox Amigurumi", "amigurumi")
    assert out["admitted"] is False and out["why"].startswith("engine_demand:"), out


def test_the_scanner_keeps_dated_favourites_readings():
    import inspect

    from brambleloop.intel import observe

    src = inspect.getsource(observe.scan)
    assert "favorers_history" in src and "FAVORERS_HISTORY_MAX" in src
    assert observe.FAVORERS_HISTORY_MAX >= 2


def test_the_engine_demand_audit_is_retained_and_the_panel_is_served():
    from brambleloop.ops import production_evidence, retention

    assert retention.KNOWN_READ_ACTIONS[D.ENGINE_DEMAND_ACTION][0] == "lifetime_total"
    assert "engine_demand" in production_evidence.SECTIONS
    api = (ROOT / "src/brambleloop/app/command_center/api.py").read_text()
    assert '@router.get("/demand")' in api
    sw = (ROOT / "src/brambleloop/app/command_center/static/sw.js").read_text()
    # Later shell merges bump VERSION past v44 (ENG-CONCEPTS-100: v45); the property is that
    # the Demand view is in the SHELL and the version moved at least to the bump that added it.
    import re as _re
    assert '"js/views/demand.js"' in sw
    assert int(_re.search(r'const VERSION = "cc-shell-v(\d+)";', sw).group(1)) >= 44


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as exc:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(exc))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
