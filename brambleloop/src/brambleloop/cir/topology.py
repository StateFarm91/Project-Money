"""Construction order and relationships as Product Truth (F-750).

The CIR already knew how each piece is worked (flat rows, joined or spiral rounds), which way
its fabric runs (`Component.grain`), which stitches a piece sets aside and which piece picks
them up (`Hold` / `resumes`), and every join (`Seam`). What it could not say was the ORDER of
construction as one object, which way each piece is worked (top-down, bottom-up, side to
side, centre out), and what each piece IS (a sleeve, a band, a hood, a pocket). Two garments
with the same silhouette -- sleeves picked up from the yoke and worked down, versus sleeves
worked separately and sewn in -- are different products, and nothing measured that.

`construction_steps` derives the ordered construction from the CIR alone; `construction_
fingerprint` hashes it, so a change of construction (built-in to seamed sleeves, top-down to
bottom-up) is a change of identity that certification and the similarity review can see;
`topology_problems` refuses a declared construction that contradicts the rows.
"""
from __future__ import annotations

import hashlib
import json

from .model import CIR, Component

DIRECTION_WORDS: dict[str, str] = {
    "bottom_up": "from the bottom up",
    "top_down": "from the top down",
    "side_to_side": "from side to side",
    "centre_out": "from the centre out",
}


def direction_line(comp: Component) -> str:
    """The sentence the writer prints for a piece that declares its work direction."""
    if comp.work_direction is None:
        return ""
    return f"Worked {DIRECTION_WORDS[comp.work_direction]}."


def _is_sleeve(comp: Component) -> bool:
    return comp.feature == "sleeve" or (comp.feature is None and "sleeve" in comp.name)


def sleeve_attachment(cir: CIR, comp: Component) -> str | None:
    """'built_in' (picked up from held stitches), 'seamed' (worked separately and joined),
    'unattached' (a sleeve nothing joins), or None for a piece that is not a sleeve."""
    if not _is_sleeve(comp):
        return None
    if comp.resumes:
        return "built_in"
    if any(s.piece_a == comp.name and s.piece_b != comp.name
           or s.piece_b == comp.name and s.piece_a != comp.name for s in cir.assembly):
        return "seamed"
    return "unattached"


def construction_steps(cir: CIR) -> list[dict]:
    """Every construction step, in the order the maker works them."""
    steps: list[dict] = []
    for comp in cir.components:
        start = (f"resume:{comp.resumes}" if comp.resumes
                 else f"{comp.foundation_kind}:{comp.foundation}")
        steps.append({
            "step": "work", "piece": comp.name, "feature": comp.feature,
            "worked": comp.construction, "direction": comp.work_direction,
            "grain": comp.grain, "make": comp.make, "starts": start,
            "holds": [[h.name, h.at_row, h.count] for h in comp.holds],
            "sleeve": sleeve_attachment(cir, comp)})
    for seam in cir.assembly:
        steps.append({"step": "join", "a": seam.piece_a, "b": seam.piece_b,
                      "method": seam.method, "edges": [seam.edge_a, seam.edge_b],
                      "at": seam.at_round})
    return steps


def construction_fingerprint(cir: CIR) -> str:
    payload = json.dumps(construction_steps(cir), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def topology_problems(cir: CIR) -> list[str]:
    """A declared construction that the rows contradict."""
    out: list[str] = []
    by_name = {c.name: c for c in cir.components}
    holders = {h.name: c for c in cir.components for h in c.holds}
    for comp in cir.components:
        d = comp.work_direction
        if d == "side_to_side" and comp.grain != "across":
            out.append(f"{comp.name} is declared worked side to side but its grain is "
                       f"{comp.grain!r}; side-to-side rows run across the body")
        if comp.grain == "across" and d not in (None, "side_to_side"):
            out.append(f"{comp.name} has grain 'across' but is declared worked "
                       f"{DIRECTION_WORDS[d]}")
        if d == "centre_out" and "round" not in comp.construction:
            out.append(f"{comp.name} is declared worked from the centre out but is worked "
                       f"in {comp.construction}")
        if comp.resumes:
            parent = holders.get(comp.resumes)
            if parent is not None and d is not None and parent.work_direction is not None \
                    and parent.work_direction != d:
                out.append(f"{comp.name} continues from stitches {parent.name} held, so it "
                           f"is worked in the same direction ({parent.work_direction}), not "
                           f"{d}")
        if sleeve_attachment(cir, comp) == "unattached":
            out.append(f"{comp.name} is a sleeve that no join attaches and no held stitches "
                       f"start, so the instructions never put it on the garment")
    for seam in cir.assembly:
        for piece in (seam.piece_a, seam.piece_b):
            if piece not in by_name:
                out.append(f"a join names {piece!r}, which is not a piece of this design")
    return out
