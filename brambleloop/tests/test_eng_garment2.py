"""ENG-GARMENT-2: clothing families beyond the chest-graded garment (`products.wearables`).

Per family, with the real compiler, twin, reverse compiler and release chain:

* every size of the family's designs is built from a sourced CYC table with stated ease and
  is granted by `gates.certificate.certify` (child-safety stage included for child sizes) and
  by the wearable gates (`gates.wearable_fit`);
* the reverse compiler reads each size's own written pattern back to the same CIR;
* size truth per size: the size each CIR's title names is the graded size the CIR is, and a
  title naming another size is refused;
* each family gate fails on the defect it exists for (mutations);
* the US and UK documents carry a size chart (every figure re-derived from the twin) and a
  schematic, and their parenthesised text reads back per size to the compiler's counts;
* routing: a research concept runs intake -> admit -> draft -> every size compiled and
  certified -> US and UK PDF, and concepts the family does not build are held.

Run: cd brambleloop && python3 tests/test_eng_garment2.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import copy
import dataclasses
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.graded import HEAD, FitIntent, GradingRefused  # noqa: E402
from brambleloop.cir.model import Op  # noqa: E402
from brambleloop.gates import child_safety as CS  # noqa: E402
from brambleloop.gates import wearable_fit as WF  # noqa: E402
from brambleloop.products import wearables as WB  # noqa: E402

BEANIE = WB.WearableSpec("ridgeway-rib-beanie", "Ridgeway Rib Beanie", "hat", "hat_beanie",
                         "all", "worsted", "wool", (("head", WB.HAT_EASE_CM),))
SLOUCHY = WB.WearableSpec("fogbank-slouchy-beanie", "Fogbank Slouchy Beanie", "hat",
                          "hat_beanie", "adult", "worsted", "wool",
                          (("head", WB.HAT_EASE_CM),), options=(("style", "slouchy"),))
BABY_HAT = WB.WearableSpec("pebble-baby-beanie", "Pebble Baby Beanie", "hat", "hat_beanie",
                           "baby", "dk", "cotton", (("head", WB.HAT_EASE_CM),))
SPECS = {s.key: s for s in (BEANIE, SLOUCHY, BABY_HAT)}


@lru_cache(maxsize=None)
def released(key: str) -> WB.WearableRelease:
    return WB.certify(WB.build(SPECS[key]))


@lru_cache(maxsize=None)
def document(key: str, terms: str):
    from brambleloop.publish import wearable_pdf as WP

    return WP.build(released(key), terms)


def _codes(spec_or_release, cirs=None) -> set[str]:
    r = spec_or_release
    return WF.evaluate(r.design, cirs or r.cirs).codes()


# ---- shared checks every family runs --------------------------------------------------------


def assert_family_release(key: str, sizes: tuple[str, ...]) -> None:
    r = released(key)
    assert tuple(r.cirs) == sizes, (key, tuple(r.cirs))
    assert r.granted, (key, r.reasons()[:5])
    for size, cert in r.certificates.items():
        assert cert.granted, (key, size, [f.code for f in cert.findings])


def assert_reverse_reads_back(key: str) -> None:
    from brambleloop.cir.reverse import compare
    from brambleloop.cir.writer import write_pattern

    for size, cir in released(key).cirs.items():
        res = compile_cir(cir)
        for terms in ("US", "UK"):
            text = write_pattern(cir, res, terminology=terms)
            diff = [f for f in compare(cir, text, terms) if f.severity == "ERROR"]
            assert not diff, (key, size, terms, [str(f) for f in diff[:3]])


def assert_size_truth(key: str) -> None:
    from brambleloop.gates.certificate import size_findings_for
    from brambleloop.creative import size_truth

    for size, cir in released(key).cirs.items():
        facts = size_truth.facts_of(cir)
        assert facts["grade"] == size.lower(), (size, facts)
        assert not size_findings_for(cir.title, 30.0, 30.0, facts), cir.title
        others = [s for s in released(key).cirs if s != size]
        if others:
            wrong = cir.title.replace(f"(size {size})", f"(size {others[0]})")
            got = size_findings_for(wrong, 30.0, 30.0, facts)
            assert any("graded size" in why for _c, why in got), (wrong, got)


def assert_document(key: str) -> None:
    from brambleloop.publish import wearable_pdf as WP

    r = released(key)
    for terms in ("US", "UK"):
        doc = document(key, terms)
        assert doc.problems == [] and set(WP.SECTIONS) <= set(doc.sections), (terms,
                                                                              doc.problems)
        flat = " ".join(doc.text.split())
        for c in r.claims:
            assert f"{c['yards']} yd" in flat and f"{c['body_cm']:g} cm" in flat, c
        assert doc.svg.startswith("<svg") and doc.figures[0]["labels"] >= 3
        assert all("(" in ln or len(r.cirs) == 1 for lines in doc.pattern_lines.values()
                   for ln in lines if "sts)" in ln)
    us, uk = document(key, "US").text, document(key, "UK").text
    assert " sc " in us and " dc " in uk


# ---- 1. beanies and hats --------------------------------------------------------------------


def test_the_head_chart_is_the_published_cyc_chart():
    assert HEAD.source_url.endswith("/standards/head-circumference-chart")
    got = {b.size: b.published["head"] for b in HEAD.sizes}
    assert got == {"Preemie": (23, 30.5), "Baby": (35.5, 40.5), "Toddler": (40.5, 46),
                   "Child": (45.5, 51), "Tween": (51, 56), "Woman": (53, 58.5),
                   "Man": (56, 61)}
    assert all(not b.is_sourced("bust") for b in HEAD.sizes)


def test_a_stretch_fit_takes_bounded_negative_ease_and_nothing_else_does():
    FitIntent({"head": -2.0})
    for bad in ({"head": -6.0}, {"bust": -1.0}):
        try:
            FitIntent(bad)
        except GradingRefused:
            continue
        raise AssertionError(f"{bad} accepted")


def test_every_beanie_size_is_granted_preemie_to_man():
    assert_family_release(BEANIE.key, WB.HAT_SIZES["all"])
    assert_family_release(SLOUCHY.key, WB.HAT_SIZES["adult"])
    assert_family_release(BABY_HAT.key, WB.HAT_SIZES["baby"])


def test_the_beanie_is_graded_body_plus_ease_and_rises_size_to_size():
    r = released(BEANIE.key)
    prev = None
    assert len(r.cirs) == 7
    for size, cir in r.cirs.items():
        m = WB.hat_measures(cir)
        g = r.design.graded_size(size)
        assert abs(m["circumference"] - g.finished_cm("head")) <= 0.5 * 10 / 12.5 + 0.05
        assert -5.0 <= m["circumference"] - g.body_cm("head") <= 1.0
        if prev:
            assert m["circumference"] > prev["circumference"] and m["height"] >= prev["height"]
        prev = m
    slouch = WB.hat_measures(released(SLOUCHY.key).cirs["Woman"])
    plain = WB.hat_measures(r.cirs["Woman"])
    assert slouch["height"] > plain["height"] + 3


def test_the_crown_decreases_in_sections_and_closes():
    assert released(BEANIE.key).cirs
    for size, cir in released(BEANIE.key).cirs.items():
        res = compile_cir(cir)
        crown = [x.stitch_count for x in res.rows if x.component == "crown"]
        assert crown[-1] == 6 and all(b - a == -6 for a, b in zip(crown[-5:], crown[-4:]))
        steps = [s.kind for s in WB.facts_of(cir).pieces["crown"]]
        assert steps == ["pick_up", "even", "spread_dec", "section_dec"], steps


def test_the_beanie_reverse_compiles_and_holds_size_truth():
    assert_reverse_reads_back(BEANIE.key)
    assert_size_truth(BEANIE.key)


def test_the_baby_beanie_passes_every_child_safety_check():
    assert released(BABY_HAT.key).cirs
    for size, cir in released(BABY_HAT.key).cirs.items():
        v = CS.evaluate(cir, compile_cir(cir))
        assert v.applies and v.verdict == CS.VERDICT_PASS, (size, v.to_dict())
    adult = released(SLOUCHY.key).cirs["Woman"]
    assert not CS.evaluate(adult, compile_cir(adult)).applies


def test_the_beanie_documents_read_back_with_chart_and_schematic():
    assert_document(BEANIE.key)
    assert_document(BABY_HAT.key)
    text = " ".join(document(BABY_HAT.key, "UK").text.split())
    assert CS.SECTION_HEADING in text and "pom-pom" in text
    assert "Size chart" in document(BEANIE.key, "US").sections


def test_hat_gates_fail_on_the_defects_they_exist_for():
    r = released(BEANIE.key)
    # a crown that does not close
    cirs = dict(r.cirs)
    cir = copy.deepcopy(cirs["Woman"])
    crown = next(c for c in cir.components if c.name == "crown")
    crown.rows = crown.rows[:-2]
    f = WB.facts_of(cir)
    f.pieces["crown"] = f.pieces["crown"][:-1] + [dataclasses.replace(
        f.pieces["crown"][-1], last=f.pieces["crown"][-1].last - 2,
        count=crown.rows[-1].declared_count,
        n=(("sections", 6), ("rounds", f.pieces["crown"][-1].get("rounds") - 2)))]
    cirs["Woman"] = cir
    got = _codes(r, cirs)
    assert "HAT_CROWN_OPEN" in got, got
    # a hat built to the wrong head (Man's body under the Woman label)
    cirs = dict(r.cirs)
    cirs["Woman"] = r.cirs["Man"]
    got = _codes(r, cirs)
    assert {"HAT_CIRCUMFERENCE", "GARMENT_SIZE_RUN"} <= got, got
    # a brim ring with an odd number of rows (the seam would not meet rib to rib)
    cirs = dict(r.cirs)
    cir = copy.deepcopy(cirs["Child"])
    brim = next(c for c in cir.components if c.name == "brim")
    brim.rows = brim.rows[:-1]
    cirs["Child"] = cir
    assert {"HAT_BRIM_RING", "GARMENT_STITCH_COUNT"} & _codes(r, cirs)
    # a pick-up that ruffles: the crown picks up far more than the brim edge holds
    cirs = dict(r.cirs)
    cir = copy.deepcopy(cirs["Tween"])
    WB.facts_of(cir).pickups[0] = dict(WB.facts_of(cir).pickups[0], edge_rows=40)
    cirs["Tween"] = cir
    assert "GARMENT_PICKUP_RATE" in _codes(r, cirs)


def test_a_tampered_hat_chart_is_refused_by_the_pdf():
    from brambleloop.publish import wearable_pdf as WP

    r = WB.certify(WB.build(BEANIE))
    r.claims[1] = dict(r.claims[1], circumference_cm=r.claims[1]["circumference_cm"] + 2)
    r.verdict = WF.evaluate(r.design, r.cirs, claims=r.claims)
    assert not r.granted and "GARMENT_SIZE_CLAIM" in r.verdict.codes()
    try:
        WP.build(r, "US")
    except WP.WearablePdfRefused:
        return
    raise AssertionError("an ungranted beanie rendered")


def test_a_written_round_with_a_wrong_count_is_caught_on_read_back():
    doc = document(BEANIE.key, "US")
    lines = {h: list(ls) for h, ls in doc.pattern_lines.items()}
    head = "Body and crown"
    lines[head][-1] = lines[head][-1].replace("(6 sts)", "(12 sts)")
    got = WF.document_problems(lines, released(BEANIE.key).cirs, doc.piece_of)
    assert any(p.code == "GARMENT_DOCUMENT" for p in got)


# ---- routing and research concepts end to end -----------------------------------------------


def _wearable_proposal(slug, title, category, form, construction, recipient, premise,
                       occasion="winter_nesting"):
    import test_eng_families as T

    return T._proposal(slug, title, category, pod="garments", form=form,
                       construction=construction, recipient=recipient, premise=premise,
                       motif="stone", function="keeps the cold off on the walk to school",
                       occasion=occasion, feeling="serene", palette_story="oat")


def _research_wearable_to_pdf(proposal: dict) -> dict:
    """Intake -> score -> draft (every size, wearable gates) -> compile and certify every size
    through the real handlers -> the US and UK documents."""
    from types import SimpleNamespace

    from sqlalchemy import select

    import test_eng_families as T
    from brambleloop.publish import wearable_pdf as WP

    assert proposal["slug"] not in T.POOL_SLUGS, "the concept under test is research-derived"
    db = T._db()
    T._benchmarks(db, proposal["concept"]["pod"])
    tid = T._answered_task(db)
    T.intake.attach_proposal(db, tid, proposal)
    got = T._run(db, "radar.concept_intake", {})
    assert got["approved"] == [proposal["slug"]], got
    restore = T._judged({proposal["slug"]})
    try:
        assert T._run(db, "radar.score")["promoted"] is True
        drafted = T._run(db, "cir.draft")
        assert drafted["drafted"] is True, drafted
        w = T.Worker(db, "wearable-e2e", job_types=["cir.compile", "gate.certify"])
        while w.run_once():
            pass
        with db.session() as s:
            draft_inputs = dict(s.scalars(select(T.Job).where(
                T.Job.job_type == "cir.draft")).first().inputs)
            jobs = list(s.scalars(select(T.Job).where(T.Job.job_type.in_(
                ["cir.compile", "gate.certify"])).order_by(T.Job.id)))
            compiled = {j.inputs["cir"]["slug"]: dict(j.outputs or {}) for j in jobs
                        if j.job_type == "cir.compile"}
            certified = {str((j.inputs.get("cir") or {}).get("slug") or j.inputs.get("slug")):
                         dict(j.outputs or {}) for j in jobs if j.job_type == "gate.certify"}
            stored = {j.inputs["cir"]["slug"]: j.inputs["cir"] for j in jobs
                      if j.job_type == "cir.compile"}
    finally:
        restore()
    concept = SimpleNamespace(key=proposal["slug"], title=proposal["title"], notes="",
                              category=proposal["category"],
                              **{k: draft_inputs[k] for k in ("form", "construction",
                                                              "premise", "recipient")})
    release = WB.certify(WB.build(WB.spec_for(concept)))
    for cir in release.cirs.values():
        assert stored[cir.slug]["components"] == cir.to_dict()["components"], cir.slug
    return {"drafted": drafted, "compiled": compiled, "certified": certified,
            "release": release, "docs": {t: WP.build(release, t) for t in ("US", "UK")}}


def assert_concept_to_pdf(out: dict, sizes: tuple, family: str) -> None:
    from brambleloop.publish import wearable_pdf as WP

    g = out["drafted"]["garment"]
    assert g["family"] == family and tuple(g["sizes"]) == sizes, g
    for cir in out["release"].cirs.values():
        assert out["compiled"][cir.slug].get("compiled") is True, cir.slug
        assert out["certified"][cir.slug].get("granted") is True, (cir.slug,
                                                                   out["certified"][cir.slug])
    assert out["release"].granted
    for terms, doc in out["docs"].items():
        assert doc.problems == [] and set(WP.SECTIONS) <= set(doc.sections), terms
        assert "Size chart" in doc.sections and "Schematic" in doc.sections
        assert doc.svg.startswith("<svg")


ADULT_HAT = _wearable_proposal(
    "hollin-ridge-beanie", "Hollin Ridge Beanie", "hat", "hat", "in_the_round", "self",
    "A ribbed-brim beanie in one soft colour for the first frosty walk of the year")
CHILD_HAT = _wearable_proposal(
    "conker-kids-beanie", "Conker Kids Beanie", "hat", "hat", "in_the_round", "child",
    "A warm kids beanie with a turned rib brim for the walk to school", "back_to_school")
BABY_HAT_P = _wearable_proposal(
    "milkweed-baby-beanie", "Milkweed Baby Beanie", "hat", "hat", "in_the_round",
    "new_parent", "A soft baby beanie in cotton for a new arrival's first outings", "new_baby")


def test_a_research_adult_beanie_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(ADULT_HAT)
    assert_concept_to_pdf(out, WB.HAT_SIZES["adult"], "hat_beanie")


def test_a_research_child_beanie_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(CHILD_HAT)
    assert_concept_to_pdf(out, WB.HAT_SIZES["child"], "hat_beanie")
    assert CS.SECTION_HEADING in " ".join(out["docs"]["US"].text.split())


def test_a_research_baby_beanie_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(BABY_HAT_P)
    assert_concept_to_pdf(out, WB.HAT_SIZES["baby"], "hat_beanie")
    assert CS.SECTION_HEADING in " ".join(out["docs"]["UK"].text.split())


def test_hats_route_to_the_beanie_and_others_are_held():
    from brambleloop.creative import construction_families as CF

    for title in ("Hollin Ridge Beanie", "Slouchy Moss Hat", "Baby Beanie", "Kids Toque"):
        got = CF.route(category="hat", title=title, form="hat", construction="in_the_round")
        assert got["admitted"] and got["family"] == "hat_beanie", (title, got)
    for title, cons in (("Pom Pom Beanie", "in_the_round"), ("Sun Hat", "in_the_round"),
                        ("Earflap Hat", "in_the_round"), ("Cabled Beanie", "in_the_round"),
                        ("Beanie", "flat_rows"), ("Bucket Hat", "in_the_round")):
        got = CF.route(category="hat", title=title, form="hat", construction=cons)
        assert not got["admitted"] and got["reason"].startswith(CF.HOLD_PREFIX), (title, got)
    assert CF.route(category="scarf", title="Ridge Beanie", form="hat",
                    construction="in_the_round")["admitted"] is False


def test_every_admitted_wearable_pair_has_a_pinned_proof():
    from brambleloop.creative import construction_families as CF

    pairs = {k: v for k, v in CF.PAIR_PROOFS.items() if k[0] in CF.WEARABLE_FAMILIES}
    assert set(pairs) == set(CF.WEARABLE_PAIR_AUDIENCE)
    for (family, _cat), proof in pairs.items():
        assert proof.startswith("tests/test_eng_garment2.py::")
        assert callable(globals()[proof.split("::")[1]])
        assert CF.FAMILIES[family].status == CF.VERIFIED
    for (family, _cat), audiences in CF.WEARABLE_PAIR_AUDIENCE.items():
        assert audiences, family
        for a in audiences:
            assert any(n.startswith(f"test_a_research_{a}_") for n in globals()), (family, a)


if __name__ == "__main__":
    failed = 0
    only = sys.argv[1:]
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn) and (not only or any(o in name
                                                                          for o in only)):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                import traceback

                traceback.print_exc()
                print(f"FAIL {name} {exc!r}")
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
