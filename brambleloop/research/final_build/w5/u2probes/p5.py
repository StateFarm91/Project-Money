import _tmp; _tmp.install()
import dataclasses as dc, sys, hashlib
sys.path.insert(0, "tests")
import test_a1r_child_safety_core as T
from p3lib import rows_from
from brambleloop.publish import pdf
ball = T._one_piece_ball()
big = dc.replace(ball, slug="juniper-pouf-b411", components=[dc.replace(ball.components[0], rows=rows_from([6,12,18,24,30,36,36,36,30,24,18]))])
for name, c in [("control one-piece ball", ball), ("big ball closing at 18", big)]:
    try:
        b = pdf.build_pattern_pdf(c)
        b = b if isinstance(b,(bytes,bytearray)) else getattr(b,"pdf",b)
        print(name, "RENDERED", type(b).__name__, len(b) if hasattr(b,'__len__') else '')
    except Exception as e:
        print(name, "REFUSED", type(e).__name__, str(e)[:100])
