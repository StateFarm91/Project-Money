"""A hand-built amigurumi CIR for exercising the template's amigurumi variant (ENG-PDF-TEMPLATE).

TEST FIXTURE ONLY. It is not a catalogue product, has no children's assignment in
`products.launch0`, and is never drafted, listed or sold. Proofs built from it are
`proof_test_double` and marked NOT CUSTOMER-READY on every page.

Three magic-ring pieces in joined rounds: a head, a body and two ears. Every piece is large
enough to clear the small-parts cylinder (gates.small_parts) at the stated gauge, the face is
embroidered (no safety eyes), and every join is placed by round number, which is what the
assembly steps' placement cues are read from.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.cir.model import CIR, Component, Gauge, Material, Op, Row, Seam  # noqa: E402

SLUG = "fixture-pebble-friend-amigurumi"


def _rounds(counts: list[int], colour: str, *, stuff_at: int | None = None) -> list[Row]:
    rows = []
    for i, n in enumerate(counts):
        prev = counts[i - 1] if i else 0
        if i == 0:
            ops = [Op("sc", n)]
        elif n > prev:
            ops = [Op("inc", n - prev)] + ([Op("sc", 2 * prev - n)] if 2 * prev > n else [])
        elif n < prev:
            ops = [Op("dec", prev - n)] + ([Op("sc", 2 * n - prev)] if 2 * n > prev else [])
        else:
            ops = [Op("sc", n)]
        note = "Stuff firmly now, before the opening closes." if stuff_at == i + 1 else None
        rows.append(Row(index=i + 1, ops=ops, declared_count=n, turning_chain=0, color=colour,
                        note=note))
    return rows


def pebble_friend() -> CIR:
    head = [6, 12, 18, 24, 30, 36, 36, 36, 36, 36, 36, 36, 30, 24, 18, 12, 6]
    body = [6, 12, 18, 24, 30, 36, 42, 42, 42, 42, 42, 42, 36, 30, 24, 18, 12, 6]
    ear = [6, 12, 18, 24, 24, 24]
    gauge = Gauge(stitches_per_10cm=18.0, rows_per_10cm=19.8, stitch_type="sc", hook_mm=4.0,
                  yarn_weight="worsted")
    comps = [
        Component(name="head", construction="joined_rounds", foundation=6,
                  foundation_kind="magic_ring", rows=_rounds(head, "oat", stuff_at=15),
                  note="Worked in joined rounds from a magic ring; the face is embroidered."),
        Component(name="body", construction="joined_rounds", foundation=6,
                  foundation_kind="magic_ring", rows=_rounds(body, "sage", stuff_at=16)),
        Component(name="ear", construction="joined_rounds", foundation=6,
                  foundation_kind="magic_ring", make=2, rows=_rounds(ear, "oat"),
                  note="Leave open; flatten before sewing."),
    ]
    assembly = [
        Seam("whipstitch", "head", "body", at_round=12, spans_rounds=1,
             stuff_before_closing=True,
             note="Sew the head's round 17 opening onto the top of the body."),
        Seam("whipstitch", "ear", "head", at_round=5, spans_rounds=3,
             stitches_from_centre=6, mirrored=True,
             note="Flatten each ear and sew its open edge across the head."),
    ]
    return CIR(slug=SLUG, title="Pebble Friend Amigurumi (fixture)", version="0.0.1",
               construction="joined_rounds", risk_class="C",
               colors={"oat": "#E8DCC4", "sage": "#8FA58A"}, gauge=gauge,
               materials=[Material(name="worsted cotton", yarn_weight="worsted",
                                   colorway="oat", color_id="oat"),
                          Material(name="worsted cotton", yarn_weight="worsted",
                                   colorway="sage", color_id="sage"),
                          Material(name="black cotton embroidery floss (face)"),
                          Material(name="polyester fibrefill")],
               components=comps, assembly=assembly)


CHILDRENS = ("amigurumi_toy", "three_to_six")
