"""Does the fabric in the picture show the pattern the buyer will make?

The gap this closes was found by the check that missed it. The first owned product asset was
a clean, believable crocheted blanket: right two colours, right surface, right light,
plausible drape, no artefacts, no third-party marks -- worked in a checkerboard, while the
certified pattern makes a diamond lattice on a nine-stitch repeat. The asset-truth gate
passed it, correctly by its own terms. It asks whether the frame shows a finished object
rather than a chart, whether anybody is in it, whether it is legible, whether somebody
else's mark is in the frame. The describer's vocabulary is closed on purpose -- an open one
accepts "a lovely blanket" -- and it had no field for the motif.

The owner's rule, and it is the right one: *where the certified pattern specifies a motif,
stitch structure, repeat or other visually material construction feature, customer-facing
imagery must faithfully represent it or be blocked. A checkerboard image for a diamond-
lattice pattern is a failure even if everything else looks convincing.*

How this asks the question matters, because the obvious way is wrong.

**The comparison is against a picture, not a description.** The chart renders
deterministically from the certified CIR and is the same data the written instructions come
from, so it cannot disagree with the pattern. Asking a model to compare the photograph to
the chart is a question about two images in front of it. Asking whether a photograph "shows
a diamond lattice" is a question about a phrase, and a generator that produced squares will
happily be told they are diamonds.

**It is not told which answer is wanted.** Same rule as `inspect.compare`: the judge
describes what the fabric does -- the repeating unit, its shape, its scale relative to the
piece, whether the two colours alternate the way the chart does -- and deterministic code
decides whether that is the chart's pattern. A grader shown the expected result grades
toward it.

**Three verdicts.** `match`, `mismatch`, and `unmeasurable` when the fabric cannot be seen
well enough to judge -- a folded blanket photographed at distance, a garment in shadow. The
third blocks exactly like the second does for a customer-facing asset, because an image
whose fabric nobody could check is not an image whose fabric is right. The difference is
what to do next: a mismatch needs a different render, an unmeasurable one needs a closer
frame.
"""
from __future__ import annotations

TASK = "asset_inspection"

MATCH = "match"
MISMATCH = "mismatch"
UNMEASURABLE = "unmeasurable"
VERDICTS = frozenset({MATCH, MISMATCH, UNMEASURABLE})

MAX_TOKENS = 500

# The closed vocabulary the judge answers in. Same discipline as the describer: an open
# vocabulary accepts "a lovely texture", and a check whose evidence is that cannot disagree
# with anything.
FIELDS: tuple[str, ...] = (
    "repeating_unit_shape",      # what one repeat looks like: diamond, square, chevron, ...
    "repeats_across",            # roughly how many repeats span the piece
    "colour_arrangement",        # how the colours sit in the repeat
    "same_pattern_as_chart",     # the direct question, and the one it is worst at alone
    "fabric_readable",           # whether the fabric can be seen well enough at all
)

SYSTEM = (
    "You are comparing the stitch pattern in a photograph of a finished crocheted piece "
    "against the chart that piece is made from. The chart is authoritative: it is generated "
    "from the same verified data as the written instructions. You are not judging whether "
    "the photograph is attractive, well lit or well styled, and you are not being asked "
    "whether it is a good picture. You are answering one question: is the fabric in the "
    "photograph working the pattern in the chart. Say so plainly when the fabric cannot be "
    "seen well enough to tell -- folded, distant, shadowed or out of focus -- because a "
    "guess is worse than an admission here."
)


def prompt() -> str:
    return (
        "The first image is a photograph of the finished piece. The second is the chart it "
        "is supposed to be worked from, one cell per stitch.\n\n"
        "Answer as JSON with exactly these keys:\n"
        '  "repeating_unit_shape": what one repeating unit in the PHOTOGRAPH looks like, '
        'in a few words (for example "diamond outline", "solid square", "chevron band", '
        '"no visible repeat")\n'
        '  "repeats_across": roughly how many times that unit repeats across the width of '
        "the piece in the photograph, as a number, or null if it cannot be counted\n"
        '  "colour_arrangement": how the colours sit within one repeat in the PHOTOGRAPH\n'
        '  "same_pattern_as_chart": true, false or null -- whether the photograph\'s fabric '
        "is working the chart's pattern; null if it cannot be told\n"
        '  "fabric_readable": true or false -- whether the stitch pattern is visible well '
        "enough in the photograph to judge at all\n\n"
        "Describe what you see in the photograph. Do not assume it matches."
    )


class MotifRefused(ValueError):
    """An answer outside the closed vocabulary, or with holes in it."""


def parse(text: str) -> dict:
    import json
    import re

    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        raise MotifRefused("no JSON object in the answer")
    parsed = json.loads(match.group(0))
    unknown = sorted(k for k in parsed if k not in FIELDS)
    if unknown:
        raise MotifRefused(
            f"{unknown} are not motif fields. The vocabulary is closed because an open one "
            f"accepts 'a lovely texture', and a check whose evidence is that cannot "
            f"disagree with any image ever rendered")
    missing = [f for f in FIELDS if f not in parsed]
    if missing:
        raise MotifRefused(
            f"{missing} were not answered. A description with holes in it passes by not "
            f"contradicting anything")
    return parsed


def expected(cir, twin) -> dict:
    """What the chart actually contains, from the certified data rather than from prose."""
    note = (cir.designer_notes or "").strip()
    motif = note.split(".")[0].strip() if note else ""
    grid = twin.chart_grid() if hasattr(twin, "chart_grid") else []
    width = max((len(row) for row in grid), default=0)
    return {
        "motif_named": motif,
        "chart_stitches_wide": width,
        "chart_rows": len(grid),
        "colours": sorted((cir.colors or {}).keys()),
        "source": "the certified CIR and its twin, which the written instructions come from",
    }


def judge(observed: dict, want: dict, *, repeat_tolerance: float = 0.5) -> dict:
    """Deterministic verdict from what the judge described. It never sees this function.

    `same_pattern_as_chart` is asked and is not trusted alone: it is the question a model
    most wants to answer politely, and the first live failure was a picture whose everything
    else was right. So a `true` there with a repeating unit that does not appear in the
    chart's own description is a mismatch, not a match.
    """
    if not observed:
        return {"verdict": UNMEASURABLE, "why": "nothing was observed"}
    if observed.get("fabric_readable") is not True:
        return {"verdict": UNMEASURABLE, "observed": observed,
                "why": ("the fabric could not be seen well enough to judge. A closer or "
                        "flatter frame is what this needs, not a different pattern")}

    said = observed.get("same_pattern_as_chart")
    shape = str(observed.get("repeating_unit_shape") or "").strip().lower()
    named = str(want.get("motif_named") or "").strip().lower()

    # The words the chart's own name uses, against the words the judge used for the shape.
    # Both are short phrases about the same thing, so an overlap is meaningful and the
    # absence of one is the signal that caught the checkerboard.
    stop = {"on", "a", "the", "and", "of", "in", "with", "repeat", "stitch", "row", "rows"}
    chart_words = {w for w in named.replace("-", " ").split() if w and w not in stop}
    shape_words = {w for w in shape.replace("-", " ").split() if w and w not in stop}
    overlap = sorted(chart_words & shape_words)

    if said is False:
        return {"verdict": MISMATCH, "observed": observed, "overlap": overlap,
                "why": "the judge says the fabric is not working the chart's pattern"}
    if said is None:
        return {"verdict": UNMEASURABLE, "observed": observed, "overlap": overlap,
                "why": "the judge could not tell whether the fabric matches the chart"}
    if not overlap and chart_words:
        return {"verdict": MISMATCH, "observed": observed, "overlap": overlap,
                "why": (f"the judge answered yes and described the repeating unit as "
                        f"{shape!r}, which shares no term with the chart's own "
                        f"{named!r}. A polite yes and a contradicting description is the "
                        f"shape of the failure this check was built for")}
    return {"verdict": MATCH, "observed": observed, "overlap": overlap,
            "why": "the described repeating unit is the chart's own, and the judge agrees"}


def chart_image(cir, twin, *, work_dir: str = "") -> str:
    """The certified chart as a picture, for a caller that wants to condition on it.

    The same render `check` compares against, exposed so the generator can be *shown* the
    fabric rather than told about it. "Patterns are software releases" cuts both ways: the
    chart is deterministic output from the certified CIR, so it is the one description of
    the fabric that cannot drift, and handing a generator a sentence about a diamond
    lattice while checking the result against the lattice itself is asking one question and
    grading another.

    Returns "" rather than raising: a chart that will not render is a reason not to
    condition on one, never a reason to fail the render.
    """
    import tempfile
    from pathlib import Path

    from .charts import ChartSpec, render_chart

    try:
        chart = render_chart(cir, twin, ChartSpec(cell_px=18))
        out = Path(work_dir or tempfile.mkdtemp(prefix="motif-chart-")) / "chart-ref.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        chart.save(str(out))
        return str(out)
    except Exception:  # noqa: BLE001 - conditioning on nothing is the fallback
        return ""


def check(db, image_ref: str, cir, twin, *, provider=None, judger=None) -> dict:
    """Render the chart, show both, and decide. Blocks a customer-facing asset unless match."""
    import tempfile
    from pathlib import Path

    from ..gateway import anthropic as gw
    from .charts import ChartSpec, render_chart

    want = expected(cir, twin)
    chart_path = ""
    try:
        chart = render_chart(cir, twin, ChartSpec(cell_px=18))
        chart_path = str(Path(tempfile.mkdtemp(prefix="motif-chart-")) / "chart.png")
        chart.save(chart_path)
    except Exception as exc:  # noqa: BLE001 - a chart that will not render is a refusal
        return {"verdict": UNMEASURABLE, "expected": want,
                "why": f"the chart could not be rendered to compare against: {exc}"[:200]}

    if judger is not None:
        answer = judger(image_ref, chart_path)
    else:
        provider = provider or gw.provider_for(TASK)
        try:
            response = provider.see(SYSTEM, prompt(), [image_ref, chart_path],
                                    max_tokens=MAX_TOKENS)
        except Exception as exc:  # noqa: BLE001
            return {"verdict": UNMEASURABLE, "expected": want,
                    "why": f"the comparison call failed: {exc}"[:240]}
        try:
            answer = parse(response.text)
        except (MotifRefused, ValueError) as exc:
            return {"verdict": UNMEASURABLE, "expected": want,
                    "why": f"the answer could not be read: {exc}"[:240]}

    out = judge(answer, want)
    out["expected"] = want
    out["chart"] = chart_path
    out["blocks_customer_facing_asset"] = out["verdict"] != MATCH
    out["why_unmeasurable_blocks_too"] = (
        "an image whose fabric nobody could check is not an image whose fabric is right. "
        "The difference is what to do next: a mismatch needs a different render, an "
        "unmeasurable one needs a closer frame")
    return out
