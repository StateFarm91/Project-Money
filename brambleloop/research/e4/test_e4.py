"""E4 regression tests: the projected-stitch instrument on the committed manifests, and the
adversarial cases it must catch. Offline: no generator, no judge. Run: python research/e4/test_e4.py"""
import json, os, sys, tempfile
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
sys.path.insert(0, HERE)
import project as P
import validate_e4 as V
D = os.path.join(os.path.dirname(HERE), "d", "out")

PASSED = FAILED = 0
def check(name, ok, detail=""):
    global PASSED, FAILED
    PASSED += bool(ok); FAILED += (not ok)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))

VIEWS = [(k, v) for k in ("sc", "hdc") for v in ("camera", "oblique")]
gen_man = json.load(open(os.path.join(OUT, "e4_manifest.json")))

for kind, view in VIEWS:
    man = json.load(open(os.path.join(OUT, f"{kind}_{view}_manifest.json")))
    sv = man["self_validation"]
    check(f"{kind} {view}: the instrument validated itself on the reference", sv["valid"] is True, str({k: sv[k] for k in ('projected_points_in_silhouette', 'worst')}))
    check(f"{kind} {view}: self-validation held at the stated bars, not below them",
          sv["projected_points_in_silhouette"] >= man["criteria"]["in_silhouette"]["value"] and sv["worst"] >= man["criteria"]["self_validation_iou"]["value"])
    ids = [s["id"] for s in man["stitches"]]
    check(f"{kind} {view}: every certified stitch is in the manifest exactly once", len(ids) == 25 and len(set(ids)) == 25, str(len(ids)))
    need = ("id", "family", "row", "position", "points_px", "centroid_px", "bbox_px", "orientation_up_px", "colour_region", "visible_fraction", "testable", "neighbours")
    check(f"{kind} {view}: each stitch carries id, family, row, image location, points, orientation, colour region, visibility and neighbours",
          all(all(k in s for k in need) for s in man["stitches"]))
    check(f"{kind} {view}: neighbours name stitches that exist",
          all((s["neighbours"][k] is None or s["neighbours"][k] in ids) for s in man["stitches"] for k in ("anchor_below", "row_ahead", "row_behind")))
    check(f"{kind} {view}: every stitch names the family the CIR ordered", all(s["family"] == kind for s in man["stitches"]))
    rec = json.load(open(os.path.join(D, f"milestone_d_{kind}_final.json")))
    check(f"{kind} {view}: the manifest is on the frozen certified geometry", man["geometry_sha256"] == rec["geometry_sha256"]["draped"])
    run = next(r for r in gen_man["runs"] if r["kind"] == kind and r["view"] == view)
    check(f"{kind} {view}: the generator was conditioned on the same frozen geometry and the self-validated reference",
          run["geometry_sha256"] == man["geometry_sha256"] and run["conditioning_sha256"][0] == sv["reference_rgb_sha256"])
    testable = [s for s in man["stitches"] if s["testable"]]
    check(f"{kind} {view}: a stitch is testable only when at least half its points are visible",
          all((s["visible_fraction"] >= 0.5) == s["testable"] for s in man["stitches"]))
    # the reference, read as if it were the photograph, passes every testable stitch
    ref = os.path.join(D, f"{kind}_draped_presentation3_{view}.png")
    loc = V.local(kind, view, ref)
    check(f"{kind} {view}: the reference itself passes every testable stitch ({loc['tested']} tested)", loc["status"] == "PASS" and loc["tested"] == len(testable), str(loc["failed_stitches"]))
    check(f"{kind} {view}: untestable stitches are reported UNKNOWN, never PASS",
          all(loc["per_stitch"][s["id"]]["status"] == "UNKNOWN" for s in man["stitches"] if not s["testable"]))

# adversarial: erase one visible stitch from the sc camera reference -> that stitch, and only stitches whose regions overlap it, fail
kind, view = "sc", "camera"
man = json.load(open(os.path.join(OUT, f"{kind}_{view}_manifest.json")))
ref = os.path.join(D, f"{kind}_draped_presentation3_{view}.png")
img = np.array(Image.open(ref).convert("RGB")); bg = img[5:40, 5:40].reshape(-1, 3).mean(axis=0)
target = next(s for s in man["stitches"] if s["id"] == "r3p2")
x0, y0, x1, y1 = target["bbox_px"]
bad = img.copy(); bad[y0:y1, x0:x1] = bg
# the same adversarial cases under both aligners: E4's (refine=False) and E5's silhouette-refined one
for REFINE in (False, True):
  tagr = "E5 refined aligner" if REFINE else "E4 aligner"
  def L(pth): return V.local(kind, view, pth, refine=REFINE)
  def G(pth): return V.global_props(kind, view, pth, refine=REFINE)
  with tempfile.TemporaryDirectory(prefix="brambleloop-e4-") as td:
    p = os.path.join(td, "erased.png"); Image.fromarray(bad.astype(np.uint8)).save(p)
    loc = L(p)
    def overlaps(s):
        a = s["bbox_px"]; return not (a[2] <= x0 or a[0] >= x1 or a[3] <= y0 or a[1] >= y1)
    allowed = {s["id"] for s in man["stitches"] if overlaps(s)}
    check(f"[{tagr}] erasing one stitch from the reference is caught, and the manifest names it", loc["status"] == "FAIL" and "r3p2" in loc["failed_stitches"], str(loc["failed_stitches"]))
    check(f"[{tagr}] the failures are confined to stitches whose regions overlap the erased one", set(loc["failed_stitches"]) <= allowed, str(set(loc["failed_stitches"]) - allowed))
    check(f"[{tagr}] stitches away from the erasure still pass", all(loc["per_stitch"][s["id"]]["status"] == "PASS" for s in man["stitches"] if s["testable"] and s["id"] not in allowed))
    # a photograph of nothing (background only) never passes
    p2 = os.path.join(td, "blank.png"); Image.fromarray(np.full_like(img, bg.astype(np.uint8))).save(p2)
    loc2 = L(p2)
    check(f"[{tagr}] a blank photograph does not pass the stitch test", loc2["status"] != "PASS", str(loc2["status"]))
    # the same fabric moved and scaled in frame still passes: the alignment is scale and shift, never shape
    moved = np.full_like(img, bg.astype(np.uint8)); small = np.array(Image.fromarray(img).resize((800, 800), Image.LANCZOS)); moved[150:950, 100:900] = small
    p3 = os.path.join(td, "moved.png"); Image.fromarray(moved).save(p3)
    loc3 = L(p3)
    check(f"[{tagr}] the reference re-framed (scaled 0.8, shifted) still passes every testable stitch", loc3["status"] == "PASS", str(loc3["failed_stitches"]))
    # mirrored fabric is not the certified fabric
    p4 = os.path.join(td, "mirrored.png"); Image.fromarray(img[:, ::-1]).save(p4)
    loc4 = L(p4)
    # A LIMITATION, RECORDED AS A TEST: the presence test cannot tell a mirror image of this
    # near-symmetric swatch from the swatch. Handedness is a separate global property.
    check(f"[{tagr}] known limit: the mirrored reference passes the presence test (so handedness must be tested elsewhere)", loc4["status"] == "PASS", str(loc4["status"]))
    g4 = G(p4)
    check(f"[{tagr}] the mirrored reference FAILS the handedness property", g4["items"]["handedness"]["status"] == "FAIL", str(g4["items"]["handedness"]))
    g0 = G(ref)
    check(f"[{tagr}] the reference itself PASSES the handedness property", g0["items"]["handedness"]["status"] == "PASS", str(g0["items"]["handedness"]))
    g2 = G(p2)
    check(f"[{tagr}] a blank photograph is UNKNOWN or FAIL on handedness, never PASS", g2["items"]["handedness"]["status"] != "PASS", str(g2["items"]["handedness"]))
    check(f"[{tagr}] a blank photograph fails the global structural properties", g2["status"] == "FAIL", str(g2["status"]))

# projection: the analytic camera puts the certified stitch centroids where the manifest says
uv = np.array([s["centroid_px"] for s in man["stitches"]])
check("projected centroids lie inside the film", bool((uv >= 0).all() and (uv < P.W).all()))
check("the criteria are named with reasons in every manifest", all(all("why" in c for c in json.load(open(os.path.join(OUT, f"{k}_{v}_manifest.json")))["criteria"].values()) for k, v in VIEWS))

print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
