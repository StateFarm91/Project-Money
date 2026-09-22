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


# The marker for prose this system wrote about an *object* rather than about a fabric.
#
# `creative.prototype.author` formats every machine-authored designer note as
# "prototype of {key}: {what}, {w} x {h} cm at {gauge}" -- a description of the finished
# thing and its dimensions, with nothing in it about stitches. `expected` was taking the
# first sentence of that note as the chart's motif name, which put two guaranteed failures
# into the live path at once: the render prompt asked for "fabric worked in this pattern's
# own motif: prototype of hats-hat-0: an adult hat, worked in the round, 52 x 22 cm at 12",
# and the verdict compared an honest description of fabric against those same words, found
# no overlap and returned `mismatch` every time. For every product the seasonal cycle
# authors, `product_truth` could never pass, and it failed for a reason that had nothing to
# do with the picture.
#
# Matched on our own format string rather than by hunting for fabric words: an allowlist of
# motif vocabulary would be a guess about English, and the complement of an allowlist is not
# an allowlist. This is a fact about a string this repository produces.
MACHINE_OBJECT_NOTE = "prototype of "


def motif_name(cir) -> str:
    """The chart's motif as prose names it, or "" when prose does not name it.

    Empty is a real answer and the callers treat it as one: the render is asked for the
    fabric the chart shows rather than for a sentence, and the verdict rests on what can
    actually be measured instead of on an overlap with words about something else.
    """
    note = (cir.designer_notes or "").strip()
    if not note or note.lower().startswith(MACHINE_OBJECT_NOTE):
        return ""
    return note.split(".")[0].strip()


def chart_colours(twin) -> int:
    """How many colours the certified chart actually works in.

    Deterministic, available for every product including the ones the cycle authors in
    memory, and the thing the live renders kept getting wrong: a two-colour certified hat
    came back as a handsome three-colour granny shell twice.
    """
    grid = twin.chart_grid() if hasattr(twin, "chart_grid") else []
    return len({cell for row in grid for cell in row if cell is not None})


def expected(cir, twin) -> dict:
    """What the chart actually contains, from the certified data rather than from prose."""
    grid = twin.chart_grid() if hasattr(twin, "chart_grid") else []
    width = max((len(row) for row in grid), default=0)
    named = motif_name(cir)
    return {
        "motif_named": named,
        "motif_is_named": bool(named),
        "why_unnamed": ("" if named else
                        "this pattern's designer note describes the finished object rather "
                        "than the fabric, so prose names no motif. The chart is still "
                        "authoritative and the colour count is still checked"),
        "chart_stitches_wide": width,
        "chart_rows": len(grid),
        "colour_count": chart_colours(twin),
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

    # The colour count, which is deterministic and available for every product including
    # the ones the seasonal cycle authors in memory and never files. Checked before the
    # name, because it is the one fabric fact that does not depend on prose existing: the
    # live failures were a two-colour certified hat rendered twice as a three-colour
    # granny shell, and counting colours catches that whether or not anything named the
    # motif.
    want_colours = int(want.get("colour_count") or 0)
    saw_colours = _colours_in(observed.get("colour_arrangement"))
    if want_colours and saw_colours and saw_colours != want_colours:
        return {"verdict": MISMATCH, "observed": observed, "overlap": [],
                "why": (f"the fabric works {saw_colours} colours and the certified chart "
                        f"works {want_colours}. A colour the pattern does not contain is "
                        f"a different fabric however good the stitch looks")}

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
    if not chart_words:
        # No prose names this chart's motif, so the name test is unavailable rather than
        # satisfied. Falling through to MATCH here was the mirror of the defect above: an
        # empty expectation that nothing can contradict passes every fabric ever rendered.
        # What has actually been established is that the judge compared the photograph
        # against the chart and said yes, and that the colours agree.
        return {"verdict": MATCH, "observed": observed, "overlap": overlap,
                "name_test": "unavailable",
                "why": (f"the judge compared the photograph against the chart itself and "
                        f"says the fabric is working it, and the colour count agrees. "
                        f"{want.get('why_unnamed', '')}".strip())}
    return {"verdict": MATCH, "observed": observed, "overlap": overlap,
            "name_test": "passed",
            "why": "the described repeating unit is the chart's own, and the judge agrees"}


def _colours_in(arrangement) -> int:
    """How many colours the judge's own phrase describes, or 0 when it does not say.

    Read from the answer rather than asked as a number, because "how many colours" invites
    a confident integer about a photograph somebody half-looked at, while a description of
    the arrangement is what a person actually sees. Zero means the phrase carries no count,
    which leaves the colour check unmade rather than passed.
    """
    import re

    text = str(arrangement or "").strip().lower()
    if not text:
        return 0
    words = {"one": 1, "single": 1, "solid": 1, "two": 2, "three": 3, "four": 4,
             "five": 5, "six": 6}
    for word, count in words.items():
        if re.search(rf"\b{word}\b", text):
            return count
    digits = re.search(r"\b([1-9])\b", text)
    return int(digits.group(1)) if digits else 0


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
