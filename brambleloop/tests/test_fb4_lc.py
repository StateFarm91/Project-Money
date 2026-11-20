"""Final Build wave fb4-LC: Learn graph consumer, lesson links, lesson-asset byte provenance,
public-source licences, upload licence terms, surface unknowns, component gauge refusal and
the represented-variant contract (F-815, F-808, F-821, F-787, F-786, F-588, F-754, F-757).

Hermetic: no network, no model, no secret. Failing checks are findings; do not weaken them.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import copy
import hashlib
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT), str(ROOT / "tests")]
_TMP = tempfile.mkdtemp(prefix="fb4_lc_")
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

from sqlalchemy import select  # noqa: E402

from brambleloop.cir.model import CIR, Configuration, Gauge, variant_key  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkLicence, BenchmarkProduct  # noqa: E402
from brambleloop.learn import service as LS  # noqa: E402
from brambleloop.learn.models import LearnEdge  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.publish import eligibility as E  # noqa: E402
from brambleloop.publish import listing_set as L  # noqa: E402

ORIGIN_VAR = "BRAMBLELOOP_LEARN_PUBLIC_ORIGIN"
OPS_TOKEN = "fb4-lc-operator-token-0123456789abcdef"


def _db(path: str | None = None) -> Database:
    db = Database("sqlite:///" + (path or f"{tempfile.mkdtemp(prefix='fb4lc_')}/t.sqlite"),
                  scratch=True)
    db.create_all()
    return db


def _spec(topics=("stitch:sc",), sha="a" * 64):
    return {"author": "pattern-engineering", "learner_problem": "work a single crochet",
            "topics": list(topics), "terminology": "US",
            "assumptions": {"hook_mm": 4, "yarn_weight": "worsted"},
            "assets": [{"rights": "brambleloop_original", "source": "canonical-demo",
                        "sha256": sha}],
            "steps": [{"stitch": "sc", "repeat": 2, "consumes": 2, "produces": 2,
                       "term": "sc", "instruction": "Work one sc in each of next two sts."}]}


def _approve(db, slug, spec):
    revision = LS.save_lesson(db, slug, spec)
    LS.review_lesson(db, slug, revision, "independent-qa",
                     dict.fromkeys(LS.DIMENSIONS, "PASS"), "fixture-review:test-only")
    assert LS.approved_lesson(db, slug) is not None
    return revision


class _Env:
    def __init__(self, **values):
        self.values = values

    def __enter__(self):
        self.saved = {k: os.environ.get(k) for k in self.values}
        for k, v in self.values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _base_cir() -> CIR:
    return copy.deepcopy(launch0.cir_for("basket_small"))


# ---- F-815: the graph is read, and an edge changes a decision -------------------------


def test_adding_a_graph_edge_changes_which_lessons_help_links_returns():
    db = _db()
    _approve(db, "single-crochet", _spec())
    assert LS.help_links(db, ["stitch:dc"]) == []
    LS.link_topics(db, "stitch:dc", "stitch:sc", "prerequisite", {"why": "test"})
    links = LS.help_links(db, ["stitch:dc"])
    assert [link["slug"] for link in links] == ["single-crochet"]
    assert links[0]["topics"] == ["stitch:sc"]
    # Not followed backwards, and only topic relations are followed.
    assert LS.help_links(db, ["stitch:hdc"]) == []
    for bad in (("pattern:1:x", "stitch:sc"), ("stitch:sc", "stitch:sc"), ("sc", "stitch:sc")):
        try:
            LS.link_topics(db, *bad)
            raise AssertionError(f"accepted a non-topic edge {bad}")
        except ValueError:
            pass


def test_graph_read_is_db_backed_and_behind_learn_editor_auth():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from brambleloop.learn.api import router

    db = _db()
    _approve(db, "single-crochet", _spec())
    app = FastAPI()
    app.include_router(router(db))
    with _Env(BRAMBLELOOP_OPS_TOKEN=OPS_TOKEN), TestClient(app) as c:
        assert c.get("/api/learn/graph").status_code == 401
        auth = {"authorization": f"Bearer {OPS_TOKEN}"}
        body = c.get("/api/learn/graph", headers=auth).json()
        assert {"source": "lesson:single-crochet", "target": "stitch:sc"} in [
            {"source": e["source"], "target": e["target"]} for e in body["edges"]]
        assert c.post("/api/learn/graph/edges", json={"source": "stitch:dc",
                                                      "target": "stitch:sc"}).status_code == 401
        added = c.post("/api/learn/graph/edges", headers=auth,
                       json={"source": "stitch:dc", "target": "stitch:sc",
                             "relation": "related", "reason": "dc builds on sc"})
        assert added.status_code == 200
        around = c.get("/api/learn/graph", params={"node": "stitch:dc"}, headers=auth).json()
        assert [(e["source"], e["relation"], e["target"]) for e in around["edges"]] == [
            ("stitch:dc", "related", "stitch:sc")]
        bad = c.post("/api/learn/graph/edges", headers=auth,
                     json={"source": "stitch:dc", "target": "stitch:sc", "relation": "copies"})
        assert bad.status_code == 422
    with db.session() as s:
        assert len(s.scalars(select(LearnEdge)).all()) == 2


# ---- F-808: support answers and listing copy link approved lessons --------------------


def _support_reply(db, cir):
    from brambleloop.support.department import CustomerExperience

    return CustomerExperience(db).handle(customer_ref="buyer-1", product_slug=cir.slug,
                                         message="How many stitches should I have at the "
                                                 "end of round 2?", cir=cir)


def test_support_answer_links_an_approved_lesson_only_with_an_owned_origin_and_via_edges():
    db = _db()
    cir = _base_cir()
    # A lesson on a topic the pattern's own structure does not name.
    _approve(db, "joining-rounds", _spec(topics=("technique:joining",)))
    with _Env(**{ORIGIN_VAR: "https://learn.example.test"}):
        first = _support_reply(db, cir)
        assert first.lesson_links == [] and "learn.example.test" not in first.body
        # The specialist's graph node routes to the lesson once an edge says so (F-815).
        LS.link_topics(db, "support:" + first.specialist, "technique:joining", "related")
        second = _support_reply(db, cir)
        assert [link["slug"] for link in second.lesson_links] == ["joining-rounds"]
        assert second.lesson_links[0]["url"].startswith("https://learn.example.test/learn/")
        assert second.lesson_links[0]["url"] in second.body
        assert second.to_dict()["lesson_links"] == second.lesson_links
    with _Env(**{ORIGIN_VAR: None}):
        assert _support_reply(db, cir).lesson_links == [], "linked with no owned origin"


def test_an_unapproved_lesson_is_never_linked_from_support_or_listing():
    db = _db()
    cir = _base_cir()
    LS.save_lesson(db, "draft-only", _spec(topics=("technique:joining",)))   # never reviewed
    LS.link_topics(db, "support:general", "technique:joining")
    with _Env(**{ORIGIN_VAR: "https://learn.example.test"}):
        assert LS.support_help_links(db, cir.to_dict(), "general") == []
        assert LS.listing_help_links(db, cir.to_dict()) == []
        _approve(db, "draft-only", _spec(topics=("technique:joining",)))
        assert [x["slug"] for x in LS.support_help_links(db, cir.to_dict(), "general")] == [
            "draft-only"]


def test_listing_description_carries_approved_lesson_links_and_nothing_without_origin():
    from brambleloop.commerce import seo

    db = _db()
    cir = _base_cir()
    topics = sorted(LS.topics(cir.to_dict()))
    assert topics, "fixture CIR exposes no topics"
    _approve(db, "pattern-topic", _spec(topics=(topics[0],)))
    args = dict(size_label=None, yardage_lines=[], tolerance_pct=10, difficulty="easy",
                colors=[], terminology="US", gauge_line=None, stitches=[])
    with _Env(**{ORIGIN_VAR: None}):
        assert LS.listing_help_links(db, cir.to_dict()) == []
        plain = seo.build_description(cir.title, **args,
                                      lesson_links=LS.listing_help_links(db, cir.to_dict()))
        assert "TECHNIQUE HELP" not in plain
    with _Env(**{ORIGIN_VAR: "https://learn.example.test"}):
        links = LS.listing_help_links(db, cir.to_dict())
        assert [x["slug"] for x in links] == ["pattern-topic"]
        text = seo.build_description(cir.title, **args, lesson_links=links)
        assert "TECHNIQUE HELP" in text and links[0]["url"] in text
        # A relative route is never printed into copy a buyer reads off-site.
        rel = seo.build_description(cir.title, **args,
                                    lesson_links=[{"url": "/learn/pattern-topic"}])
        assert "TECHNIQUE HELP" not in rel
    with _Env(**{ORIGIN_VAR: "http://not-owned.example"}):
        try:
            LS.listing_help_links(db, cir.to_dict())
            raise AssertionError("a non-HTTPS origin was accepted")
        except ValueError:
            pass


# ---- F-821: lesson assets are byte-checked against the benchmark corpus ---------------


def _benchmark(db, sha):
    with db.session() as s:
        s.add(BenchmarkProduct(ref="mjs-77", seller="fixture-seller", title="fixture",
                               files=[{"name": "photo.jpg", "sha256": sha, "bytes": 4}]))


def test_a_lesson_asset_matching_a_benchmark_file_is_refused_at_save():
    db = _db()
    competitor = hashlib.sha256(b"competitor photo bytes").hexdigest()
    _benchmark(db, competitor)
    try:
        LS.save_lesson(db, "copied", _spec(sha=competitor))
        raise AssertionError("a benchmark purchase file was saved as a lesson asset")
    except ValueError as exc:
        assert "F-821" in str(exc)
    # Renamed bytes: declared hash is fresh, the supplied bytes are the benchmark's.
    try:
        LS.save_lesson(db, "copied", _spec(sha="b" * 64),
                       asset_bytes={"canonical-demo": b"competitor photo bytes"})
        raise AssertionError("bytes that do not match their declaration were accepted")
    except ValueError as exc:
        assert "F-821" in str(exc)
    own = b"brambleloop original diagram"
    LS.save_lesson(db, "own", _spec(sha=hashlib.sha256(own).hexdigest()),
                   asset_bytes={"canonical-demo": own})


def test_a_corpus_match_found_after_drafting_is_refused_at_review():
    db = _db()
    sha = hashlib.sha256(b"later purchase").hexdigest()
    revision = LS.save_lesson(db, "late", _spec(sha=sha))
    _benchmark(db, sha)
    try:
        LS.review_lesson(db, "late", revision, "independent-qa",
                         dict.fromkeys(LS.DIMENSIONS, "PASS"), "fixture-review:test-only")
        raise AssertionError("review approved an asset now known to be a benchmark file")
    except ValueError as exc:
        assert "F-821" in str(exc)
    assert LS.approved_lesson(db, "late") is None


# ---- F-787: observed public listings are recorded as public sources -------------------


class _Reader:
    def __init__(self, listings):
        self.listings = listings

    def resolve_shop(self, name):
        return {"shop_id": 1, "shop_name": name}

    def catalogue(self, shop_id, **kwargs):
        return list(self.listings)

    def images(self, ref):
        return []

    def videos(self, ref):
        return []


def test_an_observed_public_listing_produces_a_pattern_rights_none_licence_row():
    from brambleloop.agents.registry import Registry
    from brambleloop.intel import benchmarks, observe
    from brambleloop.teardown import licence

    db = _db()
    Registry(db).seed_defaults()
    benchmarks.seed(db)
    listing = {"listing_id": 5150, "title": "Granny Square Blanket Crochet Pattern",
               "price": {"amount": 800, "divisor": 100, "currency_code": "CAD"},
               "tags": ["crochet pattern"], "materials": ["yarn"], "state": "active",
               "last_modified_timestamp": 1, "num_favorers": 3, "taxonomy_id": 66,
               "url": "https://fixture.invalid/listing/5150"}
    observe.scan(db, _Reader([listing]), env={})
    ref = licence.public_listing_ref("5150")
    with db.session() as s:
        row = s.scalar(select(BenchmarkLicence).where(BenchmarkLicence.source_ref == ref))
        assert row is not None, "no public-source licence recorded for an observed listing"
        assert row.source_kind == "public_web" and row.pattern_rights == "none"
        assert row.source_url == "https://fixture.invalid/listing/5150"
    lic = licence.licence_for(db, ref)
    assert not lic.permits("instruction_drafting")[0]
    assert lic.permits("demand_research")[0]


# ---- F-786: the upload route accepts and records licence terms ------------------


def test_the_upload_route_records_supplied_licence_terms_and_refuses_bad_ones():
    from fastapi.testclient import TestClient

    from brambleloop.core.models import BenchmarkListing
    from brambleloop.intel import benchmarks as intel_benchmarks
    from brambleloop.teardown import library

    lib = tempfile.mkdtemp(prefix="fb4lc_lib_")
    with _Env(BRAMBLELOOP_DATABASE_URL=f"sqlite:///{tempfile.mkdtemp()}/app.sqlite",
              BRAMBLELOOP_OPS_TOKEN=OPS_TOKEN, **{library.LIBRARY_ENV: lib}):
        from brambleloop.app import main
        from brambleloop.core import offsite

        os.environ.pop(offsite.ENDPOINT_VAR, None)
        with TestClient(main.app) as c:
            db = main.db
            with db.session() as s:
                s.add(BenchmarkListing(benchmark_key=intel_benchmarks.MJS_KEY,
                                       listing_ref="88", title="Fixture throw",
                                       pod="blankets", product_type="pattern", price_cad=7.0,
                                       url="https://example.invalid/88", detail={}))
            auth = {"authorization": f"Bearer {OPS_TOKEN}"}
            files = {"files": ("pattern.pdf", b"%PDF-fixture", "application/pdf")}
            bad = c.post("/api/teardown/intake", headers=auth, files=files,
                         data={"listing_ref": "88", "licence_terms": json.dumps(
                             {"pattern_rights": "licensed_commercial",
                              "allowed_uses": ["republish_pattern"],
                              "prohibited_uses": ["republish_pattern"]})})
            assert bad.status_code == 400, bad.text
            assert not (Path(lib) / "mjs-88").exists(), "files entered quarantine before refusal"
            assert c.post("/api/teardown/intake", headers=auth, files=files,
                          data={"listing_ref": "88",
                                "licence_terms": "{not json"}).status_code == 400
            terms = {"terms_source": "owner read the listing's licence note",
                     "finished_item_rights": "permitted_with_attribution",
                     "attribution": "credit the designer"}
            ok = c.post("/api/teardown/intake", headers=auth, files=files,
                        data={"listing_ref": "88", "licence_terms": json.dumps(terms)})
            assert ok.status_code == 200, ok.text
            assert ok.json()["licence"]["finished_item_rights"] == "permitted_with_attribution"
            with db.session() as s:
                row = s.scalar(select(BenchmarkLicence).where(
                    BenchmarkLicence.source_ref == "mjs-88"))
                assert row.terms_source == terms["terms_source"]
                assert row.pattern_rights == "personal_use"


# ---- F-588: surface UNKNOWN evidence reaches coverage and readiness -------------------


def test_the_partners_unknown_reaches_coverage_and_a_new_provider_reopens_it():
    from brambleloop.gateway import images
    from brambleloop.intel import etsy_surfaces as es

    unknowns = es.coverage()["unknowns"]
    assert "production_partners" in unknowns
    assert any("production partner" in u for u in unknowns["production_partners"])
    assert not es.partners_reaudit()["reopened"], es.partners_reaudit()
    assert not any("re-audited" in u for u in unknowns["production_partners"])
    # Declared unknowns are still there.
    assert "taxonomy_and_attributes" in unknowns and "webhooks" in unknowns

    saved = dict(images.BY_KEY)
    try:
        images.BY_KEY["fixture-new-model"] = next(iter(saved.values()))
        audit = es.partners_reaudit()
        assert audit["reopened"] and audit["added"] == ["fixture-new-model"]
        assert any("re-audited" in u for u in es.coverage()["unknowns"]["production_partners"])
    finally:
        images.BY_KEY.clear()
        images.BY_KEY.update(saved)
    assert es.partners_reaudit(image_providers=es.PARTNERS_REVIEWED_IMAGE_PROVIDERS,
                               fulfilment_providers=["print-shop"])["reopened"]


# ---- F-754: a second gauge regime is refused, not silently measured at the main one ---


def test_certify_refuses_a_component_gauge_that_differs_from_the_main_gauge():
    from brambleloop.gates.certificate import certify

    base = _base_cir()
    assert "COMPONENT_GAUGE_UNSUPPORTED" not in {f.code for f in certify(base).findings}

    ribbed = _base_cir()
    g = ribbed.gauge
    ribbed.components[0].gauge = Gauge(stitches_per_10cm=g.stitches_per_10cm,
                                       rows_per_10cm=g.rows_per_10cm * 1.4,
                                       stitch_type=g.stitch_type, hook_mm=g.hook_mm,
                                       yarn_weight=g.yarn_weight)
    cert = certify(ribbed)
    hits = [f for f in cert.findings if f.code == "COMPONENT_GAUGE_UNSUPPORTED"]
    assert hits and hits[0].is_error and not cert.granted
    assert "rows_per_10cm" in hits[0].message

    # Survives serialisation: a source's second gauge is never dropped between stages.
    again = CIR.from_dict(json.loads(json.dumps(ribbed.to_dict())))
    assert again.components[0].gauge == ribbed.components[0].gauge
    assert "COMPONENT_GAUGE_UNSUPPORTED" in {f.code for f in certify(again).findings}

    same = _base_cir()
    same.components[0].gauge = copy.deepcopy(same.gauge)
    assert "COMPONENT_GAUGE_UNSUPPORTED" not in {f.code for f in certify(same).findings}


def test_existing_cirs_serialise_exactly_as_before():
    base = _base_cir()
    d = base.to_dict()
    assert "configuration" not in d
    assert all("gauge" not in c for c in d["components"])
    assert base.variant_key == "single" and base.represented_variant == {}


# ---- F-757: the configuration a render or listing represents --------------------------


def _configured(default="on"):
    cir = _base_cir()
    cir.configuration = Configuration(features={"handles": ["on", "off"]},
                                      default={"handles": default})
    return cir


def test_configuration_roundtrips_and_certify_refuses_bad_blocks_and_mismatched_claims():
    from brambleloop.gates.certificate import certify

    cir = _configured()
    assert cir.variant_key == "handles=on"
    assert CIR.from_dict(json.loads(json.dumps(cir.to_dict()))).configuration == cir.configuration

    codes = lambda c, **kw: {f.code for f in certify(c, **kw).findings}  # noqa: E731
    assert not {"CONFIGURATION_INVALID", "VARIANT_MISMATCH"} & codes(cir)
    assert "VARIANT_MISMATCH" not in codes(cir, listing_variant="handles=on")
    mismatch = certify(cir, listing_variant="handles=off")
    assert "VARIANT_MISMATCH" in {f.code for f in mismatch.findings} and not mismatch.granted
    assert "VARIANT_MISMATCH" in codes(_base_cir(), listing_variant="handles=on")
    assert "VARIANT_MISMATCH" not in codes(_base_cir(), listing_variant="single")
    assert "CONFIGURATION_INVALID" in codes(_configured(default="maybe"))


def test_disclosed_render_manifest_records_the_represented_variant():
    from brambleloop.visual import disclosed_render as D

    assert D.render(_base_cir(), "hero").manifest["represented_variant"] == {
        "key": "single", "features": {}}
    assert D.render(_configured(), "hero").manifest["represented_variant"] == {
        "key": "handles=on", "features": {"handles": "on"}}


def _frame(position, variant=""):
    return L.CertifiedFrame(position=position, asset_id=f"f{position}", sha256="a" * 64,
                            job=E.DESIRE, purpose=E.CONVERSION_CREATIVE, medium="X",
                            represented_variant=variant)


def _ls_cert(frames, **kw):
    return L.certify(slug="s", version="1", frames=frames,
                     gate_results={g: E.PASSED for g in E.GATES},
                     geometry={"w": 1}, claims={}, policy_version="v", **kw)


def test_listing_set_certificate_records_and_enforces_the_represented_variant():
    legacy = _ls_cert([_frame(1), _frame(2)])
    assert legacy.represented_variant == "single"
    assert legacy.to_dict()["represented_variant"] == "single"

    ok = _ls_cert([_frame(1, "handles=on"), _frame(2, "handles=on")], variant="handles=on")
    assert ok.to_dict()["represented_variant"] == "handles=on"
    assert ok.to_dict()["frames"][0]["represented_variant"] == "handles=on"

    for frames, kw in (([_frame(1, "handles=on"), _frame(2, "handles=off")], {}),
                       ([_frame(1, "handles=off")], {"variant": "handles=on"}),
                       ([_frame(1)], {"variant": "handles=on"})):
        try:
            _ls_cert(frames, **kw)
            raise AssertionError(f"certified a mismatched set {frames} {kw}")
        except L.ListingSetRefused as exc:
            assert "F-757" in str(exc)


def test_disclosed_frames_carry_the_manifest_variant_into_the_certificate():
    from brambleloop.publish.disclosed_listing import DISCLOSURE

    def rec(manifest_variant):
        manifest = {"job": E.DESIRE}
        if manifest_variant is not None:
            manifest["represented_variant"] = {"key": manifest_variant}
        return {"frames": [{"position": 1, "view": "hero", "alt_text": DISCLOSURE,
                            "image": {"sha256": hashlib.sha256(b"png").hexdigest()},
                            "disclosed_render": manifest}]}

    images = [("hero.png", b"png", DISCLOSURE)]
    assert L.disclosed_frames(rec("handles=off"), images, slug="s")[0].represented_variant \
        == "handles=off"
    # A legacy manifest with no field is the single variant it was drawn as.
    assert L.disclosed_frames(rec(None), images, slug="s")[0].represented_variant == "single"
    frames = L.disclosed_frames(rec("handles=off"), images, slug="s")
    try:
        _ls_cert(frames, variant="handles=on")
        raise AssertionError("a frame showing handles=off certified for a handles=on listing")
    except L.ListingSetRefused:
        pass
    assert variant_key({"b": "2", "a": "1"}) == "a=1;b=2" and variant_key({}) == "single"


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}  -- {type(exc).__name__}: {str(exc)[:600]}")
            if os.environ.get("CERT_TRACE"):
                traceback.print_exc()
    print(f"\n  {len(tests) - failed} passing, {failed} failing")
    sys.exit(1 if failed else 0)
