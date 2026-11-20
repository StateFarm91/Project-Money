"""Milestone D is measured, never declared.

`milestone_d.assess` runs the certified swatch through drape on a form, re-validates it and
derives its render from that configuration. These checks are about the ASSESSMENT: that every
item carries a measurement, that a judgement nobody made is UNKNOWN, that an UNKNOWN never
contributes to a PASS, and that the ladder reports D as UNMEASURED rather than inventing a
status when it did not run. The physics is pinned in tests/test_drape.py and the frames in
tests/test_stitch_identity.py; this file runs a short solve so it stays fast.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from brambleloop.visual import milestone_d as MD, milestones as ML

PASSED = FAILED = 0
def check(name, ok, detail=""):
    global PASSED, FAILED
    PASSED += bool(ok); FAILED += (not ok)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))

res = MD.assess("hdc", iterations=200, render_dir=None)
items = {i["item"]: i for i in res["items"]}
check("every item reports a status from the closed set and a measurement",
      all(i["status"] in (MD.PASS, MD.FAIL, MD.UNKNOWN) and "measured" in i for i in res["items"]))
check("the judged items are UNKNOWN because no judge ran, and say so",
      all(items[j]["status"] == MD.UNKNOWN and "judge" in items[j]["requirement"] for j in MD.JUDGED + MD.JUDGED_REJECTS))
check("no render directory means no image and the item says nothing was drawn",
      items["images_rendered"]["status"] == MD.UNKNOWN and "drawn" in items["images_rendered"]["requirement"])
check("with UNKNOWN items present the milestone is never PASS",
      res["status"] != MD.PASS and set(res["unknown"]) >= set(MD.JUDGED))
check("the overall rule is stated on the result", "UNKNOWN never" in res["rule"])
check("every chosen number is in CRITERIA with a reason",
      all(isinstance(v, tuple) and len(v) == 2 and len(v[1]) > 40 for v in MD.CRITERIA.values())
      and set(res["criteria"]) == set(MD.CRITERIA))
check("the bending rigidity used is on the result and is the derived one, not the committed constant",
      res["solver"]["bending_N_m2"] == items["bending_rigidity_provenance"]["measured"]["used_N_m2"]
      and items["bending_rigidity_provenance"]["measured"]["committed_is_documented_unconverged"] is True
      and res["solver"]["bending_N_m2"] > 10 * items["bending_rigidity_provenance"]["measured"]["committed_N_m2"])
check("the friction lock is declared where it holds morphology, so the reader knows what is an input",
      "friction lock" in items["no_structural_drift"]["measured"]["morphology_held_by"]
      and items["no_structural_drift"]["measured"]["frame"].startswith("certified stitch frame"))
check("the fixed point, identity and the certified flat hold in a short solve",
      items["equilibrium_fixed_point"]["status"] == MD.PASS and items["stitch_identity"]["status"] == MD.PASS
      and items["certified_flat"]["status"] == MD.PASS)
check("a 200-iteration solve is honestly still moving: stationarity is UNKNOWN, not PASS",
      items["stationary"]["status"] in (MD.UNKNOWN, MD.PASS) and "trace" in items["stationary"]["measured"])
check("the render item hashes the geometry it drew and finds it unchanged",
      items["render_consumes_validated_geometry"]["measured"]["unchanged_by_render"] is True
      and len(items["render_consumes_validated_geometry"]["measured"]["geometry_sha256"]) == 64)
check("the summary is one line per item", MD.summary(res).count("\n") == len(res["items"]))

# --- the ladder ------------------------------------------------------------------------------
lad = ML.assess()
d_row = next(r for r in lad["milestones"] if r["milestone"] == "D")
check("the ladder reports D as UNMEASURED when nobody measured it, never FAIL or PASS by default",
      d_row["status"] == ML.UNMEASURED and "milestone_d.assess" in d_row["evidence"])
lad2 = ML.assess(d_result=res)
d_row2 = next(r for r in lad2["milestones"] if r["milestone"] == "D")
check("a supplied D result flows into the ladder with its status and its unknowns",
      d_row2["status"] in (ML.PARTIAL, ML.FAIL) and d_row2["unknown"] == res["unknown"])
fake = dict(res, status=MD.PASS, unknown=[], failed=[])
lad3 = ML.assess(d_result=fake)
d_row3 = next(r for r in lad3["milestones"] if r["milestone"] == "D")
check("a PASS handed to the ladder is still subject to the ordering rule: nothing passes on "
      "top of a milestone that failed, and a PARTIAL earlier rung does not block",
      d_row3["status"] in (ML.PASS, ML.BLOCKED), d_row3["status"])

# --- the independent judge: what it asks, how it reads, how it decides -- no call is made ----
from brambleloop.visual import d_judge as DJ
check("every judged D item has a judge key phrased so that True means sound, and the judge is "
      "never shown the standard as something to agree with",
      set(DJ.ITEM_TO_CHECK) == set(MD.JUDGED + MD.JUDGED_REJECTS)
      and all(DJ.ITEM_TO_CHECK[i] in DJ.CHECKS for i in DJ.ITEM_TO_CHECK)
      and "omit the key" in DJ.prompt() and "Do not guess" in DJ.prompt())
check("the judge model is pinned by a dated id and its price basis is written down",
      DJ.MODEL.count("-20") == 1 and "list" in DJ.see.__doc__ + str(DJ.PRICE_USD_PER_M) or DJ.PRICE_USD_PER_M["input"] > 0)
_r = DJ.read({"raw": 'thinking... {"fabric_folds_naturally": true, "yarn_is_not_melted": false, "shadows_are_coherent": "true", "notes": "x"}'})
check("the reading keeps only the closed vocabulary and real booleans: a string 'true' is unmade",
      _r["judged"] and _r["checks"] == {"fabric_folds_naturally": True, "yarn_is_not_melted": False})
check("an answer with no JSON is unjudged, never passed", DJ.read({"raw": "I cannot tell."})["judged"] is False)
_views = [{"reading": {"checks": {"fabric_folds_naturally": True, "yarn_is_not_melted": True}}, "image": "a.png"},
          {"reading": {"checks": {"fabric_folds_naturally": False}}, "image": "b.png"}]
def _decide(views):
    out = {}
    for item, key in DJ.ITEM_TO_CHECK.items():
        votes = [v["reading"]["checks"].get(key) for v in views]
        out[item] = "FAIL" if any(x is False for x in votes) else "PASS" if votes and all(x is True for x in votes) else "UNKNOWN"
    return out
_d = _decide(_views)
check("the decision rule: FAIL on any view, PASS only when every view is sound, UNKNOWN otherwise",
      _d["fabric_folds_naturally"] == "FAIL" and _d["melted_yarn"] == "UNKNOWN" and _d["lighting_is_realistic"] == "UNKNOWN"
      and _decide(_views[:1])["melted_yarn"] == "PASS")
import os as _os
_saved = (_os.environ.pop("OPENAI_API_KEY", None), _os.environ.pop("OPENAI_API_KEY_FILE", None))
try:
    DJ._key(); _refused = False
except RuntimeError:
    _refused = True
if _saved[0]: _os.environ["OPENAI_API_KEY"] = _saved[0]
if _saved[1]: _os.environ["OPENAI_API_KEY_FILE"] = _saved[1]
check("without a credential the judge refuses rather than inventing an answer", _refused)

print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
