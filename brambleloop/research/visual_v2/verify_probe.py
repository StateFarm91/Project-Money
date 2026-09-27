"""Independent structural schedule check + adversarial protected composition.

No provider imports/calls. Requires numpy, Pillow, scipy only for the unchanged
V1 frequency instrument. The renderer's semantic metadata is never accepted as
proof of actual crochet loop topology or photorealism.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "out"
sys.path.insert(0, str(ROOT / "src"))


def linear(rgb):
    x = rgb.astype(np.float64)/255
    return np.where(x <= .04045, x/12.92, ((x+.055)/1.055)**2.4)


def encoded(x):
    return np.rint(255*np.clip(np.where(x<=.0031308,x*12.92,1.055*np.maximum(x,0)**(1/2.4)-.055),0,1)).astype(np.uint8)


def compose(fg, proposal):
    """Proposal has no write authority over opaque foreground, even if it ignores mask.

    PNG decoded RGB is straight sRGB. Composite in linear light. Partial coverage
    mixes background as physically required; its foreground RGB and coverage stay
    authoritative. Re-copy opaque bytes to ensure exact integer equality.
    """
    a=fg[:,:,3:4].astype(np.float64)/255
    result=encoded(linear(fg[:,:,:3])*a + linear(proposal)*(1-a))
    result[fg[:,:,3]==255]=fg[:,:,:3][fg[:,:,3]==255]
    return result


def validate_schedule(table, row_edges, points):
    # Independent derivation from CIR, not geometry_manifest's claimed counts.
    from brambleloop.products.texture import build_cable_throw
    from brambleloop.cir import compiler,twin,stitches
    cir=build_cable_throw(); res=compiler.compile_cir(cir)
    tw=twin.build_twin(cir,res,cir.components[0].name)
    family={"sc":1,"bpdc":2,"fpdc":3,"cable2x2":4}
    expected=sorted((c.row,c.fabric_position,family[c.stitch],(c.fabric_position//8+1) if c.stitch in {"fpdc","cable2x2"} else 0) for c in tw.cells)
    actual=sorted(map(tuple,table.tolist()))
    height=[max(stitches.get(c.stitch).row_height for c in tw.cells if c.row==r)*100/cir.gauge.rows_per_10cm for r in range(1,122)]
    expected_edges=np.r_[0,np.cumsum(height)]
    rows={r:table[(table[:,0]==r)&(table[:,2]==4)] for r in range(5,122,4)}
    tests={
        "every_cell_exactly_once_with_original_kind":actual==expected,
        "18_cable_ids_each_crossing_row":all(set(a[:,3])==set(range(1,19)) and len(a)==72 for a in rows.values()),
        "540_crossings_no_extra_rows":int(np.sum(table[:,2]==4))==2160 and set(table[table[:,2]==4,0])==set(range(5,122,4)),
        "row_heights_from_stitch_registry":row_edges.shape==expected_edges.shape and np.allclose(row_edges,expected_edges,rtol=0,atol=1e-8),
        "one_curve_per_cell":len(points)==len(expected),
        "finite_geometry":bool(np.isfinite(points).all()),
    }
    # Verify the paths, rather than just labels, contain the specified crossings.
    cross=table[:,2]==4; pp=table[cross,1]%8-2
    delta=points[cross,-1,0]-points[cross,0,0]
    tests["crossing_pairs_swap_two_cell_widths"] = bool(np.allclose(delta,np.where(pp<2,12.5,-12.5),atol=1e-4))
    x_start=points[cross,0,0]
    tests["crossing_locations_match_cell_slots"] = bool(np.allclose(x_start,(table[cross,1]+.5)*6.25,atol=1e-4))
    return {"status":"PASS" if all(tests.values()) else "FAIL", "checks":tests}


def main(deps=None):
    if deps: sys.path.insert(0,str(Path(deps).resolve()))
    start=time.perf_counter()
    data=np.load(OUT/'routing_probe.npz'); table=data['cells']; points=data['points_mm']; edges=data['row_edges_mm']
    valid=validate_schedule(table,edges,points)
    mutants={}
    for name in ['delete_column','wrong_crossing_row','change_stitch_family','move_crossing','rescale_gauge']:
        t=table.copy(); p=points.copy(); e=edges.copy()
        if name=='delete_column':
            keep=t[:,3]!=9; t=t[keep];p=p[keep]
        elif name=='wrong_crossing_row':t[t[:,0]==5,0]=6
        elif name=='change_stitch_family':t[t[:,2]==4,2]=3
        elif name=='move_crossing':p[t[:,2]==4,:,0]+=6.25
        elif name=='rescale_gauge':e=e*1.1
        mutants[name]=validate_schedule(t,e,p)
    fg=np.array(Image.open(OUT/'product_probe.png').convert('RGBA'))
    h,w=fg.shape[:2]; yy,xx=np.mgrid[:h,:w]
    proposals={
        'slate':np.stack([66+6*np.sin(xx/160),67+5*np.cos(yy/220),73+4*np.sin((xx+yy)/250)],axis=-1).clip(0,255).astype(np.uint8),
        'warm':np.stack([181+8*np.sin(xx/150),153+6*np.cos(yy/240),117+7*np.sin(xx/140)],axis=-1).clip(0,255).astype(np.uint8),
        # Represents an arbitrary model that repaints EVERYTHING, including product.
        'hostile':np.stack([(xx//16%2)*255,(yy//16%2)*255,np.full_like(xx,255)],axis=-1).astype(np.uint8),
    }
    comp={}; opaque=fg[:,:,3]==255; edge=(fg[:,:,3]>0)&~opaque
    for name,proposal in proposals.items():
        out=compose(fg,proposal); Image.fromarray(out).save(OUT/f'composite_{name}.png')
        max_delta=int(np.max(np.abs(out[opaque].astype(int)-fg[:,:,:3][opaque].astype(int)))) if opaque.any() else None
        comp[name]={"opaque_pixels":int(opaque.sum()),"partial_coverage_pixels":int(edge.sum()),
                    "max_opaque_channel_delta":max_delta,"changed_opaque_pixels":int(np.any(out[opaque]!=fg[:,:,:3][opaque],axis=1).sum()),
                    "status":"PASS" if max_delta==0 and opaque.any() else "FAIL",
                    "sha256":hashlib.sha256((OUT/f'composite_{name}.png').read_bytes()).hexdigest()}
    Image.fromarray(fg[:,:,3]).save(OUT/'product_alpha.png')
    # A local mask alone is not our guarantee; prove bypass failure and pixel restoration.
    direct_hostile_changed=int(np.any(proposals['hostile'][opaque]!=fg[:,:,:3][opaque],axis=1).sum())
    tampered=compose(fg,proposals['slate']); first=tuple(np.argwhere(opaque)[0]); tampered[first]=(255,0,0)
    corruption_detected=bool(np.any(tampered[opaque]!=fg[:,:,:3][opaque]))
    # Self-contained semantic diagram (not used by the renderer or as photo evidence).
    ids=np.zeros((121,144),dtype=np.uint8)
    for row,pos,kind,col in table:ids[row-1,pos]=col
    palette=np.array([[40,45,48]]+[[50+(i*47)%180,50+(i*71)%180,50+(i*29)%180] for i in range(1,19)],dtype=np.uint8)
    Image.fromarray(palette[ids[::-1]]).resize((1152,968),Image.Resampling.NEAREST).save(OUT/'cable_ids.png')
    # Reuse unmodified V1 periodicity instrument; expose its phase blind spot.
    spec=importlib.util.spec_from_file_location('v1_frequency_gate',HERE.parent/'v1grad/gate.py')
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    src=HERE.parent/'v1grad/out'
    ref=np.array(Image.open(src/'ref_flatlay.png').convert('L')).astype(float)
    mask=np.array(Image.open(src/'ref_mask.png'))>127
    meta=json.loads((src/'ref_meta.json').read_text()); ce=meta['expected_px']['cable_column_pitch'];xe=meta['expected_px']['crossing_period']
    ys,xs=np.nonzero(mask); box=(slice(ys.min(),ys.max()+1),slice(xs.min(),xs.max()+1))
    shifted=ref.copy();shifted[box]=np.roll(ref[box],12,axis=0)
    old_reference=gate.measure(ref,mask,ce,xe)
    old_shifted=gate.measure(shifted,mask,ce,xe)
    # Aggregate spectrum can miss an erased repeat; record result, do not assume.
    erased=ref.copy(); x0=xs.min()+int(8*ce); erased[:,x0:x0+int(ce)]=np.median(ref[box])
    old_erased=gate.measure(erased,mask,ce,xe)
    semantic_only={"all_product_truth":"UNKNOWN", "stitch_fabric_identity":"UNKNOWN", "continuous_yarn_topology":"FAIL", "edge_turning_chain_geometry":"UNKNOWN",
        "photographic_realism":"UNKNOWN", "fibre_fuzz":"UNKNOWN", "drape":"UNKNOWN", "listing_thumbnail_suitability":"FAIL - visibly schematic carriers",
        "release":"BLOCKED - macro layout/compositor proof only"}
    result={"scope":"Structural routing and product-pixel authority proof, not a certified hero", "semantic_schedule":valid,
            "adversarial_geometry":mutants,"composites":comp,"direct_hostile_proposal_changed_opaque_pixels":direct_hostile_changed,
            "one_pixel_corruption_detected":corruption_detected,
            "legacy_instrument":{"reference":old_reference,"crossings_shifted_12px":old_shifted,"one_column_erased":old_erased,"old_gates_changed":False},
            "separate_gates":semantic_only,"external_spend_usd":0,"seconds":round(time.perf_counter()-start,3)}
    (OUT/'proof_results.json').write_text(json.dumps(result,indent=2))
    assert valid['status']=='PASS'
    assert all(v['status']=='FAIL' for v in mutants.values())
    assert all(v['status']=='PASS' for v in comp.values()) and corruption_detected and direct_hostile_changed>0
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--deps');main(ap.parse_args().deps)
