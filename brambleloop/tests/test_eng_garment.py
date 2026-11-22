"""ENG-GARMENT: garments as a research-admitted family that certifies end to end.

Slice 1 proves, with the real compiler, twin and release chain:

* five original garments in four constructions (top-down raglan, flat one-piece with built-in
  sleeves, side-to-side, drop-shoulder panels), each graded from a published body table
  (CYC woman / child-youth / baby), with stated ease, a gauge for every fabric and yardage per
  size in balls and yards from the twin;
* every size of every design is granted by `gates.certificate.certify` (the child and baby
  designs with the child-safety stage), and the garment gates (`gates.garment_fit`) find
  nothing;
* each new gate fails on the defect it exists for (mutations: seam mismatch, ease out of band,
  yardage claim, size claim, pick-up rate, shaping arithmetic, neck fit, armhole fit, stitch
  count, steps differing between sizes, a size run that does not rise);
* the child-safety garment rules: no buttonholes for under-3s, buttons on an older child held,
  a picked-up band is worked in (not sewn) but must still meet its edge, a chain the next row
  works into is fabric and a free chain loop still fails.

Run: cd brambleloop && python3 tests/test_eng_garment.py
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
from brambleloop.cir.graded import BABY, CHILD, WOMAN, FIT_EASE_BANDS_CM  # noqa: E402
from brambleloop.cir.model import Op, Row  # noqa: E402
from brambleloop.gates import child_safety as CS  # noqa: E402
from brambleloop.gates import garment_fit as GFIT  # noqa: E402
from brambleloop.products import garment_families as GF  # noqa: E402
from brambleloop.products import garment_release as GR  # noqa: E402

ADULT_CARDIGAN = "fernhollow-raglan-cardigan"
CHILD_SWEATER = "brookside-kids-sweater"
BABY_CARDIGAN = "little-wren-baby-cardigan"
VEST = "driftline-side-to-side-vest"
PULLOVER = "kestrel-drop-shoulder-pullover"


@lru_cache(maxsize=None)
def released(key: str) -> GR.GarmentRelease:
    return GR.certify(GR.build(GR.DESIGNS[key]))


def _codes(design, cirs, **kw) -> set[str]:
    return GFIT.evaluate(design, cirs, **kw).codes()


# ---- the designs ---------------------------------------------------------------------------


def test_four_constructions_five_designs_on_three_published_tables():
    cons = {s.construction for s in GR.DESIGNS.values()}
    assert cons == {"raglan", "one_piece", "side_to_side", "drop_shoulder"}, cons
    tables = {GR.DESIGNS[k].table().name for k in GR.DESIGNS}
    assert tables == {WOMAN.name, CHILD.name, BABY.name}
    assert released(ADULT_CARDIGAN).sizes == ("XS", "S", "M", "L", "XL", "2X", "3X", "4X", "5X")
    assert released(CHILD_SWEATER).sizes == GR.CHILD_SIZES
    assert released(BABY_CARDIGAN).sizes == ("3m", "6m", "12m", "18m", "24m")


def test_the_baby_table_is_the_published_cyc_chart():
    assert BABY.source_url == "https://www.craftyarncouncil.com/standards/baby-size-chart"
    assert [b.cm("bust") for b in BABY.sizes] == [40.5, 43, 45.5, 48, 50.5]
    assert [b.cm("armhole_depth") for b in BABY.sizes] == [8.5, 9, 9.5, 10, 10.5]
    assert BABY.size("3m").cm("wrist") is None, "unpublished measurements stay UNSOURCED"


def test_every_size_of_every_design_is_granted_and_passes_the_garment_gates():
    for key in GR.DESIGNS:
        r = released(key)
        assert r.granted, (key, r.reasons()[:5])
        for size, cert in r.certificates.items():
            for stage in ("compile", "twin", "assembly", "reverse", "physical_test"):
                assert stage in cert.stages_run, (key, size, stage)
        if GR.DESIGNS[key].audience != "adult":
            for size, cert in r.certificates.items():
                assert "child_safety" in cert.stages_run, (key, size)


def test_every_design_states_ease_gauge_and_per_size_counts_and_yardage():
    for key in GR.DESIGNS:
        r = released(key)
        assert r.design.fit.character in FIT_EASE_BANDS_CM
        assert r.design.fit.ease("bust") > 0
        g = r.design.gauge
        assert g.stitches_per_10cm > 0 and g.rows_per_10cm > 0 and g.yarn_weight
        claims = r.claims
        assert [c["size"] for c in claims] == list(r.sizes)
        for c in claims:
            assert c["balls"] >= 1 and c["yards"] > c["metres"] > 0, c
            assert c["finished_chest_cm"] > c["body_chest_cm"], c
        yards = [c["yards"] for c in claims]
        assert yards == sorted(yards) and len(set(yards)) == len(yards), (key, yards)
        # Per-size stitch counts come from the grading engine: the size matrix on every CIR.
        for cir in r.cirs.values():
            assert cir.grading is not None and len(cir.grading.sizes) == len(r.sizes)


def test_every_size_is_the_same_steps():
    for key in GR.DESIGNS:
        sigs = {GF.step_signature(c) for c in released(key).cirs.values()}
        assert len(sigs) == 1, key


def test_the_adult_cardigan_has_buttonholes_and_the_baby_cardigan_has_none():
    adult = released(ADULT_CARDIGAN)
    assert adult.cirs and released(BABY_CARDIGAN).cirs
    for cir in adult.cirs.values():
        f = GF.facts_of(cir)
        assert f.buttons >= 3
        holes = [o for r in cir.components[-1].rows for o in r.ops
                 if o.stitch == "ch" and o.spans == GF.BUTTONHOLE_STS]
        assert len(holes) == f.buttons, (cir.slug, len(holes), f.buttons)
    for cir in released(BABY_CARDIGAN).cirs.values():
        assert GF.facts_of(cir).buttons == 0
        assert not [o for c in cir.components for r in c.rows for o in r.ops
                    if o.stitch == "ch" and o.spans]


# ---- mutation tests: each gate catches its defect ------------------------------------------


def _fresh(key):
    d = GF.design(GR.DESIGNS[key])
    return d, {s: d.build(s) for s in d.sourced_sizes()}


def test_mutation_seam_mismatch_is_caught():
    d, cirs = _fresh(CHILD_SWEATER)
    assert not _codes(d, cirs)
    cir = cirs["6"]
    body = cir.components[0]
    # One extra plain row on the back: the halves no longer meet at the fold.
    last = body.rows[-1]
    body.rows.append(Row(index=last.index + 1, ops=[Op("sc", last.declared_count,
                                                       loop=last.ops[0].loop)],
                         declared_count=last.declared_count, turning_chain=1))
    assert "GARMENT_SEAM_MISMATCH" in _codes(d, {"6": cir}), "an extra back row is a seam that does not meet"
    d, cirs = _fresh(VEST)
    f = GF.facts_of(cirs["M"])
    f.seams[0]["b_rows"] += 1
    assert "GARMENT_SEAM_MISMATCH" in _codes(d, {"M": cirs["M"]})


def test_mutation_ease_out_of_band_is_caught():
    d, cirs = _fresh(ADULT_CARDIGAN)
    object.__setattr__(d.fit, "character", "oversized")     # a stored claim the build is not
    got = _codes(d, {"M": cirs["M"]})
    assert "GARMENT_EASE_OUT_OF_BAND" in got, got


def test_mutation_finished_off_target_is_caught():
    d, cirs = _fresh(ADULT_CARDIGAN)
    got = _codes(d, {"M": cirs["XS"]})       # an XS sold as the M
    assert "GARMENT_FINISHED_OFF_TARGET" in got, got


def test_mutation_yardage_and_size_claims_are_caught():
    d, cirs = _fresh(PULLOVER)
    claims = GFIT.size_claims(d, cirs)
    assert not _codes(d, cirs, claims=claims)
    bad = copy.deepcopy(claims)
    bad[3]["balls"] -= 1
    bad[5]["yards"] += 40
    got = GFIT.evaluate(d, cirs, claims=bad)
    yard = [f for f in got.findings if f.code == "GARMENT_YARDAGE_CLAIM"]
    assert {f.size for f in yard} == {bad[3]["size"], bad[5]["size"]}, yard
    bad = copy.deepcopy(claims)
    bad[0]["finished_chest_cm"] += 2
    assert "GARMENT_SIZE_CLAIM" in _codes(d, cirs, claims=bad)
    assert "GARMENT_SIZE_CLAIM" in _codes(d, cirs, claims=bad[:-1]), "a dropped size"


def test_mutation_pickup_rate_is_caught():
    d, cirs = _fresh(ADULT_CARDIGAN)
    cir = cirs["L"]
    band = next(c for c in cir.components if c.name == "band_left")
    n = band.foundation + 8
    band.foundation = n
    for row in band.rows:
        row.ops = [Op("sc", n, loop="back")]
        row.declared_count = n
    GF.facts_of(cir).pickups[0]["stitches"] = n
    assert "GARMENT_PICKUP_RATE" in _codes(d, {"L": cir})


def test_mutation_shaping_arithmetic_is_caught():
    d, cirs = _fresh(PULLOVER)
    f = GF.facts_of(cirs["M"])
    i = next(k for k, s in enumerate(f.pieces["sleeve"]) if s.kind == "inc")
    s = f.pieces["sleeve"][i]
    n = dict(s.n)
    n["times"] += 1
    f.pieces["sleeve"][i] = dataclasses.replace(s, n=tuple(n.items()))
    assert "GARMENT_SHAPING" in _codes(d, {"M": cirs["M"]})


def test_mutation_neck_and_armhole_fit_are_caught():
    d, cirs = _fresh(PULLOVER)
    GF.facts_of(cirs["S"]).neck_cm = 0.3 * d.graded_size("S").body_cm("cross_back")
    GF.facts_of(cirs["M"]).armhole_cm = 5.0
    v = GFIT.evaluate(d, {"S": cirs["S"], "M": cirs["M"]})
    assert ("GARMENT_NECK_FIT", "S") in {(f.code, f.size) for f in v.findings}
    assert ("GARMENT_ARMHOLE_FIT", "M") in {(f.code, f.size) for f in v.findings}


def test_mutation_stitch_count_and_differing_steps_and_size_run_are_caught():
    d, cirs = _fresh(BABY_CARDIGAN)
    f = GF.facts_of(cirs["12m"])
    f.pieces["yoke_and_body"][-1] = dataclasses.replace(f.pieces["yoke_and_body"][-1],
                                                        count=999)
    assert "GARMENT_STITCH_COUNT" in _codes(d, {"12m": cirs["12m"]})
    d, cirs = _fresh(BABY_CARDIGAN)
    GF.facts_of(cirs["6m"]).pieces["sleeve_left"].pop()
    assert "GARMENT_STEPS_DIFFER" in _codes(d, cirs)
    d, cirs = _fresh(BABY_CARDIGAN)
    swapped = {"3m": cirs["6m"], "6m": cirs["3m"]}
    assert "GARMENT_SIZE_RUN" in _codes(d, swapped)


# ---- the multi-size document: smallest size first, others in parentheses ------------------


def _document(key, terms):
    from brambleloop.publish import garment_writer as W

    r = released(key)
    doc = W.write(r.design, r.cirs, terms)
    return r, {h: [ln.text for ln in ls] for h, ls in doc.items()}, \
        {h: ls[0].piece for h, ls in doc.items()}


def test_the_multi_size_text_reads_back_to_every_compiled_row_in_both_terminologies():
    for key in GR.DESIGNS:
        for terms in ("US", "UK"):
            r, text, piece_of = _document(key, terms)
            assert text and all(text.values()), key
            probs = GFIT.multi_size_problems(text, r.cirs, piece_of)
            assert probs == [], (key, terms, [str(p) for p in probs[:3]])
            lines = [ln for ls in text.values() for ln in ls]
            # Smallest size first, the others in parentheses, a count after every row line.
            row_lines = [ln for ln in lines if ln.startswith("Row")]
            assert row_lines and all(ln.endswith("sts)") for ln in row_lines), key
            assert any(f"({len(r.sizes) - 1}" not in ln and ", " in ln for ln in row_lines)
            if terms == "UK":
                assert not any(" sc " in f" {ln} " for ln in lines), (key, "a US token in UK")


def test_mutation_a_wrong_number_in_the_document_is_caught():
    r, text, piece_of = _document(ADULT_CARDIGAN, "US")
    heading = next(iter(text))
    lines = list(text[heading])
    i = next(k for k, ln in enumerate(lines) if "(body)" in ln)
    # Change the body's stitch count for the third size only.
    import re
    m = re.search(r"\((\d+) \(([\d, ]+)\) sts\)$", lines[i])
    others = m.group(2).split(", ")
    others[1] = str(int(others[1]) + 2)
    lines[i] = lines[i][:m.start()] + f"({m.group(1)} ({', '.join(others)}) sts)"
    bad = dict(text, **{heading: lines})
    probs = GFIT.multi_size_problems(bad, r.cirs, piece_of)
    assert any(p.code == "GARMENT_DOCUMENT" and p.size == r.sizes[2] for p in probs), probs
    # A dropped instruction leaves rows the document never covers.
    bad = dict(text, **{heading: [ln for ln in text[heading] if "(hem band)" not in ln]})
    assert GFIT.multi_size_problems(bad, r.cirs, piece_of)


# ---- slice 2: the garment PDF -------------------------------------------------------------


@lru_cache(maxsize=None)
def document(key: str, terms: str):
    from brambleloop.publish import garment_pdf as GP

    return GP.build(released(key), terms)


def test_every_design_renders_the_full_benchmark_structure_in_us_and_uk():
    from brambleloop.publish import garment_pdf as GP

    for key in GR.DESIGNS:
        for terms in ("US", "UK"):
            doc = document(key, terms)
            assert doc.pdf_bytes.startswith(b"%PDF") and doc.problems == [], (key, terms)
            for section in GP.SECTIONS:
                assert section in doc.sections, (key, terms, section)
            text = " ".join(doc.text.split())
            # The overview, supplies with a gauge for each fabric, and the licence.
            for marker in ("Gauge: main fabric", "Gauge: band fabric", "Balls, by size",
                           "What you may do with this pattern", "US terms" if terms == "US"
                           else "UK terms", "CYC "):
                assert marker.lower() in text.lower(), (key, terms, marker)
            # The size chart: body vs finished, ease, balls and yards, for every size.
            assert released(key).claims, key
            for c in released(key).claims:
                assert f"{c['body_chest_cm']:g} cm" in text and f"{c['yards']} yd" in text
                assert f"{c['balls']} balls" in text or f"{c['balls']} ball" in text
            # The pattern: every line, every one ending with its count(s).
            lines = [ln for ls in doc.pattern_lines.values() for ln in ls]
            assert lines and all(" ".join(ln.split()) in text for ln in lines), key
            # The schematic: SVG drawn from geometry, and on the page with its legend.
            assert doc.svg.startswith("<svg") and "Half chest, finished" in doc.svg
            assert any(f["kind"] == "schematic" and f["labels"] >= 4 for f in doc.figures)
            assert "Half chest, finished" in text


def test_buttons_and_child_safety_are_stated_where_they_apply():
    adult = " ".join(document(ADULT_CARDIGAN, "US").text.split())
    assert "buttonhole" in adult and f"{GF.BUTTON_MM} mm" in adult
    assert CS.SECTION_HEADING not in adult
    for key in (BABY_CARDIGAN, CHILD_SWEATER):
        doc = document(key, "UK")
        text = " ".join(doc.text.split())
        assert CS.SECTION_HEADING in text and CS.SECTION_END in text, key
        assert "buttonhole" not in text.lower(), key
        v = CS.evaluate(next(iter(released(key).cirs.values())), text=doc.text)
        states = {c.code: c.state for c in v.checks}
        assert v.verdict == CS.VERDICT_PASS, (key, states)
    assert "Right front band (buttonhole band)" not in document(BABY_CARDIGAN, "US").pattern_lines


def test_the_pdf_refuses_an_ungranted_release_and_a_tampered_size_chart():
    from brambleloop.publish import garment_pdf as GP

    r = GR.certify(GR.build(GR.DESIGNS[VEST]))
    r.claims[2] = dict(r.claims[2], yards=r.claims[2]["yards"] + 50)
    r.verdict = GFIT.evaluate(r.design, r.cirs, claims=r.claims)
    assert not r.granted
    try:
        GP.build(r, "US")
    except GP.GarmentPdfRefused:
        pass
    else:
        raise AssertionError("an ungranted garment rendered")


# ---- slice 3: routing, and research concepts end to end ------------------------------------


def _garment_proposal(slug, title, category, construction, recipient, premise, occasion):
    import test_eng_families as T

    return T._proposal(slug, title, category, pod="garments", form="fitted_garment",
                       construction=construction, recipient=recipient, premise=premise,
                       motif="stone", function="a layer for the first cold mornings",
                       occasion=occasion, feeling="serene", palette_story="oat")


ADULT_PROPOSAL = _garment_proposal(
    "fernway-raglan-cardigan", "Fernway Raglan Cardigan", "cardigan", "top_down_yoke", "self",
    "A relaxed raglan cardigan with a buttoned band to pull on for the first frosty walk of "
    "winter", "winter_nesting")
CHILD_PROPOSAL = _garment_proposal(
    "puddle-lane-kids-sweater", "Puddle Lane Kids Sweater", "sweater", "flat_rows", "child",
    "A relaxed kids sweater in one piece with built-in sleeves, for school mornings",
    "back_to_school")
# D6 (catalogue-unblock): the drop-shoulder pullover, pinned through intake on the adult table.
PULLOVER_PROPOSAL = _garment_proposal(
    "tallowmere-drop-shoulder-pullover", "Tallowmere Drop Shoulder Pullover", "sweater",
    "bottom_up", "self",
    "A relaxed drop-shoulder pullover worked in panels and seamed, an easy layer for crisp "
    "autumn walks", "winter_nesting")
BABY_PROPOSAL = _garment_proposal(
    "hush-baby-cardigan", "Hush Baby Cardigan", "baby", "top_down_yoke", "new_parent",
    "A relaxed baby cardigan whose fronts meet edge to edge, nothing to fasten, for a new "
    "arrival's first visitors", "new_baby")


def _research_garment_to_pdf(proposal: dict) -> dict:
    """Intake -> score -> draft (every size, garment gates) -> compile and certify every size
    through the real handlers -> the US and UK documents. Returns everything."""
    from sqlalchemy import select

    import test_eng_families as T
    from brambleloop.publish import garment_pdf as GP

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
        w = T.Worker(db, "garment-e2e", job_types=["cir.compile", "gate.certify"])
        while w.run_once():
            pass
        with db.session() as s:
            draft_inputs = dict(s.scalars(select(T.Job).where(
                T.Job.job_type == "cir.draft")).first().inputs)
            jobs = list(s.scalars(select(T.Job).where(T.Job.job_type.in_(
                ["cir.compile", "gate.certify"])).order_by(T.Job.id)))
            compiled = {j.inputs["cir"]["slug"]: dict(j.outputs or {}) for j in jobs
                        if j.job_type == "cir.compile"}
            certified = {}
            for j in jobs:
                if j.job_type == "gate.certify":
                    certified[str((j.inputs.get("cir") or {}).get("slug") or
                                  j.inputs.get("slug"))] = dict(j.outputs or {})
            stored = {j.inputs["cir"]["slug"]: j.inputs["cir"] for j in jobs
                      if j.job_type == "cir.compile"}
    finally:
        restore()
    # The document is rendered from the same release the draft built (same spec, same CIRs).
    from types import SimpleNamespace

    concept = SimpleNamespace(key=proposal["slug"], title=proposal["title"],
                              form="fitted_garment", notes="",
                              **{k: draft_inputs[k] for k in ("construction", "premise",
                                                              "recipient", "feeling")})
    release = GR.certify(GR.build(GR.spec_for(concept)))
    for cir in release.cirs.values():
        assert stored[cir.slug]["components"] == cir.to_dict()["components"], cir.slug
    docs = {t: GP.build(release, t) for t in ("US", "UK")}
    return {"drafted": drafted, "compiled": compiled, "certified": certified,
            "release": release, "docs": docs}


def _assert_concept_to_pdf(out: dict, sizes: tuple, family: str) -> None:
    from brambleloop.publish import garment_pdf as GP

    g = out["drafted"]["garment"]
    assert g["family"] == family and tuple(g["sizes"]) == sizes, g
    slugs = [c.slug for c in out["release"].cirs.values()]
    assert len(slugs) == len(sizes)
    for slug in slugs:
        assert out["compiled"][slug].get("compiled") is True, slug
        assert out["certified"][slug].get("granted") is True, (slug, out["certified"][slug])
    assert out["release"].granted
    for terms, doc in out["docs"].items():
        assert doc.problems == [] and set(GP.SECTIONS) <= set(doc.sections), terms
        assert "Size chart" in doc.sections and "Schematic" in doc.sections
        assert doc.svg.startswith("<svg")
        assert all(f"{c['yards']} yd" in " ".join(doc.text.split())
                   for c in out["release"].claims)


def test_a_research_adult_cardigan_runs_concept_to_pdf_in_nine_sizes():
    out = _research_garment_to_pdf(ADULT_PROPOSAL)
    _assert_concept_to_pdf(out, ("XS", "S", "M", "L", "XL", "2X", "3X", "4X", "5X"),
                           "garment_raglan")
    assert all(GF.facts_of(c).buttons >= 3 for c in out["release"].cirs.values())


def test_a_research_child_sweater_runs_concept_to_pdf():
    out = _research_garment_to_pdf(CHILD_PROPOSAL)
    _assert_concept_to_pdf(out, GR.CHILD_SIZES, "garment_one_piece")
    assert CS.SECTION_HEADING in " ".join(out["docs"]["US"].text.split())


def test_a_research_baby_cardigan_runs_concept_to_pdf():
    out = _research_garment_to_pdf(BABY_PROPOSAL)
    _assert_concept_to_pdf(out, ("3m", "6m", "12m", "18m", "24m"), "garment_raglan")
    for cir in out["release"].cirs.values():
        assert GF.facts_of(cir).buttons == 0
    assert CS.SECTION_HEADING in " ".join(out["docs"]["UK"].text.split())


def test_a_research_adult_drop_shoulder_pullover_runs_concept_to_pdf():
    """D6: the drop-shoulder engine certifies every size, so a research concept is pinned
    through intake -> draft -> every size compiled and certified -> US/UK PDF."""
    from brambleloop.creative import construction_families as CF

    got = CF.route(category="sweater", title=PULLOVER_PROPOSAL["title"], form="fitted_garment",
                   construction="bottom_up")
    assert got["admitted"] and got["family"] == "garment_drop_shoulder", got
    out = _research_garment_to_pdf(PULLOVER_PROPOSAL)
    _assert_concept_to_pdf(out, ("XS", "S", "M", "L", "XL", "2X", "3X", "4X", "5X"),
                           "garment_drop_shoulder")


def test_every_admitted_garment_pair_has_a_pinned_proof_and_others_are_held():
    from brambleloop.creative import construction_families as CF

    garment_pairs = {k: v for k, v in CF.PAIR_PROOFS.items() if k[0] in CF.GARMENT_FAMILIES}
    assert set(garment_pairs) == set(CF.GARMENT_PAIR_AUDIENCE)
    for (family, category), proof in garment_pairs.items():
        name = proof.split("::")[1]
        assert proof.startswith("tests/test_eng_garment.py::") and callable(globals()[name])
    for f in CF.GARMENT_FAMILIES:
        assert (CF.FAMILIES[f].status == CF.VERIFIED) == any(k[0] == f for k in garment_pairs)
    held = [("sweater", "Cosy Adult Sweater", "flat_rows"),       # adult one-piece: unproven
            ("vest", "Driftline Vest", "side_to_side"),            # family partial
            ("sweater", "Kids Hoodie", "flat_rows"),               # a hood
            ("cardigan", "Cabled Cardigan", "top_down_yoke"),      # a feature not built
            ("cardigan", "Fitted Cardigan", "top_down_yoke"),      # fitted: premise below
            ("sweater", "Raglan Cardigan", "flat_rows"),           # title names another garment
            ("cardigan", "Mosaic Cardigan", "corner_to_corner")]   # no engine
    for cat, title, cons in held:
        premise = "a fitted cardigan" if title.startswith("Fitted") else ""
        got = CF.route(category=cat, title=title, form="fitted_garment", construction=cons,
                       premise=premise)
        assert not got["admitted"] and got["reason"].startswith(CF.HOLD_PREFIX), (title, got)
    for cat, title, cons in (("cardigan", "Fernway Raglan Cardigan", "top_down_yoke"),
                             ("sweater", "Puddle Lane Kids Sweater", "flat_rows"),
                             ("baby", "Hush Baby Cardigan", "top_down_yoke")):
        got = CF.route(category=cat, title=title, form="fitted_garment", construction=cons)
        assert got["admitted"], (title, got)


# ---- the child-safety garment rules ---------------------------------------------------------


def test_the_baby_and_child_garments_pass_every_child_safety_check():
    for key in (BABY_CARDIGAN, CHILD_SWEATER):
        assert released(key).cirs, key
        for size, cir in released(key).cirs.items():
            v = CS.evaluate(cir, compile_cir(cir))
            assert v.applies and v.verdict == CS.VERDICT_PASS, (key, size, v.to_dict())
            assert "garment" in v.profile and "sewn" not in v.profile, v.profile
            assert any(c.code == "GARMENT_CLOSURES" and c.state == CS.PASS for c in v.checks)


def test_buttonholes_on_an_under_three_garment_fail_and_on_an_older_child_are_held():
    spec = dataclasses.replace(GR.DESIGNS[BABY_CARDIGAN], buttons=True,
                               key="test-buttoned-baby", title="Test Buttoned Baby Cardigan")
    d = GF.design(spec)
    cir = d.build("12m")
    v = CS.evaluate(cir, compile_cir(cir))
    got = {c.code: c.state for c in v.checks}
    assert got["GARMENT_CLOSURES"] == CS.FAIL, got
    spec = dataclasses.replace(GR.DESIGNS[BABY_CARDIGAN], buttons=True, audience="child",
                               key="test-buttoned-child", title="Test Buttoned Child Cardigan",
                               ease_cm=GR.EASES["child"]["relaxed"], sizes=("6",))
    cir = GF.design(spec).build("6")
    v = CS.evaluate(cir, compile_cir(cir))
    got = {c.code: c.state for c in v.checks}
    assert got["GARMENT_CLOSURES"] == CS.UNKNOWN and v.verdict != CS.VERDICT_PASS, got


def test_a_free_chain_loop_still_fails_and_a_worked_chain_is_fabric():
    cir = released(CHILD_SWEATER).cirs["4"]
    assert {c.code: c.state for c in CS.evaluate(cir).checks}["NO_CORDS_OR_LOOPS"] == CS.PASS
    bad = copy.deepcopy(cir)
    nb = next(c for c in bad.components if c.name == "neckband")
    last = nb.rows[-1]
    last.ops = list(last.ops) + [Op("ch", 30)]           # a hanging loop off the last row
    last.declared_count = (last.declared_count or 0) + 30
    assert {c.code: c.state for c in CS.evaluate(bad).checks}["NO_CORDS_OR_LOOPS"] == CS.FAIL


def test_a_picked_up_band_that_does_not_meet_its_edge_fails_joins():
    cir = copy.deepcopy(released(BABY_CARDIGAN).cirs["6m"])
    band = next(c for c in cir.components if c.name == "band_left")
    n = band.foundation * 2
    band.foundation = n
    for row in band.rows:
        row.ops = [Op("sc", n, loop="back")]
        row.declared_count = n
    got = {c.code: c.state for c in CS.evaluate(cir, compile_cir(cir)).checks}
    assert got["JOINS_VALIDATED"] == CS.FAIL, got


def test_a_child_garment_with_a_sewn_on_piece_still_needs_physical_evidence():
    spec = dataclasses.replace(GR.DESIGNS[PULLOVER], audience="child", sizes=("6",),
                               key="test-child-drop", title="Test Child Drop Pullover",
                               ease_cm=GR.EASES["child"]["relaxed"], weight="dk",
                               fibre="cotton")
    cir = GF.design(spec).build("6")
    v = CS.evaluate(cir, compile_cir(cir))
    got = {c.code: c.state for c in v.checks}
    assert "sewn" in v.profile and got["PHYSICAL_EVIDENCE"] == CS.UNKNOWN, (v.profile, got)


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
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
