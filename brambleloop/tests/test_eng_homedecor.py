"""ENG-HOMEDECOR slice 1: vessels in the round the factory can certify, and the gates on them.

Runs the real handlers (`radar.concept_intake`, `radar.score`, `cir.draft`, `cir.compile`,
`gate.certify`) through the worker on a scratch SQLite file, via the ENG-FAMILIES harness, then
renders the certified CIR as the US and UK pattern PDFs. Every research source, finding,
listing and taste judgement here is a TEST FIXTURE; none is an observation or a customer.

Also pins the defect this slice found: a "Round", "Oval", "Yarn Bowl", "Plant Pot Cozy" or
"Moss Stitch" basket certified as the plain hexagon basket. Each mutation test below proves the
gate it names is what refuses the defective pattern (the mutant passes without it).
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import dataclasses
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_eng_families as EF  # noqa: E402  - the ENG-FAMILIES end-to-end harness

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.geometry import corners  # noqa: E402
from brambleloop.cir.model import CIR, Op, Repeat, Row  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.creative import construction_families as CF  # noqa: E402
from brambleloop.creative import fallback_constructions as FC  # noqa: E402
from brambleloop.creative import homedecor as HD  # noqa: E402
from brambleloop.gates.certificate import certify  # noqa: E402
from brambleloop.gates.originality import catalogue_provenance  # noqa: E402
from brambleloop.publish.pdf import build_pattern_pdf, extracted_text  # noqa: E402
from brambleloop.runtime.pipeline import Concept  # noqa: E402


def _proposal(slug: str, title: str) -> dict:
    return EF._proposal(slug, title, "basket", form="basket", construction="in_the_round",
                        motif="tide bands", function="holds rolled towels by the bath")


ROUND = _proposal("tide-round-reed-basket", "Round Tide Reed Basket")
BOWL = _proposal("tide-catchall-bowl", "Tide Catchall Bowl")
LIDDED = _proposal("tide-lidded-reed-basket", "Lidded Tide Reed Basket")
HANDLED = _proposal("tide-reed-basket-with-handles", "Tide Reed Basket With Handles")

# The family-aware PDF standard for small home goods (research/benchmarks/
# PDF_STRUCTURE_STANDARD.md): concise but complete. Each entry is (requirement, words that
# must appear in the extracted text, read case-insensitively).
SMALL_HOME_GOODS_PDF = (
    ("materials", ("what you need", "materials")),
    ("gauge", ("gauge",)),
    ("finished size", ("finished size",)),
    ("abbreviations", ("abbreviations",)),
    ("finishing", ("weave in",)),
    ("licence", ("what you may do with this pattern",)),
    ("disclosure", ("digital rendering", "ai assistance")),
)


def _pdf_text(cir: CIR, terms: str) -> str:
    doc = build_pattern_pdf(cir, terminology=terms)
    assert doc.terminology == terms and doc.pages >= 2, (terms, doc.pages)
    return extracted_text(doc.pdf_bytes)


def _assert_pdfs(cir: CIR) -> dict[str, str]:
    """Both editions render, meet the small-home-goods standard, and print every round with
    its stitch count."""
    out = {}
    result = compile_cir(cir)
    for terms in ("US", "UK"):
        text = _pdf_text(cir, terms)
        low = text.lower()
        assert f"{terms.lower()} terms" in low, terms
        for need, words in SMALL_HOME_GOODS_PDF:
            assert all(w in low for w in words), (terms, need, words)
        for comp in cir.components:
            last = comp.rows[-1]
            assert f"({last.declared_count} sts)" in text or f"{last.declared_count} sts" in text, \
                (terms, comp.name, last.declared_count)
        out[terms] = text
    assert result.ok
    # Terminology really differs: US single crochet is UK double crochet.
    assert re.search(r"\bsc\b", out["US"]), "the US edition works single crochet as sc"
    uk_sc = [m.start() for m in re.finditer(r"\bsc\b", out["UK"])]
    assert not uk_sc, ("a US abbreviation in the UK edition",
                       [out["UK"][max(0, i - 80):i + 40] for i in uk_sc[:3]])
    return out


def _certified(proposal: dict, family: str) -> tuple[CIR, dict]:
    out = EF._certify_research_concept(proposal)
    assert out["drafted"]["construction"] == family, out["drafted"]
    EF._assert_certified_end_to_end(out)
    return CIR.from_dict(out["cir"]), out


# ---- end to end: concept -> certify -> US/UK PDF ----------------------------------------------


def test_a_research_round_basket_certifies_with_a_round_base():
    cir, out = _certified(ROUND, HD.ROUND_VESSEL)
    result = compile_cir(cir)
    assert corners([r for r in result.rows]) == 0, "the base's increases never stack"
    counts = out["compiled"]["counts"]
    assert counts[0] == 6 and counts[1] == 12, counts
    assert "round" in cir.finished_size_note and "hexagon" not in cir.finished_size_note
    _assert_pdfs(cir)


def test_a_research_bowl_certifies_with_a_flared_wall():
    cir, out = _certified(BOWL, HD.BOWL)
    counts = out["compiled"]["counts"]
    nbase = HD._base_rounds(cir.components[0])
    assert counts[nbase] == counts[nbase - 1], "the base ends where the wall begins"
    assert counts[-1] > counts[nbase - 1], "the rim is wider than the base"
    rings = build_twin(cir, compile_cir(cir)).geometry.rings
    lean = math.degrees(math.atan2(rings[-1].radius_cm - rings[nbase - 1].radius_cm,
                                   sum(r.rise_cm for r in rings[nbase:])))
    assert HD.BOWL_MIN_LEAN_DEG <= lean <= HD.BOWL_MAX_LEAN_DEG, lean
    _assert_pdfs(cir)


def test_a_research_lidded_basket_certifies_with_a_fitting_lid():
    cir, _ = _certified(LIDDED, HD.LIDDED)
    assert [c.name for c in cir.components] == ["basket", "lid"]
    rim = cir.components[0].rows[-1].declared_count
    lid = cir.components[1].rows[-1].declared_count
    gap = HD.lid_clearance_cm(rim, lid, cir.gauge)
    assert HD.LID_MIN_CLEARANCE_CM <= gap <= HD.LID_MAX_CLEARANCE_CM, gap
    assert lid > rim and (lid - rim) % 6 == 0, (rim, lid)
    texts = _assert_pdfs(cir)
    assert "lid" in texts["US"].lower() and "lid" in texts["UK"].lower()
    # b19-c B2: the cover names the pieces (never "Makes 2 baskets"), its hero is the
    # schematic labelled as a rendering, and the schematic draws both pieces, unjoined.
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.publish.schematic import schematic_for
    for terms in ("US", "UK"):
        assert "In 2 pieces: 1 basket, 1 lid" in texts[terms], terms
        assert "Makes 2 baskets" not in texts[terms], terms
        assert "a rendering, not a photograph" in texts[terms][:1500], terms
        assert "not sewn together" in texts[terms], terms
    drawn = schematic_for(cir, compile_cir(cir))
    assert drawn is not None and set(drawn.labels) == {"basket", "lid"}, drawn
    assert drawn.arrows == [] and drawn.closures == []


def test_a_research_handled_basket_certifies_with_cut_out_handles():
    cir, _ = _certified(HANDLED, HD.HANDLED)
    openings = HD._openings(cir.components[0])
    assert len(openings) == 2, openings
    (r1, p1, w1), (r2, p2, w2) = openings
    n = cir.components[0].rows[-1].declared_count
    assert r1 == r2 and abs((p2 - p1) - n / 2) <= 1 and w1 == w2 == HD.handle_stitches(cir.gauge)
    assert w1 * 10.0 / cir.gauge.stitches_per_10cm >= HD.HANDLE_MIN_CM
    texts = _assert_pdfs(cir)
    assert f"ch {w1}, sk next {w1} sts" in texts["US"]
    assert f"ch {w1}, miss next {w1} sts" in texts["UK"], "UK terms say miss, not skip"


# ---- the defect this slice found: five products certified as the plain hexagon basket ---------

MISLABELLED = {
    "Round Tide Reed Basket": "VESSEL_OUTLINE_UNSUPPORTED",
    "Oval Tide Reed Basket": "VESSEL_OUTLINE_UNSUPPORTED",
    "Tide Yarn Bowl": "VESSEL_BOWL_NOT_FLARED",
    "Tide Plant Pot Cozy Basket": "VESSEL_OBJECT_UNSUPPORTED",
    "Moss Stitch Tide Basket": "VESSEL_TEXTURE_UNSUPPORTED",
    "Lidded Tide Reed Basket": "VESSEL_LID_DOES_NOT_FIT",
    "Tide Reed Basket With Handles": "VESSEL_HANDLE_UNSUPPORTED",
}


def _concept(title: str = "Tide Reed Basket") -> Concept:
    return Concept(slug="tide-fixture", title=title, category="basket",
                   stitch_repeat=[("sc", 4)], width_stitches=48, rows=14,
                   colors={"forest": "#244A3A", "cream": "#FAF6EB"})


def _provenanced(cir: CIR) -> CIR:
    return dataclasses.replace(cir, provenance=catalogue_provenance(
        "market-basket-trio", {"builder": "test_eng_homedecor", "slug": cir.slug},
        ("creative.homedecor",)))


def _codes(cir: CIR) -> set[str]:
    cert = certify(_provenanced(cir))
    return {f.code for f in cert.findings if f.severity == "ERROR"}


def test_the_plain_hexagon_basket_under_a_vessel_name_it_does_not_make_is_refused():
    plain = FC.vessel(_concept())
    assert not {c for c in _codes(plain) if c.startswith("VESSEL_")}, "the plain basket certifies"
    for title, code in MISLABELLED.items():
        codes = _codes(dataclasses.replace(plain, title=title))
        assert code in codes, (title, code, codes)


def test_intake_and_draft_hold_the_names_no_engine_backs():
    for title in ("Oval Tide Basket", "Tide Plant Pot Cozy", "Moss Stitch Tide Basket",
                  "Seed Stitch Tide Basket", "Round Lidded Tide Basket",
                  "Square Tide Basket"):
        got = CF.route(category="basket", title=title, form="basket",
                       construction="in_the_round")
        assert not got["admitted"] and got["reason"].startswith(CF.HOLD_PREFIX), (title, got)
        assert FC.plan(category="basket", title=title)["family"] == FC.REFUSED, title
    for title, family in (("Round Tide Basket", HD.ROUND_VESSEL), ("Tide Yarn Bowl", HD.BOWL),
                          ("Lidded Tide Basket", HD.LIDDED),
                          ("Tide Basket With Handles", HD.HANDLED),
                          ("Tide Basket Worked In The Round", FC.VESSEL)):
        got = CF.route(category="basket", title=title, form="basket",
                       construction="in_the_round")
        assert got["admitted"] and got["family"] == family, (title, got)
    # A bowl word that is not the object is refused, not guessed.
    assert FC.plan(category="basket", title="Bowl Tide Basket")["family"] == FC.REFUSED


def test_a_round_base_is_round_at_every_size():
    for size in ("small", "medium", "large"):
        spec = next(s for s in __import__("brambleloop.products.vessels",
                                          fromlist=["BASKET_SIZES"]).BASKET_SIZES
                    if s.key == size)
        title = {"small": "Round Bread Basket", "medium": "Round Tide Basket",
                 "large": "Round Market Basket"}[size]
        cir = HD.round_vessel(_concept(title))
        result = compile_cir(cir)
        assert result.ok and corners(result.rows) == 0, (size, spec)
        assert not {c for c in _codes(cir) if c.startswith(("VESSEL_", "TWIN_", "OBJECT_"))}, size


# ---- mutation tests: each gate is what refuses its defect -------------------------------------


def _without(gate_code: str, cir: CIR) -> set[str]:
    """The ERROR codes with `homedecor.findings` replaced by a version that drops `gate_code`."""
    real = HD.findings
    HD.findings = lambda *a, **k: [f for f in real(*a, **k) if f.code != gate_code]
    try:
        return _codes(cir)
    finally:
        HD.findings = real


def _kill(cir: CIR, code: str) -> None:
    """The mutant is refused by `code`, and nothing else refuses it once the gate is gone."""
    assert code in _codes(cir), (cir.title, code, _codes(cir))
    left = _without(code, cir)
    assert not {c for c in left if c.startswith("VESSEL_")}, (code, left)
    assert code not in left


def _base_mutant(per_round: int) -> CIR:
    """A basket whose base adds `per_round` stitches a round from round 3 (6 is flat)."""
    cir = FC.vessel(_concept())
    body = cir.components[0]
    rows = [Row(index=1, ops=[Op("sc", 6)], declared_count=6, color=body.rows[0].color),
            Row(index=2, ops=[Op("inc", 6)], declared_count=12, color=body.rows[0].color)]
    count = 12
    while count < 60:
        n = count // per_round
        body_ops = [Op("sc", n - 1), Op("inc")] if n > 1 else [Op("inc")]
        rows.append(Row(index=len(rows) + 1, ops=[Repeat(body_ops, times=per_round)],
                        declared_count=count + per_round, color=body.rows[0].color))
        count += per_round
    for _ in range(14):
        rows.append(Row(index=len(rows) + 1, ops=[Op("sc", count)], declared_count=count,
                        color=body.rows[0].color))
    return dataclasses.replace(cir, components=[dataclasses.replace(body, rows=rows)],
                               finished_size_note=None)


def test_mutant_base_that_cups_or_ruffles_is_refused_by_the_flat_base_gate():
    assert compile_cir(_base_mutant(3)).ok and compile_cir(_base_mutant(12)).ok
    _kill(_base_mutant(3), "VESSEL_BASE_NOT_FLAT")       # +3 a round: the base cups
    _kill(_base_mutant(12), "VESSEL_BASE_NOT_FLAT")      # +12 a round: the base ruffles
    assert "VESSEL_BASE_NOT_FLAT" not in _codes(_base_mutant(6))


def test_mutant_hexagon_base_titled_round_is_refused_by_the_outline_gate():
    _kill(dataclasses.replace(FC.vessel(_concept()), title="Round Tide Basket"),
          "VESSEL_OUTLINE_UNSUPPORTED")


def test_mutant_straight_or_flat_wall_titled_bowl_is_refused_by_the_bowl_gate():
    _kill(dataclasses.replace(FC.vessel(_concept()), title="Tide Catchall Bowl",
                              finished_size_note=None), "VESSEL_BOWL_NOT_FLARED")
    real = HD.BOWL_FLARE_EVERY
    try:
        HD.BOWL_FLARE_EVERY = 1000         # a mutant engine: the wall never flares
        flat = HD.bowl(_concept("Tide Catchall Bowl"))
    finally:
        HD.BOWL_FLARE_EVERY = real
    _kill(dataclasses.replace(flat, finished_size_note=None), "VESSEL_BOWL_NOT_FLARED")


def _lid_mutant(extra: int | None) -> CIR:
    cir = HD.lidded_vessel(_concept("Lidded Tide Basket"))
    if extra is None:
        return dataclasses.replace(cir, components=cir.components[:1])
    body, lid = cir.components
    rim = body.rows[-1].declared_count
    from brambleloop.products.vessels import _disc_rounds

    rows = _disc_rounds(rim + extra, lid.rows[0].color)
    for _ in range(3):
        rows.append(Row(index=rows[-1].index + 1, ops=[Op("sc", rim + extra)],
                        declared_count=rim + extra, color=lid.rows[0].color))
    return dataclasses.replace(cir, components=[body, dataclasses.replace(lid, rows=rows)],
                               finished_size_note=None)


def test_mutant_lids_that_bind_are_loose_or_missing_are_refused_by_the_lid_gate():
    assert "VESSEL_LID_DOES_NOT_FIT" not in _codes(HD.lidded_vessel(_concept("Lidded Tide Basket")))
    _kill(_lid_mutant(0), "VESSEL_LID_DOES_NOT_FIT")      # the rim's count: binds on the wall
    _kill(_lid_mutant(60), "VESSEL_LID_DOES_NOT_FIT")     # ten wedges over: slides about
    _kill(_lid_mutant(None), "VESSEL_LID_DOES_NOT_FIT")   # no lid at all


def _handle_mutant(kind: str) -> CIR:
    cir = HD.handled_vessel(_concept("Tide Basket With Handles"))
    body = cir.components[0]
    n = body.rows[-1].declared_count
    at = next(i for i, r in enumerate(body.rows) if any(getattr(o, "stitch", "") == "ch"
                                                         for o in r.ops))
    h = HD.handle_stitches(cir.gauge)
    rows = list(body.rows)
    if kind == "narrow":
        w = h - 4
        ops = [Op("sc", 4), Op("ch", w, spans=w), Op("sk", w), Op("sc", n // 2 - w),
               Op("ch", w, spans=w), Op("sk", w), Op("sc", n // 2 - 4 - w)]
    elif kind == "adjacent":
        ops = [Op("sc", 2), Op("ch", h, spans=h), Op("sk", h), Op("sc", 2),
               Op("ch", h, spans=h), Op("sk", h), Op("sc", n - 4 - 2 * h)]
    elif kind == "one":
        ops = [Op("sc", 4), Op("ch", h, spans=h), Op("sk", h), Op("sc", n - 4 - h)]
    else:   # "rim": the opening moved into the last round, with nothing above it
        rows[at] = dataclasses.replace(rows[at], ops=[Op("sc", n)])
        at = len(rows) - 1
        ops = [Op("sc", 4), Op("ch", h, spans=h), Op("sk", h), Op("sc", n // 2 - h),
               Op("ch", h, spans=h), Op("sk", h), Op("sc", n // 2 - 4 - h)]
    rows[at] = dataclasses.replace(rows[at], ops=ops)
    return dataclasses.replace(cir, components=[dataclasses.replace(body, rows=rows)])


def test_mutant_handles_too_narrow_not_opposite_single_or_at_the_rim_are_refused():
    good = HD.handled_vessel(_concept("Tide Basket With Handles"))
    assert "VESSEL_HANDLE_UNSUPPORTED" not in _codes(good)
    for kind in ("narrow", "adjacent", "one", "rim"):
        mutant = _handle_mutant(kind)
        assert compile_cir(mutant).ok, kind
        _kill(mutant, "VESSEL_HANDLE_UNSUPPORTED")
    _kill(dataclasses.replace(FC.vessel(_concept()), title="Tide Basket With Handles"),
          "VESSEL_HANDLE_UNSUPPORTED")


def test_mutant_planter_and_texture_names_are_refused_by_their_gates():
    plain = FC.vessel(_concept())
    _kill(dataclasses.replace(plain, title="Tide Plant Pot Cozy Basket"),
          "VESSEL_OBJECT_UNSUPPORTED")
    _kill(dataclasses.replace(plain, title="Moss Stitch Tide Basket"),
          "VESSEL_TEXTURE_UNSUPPORTED")
    _kill(dataclasses.replace(plain, title="Oval Tide Basket"), "VESSEL_OUTLINE_UNSUPPORTED")


# ---- review b17-b: UNKNOWN is not a pass; the `spans` exclusion is pinned -------------------


def test_a_vessel_name_with_no_readable_twin_geometry_is_an_error_not_silence():
    """Finding 1: no twin (or no geometry) used to make every vessel check emit nothing."""
    plain = FC.vessel(_concept())
    for title in ("Bowl Tide Basket", "Round Tide Basket", "Lidded Tide Basket"):
        got = {f.code for f in HD.findings(dataclasses.replace(plain, title=title), {})}
        assert "VESSEL_GEOMETRY_UNKNOWN" in got, (title, got)
    # A twin with no geometry is the same UNKNOWN.
    no_geo = {c.name: type("T", (), {"geometry": None, "sides": None})()
              for c in plain.components}
    got = {f.code for f in HD.findings(dataclasses.replace(plain, title="Bowl Tide Basket"),
                                       no_geo)}
    assert "VESSEL_GEOMETRY_UNKNOWN" in got, got
    # A title with no vessel claim is not judged here at all.
    assert HD.findings(dataclasses.replace(plain, title="Tide Reed Throw"), {}) == []


def test_a_round_vessel_not_worked_from_a_magic_ring_cannot_pass_the_flat_base_check():
    """The flat-base check only reads a magic-ring base; any other base claiming round, bowl
    or lid is UNKNOWN, and UNKNOWN is an error. The twin is the real twin of the real body."""
    good = FC.vessel(_concept())
    body = [c for c in good.components if c.construction != "flat_rows"][0]
    result = compile_cir(good)
    twins = {body.name: build_twin(good, result, body.name)}
    assert twins[body.name].geometry is not None and twins[body.name].geometry.rings
    assert body.foundation_kind == "magic_ring", body.foundation_kind
    other = dataclasses.replace(body, foundation_kind="chain")
    bad = dataclasses.replace(good, title="Round Tide Basket", components=[
        other if c.name == body.name else c for c in good.components])
    got = {f.code for f in HD.findings(bad, twins)}
    assert "VESSEL_GEOMETRY_UNKNOWN" in got, got
    # The same body from a magic ring is not UNKNOWN.
    ok = {f.code for f in HD.findings(dataclasses.replace(good, title="Round Tide Basket"),
                                      twins)}
    assert "VESSEL_GEOMETRY_UNKNOWN" not in ok, ok


def test_a_bridging_chain_with_spans_is_not_an_increase():
    """Finding 5: the chain over a cut-out handle replaces the stitches it skips. Counted as an
    increase it consumed positions and hid the base's corner count behind the opening."""
    from brambleloop.cir.compiler import ResolvedOp
    from brambleloop.cir.geometry import _increase_and_parentage

    good = HD.handled_vessel(_concept("Tide Basket With Handles"))
    result = compile_cir(good)
    assert result.ok
    body = [c for c in good.components if c.construction != "flat_rows"][0].name
    rows = [r for r in result.rows if r.component == body]
    opened = [r for r in rows if any(getattr(o, "spans", 0) for o in r.ops)]
    assert opened, "the handled vessel must have a round with a bridging chain"
    for r in opened:
        consumed, produced = _increase_and_parentage(r)
        assert consumed == [], (r.index, consumed)
        assert not any(produced), r.index
    # The corner count of the body does not change because the openings exist.
    without = [r for r in rows if r not in opened]
    assert corners(without) is not None and corners(rows) == corners(without), \
        (corners(rows), corners(without))
    # And directly: a chain with spans>0 is not an increase; the same chain with spans=0 is.
    row = opened[0]
    bridge = ResolvedOp(stitch="ch", count=1, consumes=0, produces=4, spans=4)
    plain_ch = ResolvedOp(stitch="ch", count=1, consumes=0, produces=4, spans=0)
    assert _increase_and_parentage(dataclasses.replace(row, ops=[bridge]))[0] == []
    assert _increase_and_parentage(dataclasses.replace(row, ops=[plain_ch]))[0] != []

def test_the_gates_run_on_the_listing_title_too():
    from brambleloop.gates import certificate as C

    src = Path(C.__file__).read_text()
    assert '_homedecor.findings(cir, twins, "cir.title")' in src
    assert '_homedecor_l.findings(cir, twins, "listing.title", text=listing.title)' in src


# ---- the router -------------------------------------------------------------------------------


def test_every_variant_is_a_verified_family_with_a_proof_in_this_file():
    here = {k for k in globals() if k.startswith("test_")}
    assert set(HD.VARIANTS) == {HD.ROUND_VESSEL, HD.BOWL, HD.LIDDED, HD.HANDLED}
    for v in HD.VARIANTS:
        fam = CF.FAMILIES[v]
        assert fam.status == CF.VERIFIED, v
        assert fam.proof.startswith("tests/test_eng_homedecor.py::"), fam.proof
        assert fam.proof.split("::")[1] in here, fam.proof
        assert CF.PAIR_PROOFS[(v, "basket")] == fam.proof
    # Still held, with a reason: the remaining vessel and decor work of this mission.
    for title in ("Nesting Tide Baskets", "Oval Tide Basket", "Tide Plant Pot Cozy"):
        assert not CF.route(category="basket", title=title, form="basket",
                            construction="in_the_round")["admitted"], title



def test_round_as_a_preposition_is_not_an_outline_claim():
    import re
    r = re.compile(HD._ROUND_RE)
    for text in ("a band carried round the wall", "a stripe worked round its rim",
                 "worked in rounds from a flat base"):
        assert not r.search(text), text
    for text in ("round basket", "chunky round pouf", "circular base", "circle bag"):
        assert r.search(text), text


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]


if __name__ == "__main__":
    failures = 0
    for t in TESTS:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            print("FAIL", t.__name__, repr(exc))
            traceback.print_exc()
    print(f"{failures} failure(s)")
    sys.exit(1 if failures else 0)
