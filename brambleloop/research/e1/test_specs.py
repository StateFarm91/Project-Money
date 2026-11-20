"""Both specs against E1's own evidence. The point of the last two checks: the best image E1
produced must NOT pass Milestone D today, and the gate must say UNKNOWN for it, not PASS."""
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import milestone_d_spec as D
import presentation_gate_spec as P

OUT = Path(__file__).parent / "out"
truth = json.load(open(OUT / "basket_large_structure.json"))
wine = [r for n, rs in truth["colour_bands_by_round"] if n == "wine" for r in rs]
H = truth["height_cm"]; rings = truth["rings"]
structure = {
    "slug": truth["slug"], "stitch_family": truth["stitch_family"],
    "silhouette_ratio_diameter_over_height": truth["silhouette_ratio_diameter_over_height"],
    "colour_boundaries_frac": [round(rings[r - 1][1] / H, 3) for r in wine],
    "construction_cues": ["flat_disc_base", "straight_wall", "open_top"],
    "openings": [],
    "stitches_top_round": 144,
}
ref_digest = hashlib.sha256((OUT / "basket_large_structural.png").read_bytes()).hexdigest()[:16]
n = 0
def check(name, cond, detail=""):
    global n; n += 1
    print(("OK  " if cond else "FAIL"), name, detail if not cond else "")
    assert cond, name

# --- Milestone D ---------------------------------------------------------------
d = D.assess(structure, None, twin_calibrated=False)
check("no image assessed -> final_image_product_truth UNKNOWN, overall UNKNOWN",
      d.verdict == D.UNKNOWN and [p for p in d.properties if p.name == "final_image_product_truth"][0].verdict == D.UNKNOWN)
check("conditioning_reference_complete PASSES on E1's structure",
      [p for p in d.properties if p.name == "conditioning_reference_complete"][0].verdict == D.PASS)
check("a basket's openings are NOT_APPLICABLE, not silently PASS",
      [p for p in d.properties if p.name == "shaping_openings"][0].verdict == D.NOT_APPLICABLE)

# E1's best output, C1, as a judge would have measured it (pixel-measured where it was):
c1 = {"silhouette_ratio": 1.10, "stitch_family": "sc",
      "colour_boundaries_frac": [0.37, 0.39, 0.70, 0.72],
      "construction_cues_seen": ["flat_disc_base", "straight_wall", "open_top"]}
d = D.assess(structure, c1, twin_calibrated=False)
by = {p.name: p.verdict for p in d.properties}
check("C1: silhouette PASS within 2%", by["silhouette_proportion"] == D.PASS)
check("C1: stitch family PASS", by["stitch_family"] == D.PASS)
check("C1: colour regions FAIL -- lower stripe 0.38 measured vs 0.44 expected is outside 3%",
      by["colour_regions"] == D.FAIL)
check("C1: gauge_scale_confidence UNKNOWN because twin.calibrated is False",
      by["gauge_scale_confidence"] == D.UNKNOWN)
check("C1 overall is FAIL (a measured miss), not UNKNOWN and not PASS", d.verdict == D.FAIL)

# The same image with the colour boundaries inside tolerance -- what a better measurement
# or a better sample would look like -- is STILL not a PASS while uncalibrated.
c1_ok = {**c1, "colour_boundaries_frac": [0.43, 0.45, 0.70, 0.72]}
d = D.assess(structure, c1_ok, twin_calibrated=False)
check("even with every image-side property passing, uncalibrated twin -> overall UNKNOWN",
      d.verdict == D.UNKNOWN and {p.name: p.verdict for p in d.properties}["final_image_product_truth"] == D.PASS)
d = D.assess(structure, {**c1_ok, "stitches_counted_top_round": 140}, twin_calibrated=True)
check("calibrated twin + counted stitches within 10% -> overall PASS is reachable", d.verdict == D.PASS)
d = D.assess(structure, {**c1_ok, "stitch_family": "hdc"}, twin_calibrated=True)
check("hdc where sc was certified is a FAIL, not a near miss", d.verdict == D.FAIL)

# --- Presentation gate -----------------------------------------------------------
gen = lambda cond: P.Operation("generate", touches_product=True, conditioned_on=cond)
check("generative over product, no certified reference -> UNAUTHORISED_REDESIGN",
      P.PresentationPlan([gen(None)]).verdict()["category"] == P.UNAUTHORISED_REDESIGN)
check("conditioned but never revalidated -> UNAUTHORISED_REDESIGN (conditioning is a claim)",
      P.PresentationPlan([gen(ref_digest)], certified_reference=ref_digest).verdict()["verdict"] == P.FAIL)
check("conditioned + revalidation PASS -> AUTHORISED_PRESENTATION",
      P.PresentationPlan([gen(ref_digest)], certified_reference=ref_digest, revalidation_verdict=P.PASS).verdict()["category"] == P.AUTHORISED_PRESENTATION)
v = P.PresentationPlan([gen(ref_digest)], certified_reference=ref_digest, revalidation_verdict=P.UNKNOWN).verdict()
check("conditioned + revalidation UNKNOWN -> UNKNOWN, which blocks and is not PASS", v["verdict"] == P.UNKNOWN)
check("conditioned on the WRONG reference digest -> UNAUTHORISED_REDESIGN",
      P.PresentationPlan([gen("deadbeef")], certified_reference=ref_digest, revalidation_verdict=P.PASS).verdict()["category"] == P.UNAUTHORISED_REDESIGN)
check("structure-preserving ops need neither reference nor revalidation",
      P.PresentationPlan([P.Operation("relight", True)]).verdict()["category"] == P.STRUCTURE_PRESERVED)
print(f"\n{n} passing, 0 failing")
