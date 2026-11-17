import dataclasses as dc
from brambleloop.products import inventory, launch0 as L
from brambleloop.publish import pdf
def refused(cir):
    try:
        pdf._refuse_an_undecided_childrens_title(cir, L.childrens_assignment(cir.slug)); return None
    except ValueError as e: return type(e).__name__
b = inventory._engineered("market-basket-small")
print("decision raw", L.childrens_decision("market-basket-small")[0], "assignment", L.childrens_assignment("market-basket-small"))
for t in ["Baby Basket", "Nursery Basket for Baby", "Market Basket (0-12 months)", "Market Basket for ages 2+", "Pacifier Clip"]:
    print(f"candidate slug, title {t!r}: words={L.child_words_in(t, b.slug)} refused={refused(dc.replace(b, title=t))}")
    print(f"new slug,       title {t!r}: refused={refused(dc.replace(b, slug='zz-new-x', title=t))}")
# assigned slug, different CIR (stuffed ball under an assigned slug)
import sys; sys.path.insert(0,"tests")
import test_a1r_child_safety_core as T
ball = T._one_piece_ball()
for s in ["cloudline-baby-blanket", "market-basket-medium"]:
    a = L.childrens_assignment(s)
    c = dc.replace(ball, slug=s, title="Juniper Friend")
    print("assigned slug", s, a, "ball under it ->", L.childrens_decision_for(c)[0], "refused", refused(c))
# exempt slug reused for a toy (slug-bound exemption)
c = dc.replace(ball, slug="heart-row-ring-pillow", title="Juniper Friend")
print("exempt slug reused for one-piece ball:", L.childrens_decision_for(c)[0], "refused", refused(c))
