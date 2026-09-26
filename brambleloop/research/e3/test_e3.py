"""The presentation-gate distinction against E3's actual evidence, plus the boundaries that
cannot be argued away. Run: python research/e3/test_e3.py"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
sys.path.insert(0, HERE)
from gate_spec import classify, GenerativeOperation, Correspondence, UNAUTHORISED_REDESIGN, CERTIFIED_PRESENTATION, UNKNOWN

PASSED = FAILED = 0
def check(name, ok, detail=""):
    global PASSED, FAILED
    PASSED += bool(ok); FAILED += (not ok)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))

corr = json.load(open(os.path.join(OUT, "e3_correspondence.json")))
for r in corr["per_image"]:
    props = {k: v["status"] for k, v in r["items"].items()}
    op = GenerativeOperation("gpt-image-2 edits", r["geometry_sha256"], r["reference_sha256"], r["output_sha256"])
    c = Correspondence(props, r["reference_sha256"], r["geometry_sha256"])
    got = classify(op, c, frozen_geometry_sha256=r["geometry_sha256"], frozen_reference_sha256=r["reference_sha256"])
    expect = UNAUTHORISED_REDESIGN if "FAIL" in props.values() else (UNKNOWN if "UNKNOWN" in props.values() else CERTIFIED_PRESENTATION)
    check(f"E3 {r['kind']} {r['view']}: the actual evidence classifies as {expect}", got["category"] == expect, str(got))
# boundaries
r = corr["per_image"][0]
all_pass = Correspondence({k: "PASS" for k in r["items"]}, r["reference_sha256"], r["geometry_sha256"])
check("every property PASS on the declared frozen reference is a certified presentation transformation",
      classify(GenerativeOperation("x", r["geometry_sha256"], r["reference_sha256"]), all_pass, frozen_geometry_sha256=r["geometry_sha256"], frozen_reference_sha256=r["reference_sha256"])["category"] == CERTIFIED_PRESENTATION)
check("no declared reference is redesign, however good the correspondence",
      classify(GenerativeOperation("x"), all_pass, frozen_geometry_sha256=r["geometry_sha256"], frozen_reference_sha256=r["reference_sha256"])["category"] == UNAUTHORISED_REDESIGN)
check("a reference that is not the frozen one is redesign",
      classify(GenerativeOperation("x", "0" * 64, r["reference_sha256"]), all_pass, frozen_geometry_sha256=r["geometry_sha256"], frozen_reference_sha256=r["reference_sha256"])["category"] == UNAUTHORISED_REDESIGN)
check("never revalidated is redesign: conditioning is a claim, revalidation the proof",
      classify(GenerativeOperation("x", r["geometry_sha256"], r["reference_sha256"]), None, frozen_geometry_sha256=r["geometry_sha256"], frozen_reference_sha256=r["reference_sha256"])["category"] == UNAUTHORISED_REDESIGN)
check("revalidated against a different reference than declared is redesign",
      classify(GenerativeOperation("x", r["geometry_sha256"], r["reference_sha256"]), Correspondence({"silhouette": "PASS"}, "1" * 64, r["geometry_sha256"]), frozen_geometry_sha256=r["geometry_sha256"], frozen_reference_sha256=r["reference_sha256"])["category"] == UNAUTHORISED_REDESIGN)
one_unknown = Correspondence({**{k: "PASS" for k in r["items"]}, "rows": "UNKNOWN"}, r["reference_sha256"], r["geometry_sha256"])
check("one UNKNOWN with no FAIL blocks as UNKNOWN, never certifies",
      classify(GenerativeOperation("x", r["geometry_sha256"], r["reference_sha256"]), one_unknown, frozen_geometry_sha256=r["geometry_sha256"], frozen_reference_sha256=r["reference_sha256"])["category"] == UNKNOWN)
print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
