"""Rejected iterations of the winning direction's icon, kept as evidence of the iteration.

D1's emblem (B + sprig + figure-of-eight) cannot be an Etsy icon: at 40 px its blossoms and
strand become noise. The icon was iterated three times; the two rejected versions are kept
here so the contact sheet can show why the shipped one won. Not used by any surface.
"""
from __future__ import annotations

from .directions import ICON, _d1_B, _leaf
from .vector import Circle, Fill, Knockout, Mark, Stroke, cubic_through


def d1_icon_v1() -> Mark:
    """v1 -- B with a yarn curl out of the bowl to a ball. Rejected: at 40 px the curl + ball
    read as a question mark ('B?')."""
    m = Mark("d1-icon-v1", ICON, ICON, title="rejected v1")
    size, bx, base = 410.0, 92.0, 412.0
    yarn = cubic_through([(250, 360), (330, 352), (392, 318), (420, 258), (392, 214),
                          (350, 236), (356, 300), (400, 352), (420, 396)])
    m.add(Stroke(yarn, 30, "yarn"))
    B = _d1_B(size, bx, base)
    m.add(Knockout([Fill(B, "x"), Stroke(B, 22, "x")]))
    m.add(Fill(B, "ink"))
    m.add(Knockout([Circle(412, 410, 52, "x")]))
    m.add(Circle(412, 410, 40, "yarn"))
    _leaf(m, (bx + 46, 112), -124, 104, 30, "leaf", None, 0)
    _leaf(m, (bx + 46, 112), -66, 76, 22, "leaf", None, 0)
    return m


def d1_icon_v2() -> Mark:
    """v2 -- B in a loop whose tail drops to a ball. Rejected: the tail + ball read as an
    exclamation mark ('B!') and the oversized B swallowed the loop in one colour."""
    import math

    m = Mark("d1-icon-v2", ICON, ICON, title="rejected v2")
    cx, cy, r = 248.0, 246.0, 184.0
    pts = [(cx + r * math.cos(math.radians(18 + 372 * i / 93)),
            cy + r * math.sin(math.radians(18 + 372 * i / 93))) for i in range(94)]
    end = pts[-1]
    ball = (cx + 168, cy + 168)
    tail = [(end[0] + 6, end[1] + 30), (ball[0] - 22, ball[1] - 24)]
    m.add(Stroke(cubic_through(pts[:80]), 26, "yarn"))
    B = _d1_B(430.0, cx - 632 * 0.43 / 2 + 4, cy + 750 * 0.43 / 2)
    m.add(Knockout([Fill(B, "x"), Stroke(B, 20, "x")]))
    m.add(Fill(B, "ink"))
    over = cubic_through(pts[79:] + tail)
    m.add(Knockout([Stroke(over, 46, "x")]))
    m.add(Stroke(over, 26, "yarn"))
    m.add(Circle(ball[0], ball[1], 34, "yarn"))
    return m


ITERATIONS = [
    ("v1", d1_icon_v1, "curl + ball read as 'B?' at 40 px"),
    ("v2", d1_icon_v2, "tail + ball read as 'B!'; B swallowed the loop in mono"),
    ("v3 (shipped)", None, "closed loop drawn from a ball; B interlaced with knockouts; "
                           "leaf pair; reads as a monogram seal at 40 px"),
]
