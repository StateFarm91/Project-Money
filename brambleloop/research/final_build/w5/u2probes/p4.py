import _tmp; _tmp.install()
import dataclasses as dc, sys
sys.path.insert(0, "tests")
import test_a1r_child_safety_core as T
from p3lib import rows_from
from brambleloop.products import inventory, launch0 as L
ball = T._one_piece_ball()
big = dc.replace(ball, slug="juniper-pouf-b411", components=[dc.replace(ball.components[0], rows=rows_from([6,12,18,24,30,36,36,36,30,24,18]))])
tube = dc.replace(ball, slug="juniper-snake-b411", title="Juniper Snake", components=[dc.replace(ball.components[0], rows=rows_from([6,12,12,12,12,12,12,12,12]))],
                  designer_notes="Stuff firmly with polyester fibrefill and whipstitch the opening closed.")
for name, c in [("big ball closing at 18", big), ("stuffed snake tube, notes say stuff", tube)]:
    out = T._assets_build_full(c)
    print(name, "closed=", L.closed_stuffed_form(c), "status", out["status"], "held", out["outputs"].get("held"), "out", {k:(v if k!="blocking_image_problems" else str(v)[:150]) for k,v in out["outputs"].items()}, "err", out["error"][:120])
# a pacifier strap: flat_rows basket-like strap, title "Pacifier Clip"
basket = inventory._engineered("market-basket-small")
strap = dc.replace(basket, slug="pacifier-clip-b411", title="Pacifier Clip Strap")
out = T._assets_build_full(strap)
print("pacifier clip", out["outputs"], out["status"], "held", out["outputs"].get("held"), "err", out["error"][:120])
