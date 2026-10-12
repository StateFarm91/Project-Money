"""Adversarial certification of grading: every sourced size of every garment design.

Designs under test: products/garments.DESIGNS (Harbour, Pebble) plus a matrix of
garment_design outputs -- {raglan, drop-shoulder} x {adult, child} x {QUICK, LONG} x
{relaxed, fitted}. For each size, measured from the CIR and the digital twin rather than
from the design's own size table: chest strictly rises, other finished measures never fall,
every count is a positive integer, shaping lands exactly, holds resume exactly once, the
sleeve top matches the armhole it is sewn to, body length exceeds armhole depth, and the twin
lands within TWIN_TOLERANCE of the intended finished measurement. Then the CYC provenance and
the UNSOURCED refusal.

Failing checks are findings. Do not weaken them to get green.
"""
from __future__ import annotations

import os
import re
import sys
import traceback
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir import assembly  # noqa: E402
from brambleloop.cir import graded as GR  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.grading import GradingRefused  # noqa: E402
from brambleloop.cir.model import Op, Repeat  # noqa: E402
from brambleloop.cir.twin import build_twin, row_width_cm  # noqa: E402
from brambleloop.creative import garment_design as GD  # noqa: E402
from brambleloop.creative.concept import Concept  # noqa: E402
from brambleloop.products import garments as G  # noqa: E402

# Relative error allowed between the twin's measurement and the intended finished measure.
# Rounding to whole stitches/rows and to an even count moves a width by at most ~2 stitches;
# 5% is generous for every piece here (a 2-stitch move on the smallest dc piece is ~4%).
TWIN_TOLERANCE = 0.05
# An open-front raglan's whole neck edge (fronts + sleeve tops + back neck) over the chest.
# Worked examples in this repo's own sc designs sit at 0.36-0.44.
MAX_NECK_OVER_CHEST = 0.55


def _concept(key, construction, recipient, lane, fitted=False):
    premise = ("a fitted yoke that sits close through the shoulders" if fitted else
               "a boxy layer with a wide neck that reads as weathered stone")
    return Concept(key=key, title=key.replace("-", " ").title(), premise=premise,
                   pod="garments", form="fitted_garment", construction=construction,
                   motif="stone", palette_story="granite", recipient=recipient,
                   occasion="everyday", feeling="rugged", function="a daily layer",
                   make_lane=lane, provenance="cert-test")


@lru_cache(maxsize=1)
def designs() -> dict:
    out = {k: make() for k, make in G.DESIGNS.items()}
    for cons, cname in (("top_down_yoke", "raglan"), ("side_to_side", "drop")):
        for rec in ("self", "child"):
            for lane in ("QUICK", "LONG"):
                for fitted in (False, True):
                    key = f"m-{cname}-{rec}-{lane.lower()}{'-fitted' if fitted else ''}"
                    out[key] = GD.design_for(_concept(key, cons, rec, lane, fitted))
    return out


@lru_cache(maxsize=1)
def built() -> dict:
    """{design_key: [(size, GradedSize, cir, result, twins)]} for every sourced size."""
    out = {}
    for key, d in designs().items():
        rows = []
        for size in d.sourced_sizes():
            cir = d.build(size)
            r = compile_cir(cir)
            assert r.ok, (key, size, [str(e) for e in r.errors][:2])
            twins = {c.name: build_twin(cir, r, component=c.name) for c in cir.components}
            rows.append((size, d.graded_size(size), cir, r, twins))
        out[key] = rows
    return out


def _is_raglan(cir) -> bool:
    return cir.components[0].name == "yoke_and_body"


def measures(g, cir, r, twins) -> dict:
    """What the made object measures, in cm, from the CIR and the twin."""
    gauge = cir.gauge
    if _is_raglan(cir):
        yoke = cir.components[0]
        first_body = next(row for row in yoke.rows if row.skips)
        body_rows = [x for x in r.rows if x.component == yoke.name and x.index >= first_body.index]
        chest = row_width_cm(body_rows[0], gauge)[0]
        t = twins[yoke.name]
        armhole = t.row_top_cm[first_body.index - 1] if t.row_top_cm else \
            (first_body.index - 1) / gauge.rows_per_10cm * 10
        length = t.height_cm
        sleeve = twins["sleeve_left"]
        upper = max(row_width_cm(x, gauge)[0] for x in r.rows if x.component == "sleeve_left")
        sleeve_cmp = cir.components[1]
        final_yoke = next(row for row in yoke.rows if row.index == first_body.index - 1)
        k = (final_yoke.declared_count - yoke.foundation) // 8
        back = first_body.declared_count // 2
        return {"chest": chest, "length": length, "armhole": armhole, "upper_arm": upper,
                "sleeve_len": sleeve.height_cm, "neck_edge": yoke.foundation / gauge.stitches_per_10cm * 10,
                "back_neck": (back - 2 * k) / gauge.stitches_per_10cm * 10,
                "sleeve_top_sts": sleeve_cmp.rows[0].declared_count}
    body = twins["body"]
    sleeve = twins["sleeve"]
    return {"chest": 2 * body.width_cm, "length": body.height_cm / 2.0,
            "upper_arm": sleeve.width_cm, "sleeve_len": sleeve.height_cm,
            "armhole": sleeve.width_cm / 2.0}


# ---- counts and sizes ---------------------------------------------------------------------

def test_size_counts_and_boundaries():
    counts = {k: len(v) for k, v in built().items()}
    _vac_120 = 0
    for key, d in designs().items():
        _vac_120 += 1
        expected = GR.WOMAN.names if d.table is GR.WOMAN else GR.CHILD.names
        assert tuple(s for s, *_ in built()[key]) == expected, (key, counts[key])
    assert _vac_120, "designs().items() was empty: the loop proved nothing (F-123)"
    assert sum(counts.values()) == 9 * 9 + 9 * 8, counts
    print(f"     designs={len(counts)} sized CIRs={sum(counts.values())}")


def test_finished_chest_strictly_increases_measured_from_the_cir():
    bad = []
    for key, rows in built().items():
        m = [(s, measures(g, c, r, t)) for s, g, c, r, t in rows]
        for (s0, a), (s1, b) in zip(m, m[1:]):
            if not b["chest"] > a["chest"]:
                bad.append((key, s0, s1, "chest", a["chest"], b["chest"]))
            for field in ("length", "armhole", "upper_arm"):
                if b[field] + 1e-9 < a[field]:
                    bad.append((key, s0, s1, field, a[field], b[field]))
        designs()[key].check_monotonic()
    assert not bad, bad[:6]


def test_every_count_is_a_positive_integer():
    bad = []

    def walk(nodes, where):
        for n in nodes:
            if isinstance(n, Repeat):
                walk(n.ops, where)
            elif isinstance(n, Op):
                if not isinstance(n.count, int) or n.count <= 0:
                    bad.append((where, n.stitch, n.count))
    for key, rows in built().items():
        for size, g, cir, r, t in rows:
            for comp in cir.components:
                if not isinstance(comp.foundation, int) or comp.foundation < 0 or \
                        (comp.foundation == 0 and not comp.resumes):
                    bad.append((key, size, comp.name, "foundation", comp.foundation))
                for row in comp.rows:
                    if not isinstance(row.declared_count, int) or row.declared_count <= 0:
                        bad.append((key, size, comp.name, row.index, row.declared_count))
                    walk(row.ops, (key, size, comp.name, row.index))
            for x in r.rows:
                if x.produced <= 0 or x.remainder != 0:
                    bad.append((key, size, x.component, x.index, x.produced, x.remainder))
    assert not bad, bad[:6]


def test_shaping_lands_exactly_and_holds_resume_once():
    bad = []
    for key, rows in built().items():
        for size, g, cir, r, t in rows:
            produced = {}
            for x in r.rows:
                produced.setdefault(x.component, []).append(x.produced)
            if _is_raglan(cir):
                yoke = cir.components[0]
                back = _even = None
                back = GR.GradedSize.stitches(g, g.finished_cm("bust") / 2.0)
                back += back % 2
                sleeve_top = GR.GradedSize.stitches(g, g.finished_cm("upper_arm"))
                sleeve_top += sleeve_top % 2
                first_body = next(row for row in yoke.rows if row.skips)
                last_yoke = produced[yoke.name][first_body.index - 2]
                if last_yoke != 2 * back + 2 * sleeve_top:
                    bad.append((key, size, "yoke total", last_yoke, 2 * back + 2 * sleeve_top))
                if produced[yoke.name][first_body.index - 1] != 2 * back:
                    bad.append((key, size, "body after division"))
                holds = [h for c in cir.components for h in c.holds]
                for h in holds:
                    resumers = [c for c in cir.components if c.resumes == h.name]
                    if len(resumers) != 1:
                        bad.append((key, size, h.name, "resumed", len(resumers)))
                        continue
                    if h.count != sleeve_top:
                        bad.append((key, size, h.name, "held", h.count, sleeve_top))
                    rr = [x for x in r.rows if x.component == resumers[0].name][0]
                    if rr.consumed != h.count:
                        bad.append((key, size, h.name, "picked up", rr.consumed, h.count))
                    cuff = min(sleeve_top, GR.GradedSize.stitches(
                        g, g.finished_cm("upper_arm") * G.CUFF_OF_UPPER_ARM) + 0)
                    cuff += cuff % 2
                    cuff = min(cuff, sleeve_top)
                    if produced[resumers[0].name][-1] != cuff:
                        bad.append((key, size, h.name, "cuff", produced[resumers[0].name][-1], cuff))
            else:
                sleeve = next(c for c in cir.components if c.name == "sleeve")
                top_cm = max(g.finished_cm("upper_arm"), 2 * g.finished_cm("armhole_depth"))
                top = GR.GradedSize.stitches(g, top_cm)
                top += top % 2
                if produced["sleeve"][-1] != top:
                    bad.append((key, size, "sleeve top", produced["sleeve"][-1], top))
                if sleeve.foundation >= top:
                    bad.append((key, size, "cuff not narrower than top"))
            if any(n <= 0 for v in produced.values() for n in v):
                bad.append((key, size, "non-positive count"))
    assert not bad, bad[:6]


def test_sleeve_top_matches_the_armhole_it_is_sewn_to():
    worst = 0.0
    bad = []
    for key, rows in built().items():
        for size, g, cir, r, twins in rows:
            geo = assembly.assemble(cir, twins)
            if geo.verdict != "assembles":
                bad.append((key, size, geo.verdict, geo.why))
            for j in geo.joins:
                if j.length_a_cm and j.length_b_cm:
                    d = abs(j.length_a_cm - j.length_b_cm) / max(j.length_a_cm, j.length_b_cm)
                    worst = max(worst, d)
                    if d > assembly.EDGE_TOLERANCE:
                        bad.append((key, size, j.piece_a, j.piece_b, round(d, 3)))
            if not _is_raglan(cir):
                seam = next(s for s in cir.assembly if s.piece_a == "sleeve" and s.piece_b == "body")
                sleeve_top = twins["sleeve"].width_cm
                armhole = seam.spans_rounds * (twins["body"].height_cm / len(cir.components[0].rows))
                d = abs(sleeve_top - armhole) / max(sleeve_top, armhole)
                worst = max(worst, d)
                if d > assembly.EDGE_TOLERANCE:
                    bad.append((key, size, "sleeve top vs armhole", sleeve_top, armhole))
    print(f"     worst join mismatch {worst:.2%} (tolerance {assembly.EDGE_TOLERANCE:.0%})")
    assert not bad, bad[:6]


def test_body_length_exceeds_armhole_depth():
    bad = [(k, s, m["length"], m["armhole"]) for k, rows in built().items()
           for s, g, c, r, t in rows for m in [measures(g, c, r, t)]
           if not m["length"] > m["armhole"]]
    assert not bad, bad[:6]


def test_twin_lands_within_tolerance_of_the_intended_finished_size():
    report, bad = {}, []
    for key, rows in built().items():
        worst = (0.0, "")
        for size, g, cir, r, twins in rows:
            m = measures(g, cir, r, twins)
            intended = {"chest": g.finished_cm("bust")}
            if _is_raglan(cir):
                intended["length"] = g.finished_cm("back_length")
                intended["armhole"] = g.finished_cm("armhole_depth")
                intended["upper_arm"] = g.finished_cm("upper_arm")
            else:
                intended["length"] = g.finished_cm("back_length")
                intended["upper_arm"] = max(g.finished_cm("upper_arm"),
                                            2 * g.finished_cm("armhole_depth"))
            for field, want in intended.items():
                err = abs(m[field] - want) / want
                if err > worst[0]:
                    worst = (err, f"{size} {field} {m[field]:.1f} vs {want:.1f}")
                if err > TWIN_TOLERANCE:
                    bad.append((key, size, field, round(m[field], 1), want, f"{err:.1%}"))
        report[key] = worst
    for key, (err, where) in report.items():
        print(f"     {key:34s} max rel err {err:6.2%}  ({where})")
    assert not bad, bad[:6]


def test_raglan_neck_edge_fits_the_body():
    """DESIGN PROBE. A top-down raglan whose neck edge is most of its chest, or whose back
    neck is wider than the wearer's shoulders, compiles and certifies and cannot be worn."""
    bad, seen = [], []
    for key, rows in built().items():
        for size, g, cir, r, t in rows:
            if not _is_raglan(cir):
                continue
            m = measures(g, cir, r, t)
            ratio = m["neck_edge"] / m["chest"]
            seen.append((ratio, key, size))
            if ratio > MAX_NECK_OVER_CHEST or m["back_neck"] > g.body_cm("cross_back"):
                bad.append((key, size, f"neck {m['neck_edge']:.0f}cm/chest {m['chest']:.0f}cm"
                            f"={ratio:.2f}", f"back neck {m['back_neck']:.0f} vs cross back "
                            f"{g.body_cm('cross_back'):g}"))
    print(f"     raglan neck/chest range {min(seen)[0]:.2f}-{max(seen)[0]:.2f} "
          f"(worst {max(seen)[1]} {max(seen)[2]})")
    keys = sorted({b[0] for b in bad})
    assert not bad, f"{len(bad)} sizes in {keys}; e.g. {bad[:3]}"


# ---- CYC sources and UNSOURCED refusal ----------------------------------------------------

def test_cyc_sources_are_recorded():
    for table, url in ((GR.WOMAN, GR.CYC_WOMAN_URL), (GR.CHILD, GR.CYC_CHILD_URL)):
        assert table.source_url == url and url.startswith("https://www.craftyarncouncil.com/")
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", table.retrieved), table.retrieved
        for body in table.sizes:
            assert body.cm("wrist") is None and body.cm("neck") is None, body.size
            for m in G.RAGLAN_REQUIRES:
                assert body.cm(m) and body.cm(m) > 0, (table.name, body.size, m)
    _vac_309 = 0
    for key, d in designs().items():
        _vac_309 += 1
        text = GR.write_size_table(d)
        assert d.table.source_url in text and d.table.retrieved in text, key
        assert GR.parse_size_table(text) == d.size_table(), key
    assert _vac_309, "designs().items() was empty: the loop proved nothing (F-123)"


def test_unsourced_measurement_refuses_grading():
    for table, extra, size in ((GR.WOMAN, "wrist", "M"), (GR.CHILD, "neck", "8"),
                               (GR.WOMAN, "neck", "XS"), (GR.CHILD, "wrist", "16")):
        d = GR.GradedDesign(
            key=f"needs-{extra}", title="Needs", table=table, gauge=GD.SC_WORSTED[0],
            fit=GR.FitIntent({"bust": 10}), requires=("bust", extra),
            template=lambda g: (_ for _ in ()).throw(AssertionError("template ran")))
        assert d.sourced_sizes() == (), d.sourced_sizes()
        assert d.build_all() == {}
        try:
            d.build(size)
            raise AssertionError(f"{extra} graded")
        except GradingRefused as exc:
            assert extra in str(exc) and "UNSOURCED" in str(exc) and table.source_url in str(exc)
        try:
            GD.base_size(d)
            raise AssertionError("base size chosen")
        except GD.GarmentDesignRefused:
            pass
    # A template that reads an unsourced measurement it did not declare still refuses.
    d = GR.GradedDesign(key="sneaky", title="S", table=GR.WOMAN, gauge=GD.SC_WORSTED[0],
                        fit=GR.FitIntent({}), requires=("bust",),
                        template=lambda g: g.body_cm("wrist"))
    try:
        d.build("M")
        raise AssertionError("undeclared unsourced read")
    except GradingRefused as exc:
        assert "wrist" in str(exc)
    for bad_ease in ({"wrist_girth": 1}, {"bust": -2}):
        try:
            GR.FitIntent(bad_ease)
            raise AssertionError(bad_ease)
        except GradingRefused:
            pass


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}  -- {type(exc).__name__}: {str(exc)[:700]}")
            if os.environ.get("CERT_TRACE"):
                traceback.print_exc()
    print(f"\n  {len(tests) - failed} passing, {failed} failing")
    sys.exit(1 if failed else 0)
