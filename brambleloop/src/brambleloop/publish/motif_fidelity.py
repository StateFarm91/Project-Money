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

# Whose daily permission and which purpose this call is reserved and billed under. The motif
# judgement is an asset-truth judgement on the same render `visual.inspect.inspect_image`
# judges in the same job, so it is the same agent and the same purpose: the quality
# director's `asset_inspection` permission, inside its existing ceilings. Not a new agent and
# not a new allowance -- a second line on the bill the frame review already pays.
AGENT = "quality_director"
DEPARTMENT = "quality"

# Why a verdict came back UNMEASURABLE, as a code a caller can branch on. Only the first group
# says nothing about the picture: the question was never put (or never answered) for a reason
# that is about money, permission or plumbing, so the render -- already paid for -- is still
# a candidate and the right next move is to ask again later about the *same* image rather
# than render a new one. The second group is about the picture or the answer, and re-asking
# would buy the same unreadable frame twice.
UNMEASURED_NO_LEDGER = "no_accounting_store"
UNMEASURED_BUDGET = "budget_refused"
UNMEASURED_GATE = "gate_refused"
UNMEASURED_TRANSIENT = "call_failed_transient"
UNMEASURED_IMAGE_MISSING = "image_missing"
UNMEASURED_CALL = "call_failed"
UNMEASURED_ANSWER = "answer_unreadable"
UNMEASURED_CHART = "chart_unrenderable"
REJUDGEABLE = frozenset({UNMEASURED_NO_LEDGER, UNMEASURED_BUDGET, UNMEASURED_GATE,
                         UNMEASURED_TRANSIENT})

# The paid-provider gate's refusal codes that are about money rather than permission. Either
# way nothing was sent; the split is only so the record says which.
_BUDGET_GATE_CODES = frozenset({"no_budget_reservation", "reservation_underfunded",
                                "reservation_already_used", "company_monthly_budget",
                                "provider_daily_ceiling", "provider_monthly_ceiling"})

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

    **It counted stitch codes.** `chart_grid()` is a grid of stitch abbreviations -- it is what
    draws the symbol chart -- and `color_grid()` is the grid of colours. This function read the
    first and called the answer a colour count, so a check whose whole job is to catch a render
    that invents a colour could not see colour at all.

    It was invisible because of a coincidence, measured across the 16 catalogue patterns: 13 of
    them work two stitches and two colours, so the wrong instrument returned the right number.
    The three that disagree are exactly the products rebuilt after the "Heirloom Cable Throw"
    defect -- one cream yarn each, all relief -- and they reported **2, 4 and 3 colours for a
    single-colour fabric**. The cable blanket's four stitch types became "the certified chart
    works 4 colours", so `judge` would have called a correct one-colour render a mismatch, and a
    three-colour render of it a match. That is the same fabric-claim family as the name that
    said cable over a pattern with no crossing in it, this time in the instrument rather than in
    the product.
    """
    grid = twin.color_grid() if hasattr(twin, "color_grid") else []
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
    # Reported, not implied. `_colours_in` returns 0 when the judge's phrase carries no count,
    # and its own docstring says that leaves the colour check *unmade rather than passed* -- but
    # the MATCH branches below said "and the colour count agrees" either way. That is the
    # `name_test` defect this module already fixed, in the check three lines above it: a verdict
    # naming a test it did not run. So the state travels with the verdict.
    if not want_colours:
        colour_test = "unavailable: the certified chart states no colour count"
    elif not saw_colours:
        colour_test = "unavailable: the judge's description of the arrangement carries no count"
    elif saw_colours == want_colours:
        colour_test = "passed"
    else:
        colour_test = "failed"

    if colour_test == "failed":
        return {"verdict": MISMATCH, "observed": observed, "overlap": [],
                "colour_test": colour_test,
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
                "colour_test": colour_test,
                "why": "the judge says the fabric is not working the chart's pattern"}
    if said is None:
        return {"verdict": UNMEASURABLE, "observed": observed, "overlap": overlap,
                "colour_test": colour_test,
                "why": "the judge could not tell whether the fabric matches the chart"}
    if not overlap and chart_words:
        return {"verdict": MISMATCH, "observed": observed, "overlap": overlap,
                "colour_test": colour_test,
                "why": (f"the judge answered yes and described the repeating unit as "
                        f"{shape!r}, which shares no term with the chart's own "
                        f"{named!r}. A polite yes and a contradicting description is the "
                        f"shape of the failure this check was built for")}
    colours_said = ("and the colour count agrees" if colour_test == "passed"
                    else f"and the colour count was not compared ({colour_test})")
    if not chart_words:
        # No prose names this chart's motif, so the name test is unavailable rather than
        # satisfied. Falling through to MATCH here was the mirror of the defect above: an
        # empty expectation that nothing can contradict passes every fabric ever rendered.
        # What has actually been established is that the judge compared the photograph
        # against the chart and said yes, and whatever the colour test managed to establish.
        return {"verdict": MATCH, "observed": observed, "overlap": overlap,
                "name_test": "unavailable", "colour_test": colour_test,
                "why": (f"the judge compared the photograph against the chart itself and "
                        f"says the fabric is working it, {colours_said}. "
                        f"{want.get('why_unnamed', '')}".strip())}
    return {"verdict": MATCH, "observed": observed, "overlap": overlap,
            "name_test": "passed", "colour_test": colour_test,
            "why": (f"the described repeating unit is the chart's own, the judge agrees, "
                    f"{colours_said}")}


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

    **The chart is written into the caller's directory or not at all.** This fell back to
    `tempfile.mkdtemp`, which removes nothing, and it could not own a `TemporaryDirectory`
    instead: the path it returns is handed straight to `images.generate` as a conditioning
    reference, so a directory cleaned up here would be a reference to a file that no longer
    exists. The lifetime belongs to the render, which is the caller. Both production callers
    -- owned and model photography -- already receive a directory from their handler and pass
    it through; without one this returns "" and the render is unconditioned, which is the
    same fallback a chart that will not draw already takes.
    """
    from pathlib import Path

    from .charts import ChartSpec, render_chart

    if not work_dir:
        return ""
    try:
        chart = render_chart(cir, twin, ChartSpec(cell_px=18))
        out = Path(work_dir) / "chart-ref.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        chart.save(str(out))
        return str(out)
    except Exception:  # noqa: BLE001 - conditioning on nothing is the fallback
        return ""


def _unmeasured(want, code: str, why: str) -> dict:
    """An UNMEASURABLE verdict that says why, as a code, and whether to ask again.

    `rejudge` is the whole point of the code: an answer that never came for a reason about
    money or plumbing says nothing about the render, which was paid for and is still a
    candidate. The photo jobs read it (`owned_photography.awaiting_motif`,
    `model_photography._rejudgeable_frame`) and re-ask about the same image instead of
    counting it as a failed attempt or paying for another render.
    """
    return {"verdict": UNMEASURABLE, "expected": want, "why": why[:240],
            "unmeasured": code, "rejudge": code in REJUDGEABLE}


def rejudgeable(motif) -> bool:
    """Whether this motif reading is an unasked question about a still-good render.

    Records filed before the reason was a code (production, until this change) carry only
    the gate's refusal in `why`; those are read by the refusal they name, so the renders the
    unreserved call left unjudged are re-asked rather than written off.
    """
    if not isinstance(motif, dict) or motif.get("verdict") != UNMEASURABLE:
        return False
    if "unmeasured" in motif:
        return bool(motif.get("rejudge")) and motif.get("unmeasured") in REJUDGEABLE
    why = str(motif.get("why") or "")
    return why.startswith("the comparison call failed:") and (
        "no_budget_reservation" in why or "no live company-budget reservation" in why)


def worth_rejudging(record: dict) -> bool:
    """Whether a match would make this render usable, so re-asking can buy something.

    Asked of the structural floor with the motif assumed to match. F-852 (e6b6d47) refuses
    generative product redraw and gives a generated frame no structural PASS without qualified
    whole-product evidence, so a render filed before it -- the renders the unreserved call left
    unjudged in production -- could not be used whatever the judge said. Re-asking about one
    would be a vision call bought to answer a question whose answer changes nothing, so it is
    not asked, and the render is counted as the attempt it was.
    """
    if not isinstance(record, dict):
        return False
    from ..visual.product_authority import structural_floor

    try:
        return structural_floor(dict(record, motif={"verdict": MATCH}))["status"] == "PASS"
    except Exception:  # noqa: BLE001 - unreadable evidence buys no call
        return False


def _call_judge(db, provider, image_ref: str, chart_path: str, want):
    """The one paid call, reserved before it is made and billed after it answers.

    Returns `(answer, None)` or `(None, unmeasured_record)`. The same discipline as every
    other vision judge (`visual.photoreal.judge`, `visual.inspect._call`,
    `creative.reference.read_listing`): `check_budget` with agent and purpose bound -- which
    also notes the reservation for the paid-provider gate, so `provider.see` carries its
    accounting evidence -- then `release_reservation` on the way out whatever happens, settled
    at the bill when there is one, and a `spend_report` row so the call is on the month.

    With no accounting store there is nothing to reserve against, and the gate would refuse
    the call for want of one; it is refused here instead, before anything is built.
    """
    from ..core.resilience import TransientError
    from ..gateway import providers as gw

    if db is None:
        return None, _unmeasured(want, UNMEASURED_NO_LEDGER,
                                 "no accounting store to reserve this comparison against, so "
                                 "it was not asked (fail closed); the render is still a "
                                 "candidate and the question is asked again")
    images = [image_ref, chart_path]
    try:
        budget = gw.check_budget(
            db, model=provider.model,
            # Both pictures, at the model's own per-image figure: the gate prices the call
            # it sees, and a reservation smaller than that is `reservation_underfunded`.
            input_tokens=gw.input_tokens(provider.model, system=SYSTEM, user=prompt(),
                                         images=len(images)),
            max_tokens=MAX_TOKENS, agent=AGENT, purpose=TASK)
    except gw.BudgetExceeded as exc:
        return None, _unmeasured(want, UNMEASURED_BUDGET,
                                 f"no budget to ask (fail closed), nothing was sent; the "
                                 f"render is kept and asked about again: {exc}")
    estimate, held = budget["estimate_cad"], budget["reservation_id"]
    try:
        response = provider.see(SYSTEM, prompt(), images, max_tokens=MAX_TOKENS)
    except BaseException as exc:
        gw.release_reservation(db, held)
        if not isinstance(exc, Exception):
            raise
        code = getattr(exc, "code", None)
        if isinstance(code, str) and code:
            # The paid-provider gate refused before any network I/O.
            return None, _unmeasured(
                want, UNMEASURED_BUDGET if code in _BUDGET_GATE_CODES else UNMEASURED_GATE,
                f"the paid-provider gate refused the comparison ({code}), nothing was sent; "
                f"the render is kept and asked about again: {exc}")
        if isinstance(exc, TransientError):
            return None, _unmeasured(want, UNMEASURED_TRANSIENT,
                                     f"the comparison call failed: {exc}")
        return None, _unmeasured(want, UNMEASURED_CALL, f"the comparison call failed: {exc}")
    from ..finance import spend_report

    cost = round(response.input_tokens * provider.cost_per_1k_input_cad / 1000
                 + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
    gw.release_reservation(db, held, actual_cad=cost)
    spend_report.record(
        db, agent=AGENT, amount_cad=cost, estimated_cad=estimate, purpose=TASK,
        provider=getattr(provider, "name", "anthropic"), model=provider.model,
        department=DEPARTMENT, tokens_in=response.input_tokens,
        tokens_out=response.output_tokens,
        detail={"price_basis": "assumed", "check": "motif_fidelity",
                "image": str(image_ref)[:120]})
    try:
        return parse(response.text), None
    except (MotifRefused, ValueError) as exc:
        return None, _unmeasured(want, UNMEASURED_ANSWER,
                                 f"the answer could not be read: {exc}")


def check(db, image_ref: str, cir, twin, *, provider=None, judger=None) -> dict:
    """Render the chart, show both, and decide. Blocks a customer-facing asset unless match.

    The chart is drawn for this comparison and for nothing else -- it is deterministic output
    from the certified CIR, so it can be redrawn at any time for nothing -- which is why this
    one owns its directory and removes it on the way out. Only the judge reads the file, and
    the judge has answered by the time the block ends. `chart_retained` says so in the record
    rather than leaving a path that quietly stops resolving.

    **The vision call is reserved (ENG-MOTIF, 2026-11-19).** It called `provider.see` with no
    `check_budget`, so in production the paid-provider gate refused it with
    `no_budget_reservation`, the refusal was swallowed as UNMEASURABLE, and every owned and
    model render -- already paid for -- came out unusable. It now reserves under
    `AGENT`/`TASK` like every other vision judge. When the budget genuinely refuses, the
    verdict is still UNMEASURABLE (fail closed) but carries `unmeasured` and `rejudge`, and
    the photo jobs re-ask about the same render later instead of writing it off.
    """
    from pathlib import Path

    from ..core import workspace
    from ..gateway import providers as gw
    from .charts import ChartSpec, render_chart

    want = expected(cir, twin)
    chart_path = ""
    with workspace.work_dir(None, prefix="motif-chart-") as root:
        try:
            chart = render_chart(cir, twin, ChartSpec(cell_px=18))
            chart_path = str(Path(root) / "chart.png")
            chart.save(chart_path)
        except Exception as exc:  # noqa: BLE001 - a chart that will not render is a refusal
            return _unmeasured(want, UNMEASURED_CHART,
                               f"the chart could not be rendered to compare against: "
                               f"{exc}"[:200])

        if judger is not None:
            answer = judger(image_ref, chart_path)
        else:
            answer, refused = _call_judge(db, provider or gw.provider_for(TASK),
                                          image_ref, chart_path, want)
            if refused is not None:
                return refused

    out = judge(answer, want)
    out["expected"] = want
    out["chart"] = chart_path
    out["chart_retained"] = False
    out["why_chart_is_not_kept"] = (
        "the chart is deterministic output from the certified CIR, so it is redrawn for "
        "nothing whenever it is wanted again. Keeping it would be a rendered image per "
        "asset check on a disk nothing prunes, and the path above is what was shown to the "
        "judge rather than a file to fetch")
    out["blocks_customer_facing_asset"] = out["verdict"] != MATCH
    out["why_unmeasurable_blocks_too"] = (
        "an image whose fabric nobody could check is not an image whose fabric is right. "
        "The difference is what to do next: a mismatch needs a different render, an "
        "unmeasurable one needs a closer frame")
    return out


def rejudge(db, image: dict, cir, twin, *, work_dir: str, provider=None,
            judger=None) -> dict:
    """Ask the motif question again about a render already on file, by its kept bytes.

    The other half of `rejudge` in a verdict: a render whose comparison was refused for
    money or plumbing is re-asked about *itself*, never re-rendered. The bytes are read back
    from the artifact store by digest (`tournament._keep` put them there) into the caller's
    directory, and the ordinary `check` runs on them -- the same reservation, the same chart,
    the same verdict rules.

    A render whose bytes are gone cannot be re-asked about; the answer is UNMEASURABLE with
    `image_missing`, which is not rejudgeable, so the job stops waiting on it and the render
    is counted as the attempt it was.
    """
    from pathlib import Path

    want = expected(cir, twin)
    sha = str((image or {}).get("sha256") or "")
    if not sha or not work_dir:
        return _unmeasured(want, UNMEASURED_IMAGE_MISSING,
                           "the render's bytes were never kept, so the question cannot be "
                           "asked about the same image again")
    try:
        from ..core.artifacts import ArtifactStore

        data = ArtifactStore().get(sha, db=db)
    except Exception as exc:  # noqa: BLE001 - a lost render is an answer, not a crash
        return _unmeasured(want, UNMEASURED_IMAGE_MISSING,
                           f"the render's bytes are no longer readable: {exc}")
    ctype = str((image or {}).get("content_type") or "")
    ext = ".jpg" if "jpeg" in ctype else ".webp" if "webp" in ctype else ".png"
    path = Path(work_dir) / f"rejudge-{sha[:16]}{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return check(db, str(path), cir, twin, provider=provider, judger=judger)
