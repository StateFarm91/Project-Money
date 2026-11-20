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
BABY_DRESS = WB.WearableSpec("clover-baby-dress", "Clover Baby Dress", "dress", "baby_dress",
                             "baby", "dk", "cotton", WB.BABY_EASE)
BABY_PINAFORE = WB.WearableSpec("thimble-baby-pinafore", "Thimble Baby Pinafore", "dress",
                                "baby_dress", "baby", "dk", "cotton", WB.BABY_EASE,
                                options=(("style", "pinafore"),))
BABY_ROMPER = WB.WearableSpec("bramble-baby-romper", "Bramble Baby Romper", "romper",
                              "baby_romper", "baby", "dk", "cotton", WB.BABY_EASE)
BABY_SIZES = ("3m", "6m", "12m", "18m", "24m")
TEE = WB.WearableSpec("saltwind-boxy-tee", "Saltwind Boxy Tee", "top", "top_tee", "adult",
                      "dk", "cotton", WB.TOP_EASE["adult"])
TANK = WB.WearableSpec("driftwood-tank", "Driftwood Tank", "top", "top_tank", "adult", "dk",
                       "cotton", WB.TOP_EASE["adult"])
KIDS_TANK = WB.WearableSpec("pebble-kids-tank", "Pebble Kids Tank", "top", "top_tank",
                            "child", "dk", "cotton", WB.TOP_EASE["child"])
VCARDI = WB.WearableSpec("juniper-v-neck-cardigan", "Juniper V-Neck Cardigan", "cardigan",
                         "cardigan_vneck", "adult", "worsted", "wool", WB.VCARDI_EASE["adult"])
KIDS_VCARDI = WB.WearableSpec("acorn-kids-v-neck-cardigan", "Acorn Kids V-Neck Cardigan",
                              "cardigan", "cardigan_vneck", "child", "dk", "cotton",
                              WB.VCARDI_EASE["child"])
BABY_VCARDI = WB.WearableSpec("dewdrop-baby-v-neck-cardigan", "Dewdrop Baby V-Neck Cardigan",
                              "cardigan", "cardigan_vneck", "baby", "dk", "cotton",
                              WB.VCARDI_EASE["baby"])
SOCK = WB.WearableSpec("heathland-socks", "Heathland Socks", "sock", "sock", "adult",
                       "fingering", "merino", (("foot_circ", WB.SOCK_EASE_CM),))
KIDS_SOCK = WB.WearableSpec("bramble-kids-socks", "Bramble Kids Socks", "sock", "sock",
                            "child", "fingering", "merino", (("foot_circ", WB.SOCK_EASE_CM),))
SLIPPER = WB.WearableSpec("hearthstone-slippers", "Hearthstone Slippers", "slipper", "slipper",
                          "adult", "worsted", "wool", (("foot_circ", WB.SOCK_EASE_CM),))
KIDS_SLIPPER = WB.WearableSpec("fox-den-kids-slippers", "Fox Den Kids Slippers", "slipper",
                               "slipper", "child", "worsted", "wool",
                               (("foot_circ", WB.SOCK_EASE_CM),))
SHAWL = WB.WearableSpec("tidewrack-shawl", "Tidewrack Shawl", "shawl", "shawl_triangle",
                        "adult", "dk", "merino", WB.SHAWL_EASE)
WRAP = WB.WearableSpec("tidewrack-wrap", "Tidewrack Wrap", "shawl", "shawl_wrap", "adult",
                       "dk", "merino", WB.SHAWL_EASE)
TOTE = WB.WearableSpec("quayside-tote", "Quayside Tote", "bag", "bag_tote", "adult",
                       "worsted", "cotton", WB.BAG_EASE)
MARKET = WB.WearableSpec("orchard-market-bag", "Orchard Market Bag", "bag", "bag_market",
                         "adult", "worsted", "cotton", WB.BAG_EASE)
ADULT_SIZES = ("XS", "S", "M", "L", "XL", "2X", "3X", "4X", "5X")
CHILD_SIZES = ("2", "4", "6", "8", "10", "12")
SPECS = {s.key: s for s in (BEANIE, SLOUCHY, BABY_HAT, BABY_DRESS, BABY_PINAFORE,
                            BABY_ROMPER, TEE, TANK, KIDS_TANK, VCARDI, KIDS_VCARDI,
                            BABY_VCARDI, SOCK, KIDS_SOCK, SLIPPER, KIDS_SLIPPER,
                            SHAWL, WRAP, TOTE, MARKET)}


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


# ---- 2. baby rompers, dresses and pinafores ---------------------------------------------------


def test_every_baby_dress_pinafore_and_romper_size_is_granted():
    for spec in (BABY_DRESS, BABY_PINAFORE, BABY_ROMPER):
        assert_family_release(spec.key, BABY_SIZES)


def test_babywear_is_graded_from_the_baby_table_and_rises():
    for spec in (BABY_DRESS, BABY_PINAFORE, BABY_ROMPER):
        r = released(spec.key)
        ms = [WB.babywear_measures(c) for c in r.cirs.values()]
        assert len(ms) == 5
        for (size, cir), m in zip(r.cirs.items(), ms):
            g = r.design.graded_size(size)
            assert m["chest"] >= g.body_cm("bust") + 8, (spec.key, size, m)
            assert m["neck_opening"] >= WB.PULLOVER_HEAD_CM and m["armhole"] >= \
                g.body_cm("armhole_depth")
        assert all(b["chest"] > a["chest"] and b["length"] >= a["length"]
                   for a, b in zip(ms, ms[1:])), spec.key
    dress = WB.babywear_measures(released(BABY_DRESS.key).cirs["12m"])
    pina = WB.babywear_measures(released(BABY_PINAFORE.key).cirs["12m"])
    assert dress["widest"] > pina["widest"] and dress["length"] > pina["length"]
    romper = WB.babywear_measures(released(BABY_ROMPER.key).cirs["12m"])
    assert romper["widest"] >= released(BABY_ROMPER.key).design.graded_size(
        "12m").finished_cm("hip") - 1


def test_babywear_reverse_compiles_holds_size_truth_and_passes_child_safety():
    for spec in (BABY_DRESS, BABY_PINAFORE, BABY_ROMPER):
        assert_reverse_reads_back(spec.key)
        assert_size_truth(spec.key)
        assert released(spec.key).cirs
        for size, cir in released(spec.key).cirs.items():
            v = CS.evaluate(cir, compile_cir(cir))
            assert v.applies and v.verdict == CS.VERDICT_PASS, (spec.key, size, v.to_dict())
            got = {c.code: c.state for c in v.checks}
            assert got["GARMENT_CLOSURES"] == CS.PASS and got["NO_CORDS_OR_LOOPS"] == CS.PASS


def test_babywear_documents_read_back_with_chart_and_schematic():
    for spec in (BABY_DRESS, BABY_PINAFORE, BABY_ROMPER):
        assert_document(spec.key)
        text = " ".join(document(spec.key, "UK").text.split())
        assert CS.SECTION_HEADING in text and "pulls on over the head" in text
        made = " ".join(ln for ls in document(spec.key, "UK").pattern_lines.values()
                        for ln in ls).lower()
        made += text[text.find("Finishing"):text.find(CS.SECTION_HEADING)].lower()
        assert "button" not in made and "strap" not in made and "tie" not in made.split()


def test_babywear_gates_fail_on_the_defects_they_exist_for():
    r = released(BABY_ROMPER.key)
    # a neck too small to pass a head
    cirs = dict(r.cirs)
    cir = copy.deepcopy(cirs["6m"])
    real = WB.ENGINES["baby_romper"].measure
    try:
        object.__setattr__(WB.ENGINES["baby_romper"], "measure",
                           lambda c: dict(real(c), neck_opening=30.0))
        assert "GARMENT_NECK_FIT" in _codes(r, cirs)
    finally:
        object.__setattr__(WB.ENGINES["baby_romper"], "measure", real)
    # a 24m garment sold as 12m: off target and the size run does not rise
    cirs = dict(r.cirs)
    cirs["12m"] = r.cirs["24m"]
    got = _codes(r, cirs)
    assert {"GARMENT_FINISHED_OFF_TARGET", "GARMENT_SIZE_RUN"} <= got, got
    # second shoulder one row short: the shoulder seam does not meet
    cirs = dict(r.cirs)
    cir = copy.deepcopy(cirs["18m"])
    sh = next(c for c in cir.components if c.name == "shoulder")
    sh.rows = sh.rows[:-1]
    cirs["18m"] = cir
    assert "GARMENT_SEAM_MISMATCH" in _codes(r, cirs) or "GARMENT_STITCH_COUNT" in \
        _codes(r, cirs)
    # a leg opening too tight for the hips
    cirs = dict(r.cirs)
    cir = copy.deepcopy(cirs["3m"])
    WB.facts_of(cir).numbers["leg_opening_cm"] = 10.0
    cirs["3m"] = cir
    assert "GARMENT_LEG_FIT" in _codes(r, cirs)


def test_a_buttoned_or_strapped_baby_garment_is_held_never_drafted():
    from brambleloop.creative import construction_families as CF

    for title in ("Buttoned Baby Romper", "Baby Dress with Straps", "Tie Shoulder Baby Dress",
                  "Baby Romper with Sleeves", "Footed Baby Romper", "Linen Summer Dress"):
        got = CF.route(category="dress" if title.startswith("Linen") else "baby", title=title, form="fitted_garment",
                       construction="flat_rows")
        assert not got["admitted"] and got["reason"].startswith(CF.HOLD_PREFIX), (title, got)
    for title, fam in (("Clover Baby Dress", "baby_dress"),
                       ("Thimble Baby Pinafore", "baby_dress"),
                       ("Bramble Baby Romper", "baby_romper")):
        got = CF.route(category="baby", title=title, form="fitted_garment",
                       construction="bottom_up")
        assert got["admitted"] and got["family"] == fam, (title, got)


# ---- 3. simple tops: boxy tee and tank ---------------------------------------------------------


def test_every_tee_and_tank_size_is_granted():
    assert_family_release(TEE.key, ADULT_SIZES)
    assert_family_release(TANK.key, ADULT_SIZES)
    assert_family_release(KIDS_TANK.key, CHILD_SIZES)


def test_tops_are_graded_relaxed_and_rise_size_to_size():
    for spec in (TEE, TANK, KIDS_TANK):
        r = released(spec.key)
        ms = [WB.top_measures(c) for c in r.cirs.values()]
        assert ms and all(b["chest"] > a["chest"] for a, b in zip(ms, ms[1:])), spec.key
        for (size, _c), m in zip(r.cirs.items(), ms):
            g = r.design.graded_size(size)
            assert 8 <= m["chest"] - g.body_cm("bust") <= 22, (spec.key, size, m)
            assert m["armhole"] >= g.body_cm("armhole_depth")
    tee = WB.top_measures(released(TEE.key).cirs["M"])
    assert tee["upper_arm"] >= released(TEE.key).design.graded_size("M").body_cm("upper_arm")


def test_tops_reverse_compile_hold_size_truth_and_the_kids_tank_is_child_safe():
    for spec in (TEE, TANK, KIDS_TANK):
        assert_reverse_reads_back(spec.key)
        assert_size_truth(spec.key)
    assert released(KIDS_TANK.key).cirs
    for size, cir in released(KIDS_TANK.key).cirs.items():
        v = CS.evaluate(cir, compile_cir(cir))
        assert v.applies and v.verdict == CS.VERDICT_PASS and "sewn" not in v.profile, size


def test_tops_documents_read_back_with_chart_and_schematic():
    for spec in (TEE, TANK, KIDS_TANK):
        assert_document(spec.key)
    assert CS.SECTION_HEADING in " ".join(document(KIDS_TANK.key, "US").text.split())
    assert CS.SECTION_HEADING not in " ".join(document(TEE.key, "US").text.split())


def test_top_gates_fail_on_the_defects_they_exist_for():
    r = released(TEE.key)
    cirs = dict(r.cirs)
    cirs["L"] = r.cirs["XL"]
    got = _codes(r, cirs)
    assert {"GARMENT_FINISHED_OFF_TARGET", "GARMENT_SIZE_RUN"} <= got, got
    # the back one row longer than the front: the fold does not meet
    cirs = dict(r.cirs)
    cir = copy.deepcopy(cirs["M"])
    body = next(c for c in cir.components if c.name == "body")
    extra = copy.deepcopy(body.rows[-1])
    extra.index = body.rows[-1].index + 1
    body.rows.append(extra)
    cirs["M"] = cir
    assert "GARMENT_SEAM_MISMATCH" in _codes(r, cirs)
    # a sleeve narrower than the armhole it is sewn into
    cirs = dict(r.cirs)
    cir = copy.deepcopy(cirs["S"])
    WB.facts_of(cir).seams[1] = dict(WB.facts_of(cir).seams[1], a_cm=10.0)
    cirs["S"] = cir
    assert "GARMENT_SEAM_MISMATCH" in _codes(r, cirs)


def test_tops_route_by_title_and_unbuilt_tops_are_held():
    from brambleloop.creative import construction_families as CF

    for cat, title, fam in (("top", "Saltwind Boxy Tee", "top_tee"),
                            ("top", "Driftwood Tank Top", "top_tank"),
                            ("top", "Pebble Kids Tank", "top_tank")):
        got = CF.route(category=cat, title=title, form="fitted_garment",
                       construction="flat_rows")
        assert got["admitted"] and got["family"] == fam, (title, got)
    for title in ("Kids Boxy Tee", "V-Neck Tee", "Cropped Tank", "Lace Tank",
                  "Long Sleeve Tee", "Fitted Tee"):
        got = CF.route(category="top", title=title, form="fitted_garment",
                       construction="flat_rows")
        assert not got["admitted"] and got["reason"].startswith(CF.HOLD_PREFIX), (title, got)


# ---- 4. cardigan variants: V-neck raglan --------------------------------------------------------


def test_every_v_neck_cardigan_size_is_granted_adult_child_and_baby():
    assert_family_release(VCARDI.key, ADULT_SIZES)
    assert_family_release(KIDS_VCARDI.key, CHILD_SIZES)
    assert_family_release(BABY_VCARDI.key, BABY_SIZES)


def test_the_v_neck_grows_from_a_point_and_the_band_follows_the_slope():
    from brambleloop.cir.assembly import footprint
    from brambleloop.cir.twin import build_twin

    for spec in (VCARDI, KIDS_VCARDI, BABY_VCARDI):
        r = released(spec.key)
        assert r.cirs
        for size, cir in r.cirs.items():
            res = compile_cir(cir)
            yoke = next(c for c in cir.components if c.name == "yoke_and_body")
            # the fronts start as a 2-st point and the neck increases are edge increases
            assert yoke.foundation == 2 * 2 + 2 * WB.facts_of(cir).numbers["s0"] + \
                WB.facts_of(cir).numbers["b0"]
            m = WB.vcardi_measures(cir)
            g = r.design.graded_size(size)
            assert m["front_edge"] > m["length"] and m["armhole"] >= g.body_cm("armhole_depth")
            fp = footprint(yoke, build_twin(cir, res, component=yoke.name), cir.gauge)
            assert abs(fp.edge_cm("left") - m["front_edge"]) < 0.2, (size, fp, m)
            band = WB.facts_of(cir).pickups[0]["stitches"] * 10 / cir.gauge.stitches_per_10cm
            assert abs(band - m["front_edge"]) / m["front_edge"] <= 0.04


def test_v_neck_cardigans_reverse_compile_hold_size_truth_and_child_sizes_are_safe():
    for spec in (VCARDI, KIDS_VCARDI, BABY_VCARDI):
        assert_reverse_reads_back(spec.key)
        assert_size_truth(spec.key)
    for spec in (KIDS_VCARDI, BABY_VCARDI):
        assert released(spec.key).cirs
        for size, cir in released(spec.key).cirs.items():
            v = CS.evaluate(cir, compile_cir(cir))
            assert v.applies and v.verdict == CS.VERDICT_PASS, (spec.key, size, v.to_dict())


def test_v_neck_cardigan_documents_read_back_with_chart_and_schematic():
    for spec in (VCARDI, KIDS_VCARDI, BABY_VCARDI):
        assert_document(spec.key)
    text = " ".join(document(VCARDI.key, "US").text.split())
    assert "increase 1 st at each neck edge" in text and "Set-up: on Row 1" in text


def test_v_neck_cardigan_gates_fail_on_the_defects_they_exist_for():
    r = released(VCARDI.key)
    cirs = dict(r.cirs)
    cirs["M"] = r.cirs["L"]
    assert {"GARMENT_FINISHED_OFF_TARGET", "GARMENT_SIZE_RUN"} <= _codes(r, cirs)
    # a band picked up at the vertical height, not along the V's slope: it would pull
    cirs = dict(r.cirs)
    cir = copy.deepcopy(cirs["S"])
    m = WB.vcardi_measures(cir)
    short = int(m["length"] * cir.gauge.stitches_per_10cm / 10)
    for name in ("band_left", "band_right"):
        band = next(c for c in cir.components if c.name == name)
        band.foundation = short
        for row in band.rows:
            row.ops = [Op("sc", short, loop="back")]
            row.declared_count = short
    for p in WB.facts_of(cir).pickups:
        p["stitches"] = short
    cirs["S"] = cir
    assert "GARMENT_PICKUP_RATE" in _codes(r, cirs)
    # a written yoke line whose neck schedule is wrong is caught on read-back
    doc = document(VCARDI.key, "US")
    lines = {h: list(ls) for h, ls in doc.pattern_lines.items()}
    head = next(h for h in lines if h.startswith("Yoke"))
    k = next(i for i, ln in enumerate(lines[head]) if "neck edge" in ln)
    lines[head][k] = lines[head][k].replace("times in all; work every",
                                            "times in all; work every", 1).replace(
        "on the first row and on every 3 (", "on the first row and on every 4 (")
    if lines[head][k] != doc.pattern_lines[head][k]:
        assert any(p.code == "GARMENT_DOCUMENT" for p in WF.document_problems(
            lines, r.cirs, doc.piece_of))


def test_cardigans_route_by_neckline_and_granny_square_is_held_by_name():
    from brambleloop.creative import construction_families as CF

    got = CF.route(category="cardigan", title="Juniper V-Neck Cardigan",
                   form="fitted_garment", construction="top_down_yoke")
    assert got["admitted"] and got["family"] == "cardigan_vneck", got
    got = CF.route(category="cardigan", title="Fernway Raglan Cardigan",
                   form="fitted_garment", construction="top_down_yoke")
    assert got["admitted"] and got["family"] == "garment_raglan", got
    for title in ("Granny Square Cardigan", "Granny Square V-Neck Cardigan",
                  "Buttoned V-Neck Cardigan", "Cabled V-Neck Cardigan"):
        got = CF.route(category="cardigan", title=title, form="fitted_garment",
                       construction="top_down_yoke")
        assert not got["admitted"] and got["reason"].startswith(CF.HOLD_PREFIX), (title, got)
    for cons in ("motif_join", "granny_square", "top_down_yoke"):
        got = CF.route(category="cardigan", title="Granny Square Cardigan",
                       form="fitted_garment", construction=cons)
        assert got["reason"].startswith(f"{CF.HOLD_PREFIX}granny_square_garment"), got


# ---- 5. socks and slippers -------------------------------------------------------------------


def test_the_foot_chart_is_the_published_cyc_chart():
    from brambleloop.cir.graded import FOOT

    assert FOOT.source_url.endswith("/standards/foot-size-charts")
    got = {b.size: (b.cm("foot_circ"), b.published["foot_length"]) for b in FOOT.sizes}
    assert got["Woman 7-9.5"] == (20.5, (23.5, 25.5)) and got["Man 12-14"] == (25.5,
                                                                                (28.5, 30.5))
    assert got["Baby 0-4"] == (11.0, (7.75, 11.5)) and len(got) == 11
    assert all(not b.is_sourced("sock_height") for b in FOOT.sizes)


def test_every_sock_and_slipper_size_is_granted():
    adult, child = WB.SOCK_SIZES["adult"], WB.SOCK_SIZES["child"]
    assert_family_release(SOCK.key, adult)
    assert_family_release(KIDS_SOCK.key, child)
    assert_family_release(SLIPPER.key, adult)
    assert_family_release(KIDS_SLIPPER.key, child)


def test_socks_are_graded_from_the_foot_chart_and_rise():
    for spec in (SOCK, KIDS_SOCK, SLIPPER, KIDS_SLIPPER):
        r = released(spec.key)
        ms = [WB.sock_measures(c) for c in r.cirs.values()]
        assert ms and all(b["circumference"] > a["circumference"] and
                          b["foot_length"] > a["foot_length"] for a, b in zip(ms, ms[1:]))
        for (size, _c), m in zip(r.cirs.items(), ms):
            g = r.design.graded_size(size)
            assert -3.0 <= m["circumference"] - g.body_cm("foot_circ") <= 0.5
            assert abs(m["foot_length"] - g.body_cm("foot_length")) / g.body_cm(
                "foot_length") <= 0.06
    sock = WB.sock_measures(released(SOCK.key).cirs["Woman 7-9.5"])
    slip = WB.sock_measures(released(SLIPPER.key).cirs["Woman 7-9.5"])
    assert sock["leg_length"] > 2 * slip["leg_length"]


def test_socks_reverse_compile_hold_size_truth_and_child_sizes_are_safe():
    for spec in (SOCK, KIDS_SOCK, SLIPPER, KIDS_SLIPPER):
        assert_reverse_reads_back(spec.key)
        assert_size_truth(spec.key)
    for spec in (KIDS_SOCK, KIDS_SLIPPER):
        assert released(spec.key).cirs
        for size, cir in released(spec.key).cirs.items():
            v = CS.evaluate(cir, compile_cir(cir))
            assert v.applies and v.verdict == CS.VERDICT_PASS, (spec.key, size, v.to_dict())


def test_sock_documents_read_back_with_chart_and_schematic():
    for spec in (SOCK, KIDS_SOCK, SLIPPER, KIDS_SLIPPER):
        assert_document(spec.key)
    text = " ".join(document(SOCK.key, "UK").text.split())
    assert "(heel opening)" in text and "Heel" in text


def test_sock_gates_fail_on_the_defects_they_exist_for():
    r = released(SOCK.key)
    cirs = dict(r.cirs)
    cirs["Woman 4-6.5"] = r.cirs["Woman 10-12.5"]
    got = _codes(r, cirs)
    assert {"SOCK_CIRCUMFERENCE", "SOCK_FOOT_LENGTH", "GARMENT_SIZE_RUN"} <= got, got
    # a toe that stops short of closing
    cirs = dict(r.cirs)
    cir = copy.deepcopy(cirs["Woman 7-9.5"])
    leg = next(c for c in cir.components if c.name == "leg")
    leg.rows = leg.rows[:-2]
    f = WB.facts_of(cir)
    last = f.pieces["leg"][-1]
    f.pieces["leg"][-1] = dataclasses.replace(
        last, last=last.last - 2, count=leg.rows[-1].declared_count,
        n=(("sections", 6), ("rounds", last.get("rounds") - 2)))
    cirs["Woman 7-9.5"] = cir
    assert "SOCK_CAP_OPEN" in _codes(r, cirs)
    # a heel that starts on fewer stitches than the opening holds
    cirs = dict(r.cirs)
    cir = copy.deepcopy(cirs["Man 12-14"])
    heel = next(c for c in cir.components if c.name == "heel")
    heel.foundation -= 2
    row = heel.rows[0]
    row.ops = [Op("sc", heel.foundation)]
    row.declared_count = heel.foundation
    cirs["Man 12-14"] = cir
    assert {"GARMENT_PICKUP_RATE", "GARMENT_STITCH_COUNT"} & _codes(r, cirs)


def test_socks_route_and_unbuilt_footwear_is_held():
    from brambleloop.creative import construction_families as CF

    for cat, title, fam in (("sock", "Heathland Socks", "sock"),
                            ("sock", "Bramble Kids Socks", "sock"),
                            ("slipper", "Hearthstone Slippers", "slipper")):
        got = CF.route(category=cat, title=title, form="fitted_garment",
                       construction="in_the_round")
        assert got["admitted"] and got["family"] == fam, (title, got)
    for cat, title in (("sock", "Baby Socks"), ("sock", "Knee-High Socks"),
                       ("slipper", "Moccasin Slippers"), ("slipper", "Non-Slip Slippers"),
                       ("sock", "Toe-Up Socks"), ("slipper", "Baby Booties")):
        got = CF.route(category=cat, title=title, form="fitted_garment",
                       construction="in_the_round")
        assert not got["admitted"] and got["reason"].startswith(CF.HOLD_PREFIX), (title, got)
    got = CF.route(category="stocking", title="Fireside Stocking", form="stocking",
                   construction="flat_rows")
    assert got.get("family") != "sock"


# ---- 6. shawls and wraps ---------------------------------------------------------------------


def test_every_shawl_and_wrap_size_is_granted_and_spans_the_arms():
    for spec in (SHAWL, WRAP):
        assert_family_release(spec.key, WB.SHAWL_SIZES["adult"])
        r = released(spec.key)
        ms = [WB.shawl_measures(c) for c in r.cirs.values()]
        assert ms and all(b["wingspan"] > a["wingspan"] for a, b in zip(ms, ms[1:]))
        for (size, _c), m in zip(r.cirs.items(), ms):
            assert m["wingspan"] >= 2 * r.design.graded_size(size).body_cm("neck_to_wrist")
    tri = WB.shawl_measures(released(SHAWL.key).cirs["M"])
    assert 0.38 <= tri["depth"] / tri["wingspan"] <= 0.6


def test_shawls_reverse_compile_hold_size_truth_and_render():
    for spec in (SHAWL, WRAP):
        assert_reverse_reads_back(spec.key)
        assert_size_truth(spec.key)
        assert_document(spec.key)
    assert "Wrap" in document(WRAP.key, "US").pattern_lines


def test_shawl_gates_fail_on_the_defects_they_exist_for():
    r = released(SHAWL.key)
    cirs = dict(r.cirs)
    cirs["L"] = r.cirs["XS"]
    assert {"SHAWL_WINGSPAN", "GARMENT_SIZE_RUN"} <= _codes(r, cirs)
    w = released(WRAP.key)
    cirs = dict(w.cirs)
    cir = copy.deepcopy(cirs["M"])
    comp = cir.components[0]
    comp.rows = comp.rows[:40] + comp.rows[-4:]
    for i, row in enumerate(comp.rows, start=1):
        row.index = i
    cirs["M"] = cir
    assert "SHAWL_WINGSPAN" in _codes(w, cirs)


def test_shawls_route_and_a_crescent_is_held_by_name():
    from brambleloop.creative import construction_families as CF

    for title, fam in (("Tidewrack Shawl", "shawl_triangle"), ("Tidewrack Wrap",
                                                               "shawl_wrap")):
        got = CF.route(category="shawl", title=title, form="draped_garment",
                       construction="flat_rows")
        assert got["admitted"] and got["family"] == fam, (title, got)
    for title in ("Moonrise Crescent Shawl", "Lace Shawl", "Fringed Wrap", "Granny Shawl",
                  "Kids Shawl"):
        got = CF.route(category="shawl", title=title, form="draped_garment",
                       construction="flat_rows")
        assert not got["admitted"] and got["reason"].startswith(CF.HOLD_PREFIX), (title, got)
    got = CF.route(category="shawl", title="Moonrise Crescent Shawl", form="draped_garment",
                   construction="flat_rows")
    assert "crescent" in got["reason"]


# ---- 7. bags and totes -----------------------------------------------------------------------


def test_the_sheet_table_is_iso_216():
    from brambleloop.cir.graded import SHEETS

    got = {b.size: (b.cm("sheet_width"), b.cm("sheet_height")) for b in SHEETS.sizes}
    assert got == {"A5": (14.8, 21.0), "A4": (21.0, 29.7), "A3": (29.7, 42.0)}


def test_every_tote_and_market_bag_size_is_granted_and_holds_its_sheet():
    for spec in (TOTE, MARKET):
        assert_family_release(spec.key, WB.BAG_SIZES["adult"])
        r = released(spec.key)
        ms = [WB.bag_measures(c) for c in r.cirs.values()]
        assert ms and all(b["circumference"] > a["circumference"] for a, b in zip(ms, ms[1:]))
        for (size, _c), m in zip(r.cirs.items(), ms):
            g = r.design.graded_size(size)
            assert m["width"] >= g.body_cm("sheet_width") and \
                m["height"] >= g.body_cm("sheet_height"), (spec.key, size, m)


def test_bags_reverse_compile_hold_size_truth_and_render():
    for spec in (TOTE, MARKET):
        assert_reverse_reads_back(spec.key)
        assert_size_truth(spec.key)
        assert_document(spec.key)
    text = " ".join(document(MARKET.key, "US").text.split())
    assert "make a magic ring" in text and "through the back loop in each st around" in text


def test_bag_gates_fail_on_the_defects_they_exist_for():
    r = released(TOTE.key)
    cirs = dict(r.cirs)
    cirs["A3"] = r.cirs["A5"]
    assert {"BAG_HOLDS", "GARMENT_SIZE_RUN"} <= _codes(r, cirs)
    cirs = dict(r.cirs)
    cir = copy.deepcopy(cirs["A4"])
    h = next(c for c in cir.components if c.name == "handle")
    h.rows = h.rows[:20]
    cirs["A4"] = cir
    assert "BAG_HANDLE" in _codes(r, cirs)
    cirs = dict(r.cirs)
    cir = copy.deepcopy(cirs["A5"])
    WB.facts_of(cir).pickups[0] = dict(WB.facts_of(cir).pickups[0], edge_sts=30.0)
    cirs["A5"] = cir
    assert "GARMENT_PICKUP_RATE" in _codes(r, cirs)


def test_bags_route_and_unbuilt_bags_are_held():
    from brambleloop.creative import construction_families as CF

    for title, fam in (("Quayside Tote", "bag_tote"), ("Orchard Market Bag", "bag_market"),
                       ("Quayside Tote with Strap Handles", "bag_tote")):
        got = CF.route(category="bag", title=title, form="bag", construction="in_the_round")
        assert got["admitted"] and got["family"] == fam, (title, got)
    for title in ("Lined Tote", "Mesh Market Bag", "Zippered Tote", "Kids Tote",
                  "Crossbody Tote"):
        got = CF.route(category="bag", title=title, form="bag", construction="in_the_round")
        assert not got["admitted"] and got["reason"].startswith(CF.HOLD_PREFIX), (title, got)


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


BABY_DRESS_P = _wearable_proposal(
    "sorrel-baby-dress", "Sorrel Baby Dress", "baby", "fitted_garment", "bottom_up",
    "new_parent", "A soft A-line baby dress in cotton that pulls on with nothing to fasten",
    "new_baby")
BABY_PINAFORE_P = _wearable_proposal(
    "wren-song-baby-pinafore", "Wren Song Baby Pinafore", "dress", "fitted_garment",
    "bottom_up", "new_parent", "A square-neck baby pinafore to layer over a little top",
    "new_baby")
BABY_ROMPER_P = _wearable_proposal(
    "meadowlark-baby-romper", "Meadowlark Baby Romper", "baby", "fitted_garment",
    "bottom_up", "new_parent", "A sleeveless pull-on baby romper in cotton for warm days",
    "new_baby")


def test_a_research_baby_dress_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(BABY_DRESS_P)
    assert_concept_to_pdf(out, BABY_SIZES, "baby_dress")


def test_a_research_baby_pinafore_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(BABY_PINAFORE_P)
    assert_concept_to_pdf(out, BABY_SIZES, "baby_dress")
    assert out["release"].spec.option("style") == "pinafore"


def test_a_research_baby_romper_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(BABY_ROMPER_P)
    assert_concept_to_pdf(out, BABY_SIZES, "baby_romper")


TEE_P = _wearable_proposal(
    "harbour-light-boxy-tee", "Harbour Light Boxy Tee", "top", "fitted_garment", "flat_rows",
    "self", "A boxy cotton tee with short sleeves for warm evenings by the water", "mothers_day")
TANK_P = _wearable_proposal(
    "seagrass-tank", "Seagrass Tank", "top", "fitted_garment", "flat_rows", "self",
    "A boxy cotton tank with a slash neck to layer in summer", "mothers_day")
KIDS_TANK_P = _wearable_proposal(
    "rockpool-kids-tank", "Rockpool Kids Tank", "top", "fitted_garment", "flat_rows", "child",
    "A boxy cotton kids tank for beach days", "back_to_school")


def test_a_research_adult_tee_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(TEE_P)
    assert_concept_to_pdf(out, ADULT_SIZES, "top_tee")


def test_a_research_adult_tank_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(TANK_P)
    assert_concept_to_pdf(out, ADULT_SIZES, "top_tank")


def test_a_research_child_tank_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(KIDS_TANK_P)
    assert_concept_to_pdf(out, CHILD_SIZES, "top_tank")


VCARDI_P = _wearable_proposal(
    "larkspur-v-neck-cardigan", "Larkspur V-Neck Cardigan", "cardigan", "fitted_garment",
    "top_down_yoke", "self", "A relaxed open-front V-neck cardigan for cool spring mornings",
    "mothers_day")
KIDS_VCARDI_P = _wearable_proposal(
    "chestnut-kids-v-neck-cardigan", "Chestnut Kids V-Neck Cardigan", "cardigan",
    "fitted_garment", "top_down_yoke", "child",
    "A relaxed open-front V-neck kids cardigan for the classroom", "back_to_school")
BABY_VCARDI_P = _wearable_proposal(
    "snowberry-baby-v-neck-cardigan", "Snowberry Baby V-Neck Cardigan", "baby",
    "fitted_garment", "top_down_yoke", "new_parent",
    "A soft open-front V-neck baby cardigan with nothing to fasten", "new_baby")


def test_a_research_adult_v_neck_cardigan_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(VCARDI_P)
    assert_concept_to_pdf(out, ADULT_SIZES, "cardigan_vneck")


def test_a_research_child_v_neck_cardigan_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(KIDS_VCARDI_P)
    assert_concept_to_pdf(out, CHILD_SIZES, "cardigan_vneck")


def test_a_research_baby_v_neck_cardigan_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(BABY_VCARDI_P)
    assert_concept_to_pdf(out, BABY_SIZES, "cardigan_vneck")


SOCK_P = _wearable_proposal(
    "moorland-socks", "Moorland Socks", "sock", "fitted_garment", "in_the_round", "self",
    "Soft merino socks with a ribbed cuff to wear around the house in winter")
KIDS_SOCK_P = _wearable_proposal(
    "puddle-jump-kids-socks", "Puddle Jump Kids Socks", "sock", "fitted_garment",
    "in_the_round", "child", "Cosy merino socks that stay up inside wellington boots on rainy walks to "
    "school, in a heathery green", "back_to_school")
SLIPPER_P = _wearable_proposal(
    "inglenook-slippers", "Inglenook Slippers", "slipper", "fitted_garment", "in_the_round",
    "self", "Thick wool slippers with a short ribbed cuff for cold floors")
KIDS_SLIPPER_P = _wearable_proposal(
    "burrow-kids-slippers", "Burrow Kids Slippers", "slipper", "fitted_garment",
    "in_the_round", "child", "Cosy wool slippers with a short ribbed cuff that stay on while small feet "
    "pad around a cold farmhouse kitchen")


def test_a_research_adult_sock_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(SOCK_P)
    assert_concept_to_pdf(out, WB.SOCK_SIZES["adult"], "sock")


def test_a_research_child_sock_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(KIDS_SOCK_P)
    assert_concept_to_pdf(out, WB.SOCK_SIZES["child"], "sock")


def test_a_research_adult_slipper_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(SLIPPER_P)
    assert_concept_to_pdf(out, WB.SOCK_SIZES["adult"], "slipper")


def test_a_research_child_slipper_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(KIDS_SLIPPER_P)
    assert_concept_to_pdf(out, WB.SOCK_SIZES["child"], "slipper")


SHAWL_P = _wearable_proposal(
    "saltgrass-shawl", "Saltgrass Shawl", "shawl", "draped_garment", "flat_rows", "self",
    "A soft merino triangle to wrap round the shoulders on a breezy harbour evening",
    "mothers_day")
WRAP_P = _wearable_proposal(
    "lantern-hour-wrap", "Lantern Hour Wrap", "shawl", "draped_garment", "flat_rows",
    "self", "A long merino rectangle to throw over the shoulders for evenings on the porch",
    "mothers_day")


def test_a_research_adult_shawl_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(SHAWL_P)
    assert_concept_to_pdf(out, WB.SHAWL_SIZES["adult"], "shawl_triangle")


def test_a_research_adult_wrap_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(WRAP_P)
    assert_concept_to_pdf(out, WB.SHAWL_SIZES["adult"], "shawl_wrap")


TOTE_P = _wearable_proposal(
    "chandlers-row-tote", "Chandlers Row Tote", "bag", "bag", "in_the_round", "self",
    "A sturdy cotton tote that carries a sketchbook and a flask to the harbour wall",
    "mothers_day")
MARKET_P = _wearable_proposal(
    "saturday-stall-market-bag", "Saturday Stall Market Bag", "bag", "bag", "in_the_round",
    "self", "A round-bottomed cotton bag for apples, bread and greens from the Saturday stalls",
    "mothers_day")


def test_a_research_adult_tote_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(TOTE_P)
    assert_concept_to_pdf(out, WB.BAG_SIZES["adult"], "bag_tote")


def test_a_research_adult_market_bag_runs_concept_to_pdf():
    out = _research_wearable_to_pdf(MARKET_P)
    assert_concept_to_pdf(out, WB.BAG_SIZES["adult"], "bag_market")


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
