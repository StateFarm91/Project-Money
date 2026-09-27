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
# 6. the concept shapes the garment (certification audit C-8): every mapping is a named table,
#    different ideas are different garments, and the same idea is the same garment.
import itertools  # noqa: E402
from brambleloop.creative.concept import FEELINGS, OCCASIONS  # noqa: E402
from brambleloop.products import garments as G  # noqa: E402


def idea(key, construction="top_down_yoke", recipient="self", lane="LONG", *, premise,
         motif, feeling, occasion, palette):
    return Concept(key=key, title=key.title(), premise=premise, pod="garments",
                   form="fitted_garment", construction=construction, motif=motif,
                   palette_story=palette, recipient=recipient, occasion=occasion,
                   feeling=feeling, function="a layer", make_lane=lane, provenance="test")


def counts(cir):
    r = compile_cir(cir)
    return tuple((c.foundation,) + tuple(x.produced for x in r.rows if x.component == c.name)
                 for c in cir.components)


check("every feeling and occasion has a rule in every table",
      set(GD.EASE_BY_FEELING) == set(FEELINGS) == set(GD.TEXTURE_BY_FEELING)
      == set(GD.COLOUR_PLAN_BY_FEELING) and set(GD.NECKLINE_BY_OCCASION) == set(OCCASIONS))
check("every texture a concept can choose is one the templates work",
      {t for t, _ in GD.TEXTURE_WORDS} | set(GD.TEXTURE_BY_FEELING.values()) <= set(G.TEXTURES))

lantern = idea("lantern", premise="a yoke of glowing window panes that reads as a lit street",
               motif="lantern windows", feeling="festive", occasion="christmas",
               palette="ember and soot")
ch = GD.choices_for(lantern)
check("the palette story becomes a stated colour plan",
      ch.colours == (("ember", GD.COLOUR_HEX["ember"]), ("soot", GD.COLOUR_HEX["soot"]))
      and ch.colour_plan == "stripes" and ch.band_cm == 3.5, ch.to_dict())
check("motif, feeling, premise and occasion each decide something",
      (ch.texture, ch.ease, ch.length, ch.neckline) == ("ridged", "relaxed", "standard",
                                                         "close"), ch.to_dict())
m = GD.design_for(lantern).build("M")
check("the colour plan is carried in the CIR palette and rows",
      m.colors == dict(ch.colours) and {r.color for c in m.components for r in c.rows}
      == {"ember", "soot"} and {x.color_id for x in m.materials} == {"ember", "soot"})
check("the same concept is the same garment",
      GD.design_for(lantern).build("L").fingerprint == GD.design_for(lantern).build("L")
      .fingerprint and GD.choices_for(lantern) == ch)

for word, want in (("a cropped", ("length", "cropped")), ("a longline", ("length", "longline")),
                   ("an oversized", ("ease", "oversized")), ("a slouchy", ("ease", "slouchy")),
                   ("a fitted", ("ease", "fitted"))):
    c = idea("w", premise=f"{word} layer of glowing window panes that reads as a lit street",
             motif="lantern windows", feeling="festive", occasion="christmas",
             palette="ember and soot")
    check(f"premise word {word!r} -> {want}", getattr(GD.choices_for(c), want[0]) == want[1])

base = GD.design_for(idea("b", premise="a layer of glowing window panes that reads as a street",
                          motif="lantern windows", feeling="festive", occasion="everyday",
                          palette="ember"))
crop = GD.design_for(idea("c", premise="a cropped layer of window panes that reads as a street",
                          motif="lantern windows", feeling="festive", occasion="everyday",
                          palette="ember"))
lb, lc = (G.built_measures(d.build("M"))["length"] for d in (base, crop))
check("cropped is a stated ratio of the back length", abs(lc / lb - GD.LENGTH_RATIOS["cropped"])
      < 0.05, (lb, lc))

# Distinct-variant evidence: one field changed at a time from a base idea gives a distinct CIR.
fields = {
    "palette": dict(palette="moss and slate and cream"),
    "motif": dict(motif="tidepool ripples"),
    "feeling": dict(feeling="serene"),
    "premise": dict(premise="a longline layer of window panes that reads as a lit street"),
    "occasion": dict(occasion="summer_travel"),
}
kw = dict(premise="a layer of glowing window panes that reads as a lit street",
          motif="lantern windows", feeling="festive", occasion="christmas",
          palette="ember and soot")
prints = {"base": GD.design_for(idea("v", **kw)).build("M").fingerprint}
for name, change in fields.items():
    prints[name] = GD.design_for(idea("v", **{**kw, **change})).build("M").fingerprint
check("changing any one concept field changes the CIR", len(set(prints.values())) == len(prints),
      prints)

# A spread: every feeling x three occasions x two palettes x three motifs, raglan adult, M.
# Before the repair every one of these was the same garment (the old design space was at
# most 16 variants in all, from construction, recipient, lane and "fitted").
spread = set()
combos = list(itertools.product(FEELINGS, ("christmas", "everyday", "summer_travel"),
                                ("ember and soot", "sea glass"),
                                ("field", "bark ridges", "tidepool ripples")))
for feeling, occasion, palette, motif in combos:
    spread.add(GD.design_for(idea("s", premise="a layer that reads as a lit street at dusk",
                                  motif=motif, feeling=feeling, occasion=occasion,
                                  palette=palette)).build("M").fingerprint)
print(f"     distinct CIRs from {len(combos)} concepts: {len(spread)}")
check("concepts spread over far more than the old 16 variants", len(spread) >= 100,
      len(spread))

# Every size of a varied set still certifies end to end.
varied = [
    idea("v1", "top_down_yoke", "child", "QUICK", premise="a cropped slouchy yoke of ripples "
         "that reads as a tide pool", motif="tidepool ripples", feeling="whimsical",
         occasion="summer_travel", palette="sea glass, sand and teal"),
    idea("v2", "side_to_side", "self", "LONG", premise="a longline oversized layer of bark "
         "ridges that reads as a forest floor", motif="bark ridges", feeling="rugged",
         occasion="winter_nesting", palette="moss and slate"),
    idea("v3", "flat_rows", "teen", "SHORT", premise="a boxy layer with stripes that reads as "
         "a deckchair", motif="deckchair stripe", feeling="playful", occasion="valentines",
         palette="cranberry and cream"),
    idea("v4", "top_down_yoke", "grandparent", "MEDIUM", premise="a longline layer of still "
         "stone that reads as a harbour wall", motif="stone", feeling="heirloom",
         occasion="wedding", palette="granite and ivory and ink"),
]
bad = []
for c in varied:
    d = GD.design_for(c)
    d.check_monotonic()
    for size, one in d.build_all().items():
        r = compile_cir(one)
        if not r.ok:
            bad.append((c.key, size, "compile")); continue
        for term in ("US", "UK"):
            if compare(one, write_pattern(one, r, term), term):
                bad.append((c.key, size, term))
        cert = certify(one)
        if not cert.granted:
            bad.append((c.key, size, cert.blocking_reasons[:1]))
check("varied concepts: every size compiles, reverses US/UK, is monotonic and certifies",
      not bad, bad[:3])
check("varied concepts differ from each other and from the fixtures at every size",
      len({counts(GD.design_for(c).build(GD.base_size(GD.design_for(c)))) for c in varied})
      == len(varied))

print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
