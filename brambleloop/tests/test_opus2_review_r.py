"""OPUS2R: review findings on the research -> Product Development registry.

R-1 (HIGH): a brief's title is read by the radar fallback's own title route for its family,
so it can promise nothing the construction does not make (a bunny title on a bear, two
charts, a lid, a zip, a wallet drafted as a drawstring pouch). R-2: the brief's size and the
title's size words agree, and a size is only given to a construction that takes one. R-3: a
tapestry wall is within 5% of its base. R-4: a malformed brief is a named refusal or hold,
never a crashed job. R-5: a library motif worked as tapestry keeps its own imagery. R-6: the
library grid's hash is in the provenance. R-7: a re-held brief is one knowledge gap. R-8:
each registry guard the review found unkilled is pinned here.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_review_r.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_cert_design_pipeline as T  # noqa: E402
from test_opus2_research_to_development import _brief, _ctx  # noqa: E402

from brambleloop.cir.model import CIR  # noqa: E402
from brambleloop.creative import construction_registry as R  # noqa: E402
from brambleloop.creative import fallback_constructions as FC  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402


def _c(title, form, construction, motif, palette="forest and cream", key="opus2r"):
    return NS(key=key, title=title, form=form, construction=construction, motif=motif,
              palette_story=palette)


def _fields(req):
    return [u["field"] for u in req.unresolved]


def test_r1_a_title_the_construction_does_not_make_is_held_by_name():
    held = {
        "Bunny Plush Toy": _c("Bunny Plush Toy", "toy", "amigurumi_shaping", "bear", "caramel"),
        "Diamond Heart Tapestry Basket": _c("Diamond Heart Tapestry Basket", "basket",
                                            "tapestry", "heart"),
        "Round Heart Tapestry Basket with Lid": _c("Round Heart Tapestry Basket with Lid",
                                                   "basket", "tapestry", "heart"),
        "Giant Bear with Removable Hat and Scarf": _c(
            "Giant Bear with Removable Hat and Scarf", "toy", "amigurumi_shaping", "bear",
            "caramel"),
        "Tote Bag with Zip Pocket and Lining": _c("Tote Bag with Zip Pocket and Lining", "bag",
                                                  "in_the_round", ""),
        "Zippered Coin Purse Wallet": _c("Zippered Coin Purse Wallet", "pouch", "in_the_round",
                                         ""),
        "Large Bear": _c("Large Bear", "toy", "amigurumi_shaping", "bear", "caramel"),
        # the title route accepts each, but it names another kind or chart than the brief
        "Bunny Plush": _c("Bunny Plush", "toy", "amigurumi_shaping", "bear", "caramel"),
        "Heart Tapestry Basket (pumpkin brief)": _c("Heart Tapestry Basket", "basket",
                                                    "tapestry", "pumpkin"),
        # reads as the plain vessel, not the tapestry the brief asks for
        "Heart Basket": _c("Heart Basket", "basket", "tapestry", "heart"),
    }
    assert len(held) == 10
    for name, concept in held.items():
        req = R.request_for(concept)
        assert req is not None and "title" in _fields(req), (name, req)
        assert all(u["resolved_by"] == R.ENRICH for u in req.unresolved), (name, req)
        try:
            R.build(req)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{name}: an unresolved request was built")
    ok = {"Heart Tapestry Basket": _c("Heart Tapestry Basket", "basket", "tapestry", "heart"),
          "Bear Amigurumi": _c("Bear Amigurumi", "toy", "amigurumi_shaping", "bear", "caramel"),
          "Drawstring Pouch": _c("Drawstring Pouch", "pouch", "in_the_round", ""),
          "Market Tote": _c("Market Tote", "bag", "in_the_round", ""),
          "Ridged Basket": _c("Ridged Basket", "basket", "in_the_round", "")}
    assert len(ok) == 5
    for name, concept in ok.items():
        req = R.request_for(concept)
        assert req is not None and not req.unresolved, (name, req)
        assert R.title_route(req.family, req.title, req.key)["family"] == req.family, name


def test_r1_the_handler_holds_a_misnamed_brief_and_drafts_nothing():
    db = T._db()
    concept = _brief("opus2r-bunny-bear", "toy", "amigurumi_shaping", "bear",
                     palette="caramel", title="Bunny Plush")
    ctx, emitted, audits = _ctx(db, concept)
    out = pipeline._draft_creative(ctx, concept["key"])
    assert out.get("held") is True and emitted == [], out
    assert [u["field"] for u in out["unresolved"]] == ["title"], out
    assert any(a == R.HELD_ACTION for a, _ in audits), audits


def test_r2_the_brief_size_and_the_title_size_agree_and_only_sized_families_take_one():
    conflict = R.request_for(_c("Large Heart Tapestry Basket", "basket", "tapestry", "heart"),
                             {"size": "small"})
    assert _fields(conflict) == ["size"], conflict
    for concept in (_c("Bear Amigurumi", "toy", "amigurumi_shaping", "bear", "caramel"),
                    _c("Drawstring Pouch", "pouch", "in_the_round", ""),
                    _c("Market Tote", "bag", "in_the_round", "")):
        req = R.request_for(concept, {"size": "large"})
        assert _fields(req) == ["size"] and req.unresolved[0]["resolved_by"] == R.ENGINE, req
    titled = R.request_for(_c("Large Heart Tapestry Basket", "basket", "tapestry", "heart"))
    assert not titled.unresolved and titled.params["size"] == "large", titled
    agreed = R.request_for(_c("Large Heart Tapestry Basket", "basket", "tapestry", "heart"),
                           {"size": "large"})
    assert not agreed.unresolved and agreed.params["size"] == "large", agreed
    # a plain vessel's title size is honoured too ("Large" was drafted medium before)
    vessel = R.request_for(_c("Large Ridged Basket", "basket", "in_the_round", ""))
    assert not vessel.unresolved and vessel.params["size"] == "large", vessel
    cir = R.build(vessel)
    big = R.build(R.request_for(_c("Ridged Basket", "basket", "in_the_round", "")))
    assert cir.components[0].rows[-1].declared_count > big.components[0].rows[-1].declared_count


def test_r3_a_tapestry_wall_is_within_five_percent_of_its_base_or_not_drafted():
    charts = FC.tapestry_charts()
    assert len(charts) >= 8
    fitted = refused = 0
    for name, chart in charts.items():
        for size in R.SIZE_WORDS:
            counts = FC.tapestry_counts(len(chart[0]), size, "worsted", len(chart))
            concept = pipeline.Concept(slug="r3", title=f"{size.title()} Tapestry Basket",
                                       category="basket", stitch_repeat=[("sc", 4)],
                                       width_stitches=24, rows=8,
                                       colors={"forest": "#2F4A35", "cream": "#F3EEDF"})
            if counts is None:
                refused += 1
                try:
                    FC.tapestry_basket(concept, chart=name, size=size)
                except ValueError as exc:
                    assert "does not fit" in str(exc) or "rounds tall" in str(exc), exc
                else:
                    raise AssertionError(f"{name}/{size}: an unfitting chart was drafted")
                continue
            fitted += 1
            base, wall = counts
            assert abs(wall / base - 1) <= FC.TAPESTRY_WALL_TOLERANCE, (name, size, counts)
            cir = FC.tapestry_basket(concept, chart=name, size=size)
            walls = [r.declared_count for r in cir.components[0].rows]
            assert max(walls) == max(base, wall) and walls[-1] == wall, (name, size, walls)
    assert fitted and refused, (fitted, refused)
    # the built-in charts keep their counts (no digest moves): base == wall at every size
    for name in FC.TAPESTRY_CHARTS:
        for size in R.SIZE_WORDS:
            base, wall = FC.tapestry_counts(len(charts[name][0]), size, "worsted",
                                            len(charts[name]))
            assert base == wall, (name, size)
    held = R.request_for(_c("Fir Tapestry Basket", "basket", "tapestry", "fir"),
                         {"size": "small"})
    assert _fields(held) == ["size"] and "fits:" in held.unresolved[0]["why"], held


def test_r4_a_malformed_brief_is_held_or_refused_never_a_crashed_job():
    req = R.request_for(_c("Heart Tapestry Basket", "basket", "tapestry", "heart"), ["x"])
    assert "brief" in _fields(req), req
    db = T._db()
    concept = {**_brief("opus2r-bad-refs", "basket", "tapestry", "heart",
                        title="Heart Tapestry Basket"), "provenance": "research:opus2r"}
    ctx, emitted, audits = _ctx(db, concept, {"benchmarks_consulted": "not-a-list"})
    out = pipeline._draft_creative(ctx, concept["key"])
    assert out["drafted"] is False and emitted == [], out
    assert any(a == "cir.draft_refused" for a, _ in audits), audits


def test_r5_a_tapestry_library_motif_keeps_its_own_imagery():
    from brambleloop.publish.eligibility import name_truth

    for title, motif in (("Large Fir Tree Tapestry Basket", "fir"),
                         ("Large Tulip Tapestry Basket", "tulip")):
        req = R.request_for(_c(title, "basket", "tapestry", motif))
        assert not req.unresolved, req
        cir = R.build(req, provenance=_provenance(req))
        assert not [f for f in name_truth(cir) if f.startswith("imagery")], name_truth(cir)
    # a word the chart does not draw is still refused at the title route
    assert R.title_route("tapestry", "Flower Tapestry Basket")["family"] == FC.REFUSED


def _provenance(req):
    from brambleloop.creative.prototype import source_provenance

    return source_provenance(req.key, {"provenance": "research:opus2r"}, {},
                             R.PRIMITIVES + R.declared_primitives(req))


def test_r6_the_library_grid_hash_is_recorded():
    from brambleloop.products import motifs

    prims = FC.tapestry_chart_primitives("heart-row")
    sha = motifs.get("heart-row").sha256[:12]
    assert prims == ("products.motifs:heart-row:tapestry",
                     f"products.motifs.grid:heart-row@{sha}:widened-x2"), prims
    assert FC.tapestry_chart_primitives("diamond") == ()
    req = R.request_for(_c("Heart Tapestry Basket", "basket", "tapestry", "heart"))
    assert R.declared_primitives(req) == prims


def test_r7_a_re_held_brief_is_one_gap_and_an_enrichment_hold_is_none():
    from brambleloop.core.models import AuditLog
    from brambleloop.intel import knowledge_gaps as K

    db = T._db()
    engine = {"request": {"form": "basket"}, "unresolved": [
        {"field": "construction", "why": "reach-down", "resolved_by": R.ENGINE}]}
    enrich = {"request": {"form": "basket"}, "unresolved": [
        {"field": "motif", "why": "no chart", "resolved_by": R.ENRICH}]}
    with db.session() as s:
        for artifact, detail in (("held-mosaic", engine), ("held-mosaic", engine),
                                 ("held-motif", enrich)):
            s.add(AuditLog(actor="t", action=R.HELD_ACTION, artifact=artifact, detail=detail,
                           at=datetime.now(timezone.utc)))
    lines = K.evidence(db, today=datetime.now(timezone.utc).date())
    counted = {k: v["construction_refusals"] for k, v in lines.items()
               if v["construction_refusals"]}
    refused = sorted(s for v in lines.values() for s in v["refused"])
    assert list(counted.values()) == [1] and refused == ["held-mosaic"], (counted, refused)


def test_r8_each_registry_guard_is_pinned():
    # one chart, one kind
    two_charts = R.request_for(_c("Tapestry Basket", "basket", "tapestry", "heart fir"))
    assert _fields(two_charts) == ["motif"], two_charts
    two_kinds = R.request_for(_c("Bear Amigurumi", "toy", "amigurumi_shaping", "bear bunny"))
    assert _fields(two_kinds) == ["motif"], two_kinds
    # two distinct colours
    one = R.request_for(_c("Heart Tapestry Basket", "basket", "tapestry", "heart", "cream"))
    assert _fields(one) == ["palette"], one
    # a plain construction holds a motif word
    plain = R.request_for(_c("Ridged Basket", "basket", "in_the_round", "heart"))
    assert _fields(plain) == ["motif"], plain
    # stated dimensions wait on an engine decision
    dims = R.request_for(_c("Ridged Basket", "basket", "in_the_round", ""),
                         {"dimensions_cm": [20, 15]})
    assert _fields(dims) == ["dimensions_cm"] and dims.unresolved[0]["resolved_by"] == R.ENGINE
    # build() refuses an unresolved request on its own
    try:
        R.build(plain)
    except ValueError:
        pass
    else:
        raise AssertionError("build() drafted an unresolved request")
    # the library chart words are in the tapestry allowlist
    assert FC.tapestry_route("Fir Tapestry Basket")["family"] == FC.TAPESTRY


def test_r8_an_unbacked_library_chart_is_neither_offered_nor_drafted():
    real = FC._chart_backed
    heart = FC.library_chart("heart-row")
    FC._chart_backed = lambda chart: False if chart == heart else real(chart)
    try:
        assert "heart-row" not in FC.tapestry_charts()
        assert FC.tapestry_route("Heart Tapestry Basket")["family"] == FC.REFUSED
        req = R.request_for(_c("Heart Tapestry Basket", "basket", "tapestry", "heart"))
        assert _fields(req) == ["motif"], req
    finally:
        FC._chart_backed = real
    assert "heart-row" in FC.tapestry_charts()


def test_r8_a_chart_taller_than_the_wall_is_refused():
    real = FC.tapestry_charts
    FC.tapestry_charts = lambda: {**real(), "tall": ("XXX...",) * 60}
    try:
        concept = pipeline.Concept(slug="r8", title="Tapestry Basket", category="basket",
                                   stitch_repeat=[("sc", 4)], width_stitches=24, rows=8,
                                   colors={"forest": "#2F4A35", "cream": "#F3EEDF"})
        try:
            FC.tapestry_basket(concept, chart="tall", size="small")
        except ValueError as exc:
            assert "rounds tall" in str(exc), exc
        else:
            raise AssertionError("a chart taller than the wall was drafted")
    finally:
        FC.tapestry_charts = real


def test_r8_the_radar_path_declares_the_library_motif_and_its_grid():
    import dataclasses

    from brambleloop.core.db import Database
    from brambleloop.core.models import PatternVersion, Product
    import tempfile

    seed = pipeline._seed_for("nordic-forest-basket")
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='opus2r_')}/d.sqlite")
    db.create_all()
    with db.session() as s:
        p = Product(slug=seed.slug, title=seed.title)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="0.9.0", cir_json={}, certified=True))
    inputs = {k: v for k, v in dataclasses.asdict(seed).items() if not isinstance(v, tuple)}
    inputs.update(pipeline.concept_geometry(seed))
    inputs["title"] = "Heart Tapestry Basket"
    emitted, audits = [], []
    ctx = NS(db=db, job=NS(inputs=inputs), audit=lambda a, **kw: audits.append((a, kw)),
             enqueue=lambda role, kind, data, **kw: emitted.append((kind, data)))
    out = pipeline.handle_cir_draft(ctx)
    assert out["drafted"] is True, out
    prims = set(CIR.from_dict(emitted[0][1]["cir"]).provenance.primitives_used)
    assert set(FC.tapestry_chart_primitives("heart-row")) <= prims, prims


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:600])
                import traceback
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
