"""Independent numerical checks of the emitted dense yarn path, fail closed."""
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def dump(path,data):path.write_text(json.dumps(data,indent=2),encoding="utf-8",newline="\n")
def winding(points,center,e,n):
    v=points-center
    z=np.column_stack([v@e,v@n]);z=np.vstack([z,z[:1]])
    a=z[:-1];b=z[1:]
    angles=np.arctan2(a[:,0]*b[:,1]-a[:,1]*b[:,0],(a*b).sum(axis=1))
    return float(angles.sum()/(2*np.pi))
def segment_distance(a,b,c,d):
    u=b-a;v=d-c;w=a-c
    A=(u*u).sum(1);B=(u*v).sum(1);C=(v*v).sum(1);D=(u*w).sum(1);E=(v*w).sum(1)
    den=A*C-B*B;safe=np.where(abs(den)>1e-15,den,1)
    s=(B*E-C*D)/safe;t=(A*E-B*D)/safe
    inside=(abs(den)>1e-15)&(s>=0)&(s<=1)&(t>=0)&(t<=1)
    interior=np.linalg.norm(w+s[:,None]*u-t[:,None]*v,axis=1)
    distances=[np.where(inside,interior,np.inf)]
    for p,q,delta,dd in [(a,c,v,C),(b,c,v,C),(c,a,u,A),(d,a,u,A)]:
        tt=np.clip(((p-q)*delta).sum(1)/np.maximum(dd,1e-20),0,1)
        distances.append(np.linalg.norm(p-q-tt[:,None]*delta,axis=1))
    return np.min(distances,axis=0)

def collision(points,diameter):
    from scipy.spatial import cKDTree
    p=points.astype(float);d=np.diff(p,axis=0);length=np.linalg.norm(d,axis=1)
    mids=(p[:-1]+p[1:])/2;arc=np.r_[0,np.cumsum(length)];midarc=(arc[:-1]+arc[1:])/2
    floor=.45*diameter
    pairs=cKDTree(mids).query_pairs(floor+float(length.max()),output_type="ndarray")
    pairs=pairs[(abs(pairs[:,1]-pairs[:,0])>1)&(abs(midarc[pairs[:,1]]-midarc[pairs[:,0]])>np.pi*diameter/2)]
    i,j=pairs.T
    dist=segment_distance(p[i],p[i+1],p[j],p[j+1])
    bad=dist<floor-1e-9;order=np.argsort(dist)[:25]
    return {"status":"FAIL" if bad.any() else "PASS","floor_mm":floor,"exact_segment_pairs_tested":len(dist),
      "penetrating_segment_pairs":int(bad.sum()),"minimum_distance_mm":float(dist.min()) if len(dist) else None,
      "worst_pairs":[{"segments":[int(i[k]),int(j[k])],"distance_mm":float(dist[k])} for k in order],
      "max_rendered_segment_length_mm":float(length.max()),
      "exclusion":"shared vertex and along-yarn separation <= pi*yarn radius, matching existing instrument",
      "scope":"dense centerline tubes; ply/fibre envelopes not included"}

def trace_valid(kind,trace):
    return trace==([1,2,1] if kind=="sc" else [1,1] if "chain" in kind else [1,2,3,2,1])
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--tag",required=True);ap.add_argument("--deps",required=True)
    a=ap.parse_args();sys.path.insert(0,str(Path(a.deps).resolve()))
    folder=HERE/"out"/a.tag
    meta=json.loads((folder/"geometry.json").read_text());pts=np.load(folder/"centerline.npz")["points_mm"]
    assert hashlib.sha256(pts.tobytes()).hexdigest()==meta["centerline_sha256"]
    pieces=meta["pieces"];ranges=meta["ranges"]
    bodies=[p for p in pieces if p["kind"] in ("sc","fpdc","bpdc","cable2x2")]
    inventory={k:sum(p["kind"]==k for p in bodies) for k in ("sc","fpdc","bpdc","cable2x2")}
    expected={"sc":8,"fpdc":24,"bpdc":32,"cable2x2":8}
    semantic={"coupon_inventory":inventory==expected,"unique_body_slots":len({(p["row"],p["position"]) for p in bodies})==72,
      "body_total":len(bodies)==72,"source_truth_frozen":meta["product_contract"]["product_truth_sha256"]=="cf3b9d1a9e92cff41ca2e461b9795cecbaa12d42d89ddb47420aad6307d85808",
      "full_truth_18_columns_540_crossings":meta["product_contract"]["cable_columns"]==18 and meta["product_contract"]["crossing_groups"]==540,
      "hook_loop_operation_traces":all(trace_valid(p["kind"],p["hook_trace"]) for p in pieces),
      "foundation_count":sum(p["kind"]=="foundation_chain" for p in pieces)==8,
      "turn_chain_count":sum(p["kind"]=="turn_chain" for p in pieces)==17,
      "crossing_rows":sorted({p["row"] for p in bodies if p["kind"]=="cable2x2"})==[5,9]}
    attachments=[]
    for p,(lo,hi) in zip(pieces,ranges):
        if p["kind"] not in ("fpdc","bpdc"):continue
        segment=pts[lo:hi].astype(float);wrap=np.asarray(p["wrap"])
        # Measure the dense rendered span, not the ideal arc stored in metadata.
        start=int(np.argmin(np.linalg.norm(segment-wrap[0],axis=1)))
        end=int(np.argmin(np.linalg.norm(segment-wrap[-1],axis=1)))
        span=segment[min(start,end):max(start,end)+1]
        center=np.asarray(p["anchor_center"]);e=np.asarray(p["basis_e"]);n=np.asarray(p["basis_n"])
        w=winding(span,center,e,n)
        wrong=winding(span,center+50*e,e,n)
        attachments.append({"row":p["row"],"position":p["position"],"kind":p["kind"],
           "winding":round(w,8),"moved_anchor_winding":round(wrong,8),
           "status":"PASS" if abs(abs(w)-1)<1e-4 else "FAIL"})
    contact=collision(pts,meta["yarn_diameter_mm"])
    negative={"wrong_post_target_detected":all(abs(p["moved_anchor_winding"])<1e-4 for p in attachments),
      "drop_dc_pullthrough_detected":not trace_valid("fpdc",[1,2,3,1]),
      "drop_stitch_detected":len(bodies[:-1])!=72,
      "shift_crossing_row_detected":sorted({6 if p["row"]==5 else p["row"] for p in bodies if p["kind"]=="cable2x2"})!=[5,9],
      "unresolved_product_refused":meta["strict_product_compile_refused"]}
    result={"tag":a.tag,"input_centerline_sha256":meta["centerline_sha256"],"source_semantics":{"status":"PASS" if all(semantic.values()) else "FAIL","checks":semantic,"coupon_inventory":inventory},
       "local_post_wraps":{"pass":sum(p["status"]=="PASS" for p in attachments),"total":len(attachments),"records":attachments,
          "scope":"winding of an open local arc with artificial closing chord around prior post axis; not full entanglement proof"},
       "contact":contact,"negative_checks":negative,
       "continuity":{"one_polyline":True,"declared_endpoints":2,"longest_connector_mm":max(x["length_mm"] for x in meta["connectors"]),
         "warning":"connecting splines is not proof that the connections represent crochet"},
       "structural_truth":"FAIL" if contact["status"]=="FAIL" else "UNKNOWN",
       "photographic_realism":"UNKNOWN","independent_crochet_review":"UNKNOWN","edge_chain_topology":"UNKNOWN",
       "full_throw_stage":"BLOCKED","spend_usd":0}
    dump(folder/"measurements.json",result)
    print(json.dumps({"tag":a.tag,"semantic":result["source_semantics"]["status"],"wraps":[result["local_post_wraps"]["pass"],len(attachments)],
       "penetrations":contact["penetrating_segment_pairs"],"min_distance_mm":contact["minimum_distance_mm"],
       "negatives":negative,"structural_truth":result["structural_truth"]}))
    assert all(semantic.values()) and all(negative.values()),"Fixture/protocol defect, inspect measurements"
if __name__=="__main__":main()
