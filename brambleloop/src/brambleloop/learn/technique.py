"""Deterministic technique diagrams for lessons, and a verifier that reads what is drawn (F-806).

Master v0.24 F-806: educational stitch diagrams must show the correct loops, insertion points,
yarn overs, posts and orientation; generic imagery cannot illustrate a different stitch because
it looks attractive. Until this module the only control was a human `visual_accuracy`
attestation, honestly labelled `automated_truth_proof: false`. That attestation stays (nothing
here loosens the review contract); this adds the measured half for diagrams:

* `technique(code, loop)` is the canonical working sequence of one stitch: the yarn overs
  before insertion, where the hook goes in (both loops, front loop, back loop, around the post
  from the front or from the back), and how many loops each pull-through closes. It is a table
  of crochet facts, cross-checked against `cir.stitches` so a code the CIR does not know has no
  diagram.
* `render(code, loop)` draws that sequence as an SVG, deterministically (same input, same
  bytes), one panel per stage.
* `verify(svg, claimed_stitch, loop)` re-derives the sequence from the DRAWN primitives -- the
  loop ellipses on the hook in each panel, the yarn-over strokes, where the insertion marker
  sits against the drawn stitch top and post, the direction-of-work arrow -- and compares it to
  the canonical sequence for the stitch the diagram claims to show. Labels and data attributes
  are not trusted: a single-crochet drawing relabelled `dc` fails, because a dc has a yarn over
  before insertion, three loops after pulling up and two pull-throughs, and the drawing has none
  of that.

Photographs and generic images are a different matter: nothing here can read loops off a
photo, so `learn.service.validate_spec` refuses any asset that claims to illustrate a stitch
unless it is a diagram this module generated and verified. That is a refusal, not a pass.
"""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from ..cir import stitches

SVG_NS = "http://www.w3.org/2000/svg"

# Insertion targets, and where each one is drawn on the stitch-top glyph. The verifier maps a
# drawn marker back to a target by these anchors, so a marker drawn on the back loop of a
# diagram that claims "front loop only" is a different technique, whatever its label says.
INSERTION_ANCHORS: dict[str, tuple[float, float]] = {
    "both": (60.0, 152.0),        # under both top loops
    "front": (48.0, 146.0),       # front loop only
    "back": (72.0, 146.0),        # back loop only
    "post_front": (40.0, 182.0),  # around the post, hook entering from the front
    "post_back": (80.0, 182.0),   # around the post, hook entering from the back
}
ANCHOR_TOLERANCE = 3.0
PANEL_WIDTH = 120
PANEL_HEIGHT = 220


class UnsupportedTechnique(ValueError):
    """A stitch or loop with no canonical working sequence here: no diagram is claimed."""


class DiagramRefused(ValueError):
    """A diagram whose drawing does not show the technique it claims."""


@dataclass(frozen=True)
class Technique:
    code: str
    yarn_overs_before: int
    insertion: str
    # Loops each yarn-over closes after the loop is pulled up, in order. Each closes `k` loops
    # into one, so the hook goes from n to n-k+1 loops.
    pull_throughs: tuple[int, ...]

    def stages(self) -> list[dict]:
        """The canonical sequence a correct diagram must draw, panel by panel."""
        loops = 1
        out = [{"action": "start", "loops": loops, "yarn_over": False, "insertion": None}]
        for _ in range(self.yarn_overs_before):
            loops += 1
            out.append({"action": "yarn_over", "loops": loops, "yarn_over": True,
                        "insertion": None})
        out.append({"action": "insert", "loops": loops, "yarn_over": False,
                    "insertion": self.insertion})
        loops += 1
        out.append({"action": "pull_up", "loops": loops, "yarn_over": True, "insertion": None})
        for k in self.pull_throughs:
            loops = loops - k + 1
            out.append({"action": f"pull_through_{k}", "loops": loops, "yarn_over": True,
                        "insertion": None})
        return out


# The working sequence of each supported stitch (US names; the CIR is terminology-neutral).
#   sc : insert, yo pull up (2 loops), yo through 2.
#   hdc: yo, insert, yo pull up (3 loops), yo through all 3.
#   dc : yo, insert, yo pull up (3 loops), [yo through 2] twice.
#   tr : yo twice, insert, yo pull up (4 loops), [yo through 2] three times.
#   fpdc / bpdc: a dc worked around the post, from the front / from the back.
_SEQUENCES: dict[str, tuple[int, str, tuple[int, ...]]] = {
    "sc": (0, "top", (2,)),
    "hdc": (1, "top", (3,)),
    "dc": (1, "top", (2, 2)),
    "tr": (2, "top", (2, 2, 2)),
    "fpdc": (1, "post_front", (2, 2)),
    "bpdc": (1, "post_back", (2, 2)),
}
LOOP_CHOICES = ("both", "front", "back")


def supported() -> list[str]:
    return sorted(_SEQUENCES)


def technique(code: str, loop: str = "both") -> Technique:
    if code not in _SEQUENCES:
        raise UnsupportedTechnique(
            f"no canonical working sequence for {code!r}; supported: {supported()}. A stitch "
            f"without one gets no diagram rather than a borrowed one")
    stitches.get(code)  # a code the CIR taxonomy does not know cannot be taught
    yo, where, pulls = _SEQUENCES[code]
    if where == "top":
        if loop not in LOOP_CHOICES:
            raise UnsupportedTechnique(f"loop must be one of {LOOP_CHOICES}, not {loop!r}")
        insertion = loop
    else:
        if loop != "both":
            raise UnsupportedTechnique(f"{code} is worked around the post; it has no "
                                       f"{loop!r}-loop variant")
        insertion = where
    t = Technique(code, yo, insertion, pulls)
    if t.stages()[-1]["loops"] != 1:  # pragma: no cover - table invariant, tested
        raise UnsupportedTechnique(f"{code}: sequence does not finish with one loop")
    return t


# ---- rendering -------------------------------------------------------------------------------


def _f(x: float) -> str:
    return f"{x:.1f}"


def _panel(i: int, stage: dict) -> list[str]:
    ox = i * PANEL_WIDTH
    out = [f'<g class="stage" transform="translate({ox},0)">',
           f'<rect x="2" y="2" width="{PANEL_WIDTH - 4}" height="{PANEL_HEIGHT - 4}" '
           f'fill="none" stroke="#c9c2b8" stroke-width="1"/>',
           # The hook shaft, horizontal, tip to the left (right-handed, working right to left).
           '<path class="hook" d="M14 60 L106 60 M14 60 q-6 -6 0 -10" fill="none" '
           'stroke="#5b4636" stroke-width="3"/>']
    for n in range(stage["loops"]):
        cx = 30 + n * 16
        out.append(f'<ellipse class="loop-on-hook" cx="{cx}" cy="60" rx="6" ry="11" '
                   f'fill="none" stroke="#8a5a44" stroke-width="2"/>')
    if stage["yarn_over"]:
        out.append('<path class="yarn-over" d="M20 30 C 34 10, 52 10, 52 34" fill="none" '
                   'stroke="#3f7d6e" stroke-width="2.5"/>')
    # The stitch the hook works into: its two top loops and its post, always drawn, so the
    # insertion marker has something real to be measured against.
    out.append('<path class="stitch-top front-loop" d="M40 146 q8 -10 16 0" fill="none" '
               'stroke="#6d6258" stroke-width="2"/>')
    out.append('<path class="stitch-top back-loop" d="M64 146 q8 -10 16 0" fill="none" '
               'stroke="#6d6258" stroke-width="2"/>')
    out.append('<path class="stitch-post" d="M60 156 L60 206" fill="none" stroke="#6d6258" '
               'stroke-width="4"/>')
    if stage["insertion"]:
        x, y = INSERTION_ANCHORS[stage["insertion"]]
        out.append(f'<circle class="insertion" cx="{_f(x)}" cy="{_f(y)}" r="4" '
                   f'fill="#c0392b"/>')
    # Direction of work: right-handed rows travel right to left.
    out.append('<path class="work-direction" d="M100 120 L20 120" fill="none" '
               'stroke="#9a9086" stroke-width="1.5" marker-end="url(#arrow)"/>')
    out.append(f'<text x="8" y="{PANEL_HEIGHT - 8}" font-size="9" fill="#4a4038">'
               f'{i + 1}. {stage["action"].replace("_", " ")}</text>')
    out.append("</g>")
    return out


def render(code: str, loop: str = "both") -> bytes:
    """The canonical diagram for one stitch: deterministic SVG bytes."""
    t = technique(code, loop)
    stages = t.stages()
    name = stitches.get(code).name_us
    width = PANEL_WIDTH * len(stages)
    parts = [f'<svg xmlns="{SVG_NS}" viewBox="0 0 {width} {PANEL_HEIGHT}" width="{width}" '
             f'height="{PANEL_HEIGHT}" data-technique="{code}" data-loop="{loop}" '
             f'data-handedness="right">',
             f"<title>{name} ({code}), {loop} loop(s): working sequence</title>",
             '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
             'markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#9a9086"/>'
             '</marker></defs>']
    for i, stage in enumerate(stages):
        parts.extend(_panel(i, stage))
    parts.append("</svg>")
    return "\n".join(parts).encode("utf-8")


def digest(code: str, loop: str = "both") -> str:
    return hashlib.sha256(render(code, loop)).hexdigest()


# ---- verification ----------------------------------------------------------------------------


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _classes(el) -> set[str]:
    return set((el.get("class") or "").split())


def _target_at(x: float, y: float) -> str | None:
    for target, (ax, ay) in INSERTION_ANCHORS.items():
        if abs(x - ax) <= ANCHOR_TOLERANCE and abs(y - ay) <= ANCHOR_TOLERANCE:
            return target
    return None


def read_drawing(svg: bytes) -> dict:
    """The sequence a diagram actually draws, re-derived from its primitives."""
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise DiagramRefused(f"diagram is not well-formed SVG: {exc}") from None
    if _local(root.tag) != "svg":
        raise DiagramRefused("diagram root is not <svg>")
    panels = [g for g in root.iter() if _local(g.tag) == "g" and "stage" in _classes(g)]
    if not panels:
        raise DiagramRefused("diagram draws no stages")
    stages, directions = [], []
    for g in panels:
        loops = yarn_over = 0
        targets = []
        for el in g.iter():
            cls = _classes(el)
            tag = _local(el.tag)
            if tag == "ellipse" and "loop-on-hook" in cls:
                loops += 1
            elif tag == "path" and "yarn-over" in cls:
                yarn_over += 1
            elif tag == "circle" and "insertion" in cls:
                try:
                    x, y = float(el.get("cx")), float(el.get("cy"))
                except (TypeError, ValueError):
                    raise DiagramRefused("insertion marker has no position") from None
                target = _target_at(x, y)
                if target is None:
                    raise DiagramRefused(f"insertion marker at ({x}, {y}) is on no loop or "
                                         f"post of the drawn stitch")
                targets.append(target)
            elif tag == "path" and "work-direction" in cls:
                parts = (el.get("d") or "").replace("M", " ").replace("L", " ").split()
                try:
                    x1, _y1, x2, _y2 = (float(p) for p in parts[:4])
                except ValueError:
                    raise DiagramRefused("direction-of-work arrow is unreadable") from None
                directions.append("right_to_left" if x2 < x1 else "left_to_right")
        if yarn_over > 1 or len(targets) > 1:
            raise DiagramRefused("a stage draws more than one yarn over or insertion")
        stages.append({"loops": loops, "yarn_over": bool(yarn_over),
                       "insertion": targets[0] if targets else None})
    return {"stages": stages, "directions": directions,
            "claimed": root.get("data-technique"), "claimed_loop": root.get("data-loop")}


def verify(svg: bytes, claimed_stitch: str, loop: str = "both") -> dict:
    """Does this drawing show `claimed_stitch` worked into `loop`? Refuses if not."""
    expected = [{k: s[k] for k in ("loops", "yarn_over", "insertion")}
                for s in technique(claimed_stitch, loop).stages()]
    drawn = read_drawing(svg)
    problems = []
    if drawn["stages"] != expected:
        problems.append(
            f"drawn sequence {[(s['loops'], s['yarn_over'], s['insertion']) for s in drawn['stages']]} "
            f"is not the {claimed_stitch} ({loop}) sequence "
            f"{[(s['loops'], s['yarn_over'], s['insertion']) for s in expected]}")
    if not drawn["directions"] or any(d != "right_to_left" for d in drawn["directions"]):
        problems.append("direction of work is missing or not right-to-left for a "
                        "right-handed diagram")
    if problems:
        raise DiagramRefused("; ".join(problems))
    return {"stitch": claimed_stitch, "loop": loop, "stages": len(expected),
            "basis": "measured: sequence re-derived from drawn primitives",
            "sha256": hashlib.sha256(svg).hexdigest()}
