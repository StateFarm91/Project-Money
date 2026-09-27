"""P07: ordered DC operation graph + spatial draw-through instrumentation.

Two idealized loop fixtures are NOT a DC asset: they are separate local operation
tests. No persistent material transport, actual parent attachment, relaxation,
neighbor, edge, gauge, or product qualification is claimed. Offline/no providers.
"""
from pathlib import Path
import copy, hashlib, importlib.util, json, sys, time
import numpy as np
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
V2=HERE.parent
ROOT=V2.parents[1]
sys.path.insert(0,str(ROOT/"src"))
from brambleloop.visual.linkage import linking_number, close_arc
spec=importlib.util.spec_from_file_location("coupon_distance",V2/"coupon/verify_coupon.py")
distance_module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(distance_module)
segment_distance=distance_module.segment_distance
TRUTH="cf3b9d1a9e92cff41ca2e461b9795cecbaa12d42d89ddb47420aad6307d85808"
DIA=1.8
FLOOR=.45*DIA
def save(path,obj):
    path.write_text(json.dumps(obj,indent=2)+"\n",encoding="utf-8",newline="\n")
def nominal():
    return [
      {"id":"yarn_over","action":"yarn_over","creates":"wrap"},
      {"id":"draw_up","action":"draw_up","creates":"drawn_up","anchor":"prior_post","face":"front"},
      {"id":"close_1","action":"draw_two","consumes":["drawn_up","wrap"],"creates":"intermediate"},
      {"id":"close_2","action":"draw_two","consumes":["intermediate","live_0"],"creates":"live_1"},
    ]
def validate_graph(ops):
    stack=["live_0"];created={"live_0":"input"};consumed={};states=[stack.copy()]
    issues=[];stages=[]
    for op in ops:
        new=op["creates"]
        if new in created:issues.append("loop ID reused");break
        if op["action"]=="yarn_over":
            stack.insert(0,new)
        elif op["action"]=="draw_up":
            if op.get("anchor")!="prior_post" or op.get("face")!="front":
                issues.append("wrong attachment target/face")
            stack.insert(0,new)
        elif op["action"]=="draw_two":
            if op.get("consumes")!=stack[:2] or len(op.get("consumes",[]))!=2:
                issues.append("wrong ordered loop consumption")
            for loop in op.get("consumes",[]):
                if loop in consumed:issues.append("loop consumed twice")
                consumed[loop]=op["id"]
            stages.append(op.get("consumes",[]))
            stack=[new]+stack[2:]
        else:issues.append("unknown operation")
        created[new]=op["id"];states.append(stack.copy())
    if [len(s) for s in states]!=[1,2,3,2,1]:issues.append("wrong hook sequence")
    if [op["action"] for op in ops]!=["yarn_over","draw_up","draw_two","draw_two"]:
        issues.append("wrong operation sequence")
    if stages!=[["drawn_up","wrap"],["intermediate","live_0"]]:
        issues.append("not the ordered two-stage DC trace")
    return {"status":"FAIL" if issues else "PASS","issues":sorted(set(issues)),
      "hook_states_nearest_tip_first":states,"created_by":created,"consumed_by":consumed,
      "qualification":"semantic operation graph only"}
def ring(z,r=3.3):
    t=np.linspace(0,2*np.pi,129)
    return np.c_[r*np.cos(t),r*np.sin(t),np.full_like(t,z)]
def bight(h,offset=0):
    r=1.1;base=-7.
    left=np.c_[np.full(25,-r),np.zeros(25),np.linspace(base,h-r,25)]
    t=np.linspace(np.pi,0,25)
    nose=np.c_[r*np.cos(t),np.zeros(25),h-r+r*np.sin(t)]
    right=np.c_[np.full(25,r),np.zeros(25),np.linspace(h-r,base,25)]
    result=np.vstack([left,nose[1:],right[1:]])
    result[:,0]+=offset
    return result
def distance(a,b):
    na=len(a)-1;nb=len(b)-1
    return float(segment_distance(np.repeat(a[:-1],nb,axis=0),np.repeat(a[1:],nb,axis=0),
      np.tile(b[:-1],(na,1)),np.tile(b[1:],(na,1))).min())
def disk_crossings(path,z,r=3.3):
    # Planar convex ring control fixture only; not arbitrary deformed stitch loops.
    hits=[]
    for i,(a,b) in enumerate(zip(path[:-1],path[1:])):
        dz=b[2]-a[2]
        if abs(dz)<1e-12:continue
        t=(z-a[2])/dz
        if not (0<t<=1):continue
        q=a+t*(b-a)
        # Actual polygonal rim, rather than a nearby axis. Inradius prevents
        # mistaking the polygon's tiny outside slivers for its opening.
        if np.linalg.norm(q[:2])<r*np.cos(np.pi/128)-1e-9:
            hits.append({"segment":i,"t":float(t),"point_mm":q.tolist(),"sign":1 if dz>0 else -1})
    return hits
def fixture(tag,names,height=4.8,offset=0,steps=32):
    loops={name:ring(i*3.) for i,name in enumerate(names)}
    frames=[bight(h,offset) for h in np.linspace(-2.,height,steps+1)]
    rows=[];minsep=float("inf");maxmove=0.
    for i,p in enumerate(frames):
        ds={name:distance(p,q) for name,q in loops.items()}
        cs={name:disk_crossings(p,j*3.) for j,name in enumerate(names)}
        minsep=min(minsep,min(ds.values()))
        if i:maxmove=max(maxmove,float(np.linalg.norm(p-frames[i-1],axis=1).max()))
        rows.append({"frame":i,"clearance_mm":ds,"crossings":cs})
    final=rows[-1]["crossings"]
    targets=names[:2];preserved=names[2:]
    crossed={name:len(v)==2 and sorted(h["sign"] for h in v)==[-1,1] for name,v in final.items()}
    intended=all(crossed[n] for n in targets) and all(not final[n] for n in preserved)
    # Corresponding vertices move linearly in height. Distance to fixed segments
    # is 1-Lipschitz, so sample minimum minus max point motion is a conservative
    # lower bound throughout every interval. Not a generic collision solver.
    continuous_bound=minsep-maxmove
    result={"tag":tag,"intended_targets":targets,"must_remain_unconsumed":preserved,
      "frames":len(frames),"frame_samples":rows,"minimum_sampled_clearance_mm":minsep,
      "max_vertex_motion_between_frames_mm":maxmove,"continuous_clearance_lower_bound_mm":continuous_bound,
      "contact_floor_mm":FLOOR,"uncompressed_diameter_mm":DIA,
      "clearance_at_original_floor":"PASS" if continuous_bound>=FLOOR else "FAIL",
      "clearance_at_full_diameter":"PASS" if continuous_bound>=DIA else "FAIL",
      "correct_target_passage":"PASS" if intended else "FAIL",
      "local_fixture_status":"PASS" if continuous_bound>=FLOOR and intended else "FAIL",
      "closed_whole_bight_linking_numbers":{name:linking_number(q,close_arc(frames[-1])) for name,q in loops.items()} if continuous_bound>=FLOOR else None}
    return result,loops,frames
def chart(cases,path):
    colours=["#7d8c96","#a2b5a2","#ce9471"]
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="520" viewBox="0 0 1280 520">',
      '<rect width="1280" height="520" fill="#f3f1eb"/>',
      '<text x="30" y="35" font-family="sans-serif" font-size="20">P07: draw-through test fixtures — NOT a crochet stitch or product render</text>']
    for index,(record,loops,frames) in enumerate(cases):
        ox=140+index*315;oy=305
        def poly(p,col,w):
            xy=np.c_[p[:,0]+.55*p[:,1],p[:,2]-.35*p[:,1]]
            pts=" ".join(f"{ox+x*17:.2f},{oy-y*17:.2f}" for x,y in xy)
            return f'<polyline points="{pts}" stroke="{col}" stroke-width="{w}" fill="none" stroke-linecap="round"/>'
        for col,(name,p) in zip(colours,loops.items()):parts.append(poly(p,col,4))
        parts.append(poly(frames[-1],"#553575",5))
        parts.append(f'<text x="{ox-112}" y="450" font-family="sans-serif" font-size="15">{record["tag"]}: {record["local_fixture_status"]}</text>')
        parts.append(f'<text x="{ox-112}" y="475" font-family="sans-serif" font-size="12">Local passage/clearance only</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts),encoding="utf-8",newline="\n")
def main():
    start=time.perf_counter();out=HERE/"out";out.mkdir(exist_ok=True)
    truth_path=V2.parent/"v1grad/out/product_truth.json"
    assert hashlib.sha256(truth_path.read_bytes()).hexdigest()==TRUTH
    ops=nominal();graph=validate_graph(ops);assert graph["status"]=="PASS"
    negatives={}
    for tag,edit in [
      ("same_counts_wrong_first_pair",lambda a:a[2].update(consumes=["drawn_up","live_0"])),
      ("reverse_first_pair",lambda a:a[2].update(consumes=["wrap","drawn_up"])),
      ("reuse_consumed_loop",lambda a:a[3].update(consumes=["drawn_up","live_0"])),
      ("wrong_anchor",lambda a:a[1].update(anchor="different_post")),
      ("wrong_face",lambda a:a[1].update(face="back")),
      ("one_three_loop_closure",lambda a:a[2].update(consumes=["drawn_up","wrap","live_0"])),
      ("reuse_loop_id",lambda a:a[2].update(creates="drawn_up")),
    ]:
        mutated=copy.deepcopy(ops);edit(mutated);negatives[tag]=validate_graph(mutated)
    assert all(r["status"]=="FAIL" for r in negatives.values())
    cases=[
      fixture("stage1_two_of_three",["drawn_up","wrap","live_0"]),
      fixture("stage2_two_of_two",["intermediate","live_0"]),
      fixture("miss_second_loop",["drawn_up","wrap","live_0"],height=1.8),
      fixture("consume_third_loop",["drawn_up","wrap","live_0"],height=7.8),
      fixture("outside_targets",["drawn_up","wrap","live_0"],offset=6.6),
      fixture("rim_collision",["drawn_up","wrap","live_0"],offset=2.2),
    ]
    for i,(r,loops,frames) in enumerate(cases):
        assert r["local_fixture_status"]==("PASS" if i<2 else "FAIL"),r["tag"]
        save(out/(r["tag"]+".json"),r)
    # Same final bight, same closed-linking result zero whether inside or outside.
    # Signed linking is not wrong: a folded bight can be withdrawn. A predicate
    # requiring nonzero linking of whole bights would reject this legitimate
    # local draw-through primitive and cannot prove a completed stitch.
    assert set(cases[0][0]["closed_whole_bight_linking_numbers"].values())=={0}
    assert set(cases[4][0]["closed_whole_bight_linking_numbers"].values())=={0}
    graph["operations"]=ops
    graph["semantic_adversaries"]=negatives
    graph["geometry_binding"]={"status":"UNKNOWN","missing":["prior post insertion/wrap",
      "actual parent loop strands","persistent material coordinates between stages",
      "tightening/contact equilibrium","connected single yarn with foundation and live end",
      "independent crochet construction review"]}
    save(out/"operation_graph.json",graph)
    geometry={"units":"mm","research_yarn_diameter_mm":DIA,
      "not_a_product":True,"cases":{r["tag"]:{"rings":{k:v.tolist() for k,v in loops.items()},
      "bight_frames":[p.tolist() for p in frames]} for r,loops,frames in cases}}
    save(out/"geometry.json",geometry)
    chart([cases[i] for i in (0,1,2,3)],out/"diagnostic.svg")
    summary={"experiment":"V2-P07","product_truth_sha256":TRUTH,
      "operation_graph":"PASS","semantic_adversaries_rejected":len(negatives),
      "local_kinematic_fixtures_passed":2,"spatial_adversaries_rejected":4,
      "draw_through_cancellation_control":"PASS",
      "structural_truth":"UNKNOWN","photographic_realism":"UNKNOWN",
      "full_product_emission":"BLOCKED","spend_usd":0,
      "seconds":round(time.perf_counter()-start,3),
      "cases":[{k:v for k,v in r.items() if k!="frame_samples"} for r,_,_ in cases],
      "files":{name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in [r["tag"]+".json" for r,_,_ in cases]+["operation_graph.json","geometry.json","diagnostic.svg"]},
      "source_hashes":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/"src/brambleloop/visual/linkage.py",V2/"coupon/verify_coupon.py"]}}
    save(out/"result.json",summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ("cases","files","source_hashes")},indent=2))
if __name__=="__main__":main()

