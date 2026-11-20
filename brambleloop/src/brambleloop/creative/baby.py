"""ENG-PLUSH slice 3: baby items (D-OWNER-CORE-FAMILIES), under the child-safety gate.

* Baby blankets are the verified flat-panel family (`construction_families` FLAT_PANEL,
  category "baby"); this module adds nothing to their construction. They are inside
  `gates.child_safety` by their child words (profile: base + sleep), so every baby blanket PDF
  carries the safety section with the safe-sleep statement and its citations.
* Simple flat baby garments are HELD: grading a garment for a baby needs the sourced body
  measurements and ease the radar draft path does not carry (`construction_families` holds
  every garment by name, `UNBUILT["garment"]`).
* `lovey` -- an amigurumi head (the slice 1 closed spiral ball with two ears, stuffed after its
  stated round and closed) sewn to the centre of a flat square by a SURFACE join that
  `cir.assembly` checks lies inside the square. Embroidered features only; no cords, no
  loops; the square has no border of picots, loops or tassels.

A lovey is for supervised, awake use: the safe-sleep statement is required by its profile
(`child_safety` "sleep"), and certification withholds for physical evidence (seam pull on the
head, closure, stuffing) that nothing can yet bind -- HELD, never PASS.
"""
from __future__ import annotations

import dataclasses
import re

from ..cir.model import CIR, Component, Material, Op, Row, Seam

LOVEY_SQUARE_CM = 30.0            # a lovey square, design choice (stated, not a standard)
LOVEY_HEAD_STITCHES = 36          # the slice 1 body: the head
_LOVEY_WORDS = r"\b(?:lovey|loveys|comforter|security blanket|snuggle square)\b"


def lovey_route(title: str | None) -> dict:
    """A plain bear or bunny lovey; anything else held by name."""
    from . import fallback_constructions as FC

    t = FC.fold_title(title)
    if not re.search(_LOVEY_WORDS, t):
        return {"family": FC.REFUSED, "needs": "a lovey title", "why": "not a lovey"}
    animal_title = re.sub(_LOVEY_WORDS, "", t).strip() or "bear"
    if not re.search(r"\b(?:bear|bunny|rabbit|teddy)\b", animal_title):
        animal_title = f"{animal_title} bear".strip()
    head = FC.amigurumi_route(animal_title.title())
    if head["family"] != FC.AMIGURUMI:
        return {"family": FC.REFUSED, "needs": head.get("needs", ""),
                "why": f"the lovey's head: {head['why']}"}
    return {"family": "lovey", "kind": head["kind"], "needs": "",
            "why": "a closed amigurumi head sewn to the centre of a flat square"}


def lovey(concept, *, version: str = "1.0.0", provenance=None) -> CIR:
    from . import fallback_constructions as FC
    from .prototype import gauge_for

    route = lovey_route(concept.title)
    if route["family"] != "lovey":
        raise ValueError(f"{concept.slug}: {route['why']}")
    kind = route["kind"]
    head_concept = dataclasses.replace(concept) if dataclasses.is_dataclass(concept) else \
        type("C", (), {})()
    for attr in ("slug", "category", "colors", "yarn_weight"):
        setattr(head_concept, attr, getattr(concept, attr))
    head_concept.title = "Ball " + kind.title()
    head = FC.amigurumi(head_concept)
    palette = list(dict.fromkeys(concept.colors))
    gauge = gauge_for(concept.yarn_weight)
    sts = int(round(LOVEY_SQUARE_CM * gauge.stitches_per_10cm / 10.0))
    n_rows = int(round(LOVEY_SQUARE_CM * gauge.rows_per_10cm / 10.0))
    square_colour = palette[-1]
    square = Component(name="square", construction="flat_rows", foundation=sts,
                       foundation_kind="chain",
                       note="Worked flat; a plain square whose every edge is a stitched edge, with nothing added to it.",
                       rows=[Row(index=i, ops=[Op("sc", sts)], declared_count=sts,
                                 turning_chain=1, color=square_colour)
                             for i in range(1, n_rows + 1)])
    body, ear = head.components
    head_piece = dataclasses.replace(body, name="head")
    ear_seam = dataclasses.replace(head.assembly[0], piece_b="head")
    centre_row = (n_rows + 1) // 2
    attach = Seam("sew", "head", "square", edge_a="bottom", edge_b="surface",
                  at_round=centre_row, spans_rounds=1, stitches_from_centre=0,
                  note=(f"Centre the head's closed end on row {centre_row} of the square, on "
                        f"the centre line; sew all round the head's last 4 rounds through both "
                        f"loops and the square, around twice, knot on the wrong side and bury "
                        f"the tail through at least 5 cm of stitches"))
    materials = [m for m in head.materials if m.yarn_weight] + [
        Material(name="new polyester fibrefill (toy stuffing) for the head")]
    if square_colour not in {m.color_id for m in materials}:
        materials.insert(0, Material(name=f"{concept.yarn_weight} acrylic",
                                     yarn_weight=concept.yarn_weight, color_id=square_colour))
    return CIR(
        slug=concept.slug, title=concept.title, version=version, construction="flat_rows",
        risk_class="C", colors=dict(concept.colors), gauge=gauge, materials=materials,
        components=[square, head_piece, ear], assembly=[ear_seam, attach],
        designer_notes=(f"{concept.category} concept drafted as a {kind} lovey: a {sts}-st x "
                        f"{n_rows}-row square and a closed, stuffed {LOVEY_HEAD_STITCHES}-st head "
                        f"with two ears, sewn to the centre. Features embroidered with yarn "
                        f"only."),
        finished_size_note=(f"The square is about {LOVEY_SQUARE_CM:.0f} x {LOVEY_SQUARE_CM:.0f} "
                            f"cm at the stated gauge; the head is about "
                            f"{LOVEY_HEAD_STITCHES / gauge.stitches_per_10cm * 10:.0f} cm around. "
                            f"Computed, not yet measured on a worked sample."),
        provenance=provenance,
    )
