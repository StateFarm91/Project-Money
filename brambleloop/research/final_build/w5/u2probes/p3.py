import _tmp; _tmp.install()
import dataclasses as dc, sys
sys.path.insert(0, "tests")
from test_a1r_child_safety_core import _one_piece_ball, _unflagged_pillow
from brambleloop.cir.model import Material, Row, Op
from brambleloop.products import inventory, launch0 as L
from brambleloop.products.text_fold import fold
from brambleloop.creative.fallback_constructions import fold_title
from brambleloop.publish import pdf
from brambleloop.gates import small_parts as SP
from brambleloop.cir.compiler import compile_cir

def refused(cir):
    try:
        pdf._refuse_an_undecided_childrens_title(cir, L.childrens_assignment(cir.slug)); return None
    except ValueError as e: return type(e).__name__
def rows_from(counts):
    rows=[]
    for i,n in enumerate(counts):
        prev = counts[i-1] if i else 0
        if i==0: ops=[Op("sc",n)]
        elif n>prev: ops=[Op("inc",n-prev)]+([Op("sc",2*prev-n)] if 2*prev>n else [])
        elif n<prev: ops=[Op("dec",prev-n)]+([Op("sc",2*n-prev)] if 2*n>prev else [])
        else: ops=[Op("sc",n)]
        rows.append(Row(index=i+1, ops=ops, declared_count=n, turning_chain=0))
    return rows
ball=_one_piece_ball()
def variant(name, counts, **kw):
    c = dc.replace(ball, components=[dc.replace(ball.components[0], rows=rows_from(counts), foundation=counts[0])], **kw)
    print(f"{name}: closed={L.closed_stuffed_form(c)} compile_ok={compile_cir(c).ok} refused={refused(c)}")
    return c
variant("G1 ball closing at 6 (control)", [6,12,18,24,24,18,12,6])
variant("G2 pouf/ball closing at 18", [6,12,18,24,30,36,36,36,30,24,18])
variant("G3 ball closing at 15", [6,12,18,24,24,24,18,15])
variant("G4 tube cinched (no decrease) 6->24 then 24 x6", [6,12,18,24,24,24,24,24,24])
variant("G5 sausage tube: constant 12 rounds", [12,12,12,12,12,12,12,12])
variant("G6 2-round ball", [6,6])
# flat single panel folded, no seams, fibrefill + note
flat = inventory._engineered("autumn-oak-mosaic-throw") if False else None
pil = inventory._engineered("heart-row-ring-pillow")
one = dc.replace(pil, slug="juniper-flat-x", title="Juniper Friend", components=[pil.components[0]], assembly=[],
                 designer_notes="Fold the panel in half, slip stitch the edges closed and stuff firmly with fibrefill.")
print("G7 ring pillow piece[0] alone", pil.components[0].construction, [r.declared_count for r in pil.components[0].rows][-3:], "closed", L.closed_stuffed_form(one), "refused", refused(one), "compile", compile_cir(one).ok)
# self seam piece_a == piece_b
if pil.assembly:
    selfseam = dc.replace(one, assembly=[dc.replace(pil.assembly[0], piece_a=pil.components[0].name, piece_b=pil.components[0].name, stuff_before_closing=False, note=None)], designer_notes=None)
    print("G8 self-seam", L.closed_stuffed_form(selfseam), refused(selfseam))
# filling with yarn weight and unmatched word
for fill in ["polyester fiber", "cluster fiber", "polyester fibers", "wool fleece", "scrap yarn", "rice", "lentils", "plastic poly pellets", "cotton batting", "fiberfill", "polyfil"]:
    p = _unflagged_pillow("x"); 
    w = dc.replace(p, materials=[m for m in p.materials if m.yarn_weight]+[Material(name=fill, yarn_weight="worsted")])
    print(f"H weighted filling {fill!r}: closed={L.closed_stuffed_form(w)}")
# false positives on non-stuffed catalogue
for slug in inventory.universe() if hasattr(inventory,'universe') else []:
    pass
for t in ["ꓐaby Basket","ᗷaby Basket","Bɑby Basket","Babʏ Basket","ΒΑΒΥ","Кid Basket","Ⲕid","Ꮶid","ᏦID","Toԁԁler","Ьаby","BABY","b a b y basket","B.a.b.y Basket","Ba-by Basket","Ba_by Basket","Baby's","Babies","Bebe","Kiddo","Tot Basket","Newborn","Infant","Nursery","Toddler","Teether","Rattle","Lovey","Plushie","Amigurumi","Dummy Clip","Binky Leash","Paci Holder","Pacifier Clip","Crib Mobile","Cot Garland","Nappy Cover","Bib","Stroller Toy","Car Seat Cover","Bonnet","Booties","Onesie","Teddy","Snuggle Buddy","Security Blanket","Kids Hat","Child Scarf","Boys Hat","Girls Bag","Doll","Puppet","Toy"]:
    w = L.child_words_in(t)
    print(f"W {t!r} -> fold={fold(t)!r} fold_title={fold_title(t)!r} words={w}")
