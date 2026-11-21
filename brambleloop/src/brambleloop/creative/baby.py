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
# Who a lovey is for, not what its head is.
_LOVEY_AUDIENCE = r"\b(?:baby|babies|baby's|nursery|infant|newborn|toddler)\b"


def lovey_route(title: str | None) -> dict:
    """A plain bear or bunny lovey; anything else held by name."""
    from . import fallback_constructions as FC

    t = FC.fold_title(title)
    if not re.search(_LOVEY_WORDS, t):
        return {"family": FC.REFUSED, "needs": "a lovey title", "why": "not a lovey"}
    animal_title = re.sub(_LOVEY_WORDS, "", t).strip()
    if not re.sub(_LOVEY_AUDIENCE, "", animal_title).strip():
        # CERTFIX-3: a title naming no head ("Baby Lovey") is the plain lovey object, which
        # has no cited size band (D-S1-SIZE-FAMILIES); it is not silently drafted as a bear
        # the title never named. "Bear Lovey" / "Baby Bunny Lovey" name the head and draft.
        return {"family": FC.REFUSED,
                "needs": "a size band and a template that make the size the title names, "
                         "or a head the title names (bear or bunny)",
                "why": "the title names no lovey head, and a lovey square on its own has no "
                       "size band"}
    animal_title = re.sub(_LOVEY_AUDIENCE, "", animal_title).strip()
    # ENG-AMIGURUMI-BREADTH: a sleepy face is an embroidered variant (closed eyes), and a lamb
    # head is the same closed head with its own ears (LOVEY_HEADS); both are read here and the
    # rest of the title is held to the ball-body head's own vocabulary.
    sleepy = bool(re.search(r"\bsleepy\b", animal_title))
    animal_title = re.sub(r"\bsleepy\b", "", animal_title).strip()
    lamb = re.search(r"\b(?:lamb|sheep)\b", animal_title)
    if lamb:
        animal_title = re.sub(r"\b(?:lamb|sheep)\b", "bear", animal_title)
    if not re.search(r"\b(?:bear|bunny|rabbit|teddy)\b", animal_title):
        animal_title = f"{animal_title} bear".strip()
    head = FC.amigurumi_route(animal_title.title())
    if head["family"] != FC.AMIGURUMI:
        return {"family": FC.REFUSED, "needs": head.get("needs", ""),
                "why": f"the lovey's head: {head['why']}"}
    if lamb and head["kind"] != "bear":
        return {"family": FC.REFUSED, "needs": "one head per lovey",
                "why": "the lovey's head: the title names a lamb and another animal"}
    return {"family": "lovey", "kind": "lamb" if lamb else head["kind"], "needs": "",
            "sleepy": sleepy,
            "why": "a closed amigurumi head sewn to the centre of a flat square"}


# ENG-AMIGURUMI-BREADTH: lovey heads beyond the ball-body bear and bunny. Each is the same
# closed 36-st head (so every closure, stuffing and small-parts reading is the slice 1 head's)
# with its own ears: (plain rounds after the ear's increases, its shaping note). House design.
LOVEY_HEADS: dict[str, dict] = {
    "lamb": {"base": "bear", "plain": 4,
             "note": "a soft drooping ear: flatten the cup so its opening closes into a "
                     "straight edge, and sew it on pointing outwards and down"},
}
SLEEPY_EYES = ("two closed, sleepy eyes, each a curved line of 3 backstitches over 1 st each")


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
    spec = LOVEY_HEADS.get(kind)
    head_concept.title = "Ball " + (spec["base"] if spec else kind).title()
    head = FC.amigurumi(head_concept)
    if spec is not None:
        # The base head's ear with this head's own plain rounds and note.
        ear0 = head.components[1]
        widest = ear0.rows[-1 - FC.AMI_ANIMALS[spec["base"]]["plain"]].declared_count
        incs = ear0.rows[:len(ear0.rows) - FC.AMI_ANIMALS[spec["base"]]["plain"]]
        rows = [dataclasses.replace(r) for r in incs]
        for i in range(spec["plain"]):
            rows.append(Row(index=len(rows) + 1, ops=[Op("sc", widest)], declared_count=widest,
                            color=incs[-1].color))
        rows[-1].note = ear0.rows[-1].note
        head.components[1] = dataclasses.replace(
            ear0, rows=rows, note=f"Make 2. Unstuffed: {spec['note']}.")
    if route.get("sleepy"):
        body0 = head.components[0]
        head.components[0] = dataclasses.replace(body0, note=body0.note.replace(
            "two eyes of 4 or 5 straight stitches over 1 st each", SLEEPY_EYES))
        head.assembly[0] = dataclasses.replace(head.assembly[0], note=head.assembly[0].note
                                               .replace("two eyes of 4 or 5 straight stitches "
                                                        "over 1 st each", SLEEPY_EYES))
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
