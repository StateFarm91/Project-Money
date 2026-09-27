"""An original garment concept is designed end to end by rules, graded from sourced body data,
and taken through the release chain -- no person calling a template, no purchased pattern."""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.reverse import compare  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.gates.certificate import certify  # noqa: E402
from brambleloop.creative import garment_design as GD, prototype  # noqa: E402
from brambleloop.creative.concept import Concept  # noqa: E402

PASSED = FAILED = 0


def check(name, ok, detail=""):
    global PASSED, FAILED
    PASSED += bool(ok); FAILED += (not ok)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))


def concept(key="tide-raglan", construction="top_down_yoke", recipient="child",
            lane="MEDIUM", premise="a slouchy striped yoke that reads as seaside at a glance"):
    return Concept(key=key, title="Tide Raglan", premise=premise, pod="garments",
                   form="fitted_garment", construction=construction, motif="tide stripes",
                   palette_story="sea glass and sand", recipient=recipient,
                   occasion="everyday", feeling="playful",
                   function="a layer a child can pull on alone", make_lane=lane,
                   provenance="test")


# 1. the prototype stage authors a garment concept instead of refusing it
cir = prototype.author(concept())
res = compile_cir(cir)
check("a garment concept is authored by the prototype stage and compiles", res.ok,
      [str(e) for e in res.errors][:3])
check("it is Brambleloop's own, with provenance naming the concept and no benchmark",
      cir.authored == "brambleloop" and cir.provenance is not None
      and cir.provenance.concept_key == "tide-raglan" and not cir.provenance.benchmarks_consulted)

# 2. every sourced size, both constructions, both body tables, both fabrics
for c in (concept(), concept(key="dune-pullover", construction="flat_rows", recipient="self",
                             lane="QUICK", premise="a boxy pullover with a wide slash neck")):
    design = GD.design_for(c)
    built = design.build_all()
    bad = []
    for size, one in built.items():
        r = compile_cir(one)
        if not r.ok:
            bad.append((size, "compile", [str(e) for e in r.errors][:1])); continue
        for term in ("US", "UK"):
            diffs = compare(one, write_pattern(one, r, term), term)
            if diffs:
                bad.append((size, term, [str(d) for d in diffs][:1]))
        cert = certify(one)
        if not cert.granted:
            bad.append((size, "certify", cert.blocking_reasons[:2]))
    check(f"{c.key}: every sourced size compiles, reverse-compiles (US+UK) and certifies "
          f"({len(built)} sizes)", built and not bad, bad[:2])

# 3. refusals are named, never guessed
for c, word in ((concept(recipient="new_parent"), "babywear"),
                (concept(construction="granny_square"), "engine gap")):
    try:
        GD.design_for(c)
        check(f"{c.recipient}/{c.construction} is refused", False, "not refused")
    except GD.GarmentDesignRefused as exc:
        check(f"{c.recipient}/{c.construction} is refused with its reason", word in str(exc), str(exc))
fitted = GD.design_for(concept(premise="a fitted cropped yoke for layering"))
check("a premise that asks for a fitted garment gets close ease (class C: a fit test is owed)",
      fitted.fit.ease_cm["bust"] < GD.RELAXED_EASE_CHILD["bust"])

# 4. the whole release chain, run rather than named
from brambleloop.creative import certification as C  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402

db = Database(f"sqlite:///{tempfile.mkdtemp()}/g.sqlite"); db.create_all()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_certification as TC  # noqa: E402

out = C.release(TC._priced(db), [concept()])
check("an autonomously designed garment survives the whole release chain",
      [c.key for c in out["survivors"]] == ["tide-raglan"] and not out["killed"],
      str(out.get("detail"))[:400])

# 5. regression: asset truth reads every piece, so a sleeve's decreases are the pattern's
from brambleloop.gates import asset_truth as AT  # noqa: E402
design = GD.design_for(concept())
multi = design.build(GD.base_size(design))
worked = AT._stitches_worked(multi)
first_piece = {op.stitch for row in multi.components[0].rows
               for op in AT_ops(row.ops)} if (AT_ops := (lambda ops: [o for o in ops
                                                  if getattr(o, "stitch", None)])) else set()
check("asset truth counts stitches worked in every piece, not only the first",
      worked >= first_piece and len(multi.components) > 1 and "dec" in worked, sorted(worked))
print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
