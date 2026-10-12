"""Certification repair: the culture engine and the teardown laboratory, through the runtime.

The proof-chain audit (2026-09-27, C-41/C-43/C-44) found the culture libraries (#134-#146)
and the teardown libraries (#151-#170) tested and unreachable: `culture.sweep` stored
readings and never translated, scored, cleared or exited anything; nothing could write a
`TeardownFinding`; `promise_audit`, `prefill`, `promote`, `check_unique_value`,
`delight_question` and `manifest_markdown` had no caller.

These tests drive the `culture.sweep` handler through the handler registry with a real
JobContext, the engine it calls, the intake path, and the new teardown and culture routes
through FastAPI's TestClient. Every topic, listing, purchase and file here is a synthetic
fixture: no purchased PDF, text or photo is read, and no network is touched.

Run: cd brambleloop && $PY tests/test_cert_culture_teardown.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="cert_culture_teardown_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP}/app.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_BENCHMARK_LIBRARY"] = os.path.join(_TMP, "library")
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)
os.environ.pop("BRAMBLELOOP_CULTURE_TOPICS", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)
TOKEN = "t" * 32
os.environ["BRAMBLELOOP_OPS_TOKEN"] = TOKEN


def _no_network(*_a, **_k):
    raise OSError("network refused by the certification harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, BenchmarkListing, BenchmarkProduct, CultureConcept, CultureIPElement,
    CultureSignal, Improvement, Job, ListingOutcome, PatternVersion, Product, TeardownFinding,
)
from brambleloop.core.resilience import TransientError  # noqa: E402
from brambleloop.culture import classify, engine, feeds, radar, rights  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import JobContext, handlers  # noqa: E402
from brambleloop.teardown import audits, intake, lab, library, scorecard  # noqa: E402

TODAY = date(2026, 9, 27)          # 89 days before 25 December
ENGINEERING_TYPES = ("cir.draft", "cir.compile", "gate.certify", "listing.draft",
                     "store.publish")


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/c.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _reading(key: str, article: str, on: str = "2026-09-25") -> dict:
    return {"signal_key": key, "article": article, "source": f"wikimedia_pageviews:{article}",
            "observed_on": on}


def _observe(db, key: str, values: list[float], start: date = date(2026, 9, 20)) -> None:
    for i, v in enumerate(values):
        radar.observe(db, key, channel="reference", interest=v,
                      observed_on=(start + timedelta(days=i)).isoformat(), source="fixture")


def _candidates(db, **where) -> list[CultureConcept]:
    with db.session() as s:
        q = select(CultureConcept)
        for k, v in where.items():
            q = q.where(getattr(CultureConcept, k) == v)
        rows = list(s.scalars(q))
        s.expunge_all()
        return rows


def _signal(db, key: str) -> CultureSignal:
    with db.session() as s:
        row = s.scalar(select(CultureSignal).where(CultureSignal.key == key))
        s.expunge_all()
        return row


def _no_engineering_jobs(db) -> None:
    with db.session() as s:
        types = {j.job_type for j in s.scalars(select(Job))}
    assert not (types & set(ENGINEERING_TYPES)), types


# ---------------------------------------------------------------------------
# culture.sweep, through the handler registry


def _fake_get(url: str) -> dict:
    """A rising 28-day pageview series for any article: synthetic, never fetched."""
    return {"items": [{"timestamp": f"202609{d:02d}00", "views": 100 + d * 10}
                      for d in range(1, 29)]}


def test_the_sweep_handler_translates_scores_clears_and_persists_what_it_stored():
    db = _db()
    saved = (feeds.discover, feeds._get, classify.classify, time.sleep)
    os.environ["BRAMBLELOOP_CULTURE_TOPICS"] = "Nostalgia,Home_Alone,Crochet"

    def no_discovery(**_k):
        raise TransientError("discovery refused by the harness")

    feeds.discover = no_discovery
    feeds._get = _fake_get
    classify.classify = lambda topics, **_k: {"filed": {}, "placed": {}}
    time.sleep = lambda _s: None
    try:
        queue = JobQueue(db)
        ctx = JobContext(job=queue.enqueue("market_radar", "culture.sweep", {}), db=db,
                         queue=queue, registry=Registry(db), phase=None)
        out = handlers.get("culture.sweep")(ctx)
    finally:
        feeds.discover, feeds._get, classify.classify, time.sleep = saved
        os.environ.pop("BRAMBLELOOP_CULTURE_TOPICS", None)

    assert out["ran"] and out["recorded"] == 3, out
    culture = out["culture"]
    # Crochet is a craft reference, not a cultural signal: reported unfiled, never invented.
    assert "crochet" in culture["unfiled"], culture
    nostalgia = _signal(db, "nostalgia")
    assert nostalgia is not None and nostalgia.domain == "nostalgia_era"
    # #134: decomposed into primitives, the absent ones named rather than filled.
    assert nostalgia.primitives["primitives"]["emotion"].startswith("longing")
    assert "character_archetype" in nostalgia.primitives["absent"]
    # #136: scored from observations, with the evidence weight and provenance stored.
    assert nostalgia.score["observed"]["search_momentum"] == 1.0
    assert "evidence_weight" in nostalgia.score and nostalgia.score["provenance"]
    # #137/#144: one candidate per era territory, persisted at creative development.
    era_rows = _candidates(db, signal_key="nostalgia", origin="era_combination")
    assert len({r.era for r in era_rows}) == 9, [r.era for r in era_rows]
    assert all(r.stage == "creative_development" for r in era_rows)
    # Home Alone is not a cue the table can read and is not placed by a classifier: unfiled.
    assert "home_alone" in culture["unfiled"]
    with db.session() as s:
        assert s.scalar(select(AuditLog).where(AuditLog.action == engine.ACTION_SWEEP))
    _no_engineering_jobs(db)


# ---------------------------------------------------------------------------
# The engine, on a fixed date


def test_a_property_topic_goes_to_the_original_lane_and_its_title_never_reaches_a_premise():
    db = _db()
    _observe(db, "christmas_vacation", [0.6, 0.9])
    out = engine.run(db, [_reading("christmas_vacation", "Christmas_Vacation")],
                     placed={"Christmas_Vacation": "film"}, today=TODAY)
    row = _signal(db, "christmas_vacation")
    assert row.lane == rights.ORIGINAL                               # #135: routed, not blocked
    assert row.protected_tokens[0]["text"] == "Christmas Vacation"
    rows = _candidates(db, signal_key="christmas_vacation")
    assert rows, out                                               # the territory continues
    assert all("christmas vacation" not in r.premise.lower() for r in rows)
    assert row.score["observed"]["rights_feasibility"] == 0.5


def test_a_premise_carrying_a_declared_token_is_kept_as_a_rejection_not_a_candidate():
    db = _db()
    token = rights.ProtectedToken(text="Grinchly Pete", asset_class=rights.CHARACTER_NAME)
    t = engine.translate.Translation(slug="x-grinchly", family="pillow",
                                     premise="a Grinchly Pete cushion for the reading chair")
    got = engine.persist_candidate(db, signal_key="x", translation=t,
                                   lane=rights.ORIGINAL, origin="white_space", tokens=[token])
    assert got["status"] == engine.REJECTED
    row = _candidates(db, slug="x-grinchly")[0]
    assert row.status == "rejected" and "Grinchly Pete" in row.reason


def test_an_unreadable_topic_is_recorded_and_not_given_invented_primitives():
    db = _db()
    _observe(db, "home_alone", [0.5, 0.7])
    out = engine.run(db, [_reading("home_alone", "Home_Alone")],
                     placed={"Home_Alone": "film"}, today=TODAY)
    got = out["processed"][0]
    assert got["translated"] is False and "inventing" in got["reason"]
    assert _signal(db, "home_alone").lane == rights.ORIGINAL
    assert not _candidates(db, signal_key="home_alone")


def test_a_strong_dated_signal_gets_the_rapid_cell_and_nothing_past_creative_development():
    db = _db()
    _observe(db, "christmas", [0.6, 0.95])
    out = engine.run(db, [_reading("christmas", "Christmas")], today=TODAY)
    assert out["rapid"] and out["rapid"][0]["signal"] == "christmas", out
    rapid_run = out["rapid"][0]
    assert set(rapid_run["accelerated"]) == set(engine.RAPID_ACCELERATES)
    assert "cir_validation" in rapid_run["gates_unchanged"]
    rows = _candidates(db, signal_key="christmas", status="candidate")
    # #138: the tournament field spans every family with distinct premises.
    ws = [r for r in rows if r.origin == "rapid_response"]
    assert len({r.family for r in ws}) == 15 and len({r.premise for r in ws}) == 15
    assert all(r.priority == "rapid" and r.stage == "creative_development" for r in rows)
    assert _signal(db, "christmas").outcome["white_space"]["broad_enough"] is True
    # #143: the territory is architected as a collection with every role filled.
    plans = {p["theme"]: p for p in out["collections"]}
    assert plans["chaotic_family_holiday"]["is_a_collection"] is True
    # #146: a collection world proposed, as proposed -- never recurring by assertion.
    with db.session() as s:
        world = s.scalar(select(CultureIPElement).where(
            CultureIPElement.key == "world:chaotic_family_holiday"))
        assert world is not None and world.status == "proposed"
    _no_engineering_jobs(db)


def test_a_thinly_observed_signal_is_scored_and_remembered_but_not_developed():
    """A number over the bar with under half its components observed is an impression."""
    db = _db()
    _observe(db, "summer", [0.1])
    out = engine.run(db, [_reading("summer", "Summer")], today=TODAY)
    got = out["processed"][0]
    score = _signal(db, "summer").score
    assert score["score"] >= engine.STRONG and score["trustworthy"] is False, score
    assert got["strong"] is False and not out["tournaments"] and not out["rapid"]
    assert not _candidates(db, signal_key="summer", origin="white_space")


def test_a_declining_signal_exits_with_its_lesson_and_its_candidates_are_withdrawn():
    db = _db()
    _observe(db, "nostalgia", [0.9, 0.95])
    engine.run(db, [_reading("nostalgia", "Nostalgia")], today=TODAY)
    assert _candidates(db, signal_key="nostalgia", status="candidate")
    _observe(db, "nostalgia", [0.4], start=date(2026, 9, 26))    # down 58% from its peak
    out = engine.run(db, [_reading("nostalgia", "Nostalgia", on="2026-09-26")], today=TODAY)
    assert out["exits"] == ["nostalgia"], out
    row = _signal(db, "nostalgia")
    assert row.state == radar.EXITED and "declining_interest" in row.exit_reason
    assert row.outcome["lesson"]
    assert not _candidates(db, signal_key="nostalgia", status="candidate")
    assert _candidates(db, signal_key="nostalgia", status="withdrawn")
    assert "nostalgia" in radar.memory(db)["exited_with_a_lesson"]


def test_a_closing_window_exits_on_make_time_even_while_interest_is_rising():
    db = _db()
    _observe(db, "halloween", [0.5, 0.9])
    out = engine.run(db, [_reading("halloween", "Halloween")], today=date(2026, 10, 20))
    assert out["exits"] == ["halloween"] and not out["rapid"]
    assert "insufficient_make_time" in _signal(db, "halloween").exit_reason
    rejected = _candidates(db, signal_key="halloween", status="rejected")
    assert rejected and all("window" in r.reason for r in rejected)


def test_the_clearance_lane_refuses_a_hope_and_accepts_a_recorded_basis():
    db = _db()
    _observe(db, "old_tale", [0.6, 0.9])
    engine.run(db, [_reading("old_tale", "Old_Tale_Christmas")],
               placed={"Old_Tale_Christmas": "film"}, today=TODAY)
    assert _signal(db, "old_tale").lane == rights.ORIGINAL
    try:
        engine.clear(db, "old_tale", kind="generic", evidence="seems fine",
                     recorded_by="owner")
        raise AssertionError("a basis with nothing behind it was accepted")
    except rights.RightsRefused:
        pass
    assert _signal(db, "old_tale").lane == rights.ORIGINAL
    got = engine.clear(db, "old_tale", kind=rights.PUBLIC_DOMAIN,
                       evidence="first published in a London annual, bibliographic record",
                       recorded_by="owner", publication_year=1843)
    assert got["routing"]["lane"] == rights.DIRECT
    # The basis survives the next sweep rather than being reset by it.
    engine.run(db, [_reading("old_tale", "Old_Tale_Christmas")],
               placed={"Old_Tale_Christmas": "film"}, today=TODAY)
    assert _signal(db, "old_tale").lane == rights.DIRECT


def test_a_launched_concept_carries_its_measured_outcomes_back_to_its_signal():
    db = _db()
    _observe(db, "nostalgia", [0.8, 0.9])
    engine.run(db, [_reading("nostalgia", "Nostalgia")], today=TODAY)
    slug = _candidates(db, signal_key="nostalgia")[0].slug[:80]
    with db.session() as s:
        s.query(CultureConcept).filter(CultureConcept.signal_key == "nostalgia").first() \
            .product_slug = slug
        s.add(Product(slug=slug, title="fixture", status="certified"))
        s.add(ListingOutcome(product_slug=slug, period_start="2026-09-01",
                             period_end="2026-09-07", impressions=10, visits=2,
                             source="fixture"))
    got = engine.record_launch_outcomes(db)
    assert got["launches"] == 1
    row = _signal(db, "nostalgia")
    assert row.state == radar.LAUNCHED
    assert row.outcome["launches"][0]["outcomes"][0]["visits"] == 2


# ---------------------------------------------------------------------------
# Teardown: intake, recording, promotion, QA and the manifest


def _listing(db, ref: str = "1234") -> None:
    with db.session() as s:
        s.add(BenchmarkListing(
            benchmark_key=benchmarks.MJS_KEY, listing_ref=ref, title="Synthetic throw",
            pod="blankets", product_type="pattern", price_cad=8.5, media_count=5,
            url=f"https://example.invalid/{ref}",
            detail={"deliverable": {"has_chart": True, "has_video": True}}))


def test_intake_runs_the_promise_audit_prefills_the_audits_and_writes_the_manifest():
    db = _db()
    _listing(db)
    tmp = Path(tempfile.mkdtemp())
    result = intake.receive(db, "1234", [("synthetic-pattern.pdf", b"PDF"),
                                         ("synthetic-chart.png", b"PNG")],
                            env={library.LIBRARY_ENV: str(tmp)}, mirror_files=False)
    alignment = result["promise_alignment"]
    assert "chart_included" in alignment["kept"]
    assert {b["promise"] for b in alignment["broken"]} == {"video_included"}
    assert result["audit_prefill"]["delivery_packaging"]["file_count"]["files"] == 2
    manifest = Path(result["manifest"]["path"])
    assert manifest.parent == tmp.resolve() and manifest.name == "BENCHMARK_MANIFEST.md"
    assert "mjs-1234" in manifest.read_text()
    assert ROOT.resolve() not in manifest.resolve().parents
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == intake.INTAKE_ACTION))
        assert row.detail["broken_promises"]


def _answers(spec_key: str, *, strong: str = "", weak: str = "") -> dict:
    spec = audits.BY_KEY[spec_key]
    out = {}
    for e in spec.elements:
        if e.kind == audits.PRESENCE:
            out[e.key] = True
        elif e.key == strong:
            out[e.key] = {"score": 5, "mechanism": "every chart page repeats its full legend",
                          "advantage": "colour_independent_charts"}
        elif e.key == weak:
            out[e.key] = {"score": 1, "mechanism": "row numbers sit on the opposite edge"}
        else:
            out[e.key] = 3
    return out


def _client():
    from fastapi.testclient import TestClient

    from brambleloop.app import main

    main.db.create_all()
    Registry(main.db).seed_defaults()
    return TestClient(main.app), main.db


def _purchase(db, ref: str = "mjs-9") -> None:
    with db.session() as s:
        if s.scalar(select(BenchmarkProduct).where(BenchmarkProduct.ref == ref)) is None:
            s.add(BenchmarkProduct(ref=ref, seller="SyntheticShop", category="blanket",
                                   files=[{"name": "p.pdf", "role": "pattern_pdf",
                                           "bytes": 3, "sha256": "0" * 64},
                                          {"name": "chart.png", "role": "chart",
                                           "bytes": 3, "sha256": "1" * 64}]))


def test_the_audit_route_records_findings_promotes_each_and_asks_the_delight_question():
    client, db = _client()
    _purchase(db)
    auth = {"Authorization": f"Bearer {TOKEN}"}
    body = {"benchmark_ref": "mjs-9", "audit": "chart_benchmark",
            "answers": _answers("chart_benchmark", strong="legends", weak="row_numbering")}
    assert client.post("/api/teardown/audit", json=body).status_code == 401
    r = client.post("/api/teardown/audit", json=body, headers=auth)
    assert r.status_code == 200, r.text
    got = r.json()
    assert len(got["findings_recorded"]) == 2
    assert all(p["promoted"] for p in got["promotions"]), got["promotions"]
    assert got["delight"]["answerable"] is True and got["delight"]["weakest"] == "chart_quality"
    with db.session() as s:
        rows = list(s.scalars(select(TeardownFinding).where(
            TeardownFinding.benchmark_ref == "mjs-9")))
        assert rows and all(r.promoted for r in rows)
        ids = [r.detail["improvement_id"] for r in rows]
        assert len(list(s.scalars(select(Improvement).where(Improvement.id.in_(ids))))) == 2
    # #162: the composite now has a writer.
    assert "chart_quality" in scorecard.composite_standard(db)["dimensions"]


def test_the_audit_route_refuses_a_partial_schedule_and_an_unknown_benchmark():
    client, db = _client()
    _purchase(db)
    auth = {"Authorization": f"Bearer {TOKEN}"}
    partial = _answers("chart_benchmark")
    partial.pop("legends")
    r = client.post("/api/teardown/audit", headers=auth,
                    json={"benchmark_ref": "mjs-9", "audit": "chart_benchmark",
                          "answers": partial})
    assert r.status_code == 400 and "incomplete" in r.json()["error"]
    r = client.post("/api/teardown/audit", headers=auth,
                    json={"benchmark_ref": "mjs-never-bought", "audit": "chart_benchmark",
                          "answers": _answers("chart_benchmark")})
    assert r.status_code == 400 and "not a purchased benchmark" in r.json()["error"]


def test_the_finding_route_refuses_competitor_text_and_records_a_governance_refusal():
    client, db = _client()
    _purchase(db)
    auth = {"Authorization": f"Bearer {TOKEN}"}
    r = client.post("/api/teardown/finding", headers=auth, json={
        "benchmark_ref": "mjs-9", "dimension": "instruction_clarity", "score": 4,
        "mechanism": "Row 1: ch 3, dc in each across", "improvement": "copy this layout"})
    assert r.status_code == 400
    r = client.post("/api/teardown/finding", headers=auth, json={
        "benchmark_ref": "mjs-9", "dimension": "listing_promise_alignment", "score": 5,
        "mechanism": "the listing states exactly what the download contains",
        "improvement": "loosen the claim gates so our listings sound as confident as theirs"})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["promotion"]["promoted"] is False
    with db.session() as s:
        row = s.get(TeardownFinding, got["finding"])
        assert row.promoted is False and row.detail["promotion_refused"]


def test_our_own_product_is_qa_checked_for_unique_value_and_delight():
    db = _db()
    with db.session() as s:
        good = Product(slug="fixture-good", title="g", status="certified")
        bare = Product(slug="fixture-bare", title="b", status="certified")
        s.add_all([good, bare])
        s.flush()
        s.add(PatternVersion(product_id=good.id, version="1.0.0", cir_json={},
                             certified=True, release_hash="a" * 64, certificate={
                                 "granted": True, "findings": [],
                                 "stages_run": ["compile", "specification", "twin",
                                                "write", "reverse"]}))
        s.add(PatternVersion(product_id=bare.id, version="1.0.0", cir_json={},
                             certified=True, release_hash="b" * 64,
                             certificate={"granted": True, "findings": [],
                                          "stages_run": ["twin"]}))
    out = lab.product_qa_all(db)
    by = {r["product"]: r for r in out["results"]}
    assert by["fixture-good"]["blocks_release"] is False
    assert set(by["fixture-good"]["unique_value"]["advantages"]) == {
        "deterministic_validation", "reverse_compilation"}
    assert by["fixture-bare"]["blocks_release"] is True             # parity is not a position
    # C-69 (#169): our own product's delight is measured from what it has -- here only its
    # certificate (confidence 3: certified, no physical sample) -- and the mechanisms with
    # nothing to read stay unscored rather than neutral. C-80 defect 2: this fixture stores an
    # empty CIR, so its size run is UNMEASURED and customization is unscored too (it used to
    # read 3 from a `sizes` key no CIR ever carried).
    good_delight = by["fixture-good"]["delight"]
    assert good_delight["answerable"] is True
    assert good_delight["drivers"] == {"confidence": 3}, good_delight
    assert "customization" in good_delight["unscored"]
    assert "bonus_utility" in good_delight["unscored"] and "navigation" in good_delight["unscored"]
    assert by["fixture-good"]["unique_value"]["status"] == "UNMEASURED"   # no benchmark scored
    lab.record_finding(db, "brambleloop:fixture-good", "chart_quality", 4,
                       "every chart carries a per-yarn letter in each cell",
                       "keep the per-yarn letter on every chart page we publish")
    again = lab.product_qa(db, "fixture-good")
    assert again["delight"]["answerable"] is True
    # Our own scores never enter the competitor composite.
    assert "brambleloop:fixture-good" not in scorecard.composite_standard(db)[
        "source_benchmarks"]
    with db.session() as s:
        assert s.scalar(select(AuditLog).where(AuditLog.action == lab.ACTION_QA))


def test_the_manifest_and_clearance_routes_write_and_are_authenticated():
    client, db = _client()
    _purchase(db, "mjs-10")
    auth = {"Authorization": f"Bearer {TOKEN}"}
    assert client.post("/api/teardown/manifest").status_code == 401
    r = client.post("/api/teardown/manifest", headers=auth)
    assert r.status_code == 200 and "mjs-10" in r.json()["markdown"]
    assert Path(r.json()["path"]).is_file()
    assert client.post("/api/culture/clearance", json={}).status_code == 401
    r = client.post("/api/culture/clearance", headers=auth,
                    json={"signal_key": "nothing", "kind": "generic",
                          "evidence": "x", "recorded_by": "owner"})
    assert r.status_code == 400 and r.json()["lane"] == rights.ORIGINAL
    assert client.get("/api/culture/development").status_code == 200


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
