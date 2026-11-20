"""ENG-RESEARCH: the research loop runs from a watchlist change to engineering, unattended,
and every cycle ends in a recorded outcome.

* A simulated watchlist change (two watchlist shops start listing in an arena we do not
  cover) becomes a validated opportunity, an answered research question, an ORIGINAL
  proposal, an approved concept, a radar.score that passes the pre-engineering gate, and a
  `cir.draft` engineering job -- driven only by the real job handlers on the production
  cadence. The only stand-in is the vision judge's recorded verdict (model I/O), exactly as
  in test_w5_a4a_research_to_concept.
* Without that verdict the concept is held WAITING (no bypass) and the hold is named.
* With nothing corroborated, the cycle records "no qualifying opportunity" with evidence.
* An inaccessible watchlist shop stays visible and never stops the others.
* No competitor text, shop name or key reaches a proposal or the recorded conclusion.

Every competitor listing and shop record here is a TEST FIXTURE, not an observation.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_research_flow.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import _watchlist_sim as S  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import BenchmarkListing, Job, Phase  # noqa: E402
from brambleloop.intel import research, research_flow, watchlist  # noqa: E402
from brambleloop.radar import intake  # noqa: E402
from brambleloop.runtime.worker import Worker  # noqa: E402

# Fixture titles: no bare numbers, and each states a form and a feeling so the anti-clone
# check has comparable cards to measure against.
KITCHEN_A = ["Farmhouse Dishcloth Crochet Pattern", "Rustic Washcloth Crochet Pattern",
             "Granny Potholder Crochet Pattern"]
KITCHEN_B = ["Cottage Dishcloth Pattern", "Vintage Washcloth Pattern",
             "Classic Potholder Pattern"]
# Review H1: the end-to-end arena is one whose concept HONESTLY clears #108. Our home-decor
# concept is a pillow, which is an outline rather than a generic shape (`GENERIC_FORMS`), so
# it needs no qualifier; the kitchen concept is a coaster, a generic form whose plain-row
# stripes carry none, and #108 holds it.
DECOR_A = ["Boho Cushion Cover Crochet Pattern", "Meadow Cushion Pattern",
           "Square Pillow Crochet Pattern"]
DECOR_B = ["Scandi Pillow Sham Pattern", "Lumbar Cushion Cover Pattern",
           "Sunrise Cushion Pattern"]
ARENAS = {"home_decor": (DECOR_A, DECOR_B), "kitchen_bath": (KITCHEN_A, KITCHEN_B)}
QUALIFYING_POD = "home_decor"
ELSEWHERE = {"MadelineMaeCo": ["Chunky Beanie Crochet Pattern"],
             "ZKBDESIGNER": ["Boho Tote Bag Crochet Pattern"]}
SECRET_WORDS = ("Farmhouse", "Rustic", "Granny", "Cottage", "Vintage", "Classic", "Boho",
                "Meadow", "Scandi", "Lumbar", "Sunrise", "Sham")


def _catalogues(changed: bool, pod: str = QUALIFYING_POD) -> dict[str, list[dict]]:
    cats = {m.shop_name: [] for m in watchlist.WATCHLIST}
    for shop, titles in ELSEWHERE.items():
        base = 7000 if shop == "MadelineMaeCo" else 8000
        cats[shop] = [S.listing(base + i, t) for i, t in enumerate(titles)]
    if changed:   # the change: both shops start selling in the arena
        a, b = ARENAS[pod]
        cats["MadelineMaeCo"] += [S.listing(7100 + i, t) for i, t in enumerate(a)]
        cats["ZKBDESIGNER"] += [S.listing(8100 + i, t) for i, t in enumerate(b)]
    return cats


def _judge_gap_concepts():
    """The vision judge's recorded verdict, for our own watchlist-gap concepts only."""
    from brambleloop.creative import intake as creative_intake

    real = creative_intake.judgement_for

    def fixture(db, key):
        if "-gap-" in str(key):
            return {"thumbnail_reads_small": True, "craft_impression": 4.2,
                    "sources": ["fixture vision verdict"]}
        return real(db, key)

    creative_intake.judgement_for = fixture
    return lambda: setattr(creative_intake, "judgement_for", real)


def _drain(db, types=("radar.score", "cir.draft")) -> None:
    w = Worker(db, "rf", phase=Phase.SHADOW, job_types=list(types))
    for _ in range(50):
        if not w.run_once():
            return
    raise AssertionError("the chain did not go idle")


def _day(db, reader, days_ago: int) -> None:
    """One simulated day on the production cadences (scan + intake 6-hourly, comparison and
    research sweep daily), then the worker runs whatever those enqueued downstream."""
    for hour in (0, 6, 12, 18):
        when = S.at(days_ago, hour)
        research.expire_due(db, now=when)
        S.scan(db, reader, when)
        if hour == 6:
            S.compare(db, when.replace(minute=30))
            S.run_job(db, "research.sweep", agent="research_agent")
            for _ in range(3):
                try:
                    S.run_job(db, "research.investigate", agent="research_agent")
                except AssertionError:
                    break
        S.intake(db, when.replace(minute=45))
        _drain(db)


def _drafts(db) -> list[Job]:
    with db.session() as s:
        return list(s.scalars(select(Job).where(Job.job_type == "cir.draft")))


def _run_change(db, *, judged: bool, pod: str = QUALIFYING_POD):
    reader = S.Reader(_catalogues(changed=False))
    _day(db, reader, 4)                       # baseline: nothing to corroborate
    assert research_flow.latest_conclusion(db)["outcome"] == research_flow.NO_QUALIFYING
    reader.catalogues = _catalogues(changed=True, pod=pod)   # the watchlist change
    restore = _judge_gap_concepts() if judged else (lambda: None)
    try:
        for d in (2, 1, 0, -1):
            _day(db, reader, d)
    finally:
        restore()


def test_a_watchlist_change_reaches_engineering_with_no_manual_step():
    db = S.make_db()
    _run_change(db, judged=True)
    rows = research_flow.lineage(db)
    assert len(rows) == 1 and rows[0]["pod"] == QUALIFYING_POD, rows
    row = rows[0]
    assert row["stage"] == "engineering", row
    assert row["qualifying"] and not row["held_by_108"], row
    assert row["research_task"], "the opportunity was validated by a research question"
    slug = row["proposals"][0]["slug"]
    assert [c.state for c in S.concepts(db) if c.slug == slug] == [intake.APPROVED]
    drafts = [j for j in _drafts(db) if j.idempotency_key == f"draft:{slug}"]
    assert len(drafts) == 1, "radar.score enqueued engineering itself"
    assert drafts[0].agent == "crochet_engineer"
    score = row["proposals"][0]["score_job"]
    assert score["promoted"] is True and score["gate"] == "passed", score
    # Each corroborating shop's downstream evidence names the concept and the product.
    by_alias = research_flow.per_alias(rows)
    assert len(by_alias) == 2
    for e in by_alias.values():
        assert e["findings"] == 1 and e["concepts"] == [slug] and e["engineering"] == [slug]
    concl = research_flow.latest_conclusion(db)
    assert concl["outcome"] == research_flow.OPPORTUNITIES
    assert [q["slugs"] for q in concl["qualifying"]] == [[slug]]


def test_without_a_vision_verdict_the_concept_waits_and_the_hold_is_named():
    db = S.make_db()
    _run_change(db, judged=False)
    row = research_flow.lineage(db)[0]
    assert row["stage"] == "gate_waiting", row
    assert "image_vision" in row["held_because"]
    assert not _drafts(db), "no bypass: nothing is engineered on an unmeasured judgement"
    concl = research_flow.latest_conclusion(db)
    assert concl["outcome"] == research_flow.OPPORTUNITIES
    assert concl["qualifying"][0]["stage"] in ("approved", "gate_waiting")


def test_an_honestly_qualifying_proposal_clears_the_gates_deterministic_checks():
    """The brief is derived (never typed): the home-decor concept is a pillow, an outline
    #108 accepts without a qualifier, and `qualifiers_for` honestly finds none on it."""
    from brambleloop.creative.invention import GENERIC_FORMS

    db = S.make_db()
    _run_change(db, judged=False)
    row = research_flow.lineage(db)[0]
    score = row["proposals"][0]["score_job"]
    assert score["gate"] == "waiting" and score["failed"] == [], score
    (task,) = [t for t in S.tasks(db) if (t.detail or {}).get("concept_proposals")
               # ENG-DEMAND-SUPPLY: demand originals carry their own evidence task
               and not str(t.trigger or "").startswith("demand_originals:")]
    (prop,) = task.detail["concept_proposals"]
    assert prop["concept"]["form"] not in GENERIC_FORMS
    assert prop["brief"]["silhouette_qualifiers"] == [], prop["brief"]
    assert prop["silhouette_precheck"]["passes"] is True
    prov = prop["brief_provenance"]
    assert prov["silhouette_qualifiers"]["rule"] == "creative.intake.qualifiers_for"
    assert "concept.premise" in prov["silhouette_qualifiers"]["derived_from"]
    assert "concept.motif" in prov["thumbnail_storyboard"]["derived_from"]


def test_a_generic_concept_with_no_qualifier_is_held_by_108_and_says_so():
    """The kitchen arena's concept is a plain-row striped coaster: a generic form carrying no
    qualifier. It is never relabelled; #108 refuses it at the gate, nothing is engineered,
    and the lineage and conclusion name the hold."""
    db = S.make_db()
    _run_change(db, judged=True, pod="kitchen_bath")
    (row,) = research_flow.lineage(db)
    assert row["pod"] == "kitchen_bath"
    (task,) = [t for t in S.tasks(db) if (t.detail or {}).get("concept_proposals")
               # ENG-DEMAND-SUPPLY: demand originals carry their own evidence task
               and not str(t.trigger or "").startswith("demand_originals:")]
    (prop,) = task.detail["concept_proposals"]
    assert prop["brief"]["silhouette_qualifiers"] == [], prop["brief"]
    assert prop["silhouette_precheck"]["passes"] is False
    # Two honest holds can stop it first: concept intake (ENG-FAMILIES: no verified
    # construction engine makes a coaster disc from flat rows) or the #108 gate at scoring.
    # Either way it is never engineered and the lineage names #108.
    score = row["proposals"][0]["score_job"]
    if row["stage"] == "intake_refused":
        assert score is None, score
        assert "concept intake refused it" in row["held_because"], row["held_because"]
        assert row["proposals"][0]["intake_reasons"], row["proposals"][0]
    else:
        assert score is not None and "silhouette" in score["failed"], score
        assert row["stage"] == "gate_refused", row
    assert row["held_by_108"], row
    assert not row["qualifying"]
    assert "#108" in row["held_because"] and "shape rather than an outline" in \
        row["held_because"], row["held_because"]
    assert not _drafts(db), "a #108-refused concept never reaches engineering"
    concl = research_flow.latest_conclusion(db)
    assert concl["outcome"] == research_flow.NO_QUALIFYING, concl
    assert "#108" in concl["why"], concl["why"]


def test_the_brief_is_derived_from_the_concept_not_a_constant():
    """Mutation guard: the same writer yields different qualifiers for different premises,
    exactly as `creative.intake.qualifiers_for` reads them."""
    from brambleloop.creative.intake import qualifiers_for
    from brambleloop.radar import proposal_writer as W

    for pod, spec in W.POD_CONCEPTS.items():
        p = W.proposal_for(1, pod, 1, 2, {"refs": [], "confidence": "medium", "facts": 1},
                           W.bands(spec["category"]))
        want = qualifiers_for(W.creative_concept(p["slug"], p["title"], p["concept"]))
        assert p["brief"]["silhouette_qualifiers"] == want, (pod, p["brief"])
        assert want == [], (pod, "plain-row stripes carry no #108 qualifier")
    c = dict(p["concept"], premise="A cushion front whose motif procession of figures fills "
                                   "the whole front, worked in rows")
    assert W.brief_for("x", "Cushion", "pillow", c)["silhouette_qualifiers"] == \
        ["motif_composition"]
    c = dict(c, premise="A cushion front worked in plain rows of quiet horizontal bands")
    assert W.brief_for("x", "Cushion", "pillow", c)["silhouette_qualifiers"] == []


def test_no_corroborated_arena_records_no_qualifying_opportunity_with_evidence():
    db = S.make_db()
    reader = S.Reader(_catalogues(changed=False))
    _day(db, reader, 0)
    concl = research_flow.latest_conclusion(db)
    assert concl["outcome"] == research_flow.NO_QUALIFYING
    assert concl["qualifying"] == []
    ev = concl["evidence"]
    assert ev["comparison_at"] and ev["shops_compared"] == len(watchlist.WATCHLIST)
    assert ev["validated_arenas"] == [] and ev["gaps"] == []
    assert "validated no arena" in concl["why"]


def test_no_comparison_at_all_is_its_own_named_conclusion():
    db = S.make_db()
    out = research_flow.conclude(db)
    assert out["outcome"] == research_flow.NO_QUALIFYING
    assert "no watchlist comparison" in out["why"]


def test_an_inaccessible_shop_stays_visible_and_does_not_stop_the_others():
    db = S.make_db()
    reader = S.Reader(_catalogues(changed=True))

    class Gone(Exception):
        status = 404

    real = reader.resolve_shop

    def resolve(name):
        if name == "IvyLoop":
            raise Gone("not found")
        return real(name)

    reader.resolve_shop = resolve
    out = S.scan(db, reader, S.at(0, 6))
    assert out["observed"] >= 2, out
    st = watchlist._state(db, "ivyloop")
    assert st.get("state") in (watchlist.NOT_ACCESSIBLE, "source_outage"), st
    assert st.get("consecutive_failures") == 1 and st.get("last_error"), st
    # Visible in the registry as a watchlist source, with its collector named.
    src = {s["id"]: s for s in research_flow.sources()}
    assert src["ivyloop"]["job_type"] == "intel.watchlist_scan"
    assert watchlist._state(db, "zkbdesigner").get("state") == "ok"


def test_no_competitor_text_reaches_a_proposal_or_the_conclusion():
    db = S.make_db()
    _run_change(db, judged=True)
    task_text = json.dumps([t.detail for t in S.tasks(db)], default=str)
    concept_text = json.dumps([(c.seed, c.concept, c.brief) for c in S.concepts(db)],
                              default=str)
    concl = json.dumps(research_flow.latest_conclusion(db), default=str)
    for blob in (concept_text, concl):
        for w in SECRET_WORDS:
            assert w.lower() not in blob.lower(), (w, blob[:300])
    for blob in (task_text, concept_text, concl):
        for m in watchlist.WATCHLIST:
            assert m.shop_name.lower() not in blob.lower(), m.shop_name


def test_the_conclusion_refuses_a_shop_name():
    try:
        research_flow._assert_no_content({"why": "seen at ZKBDESIGNER"})
    except ValueError:
        return
    raise AssertionError("a shop name reached the conclusion")


def test_novelty_measures_against_every_watchlist_shop_not_only_the_anchor():
    from brambleloop.creative import prospecting

    db = S.make_db()
    with db.session() as s:
        for i, t in enumerate(KITCHEN_A):
            s.add(BenchmarkListing(benchmark_key="zkbdesigner", listing_ref=f"fx-k-{chr(97 + i)}",
                                   title=t, pod=S.POD, audit_state="audited", detail={}))
    assert not prospecting.benchmark_comparables(db), "precondition: the anchor has none"
    assert len(prospecting.watchlist_comparables(db)) == len(KITCHEN_A)
    assert len(prospecting.watchlist_comparables(db, pod=S.POD)) == len(KITCHEN_A)
    from brambleloop.creative import preengineering
    from brambleloop.radar import proposal_writer as W

    p = W.proposal_for(1, S.POD, 1, 2, {"refs": [], "confidence": "medium", "facts": 1},
                       W.bands("coaster"))
    verdict = preengineering.gate_concept(db, {**p["concept"], "key": p["slug"],
                                               "title": p["title"], "make_lane": "SHORT",
                                               "brief": p["brief"]}, catalogue=[])
    assert verdict["checks"]["novelty"]["status"] == "pass", verdict["checks"]["novelty"]
    assert verdict["checks"]["premise_thumbnail"]["status"] != "fail"
    # Review H1: the coaster's derived brief carries no qualifier, so #108 refuses it -- and
    # the writer's recorded precheck agrees with the gate.
    assert verdict["checks"]["silhouette"]["status"] == "fail", verdict["checks"]["silhouette"]
    assert p["silhouette_precheck"]["passes"] is False


def test_every_research_cadence_is_in_the_registry_and_every_mandatory_shop_too():
    from brambleloop.runtime.worker import CADENCES

    reg = research_flow.sources()
    ids = [s["id"] for s in reg]
    assert len(ids) == len(set(ids))
    # The exact watchlist set, derived from the registry (not a hardcoded count: a ninth
    # shop is being added on eng/ninth-shop).
    shop_ids = {s["id"] for s in reg if s["job_type"] in ("mjs.scan", "intel.watchlist_scan")}
    assert shop_ids == {m.key for m in watchlist.WATCHLIST}, shop_ids
    covered = {s["job_type"] for s in reg if s["job_type"]}
    research_jobs = {jt for _n, agent, jt, _p in CADENCES
                     if agent in ("market_radar", "research_agent")
                     and jt.split(".")[0] in ("intel", "mjs", "radar", "culture", "research")}
    # Intel jobs over our own rows that are not sources (learning, sentinels, acceptance).
    not_sources = {"intel.pod_learning", "mjs.seasonal_sentinel", "intel.acceptance",
                   "intel.children_portfolio"}
    assert research_jobs - not_sources <= covered, sorted(research_jobs - not_sources - covered)


def test_status_is_derived_never_assumed():
    reg = {s["id"]: s for s in research_flow.sources()}
    cad = research_flow.cadences()
    assert research_flow.status_of(reg["serp_capture"], env={}, credential="OK",
                                   cad=cad)[0] == research_flow.SCHEDULED
    assert research_flow.status_of(reg["serp_capture"], env={}, credential="REFUSED",
                                   cad=cad)[0] == research_flow.BLOCKED
    assert research_flow.status_of(reg["research_fetch"], env={}, cad=cad)[0] == \
        research_flow.DISABLED
    assert research_flow.status_of(reg["research_fetch"], env={research_flow.FETCH_ENV: "1"},
                                   cad=cad)[0] == research_flow.SCHEDULED
    assert research_flow.status_of(reg["external_trends"], env={}, cad=cad)[0] == \
        research_flow.MISSING
    assert research_flow.status_of(reg["serp_capture"], env={}, credential="OK",
                                   cad={})[0] == research_flow.MISSING
    assert research_flow.status_of(reg["gallery_analysis"], env={}, vision_ok=False,
                                   cad=cad)[0] == research_flow.BLOCKED


# ---- Mission Control: per-source evidence (read-only, owner-only route) ----------------------


def test_the_board_shows_every_source_and_what_each_shop_led_to():
    from brambleloop.app.command_center import p0_board as B
    from brambleloop.runtime.intel_ops import benchmark_alias

    db = S.make_db()
    _run_change(db, judged=True)
    slug = research_flow.lineage(db)[0]["proposals"][0]["slug"]
    sec = B.view(db)["sections"]["research_sources"]
    assert sec["level"] is not None, sec
    srcs = {r["id"]: r for r in sec["sources"]}
    assert len(srcs) == len(research_flow.sources())
    corroborating = {benchmark_alias("madeline_mae_co"), benchmark_alias("zkbdesigner")}
    for m in watchlist.WATCHLIST:
        r = srcs[benchmark_alias(m.key)]
        assert r["agent"] == "market_radar" and "Open API v3" in r["method"]
        for k in ("last_attempt", "last_success", "source_timestamp", "listings_observed",
                  "changes_discovered", "next_scan", "consecutive_failures", "backoff_until",
                  "findings", "concepts", "engineering"):
            assert k in r, (m.key, k)
        if benchmark_alias(m.key) in corroborating:
            assert r["findings"] == 1 and r["concepts"] == [slug] and r["engineering"] == [slug]
            assert r["listings_observed"] and r["last_success"]
        else:
            assert r["engineering"] == []
    assert srcs["research_fetch"]["status"] == research_flow.DISABLED
    assert srcs["external_trends"]["status"] == research_flow.MISSING
    assert {x["id"] for x in sec["limitations"]} >= {"research_fetch", "external_trends"}
    assert sec["loop"]["in_engineering"] == 1
    assert sec["conclusion"]["outcome"] == research_flow.OPPORTUNITIES
    text = json.dumps(sec, default=str).lower()
    for m in watchlist.WATCHLIST:
        assert m.shop_name.lower() not in text and m.key not in text, m.key


def test_the_board_names_a_failing_shop_and_still_reads_the_rest():
    from brambleloop.app.command_center import p0_board as B
    from brambleloop.runtime.intel_ops import benchmark_alias

    db = S.make_db()
    reader = S.Reader(_catalogues(changed=True))
    real = reader.resolve_shop

    def resolve(name):
        if name == "FireflyCrochets":
            raise RuntimeError("upstream timeout")
        return real(name)

    reader.resolve_shop = resolve
    S.scan(db, reader, S.at(0, 6))
    srcs = {r["id"]: r for r in B.view(db)["sections"]["research_sources"]["sources"]}
    bad = srcs[benchmark_alias("firefly_crochets")]
    assert bad["consecutive_failures"] == 1 and bad["failure_class"], bad
    ok = srcs[benchmark_alias("zkbdesigner")]
    assert ok["consecutive_failures"] == 0 and ok["last_success"], ok


def test_the_board_section_writes_nothing():
    from brambleloop.app.command_center import p0_board as B
    from sqlalchemy import inspect

    from brambleloop.radar.intake import RadarConcept

    db = S.make_db()
    # A database where no concept was ever proposed: the board must not create the table.
    RadarConcept.__table__.drop(bind=db.engine, checkfirst=True)
    research.ResearchTask.__table__.drop(bind=db.engine, checkfirst=True)
    before = set(inspect(db.engine).get_table_names())
    assert RadarConcept.__tablename__ not in before
    assert research.ResearchTask.__tablename__ not in before
    sec = B.view(db)["sections"]["research_sources"]
    assert set(inspect(db.engine).get_table_names()) == before
    assert sec["conclusion"] is None and sec["state"] == "DEGRADED"
    assert research_flow.latest_conclusion(db) is None



def test_a_shop_name_in_the_evidence_makes_the_section_unknown_not_shown():
    from unittest.mock import patch

    from brambleloop.app.command_center import p0_board as B

    db = S.make_db()
    leaky = tuple({**src, "note": "seen at ZKBDESIGNER"} if src["id"] == "serp_capture"
                  else src for src in research_flow.sources())
    with patch.object(research_flow, "sources", lambda: leaky):
        try:
            research_flow.evidence(db)
        except ValueError:
            pass
        else:
            raise AssertionError("a shop name would have reached Mission Control")
        leaky_label = tuple({**src, "label": "about ZKBDESIGNER"} if src["id"] == "serp_capture"
                            else src for src in research_flow.sources())
    with patch.object(research_flow, "sources", lambda: leaky_label):
        sec = B.view(db)["sections"]["research_sources"]
    assert sec["state"] == B.UNKNOWN and "zkbdesigner" not in json.dumps(sec).lower(), sec


def test_a_never_succeeded_or_failing_source_never_reads_ok():
    """Review M1: the per-row pill is derived. A shop that has never scanned successfully, or
    is failing, reads UNKNOWN / DEGRADED -- never OK."""
    from brambleloop.app.command_center import p0_board as B
    from brambleloop.runtime.intel_ops import benchmark_alias

    H = research_flow.health_of
    base = {"status": research_flow.SCHEDULED, "consecutive_failures": 0, "stale": False}
    assert H({**base, "last_success": None}) == "UNKNOWN"
    assert H({**base, "last_success": "2026-11-19T00:00:00+00:00",
              "consecutive_failures": 2}) == "DEGRADED"
    assert H({**base, "last_success": None, "consecutive_failures": 1}) == "DEGRADED"
    assert H({**base, "last_success": "2026-11-19T00:00:00+00:00", "stale": True}) == "STALE"
    assert H({**base, "last_success": "2026-11-19T00:00:00+00:00"}) == "OK"
    assert H({"status": research_flow.SCHEDULED, "failures_7d": 3,
              "last_success": "2026-11-19T00:00:00+00:00"}) == "DEGRADED"
    assert H({"status": research_flow.MISSING}) == "UNKNOWN"
    assert H({"status": research_flow.DISABLED, "last_success": "x"}) == "DEGRADED"

    db = S.make_db()
    reader = S.Reader(_catalogues(changed=True))
    real = reader.resolve_shop

    def resolve(name):
        if name == "FireflyCrochets":
            raise RuntimeError("upstream timeout")
        return real(name)

    reader.resolve_shop = resolve
    S.scan(db, reader, S.at(0, 6))
    srcs = {r["id"]: r for r in B.view(db)["sections"]["research_sources"]["sources"]}
    bad = srcs[benchmark_alias("firefly_crochets")]
    assert bad["last_success"] is None and bad["health"] in ("UNKNOWN", "DEGRADED"), bad
    assert bad["health"] != "OK"
    never = [r for r in srcs.values() if not r.get("last_success")]
    assert never and all(r["health"] != "OK" for r in never), \
        [(r["id"], r["health"]) for r in never if r["health"] == "OK"]
    # A shop that scanned is OK only once its gate is open: here the fixture credential
    # reads UNKNOWN, so it is blocked (DEGRADED); with the gate open it would read OK.
    ok = srcs[benchmark_alias("zkbdesigner")]
    assert ok["last_success"] and ok["status"] == research_flow.BLOCKED
    assert ok["health"] == "DEGRADED"
    assert H({**ok, "status": research_flow.SCHEDULED}) == "OK"


def test_the_off_etsy_channels_of_mp1_2_s4_are_visible_as_unavailable():
    """Review M2: competitors' websites, YouTube and Pinterest are registry rows, MISSING
    with their reason, in the code registry, the prose registry and the board."""
    from brambleloop.app.command_center import p0_board as B

    reg = {s["id"]: s for s in research_flow.sources()}
    md = (ROOT / "research/final_build/w6/research_sources.md").read_text()
    for sid in ("competitor_websites", "youtube", "pinterest"):
        st, why = research_flow.status_of(reg[sid], env={}, credential="OK")
        assert st == research_flow.MISSING and "UNAVAILABLE" in why, (sid, st, why)
        assert f"`{sid}`" in md, sid
    sec = B.view(S.make_db())["sections"]["research_sources"]
    lim = {x["id"]: x for x in sec["limitations"]}
    assert {"competitor_websites", "youtube", "pinterest"} <= set(lim)
    assert all("UNAVAILABLE" in lim[k]["why"] for k in ("competitor_websites", "youtube",
                                                         "pinterest"))


def test_an_unreadable_vision_state_never_reads_scheduled():
    reg = {s["id"]: s for s in research_flow.sources()}
    cad = research_flow.cadences()
    st, why = research_flow.status_of(reg["gallery_analysis"], env={}, vision_ok=None, cad=cad)
    assert st == research_flow.BLOCKED and "could not be read" in why, (st, why)
    assert research_flow.status_of(reg["gallery_analysis"], env={}, vision_ok=True,
                                   cad=cad)[0] == research_flow.SCHEDULED


def test_findings_read_unknown_not_zero_without_lineage_tables():
    from brambleloop.radar.intake import RadarConcept

    db = S.make_db()
    RadarConcept.__table__.drop(bind=db.engine, checkfirst=True)
    rows = [r for r in research_flow.evidence(db)["sources"] if r["kind"] == "shop"]
    assert rows and all(r["findings"] is None and r["concepts"] is None
                        and r["engineering"] is None for r in rows), rows[0]


def test_a_conclusion_failure_is_recorded_and_does_not_fail_intake():
    """Review LOW: intake has already written when the conclusion runs; a failure there is
    audited and named in the job's output, and the job still succeeds."""
    from unittest.mock import patch

    from brambleloop.core.models import AuditLog

    db = S.make_db()

    def boom(*a, **k):
        raise RuntimeError("conclusion store unavailable")

    with patch.object(research_flow, "conclude", boom):
        out = S.intake(db, S.at(0, 6))
    assert out["research_outcome"] == research_flow.CONCLUSION_FAILED, out
    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(
            AuditLog.action == "intel.research_conclusion_failed")))
    assert rows and "conclusion store unavailable" in rows[0].detail["error"]


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                fails += 1
                import traceback

                traceback.print_exc()
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if fails else 0)
