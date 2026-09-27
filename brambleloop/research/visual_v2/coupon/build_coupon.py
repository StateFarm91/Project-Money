"""Local stage-1 yarn-path hypotheses; never a certified product renderer."""
import argparse, collections, hashlib, json, sys
from pathlib import Path
import numpy as np
sys.dont_write_bytecode = True
HERE=Path(__file__).resolve().parent
V2=HERE.parent
sys.path.insert(0,str(V2))
from build_probe import compile_cells
from brambleloop.visual.crochet_topology import _sc_cell, COMPRESSED_CONTACT
DIA=1.8  # Research parameter, not a measured yarn fact. Fixed across trials.
TRUTH="cf3b9d1a9e92cff41ca2e461b9795cecbaa12d42d89ddb47420aad6307d85808"

def write(p,data):
    p.write_text(json.dumps(data,indent=2),encoding="utf-8",newline="\n")

def source_contract():
    cir,tw,pt,cells,edges,w=compile_cells()
    assert hashlib.sha256(pt.read_bytes()).hexdigest()==TRUTH
    records=[]
    for c in cells:
        p=int(c.fabric_position); r=int(c.row)
        rec={"row":r,"position":p,"kind":c.stitch,"direction":1 if r%2 else -1,
             "top_xy_mm":[(p+.5)*w,float(edges[r])],"row_height_mm":float(edges[r]-edges[r-1])}
        rec["target_kind"]="foundation_top" if r==1 else "post" if c.stitch in ("fpdc","bpdc") else "UNRESOLVED_CABLE"
        rec["target_row"]=r-1
        rec["target_position"]=p if c.stitch!="cable2x2" else None
        records.append(rec)
    contract={"fingerprint":cir.fingerprint,"product_truth_sha256":TRUTH,"cell_count":len(cells),
      "counts":dict(collections.Counter(c.stitch for c in cells)),"width_mm":144*w,"height_mm":float(edges[-1]),
      "cable_columns":18,"crossing_rows":sorted({c.row for c in cells if c.stitch=="cable2x2"}),
      "crossing_groups":sum(c.stitch=="cable2x2" for c in cells)//4,
      "foundation_count":cir.components[0].foundation,
      "turning_chains":[{"row":r.index,"count":r.turning_chain,"counts_as_stitch":r.turning_chain_counts} for r in cir.components[0].rows],
      "strict_status":"UNKNOWN","strict_blockers":["cable anchor operation not resolved","cable crossing direction absent from stitch registry",
        "DC path and edge-chain topology not independently reviewed"],
      "records":records}
    return contract,edges,w

def strict_build(contract):
    if any(r["target_kind"].startswith("UNRESOLVED") for r in contract["records"]):
        raise ValueError("UNRESOLVED_CABLE: no authoritative full-product geometry emitted")
    return contract

def dense(control, spacing=.25):
    # Cardinal interpolation, then arc-length densification. Collision checks use THIS path.
    p=np.asarray(control,float)
    q=np.vstack([p[0],p,p[-1]])
    ts=np.linspace(0,1,7,endpoint=False)
    chunks=[]
    for i in range(1,len(q)-2):
        a,b,c,d=q[i-1:i+3]
        m0=.3*(c-a);m1=.3*(d-b)
        t=ts[:,None]
        chunks.append((2*t**3-3*t**2+1)*b+(t**3-2*t**2+t)*m0+(-2*t**3+3*t**2)*c+(t**3-t**2)*m1)
    smooth=np.vstack(chunks+[p[-1:]])
    ds=np.linalg.norm(np.diff(smooth,axis=0),axis=1)
    arc=np.r_[0,np.cumsum(ds)]
    keep=np.r_[True,ds>1e-9];smooth=smooth[keep];arc=arc[keep]
    target=np.linspace(0,arc[-1],max(2,int(np.ceil(arc[-1]/spacing))+1))
    return np.column_stack([np.interp(target,arc,smooth[:,k]) for k in range(3)])

def frame(axis):
    v=axis/np.linalg.norm(axis)
    e=np.array([1.,0,0]); e=e-np.dot(e,v)*v;e/=np.linalg.norm(e)
    n=np.cross(e,v);n/=np.linalg.norm(n)
    return e,n,v

def post_route(x,y0,y1,parent,kind,direction,spread,anchor_mode="post", revision=0):
    H=y1-y0; L=6.25; face=direction*(1 if kind!="bpdc" else -1)
    center=np.asarray(parent["post_center"],float); axis=np.asarray(parent["post_axis"],float)
    if anchor_mode=="top":
        center=np.asarray(parent["top_center"],float);axis=np.array([1.,0,0])
        e=np.array([0.,1,0]);n=np.array([0.,0,1]);v=axis
    else:e,n,v=frame(axis)
    # Explicit major arc around lower post. The closing chord is diagnostic only.
    angle=np.linspace(np.pi/6,11*np.pi/6,19)
    rx=2.2;rz=spread
    wrap=center+rx*np.sin(angle)[:,None]*e+face*rz*np.cos(angle)[:,None]*n
    z=face*spread
    # Hypothesis for the two draw-through stages; loops are modeled, not only named.
    close1=[]
    close2=[]
    for cy,arr in [(y0+.42*H,close1),(y0+.70*H,close2)]:
        for t in np.linspace(0,1,10):
            arr.append([x+direction*1.05*np.cos(2*np.pi*t),cy+.65*np.sin(2*np.pi*t),
                        z+face*1.05*np.sin(2*np.pi*t)+(1.2 if revision else .3)*t])
    head=np.array([[x+direction*2.1,y1,-1.35],[x-direction*2.1,y1,-1.35],
      [x-direction*2.5,y1+.30,0],[x-direction*2.1,y1+.45,1.35],[x+direction*2.1,y1+.1,1.35]])
    start=np.array([x-direction*L/2,y1-.3*H,face*.8])
    end=np.array([x+direction*L/2,y1-.3*H,face*.8])
    controls=np.vstack([start,[x-direction*.9,y0+.5*H,z],wrap,
                        [x+direction*.85,y0+.28*H,z],close1,close2,head,end])
    # The stem reference is an actual straight connection in the generated control path.
    pa=np.array([x+direction*.85,y0+.28*H,z]);pb=np.asarray(close1[0])
    return controls,{"wrap":wrap.tolist(),"anchor_center":center.tolist(),"anchor_axis":axis.tolist(),
       "basis_e":e.tolist(),"basis_n":n.tolist(),"face":face,"target_mode":anchor_mode,
       "post_center":((pa+pb)/2).tolist(),"post_axis":(pb-pa).tolist(),
       "top_center":[x,y1,0],"closure_count":2,"hook_trace":[1,2,3,2,1]}

def build(spread, cable_mode, revision=0):
    contract,edges,w=source_contract()
    records={(r["row"],r["position"]):r for r in contract["records"]}
    pieces=[];infos=[];parent={}
    def add(kind,row,pos,control,meta):
        pts=dense(control)
        meta.update({"kind":kind,"row":row,"position":pos,"control_points":np.asarray(control).tolist()})
        pieces.append(pts);infos.append(meta)
    # Diagnostic eight-stitch coupon: foundation/turn hypotheses explicit, not product edge certification.
    for pos in (range(7,-1,-1) if revision else range(8)):
        x=(pos+.5)*w;t=np.linspace(0,2*np.pi,17)
        q=np.column_stack([x+2.0*np.cos(t),.5*np.sin(t),1.2*np.sin(t)])
        q[0]=[pos*w,0,0];q[-1]=[(pos+1)*w,0,0]
        if revision:q=q[::-1].copy()
        add("foundation_chain",0,pos,q,{"hook_trace":[1,1],"closure_count":1})
    for row in range(1,10):
        direction=1 if row%2 else -1
        if row>1:
            edge_x=0 if direction>0 else 8*w
            for j in range(2):
                cy=float(edges[row-1]+(j+.5)*(edges[row]-edges[row-1])/2)
                t=np.linspace(0,2*np.pi,17)
                q=np.column_stack([edge_x-direction*(1+1.5*np.sin(t)),cy+1.8*np.cos(t),1.4*np.sin(t)])
                if revision:q[:,1]+=1.2*t/(2*np.pi)
                add("turn_chain",row,-1,q,{"hook_trace":[1,1],"closure_count":1})
        else:
            add("turn_chain",1,-1,[[-1,0,0],[-2,1,1],[-1,2,-1],[0,2.1,2] if revision else [0,0,0]],{"hook_trace":[1,1],"closure_count":1})
        current={}
        for pos in (range(8) if direction>0 else range(7,-1,-1)):
            rec=records[(row,pos)];kind=rec["kind"];x=(pos+.5)*w;y0,y1=edges[row-1:row+1]
            if kind=="sc":
                q,spans=_sc_cell(w,y1-y0,spread*2,direction,"both",y0,DIA)
                q[:,0]+=pos*w
                k=spans["pull_through"][1]; a=q[k];b=q[min(k+2,len(q)-1)]
                meta={"post_center":((a+b)/2).tolist(),"post_axis":(b-a).tolist(),
                      "top_center":[x,float(y1),0],"hook_trace":[1,2,1],"closure_count":1,
                      "asset":"existing _sc_cell, no inferred certification"}
            else:
                target=pos;mode="post"
                if kind=="cable2x2":
                    offset=pos%8-2;target=pos+(2 if offset<2 else -2);mode=cable_mode
                q,meta=post_route(x,y0,y1,parent[target],kind,direction,spread,mode,revision)
                meta["target_position"]=target
                meta["research_hypothesis"]=kind=="cable2x2"
            add(kind,row,pos,q,meta);current[pos]=meta
        parent=current
    # Join piece endpoints in yarn order, and retain connector identities for inspection.
    path=[];ranges=[];connectors=[]
    for piece,info in zip(pieces,infos):
        if path:
            a=path[-1];b=piece[0];length=float(np.linalg.norm(b-a))
            link=np.linspace(a,b,max(2,int(np.ceil(length/.25))+1))[1:-1]
            connectors.append({"from":len(ranges)-1,"to":len(ranges),"length_mm":length})
            path.extend(link)
        start=len(path);path.extend(piece);ranges.append([start,len(path)])
    pts=np.asarray(path,dtype=np.float32)
    meta={"scope":"8x9 diagnostic coupon, NOT a reduced product or certified crochet",
          "route_revision":revision,"spread_mm":spread,"yarn_diameter_mm":DIA,"contact_floor_mm":COMPRESSED_CONTACT*DIA,
          "cable_mode_hypothesis":cable_mode,"coupon_source_rows":[1,9],"coupon_source_positions":[0,7],
          "product_contract":{k:v for k,v in contract.items() if k!="records"},
          "pieces":infos,"ranges":ranges,"connectors":connectors,
          "centerline_sha256":hashlib.sha256(pts.tobytes()).hexdigest(),
          "construction_status":"UNKNOWN","border_topology":"UNKNOWN",
          "warnings":["DC draw-through spatial realization is a hypothesis","chain and turn paths not independently validated",
                      "local wrap winding is not a complete topological invariant","coupon boundaries are artificial test boundaries"]}
    return pts,meta,contract

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--spread",type=float,default=2.2)
    ap.add_argument("--route-revision",type=int,choices=[0,1],default=0)
    ap.add_argument("--cable-mode",choices=["post","top"],default="top");ap.add_argument("--tag",required=True)
    args=ap.parse_args();out=HERE/"out"/args.tag;out.mkdir(parents=True,exist_ok=True)
    pts,meta,contract=build(args.spread,args.cable_mode,args.route_revision)
    strict_refused=False
    try:strict_build(contract)
    except ValueError:strict_refused=True
    assert strict_refused
    meta["strict_product_compile_refused"]=strict_refused
    meta["builder_sha256"]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    np.savez_compressed(out/"centerline.npz",points_mm=pts)
    write(out/"geometry.json",meta);write(HERE/"out/source_contract.json",contract)
    print(json.dumps({"tag":args.tag,"points":len(pts),"source_cells":contract["cell_count"],"strict_refused":strict_refused}))
if __name__=="__main__":main()
