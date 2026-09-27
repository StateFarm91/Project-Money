"""Independent saved-artifact check and assembly boundary for P07.

Reads serialized geometry, not the fixture builder. Never awards full-product
certification from two local operation controls. No network or providers.
"""
from pathlib import Path
import hashlib, importlib.util, json, sys
import numpy as np
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
V2=HERE.parent
spec=importlib.util.spec_from_file_location("distance_instrument",V2/"coupon/verify_coupon.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def distance(a,b):
    nb=len(b)-1;na=len(a)-1
    return float(module.segment_distance(np.repeat(a[:-1],nb,axis=0),np.repeat(a[1:],nb,axis=0),
      np.tile(b[:-1],(na,1)),np.tile(b[1:],(na,1))).min())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    out=HERE/"out";summary=json.loads((out/"result.json").read_text())
    data=json.loads((out/"geometry.json").read_text())
    checks={name:sha(out/name)==digest for name,digest in summary["files"].items()}
    assert all(checks.values())
    truth=V2.parent/"v1grad/out/product_truth.json"
    assert sha(truth)==summary["product_truth_sha256"]
    measurements=[]
    for record in summary["cases"]:
        case=data["cases"][record["tag"]]
        frames=np.array(case["bight_frames"]);rings={k:np.array(v) for k,v in case["rings"].items()}
        affine=np.linspace(frames[0],frames[-1],len(frames))
        affine_error=float(np.abs(frames-affine).max())
        assert affine_error<1e-12
        minsep=min(distance(p,q) for p in frames for q in rings.values())
        maxstep=float(np.linalg.norm(np.diff(frames,axis=0),axis=2).max())
        assert abs(minsep-record["minimum_sampled_clearance_mm"])<1e-9
        assert abs(minsep-maxstep-record["continuous_clearance_lower_bound_mm"])<1e-9
        lengths=np.linalg.norm(np.diff(frames,axis=1),axis=2).sum(axis=1)
        stationary_ends=float(np.linalg.norm(frames[:,[0,-1]]-frames[0,[0,-1]],axis=2).max())
        measurements.append({"tag":record["tag"],"affine_interpolation_error_mm":affine_error,
          "first_visible_length_mm":float(lengths[0]),"last_visible_length_mm":float(lengths[-1]),
          "required_material_supply_mm":float(lengths[-1]-lengths[0]),
          "endpoint_max_displacement_mm":stationary_ends,
          "persistent_material_ids_present":False,"feed_ledger_present":False})
    # New assembly check: same live_0 has been independently restaged by 3mm.
    one=data["cases"]["stage1_two_of_three"];two=data["cases"]["stage2_two_of_two"]
    shift=float(np.linalg.norm(np.array(one["rings"]["live_0"])-np.array(two["rings"]["live_0"]),axis=1).max())
    assert abs(shift-3.)<1e-12
    asset_gate={"status":"BLOCKED","structural_truth":"UNKNOWN","photographic_realism":"UNKNOWN",
      "blockers":["only independent closed-ring fixtures, not actual parent stitch strands",
      "interstage live_0 restaged without a continuous trajectory",
      "intermediate bight replaced by an unrelated closed ring",
      "no material ID/advection/feed ledger for increasing visible yarn length",
      "no actual prior-post attachment or continuous complete stitch",
      "self-contact, relaxation, gauge and independent crochet review unqualified"]}
    # This is an assembly refusal, not a redefinition of the historical product gate.
    assert asset_gate["status"]!="PASS"
    original=(out/"geometry.json").read_bytes()
    damaged=bytearray(original);at=damaged.index(b"1.8");damaged[at:at+3]=b"1.0"
    mutation_detected=hashlib.sha256(damaged).hexdigest()!=summary["files"]["geometry.json"]
    assert mutation_detected
    result={"experiment":"V2-P07","saved_artifact_hashes":checks,
      "truth_hash_unchanged":True,"one_byte_or_parameter_mutation_detected":mutation_detected,
      "measured_clearance_and_affine_bounds_reproduced":True,
      "material_measurements":measurements,"unexplained_live_loop_restage_mm":shift,
      "asset_gate":asset_gate,"spend_usd":0,"verifier_sha256":sha(Path(__file__))}
    (out/"validation.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"artifact_hashes_pass":len(checks),"assembly":asset_gate,
      "nominal_required_feed_mm":measurements[0]["required_material_supply_mm"],
      "unexplained_live_loop_restage_mm":shift},indent=2))
if __name__=="__main__":main()
