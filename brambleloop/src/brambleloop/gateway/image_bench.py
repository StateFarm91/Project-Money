"""Choosing the image generator by measuring it, not by reading its price list.

The owner's instruction is explicit: do not lock a provider because it is inexpensive, and a
moderately more expensive model that materially outperforms is worth paying for. That makes
this a measurement problem, and the measurement has to be against *this company's* work --
crochet fabric, stitch scale, a recurring fictional model, an Etsy thumbnail -- because
general image-quality leaderboards are won by pictures nobody is trying to sell a pattern
with.

**Published capability is not measurement, and the two are kept apart.** `CANDIDATES` carries
what each provider publishes about itself, labelled as a claim, and it is used for one thing
only: ruling a model out on a requirement it cannot meet at all. A model with no reference
conditioning cannot hold a permanent identity (#200, #201) however photoreal it is, so it
leaves before the benchmark rather than losing it. Everything else is decided by scores.

**Three samples per trial, because one sample from a generative model is noise.** A single
render can be the best or worst that model does, and a benchmark that took one would be
measuring luck and reporting it as capability. The budget is spent on repetition rather than
hoarded -- which is the owner's own principle applied to measurement.

**The judge is blind and is not the generator.** Each rendered image is scored by the vision
capability against a rubric whose every line cites the requirement it comes from, with no
knowledge of which provider made it. A judge told the brand grades the brand, and a
generator asked to grade itself has never failed.

**Nothing here can be run without credentials, and it says so rather than estimating.** A
benchmark that produced scores from published specifications would be a literature review
with a score column.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.resilience import PermanentError, TransientError

# The owner's benchmark budget, read from the policy rather than restated. A measurement
# that can overrun is a measurement somebody stops trusting, and an authorised figure written
# in two files is a figure that will drift.
from ..finance.spend_policy import BENCHMARK_BUDGET_CAD as BENCHMARK_CEILING_CAD  # noqa: E402

# One render is a sample of a distribution. Five, at five of the six trials, gives each
# rubric dimension twenty-five observations per model -- enough to separate a model that is
# reliably good from one that is occasionally spectacular, which is the distinction that
# matters for a catalogue somebody has to ship every week.
#
# Three would have cost CA$2.50 less and left the decision closer to the noise. This choice
# governs every listing image this company ships, so the extra buys a measurable reduction
# in the risk of picking the wrong provider on luck -- which is what the budget is for, and
# the reason it is five rather than as many as the ceiling would allow.
SAMPLES_PER_TRIAL = 5

USD_TO_CAD = 1.37


@dataclass(frozen=True)
class Candidate:
    """A provider as it describes itself. Claims, not findings."""

    key: str
    what: str
    usd_per_image: float
    reference_images: int
    published_claim: str
    resolution: str = "1024"

    @property
    def cad_per_image(self) -> float:
        return round(self.usd_per_image * USD_TO_CAD, 6)

    @property
    def can_hold_an_identity(self) -> bool:
        """Reference conditioning is what an identity lock is. Without it, #200 is unmeetable."""
        return self.reference_images > 0

    def to_dict(self) -> dict:
        return {"model": self.key, "what": self.what,
                "usd_per_image": self.usd_per_image,
                "cad_per_image": self.cad_per_image,
                "reference_images": self.reference_images,
                "can_hold_an_identity": self.can_hold_an_identity,
                "published_claim": self.published_claim,
                "claim_basis": "the provider's own published description, read 2026-09-20. "
                               "Not a measurement of anything"}


CANDIDATES: tuple[Candidate, ...] = (
    Candidate("flux-2-pro", "Black Forest Labs FLUX 2 Pro", 0.020, 8,
              "detailed textures and natural lighting; recommended as a safe default for "
              "product photography"),
    Candidate("seedream-v5-lite", "ByteDance Seedream v5.0 Lite", 0.026, 4,
              "production-quality output at 2048px for customer-facing use"),
    Candidate("gpt-image-2", "OpenAI GPT Image 2", 0.030, 16,
              "highest blind-human-vote arena score among general image models as of "
              "September 2026; sixteen reference images per call"),
    Candidate("nano-banana-2", "Google Gemini 3.1 Flash Image (Nano Banana 2)", 0.101, 5,
              "fine-grained fabric and material texture at up to 4K; feature consistency "
              "maintained across up to five characters. US$0.101 is the 2048px figure read "
              "from Google's pricing page 2026-09-21, which is the size this benchmark "
              "renders at; the 0.063 it replaced was nearer the 1K price",
              resolution="2048"),
    Candidate("imagen-4-ultra", "Google Imagen 4 Ultra", 0.054, 0,
              "the most photorealistic output available; skin, fabric, lighting and "
              "reflections hardest to distinguish from a photograph. Excluded on the "
              "requirement, and as of 2026-09-21 no longer listed on Google's Gemini API "
              "pricing page either -- the price here is the last one read and is kept only "
              "so the exclusion stays a recorded decision rather than a deletion"),
)

BY_KEY: dict[str, Candidate] = {c.key: c for c in CANDIDATES}


@dataclass(frozen=True)
class Trial:
    """One thing this company actually has to render, and what it is testing."""

    key: str
    prompt: str
    requirement: int
    tests: str
    needs_reference: bool = False


# Every trial is a frame this catalogue genuinely needs, not a benchmark pose. The prompts
# deliberately describe *original* Brambleloop subjects: benchmarking on a competitor's
# product would be commissioning a copy to see how good the copier is.
TRIALS: tuple[Trial, ...] = (
    Trial("stitch_truth",
          "A finished hand-crocheted cushion cover in undyed cream wool, photographed flat "
          "on a pale linen surface in soft daylight. The stitch texture is the subject: "
          "individual stitches legible, consistent scale, visible yarn ply and a clean "
          "worked edge.",
          79, "stitch scale, yarn continuity and edge construction -- the artefacts a maker "
              "sees instantly and a general viewer does not"),
    Trial("hero_comprehension",
          "A finished hand-crocheted basket in sage green cotton on a white background, "
          "product photograph, the whole object in frame with no crop, even lighting, no "
          "props.",
          75, "HERO: whether the finished result is comprehensible at a glance"),
    Trial("thumbnail_strength",
          "A finished hand-crocheted winter hat in rust-coloured wool, product photograph "
          "composed so the object fills the frame and reads clearly when reduced to a small "
          "square thumbnail. High contrast against the background.",
          66, "MOBILE GRID: whether it survives reduction to an Etsy search thumbnail, "
              "which is where the buying decision starts"),
    Trial("lifestyle_premium",
          "A finished hand-crocheted throw blanket in oatmeal wool draped over a linen "
          "armchair beside a window, editorial interior photograph, natural afternoon light, "
          "shallow depth of field, the blanket clearly the subject.",
          75, "LIFESTYLE QUALITY: premium lighting, composition and material realism "
              "without the product ceasing to be the subject"),
    Trial("model_identity",
          "An adult woman with long very dark brunette hair, light blue-green eyes, strong "
          "dark brows and defined cheekbones, wearing a finished hand-crocheted cream "
          "cardigan, three-quarter length editorial fashion photograph in soft daylight. "
          "The cardigan's fit, texture and construction are clearly visible.",
          198, "the canonical model brief: whether the face is producible at all, and "
               "whether the garment stays the commercial subject (#202)",
          needs_reference=False),
    Trial("identity_repeat",
          "The same woman as the reference image, now wearing a finished hand-crocheted "
          "mustard beanie, outdoor autumn setting, three-quarter portrait. Same face, same "
          "hair, same eyes, same age.",
          201, "ANTI-DRIFT: whether it is the same person. A beautiful image of the wrong "
               "woman fails",
          needs_reference=True),
)

TRIAL_BY_KEY: dict[str, Trial] = {t.key: t for t in TRIALS}


@dataclass(frozen=True)
class Dimension:
    """One thing the judge scores, and the requirement it comes from."""

    key: str
    requirement: int
    question: str


# Every line cites a requirement. A rubric line with no requirement behind it is somebody's
# taste, and taste is what this whole build refuses to decide with.
RUBRIC: tuple[Dimension, ...] = (
    Dimension("stitch_fidelity", 79,
              "Are the stitches a real crochet fabric -- consistent scale, plausible ply, "
              "no repeating texture tile, no impossible seams?"),
    Dimension("material_truth", 79,
              "Does the yarn behave like yarn: drape, weight, how it folds and compresses?"),
    Dimension("geometry_fidelity", 75,
              "Is the object's construction geometry coherent -- panels, joins, shaping and "
              "proportion consistent with something that could be made?"),
    Dimension("finished_result_clarity", 75,
              "Is it immediately obvious what the finished object is?"),
    Dimension("thumbnail_strength", 66,
              "Would this still read as this object at Etsy search-thumbnail size?"),
    Dimension("lifestyle_quality", 75,
              "Is the lighting, composition and setting premium editorial rather than "
              "generic stock?"),
    Dimension("product_is_the_subject", 202,
              "Does the crocheted object remain the commercial subject, rather than the "
              "setting or the model?"),
    Dimension("physical_plausibility", 79,
              "Would a maker looking at this see anything physically impossible?"),
    Dimension("human_photorealism", 198,
              "Where a person is shown, do skin, hair and eyes read as photography rather "
              "than as rendering? Score 4 and note `not_applicable` if nobody is shown."),
    Dimension("hands_and_anatomy", 79,
              "Are hands, fingers and body proportions correct where visible? Hands are "
              "where generated imagery fails most visibly to a human eye."),
    Dimension("garment_fit", 75,
              "Where a garment is worn, does it fit and hang as a real knitted or crocheted "
              "garment would on that body?"),
    Dimension("text_rendering", 75,
              "If any text, label or logo appears, is it correctly formed rather than "
              "approximated glyphs? Score 4 and note `not_applicable` if no text appears."),
)

# The identity dimension is scored differently: against a reference rather than on its own,
# so it is kept out of the rubric above and asked separately.
IDENTITY_DIMENSION = Dimension(
    "identity_match", 201,
    "Is this the same person as the reference: same facial geometry, hair, eye colour and "
    "apparent age, with no drift in style?")

# Gallery consistency is a judgement about a *set*, so it cannot be a per-image score. Asked
# once per model over that model's own renders of the six trials: whether they would read as
# one shop's gallery rather than six unrelated stock photographs.
GALLERY_DIMENSION = Dimension(
    "gallery_consistency", 66,
    "Would these images read as one Etsy shop's gallery -- consistent light, palette "
    "discipline and styling language -- rather than as unrelated stock photographs?")

# Two things the owner named that are measured rather than judged, from data the run already
# produces. A model asked to rate its own consistency would be answering a different question.
#
# Repeatability is the spread of a model's own scores across its five samples of the same
# trial: a model that is sometimes excellent and sometimes poor is worse to ship with than one
# that is consistently good, because a catalogue is shipped weekly and nobody re-rolls.
# Latency is recorded per render and reported; it disqualifies nothing on its own, because a
# slow generator for a weekly batch of gallery images is an inconvenience rather than a fault.
MEASURED_NOT_JUDGED: dict[str, str] = {
    "repeatability": ("standard deviation of the model's own overall score across its five "
                      "samples of each trial, inverted. A model asked to rate its own "
                      "consistency would be answering a different question"),
    "latency_ms": ("recorded per render. It disqualifies nothing by itself: a slow generator "
                   "for a weekly batch of gallery images is an inconvenience, not a fault"),
    "cost_cad_per_image": "the published rate, used only to break a tie inside the margin",
}

# The judgement that decides which provider renders every listing image afterwards. Deep
# tier, declared in `routing.TASKS`: it is made a few dozen times and it is the whole point
# of spending the benchmark budget, so scoring it on the cheapest model would be measuring
# carefully with a blunt instrument.
JUDGE_TASK = "image_benchmark_judging"
# Measured against real answers 2026-09-21, not guessed. At 500 the judge's JSON was cut
# mid-object -- twelve dimensions plus a `notes` map does not fit -- and every truncated
# answer was correctly refused as "not JSON" and recorded as a failed sample. Sixteen of
# flux-2-pro's thirty samples died that way, which is a complete schedule turned into an
# incomplete one by a token budget set before the rubric grew.
JUDGE_MAX_TOKENS = 900

SCORE_MIN, SCORE_MAX = 0, 4

# A model that cannot render crochet fabric convincingly is not a candidate at any price,
# whatever it does with lighting. Below this mean on the fabric-and-construction dimensions
# it is out.
FABRIC_FLOOR = 2.5
FABRIC_DIMENSIONS: tuple[str, ...] = ("stitch_fidelity", "material_truth",
                                      "geometry_fidelity")

# An identity that does not survive one regeneration is a failed asset (#201), so the model
# that renders the canonical woman has to clear this on its own, separately from its total.
# Below it, a beautiful catalogue drifts into somebody else by February.
IDENTITY_FLOOR = 3.0

# How much a cost difference is allowed to matter. The owner's instruction, in arithmetic:
# quality decides unless the quality difference is inside the noise, and then cost breaks the
# tie. Expressed as a score margin rather than as a dollar rule, because the dollars here are
# small enough that any dollar rule would dominate.
DECIDING_MARGIN = 0.25


class BenchmarkRefused(ValueError):
    """A benchmark that would report something it did not measure."""


BY_KEY_TRIAL: dict[str, Trial] = {t.key: t for t in TRIALS}


def eligible() -> dict:
    """Which candidates can meet the requirements at all, before anything is rendered.

    One exclusion, and it is on a requirement rather than on quality: a model with no
    reference conditioning cannot hold a permanent identity across seasons, so #200 and #201
    are unmeetable by it. Ruling it out here rather than benchmarking it and discarding the
    winner is the honest order -- and it is the case where "most photorealistic available"
    is true and irrelevant.
    """
    keep = [c for c in CANDIDATES if c.can_hold_an_identity]
    drop = [{"model": c.key, "why": (
        "no reference conditioning, so the canonical model cannot be held across seasons "
        "(#200, #201). An identity lock is conditioning rather than a better prompt, and "
        "photorealism does not substitute for it")}
        for c in CANDIDATES if not c.can_hold_an_identity]
    return {"benchmarked": [c.to_dict() for c in keep],
            "excluded": drop,
            "excluded_on": "a requirement, not a score"}


def plan(env: dict | None = None) -> dict:
    """What the benchmark would render and what it would cost, answerable before any key.

    Refuses rather than trimming if the plan exceeds the ceiling: a benchmark that quietly
    drops samples to fit a budget is measuring a different thing from the one it reports.
    """
    keep = [c for c in CANDIDATES if c.can_hold_an_identity]
    per_model = len(TRIALS) * SAMPLES_PER_TRIAL
    rows = [{"model": c.key, "images": per_model,
             "cad": round(per_model * c.cad_per_image, 4)} for c in keep]
    render_cad = round(sum(r["cad"] for r in rows), 4)

    # Judging cost: one vision call per rendered image, at the cheap tier's measured rate.
    judged = per_model * len(keep)
    # Read from the routing table rather than written here. It was a literal 0.004, which
    # was the cheap tier's rate, and judging moved to the deep tier when the policy changed
    # -- so the plan would have quoted a quarter of what the benchmark now costs.
    from . import routing

    judge_cad = round(judged * routing.estimate_cad(JUDGE_TASK), 4)
    total = round(render_cad + judge_cad, 4)

    if total > BENCHMARK_CEILING_CAD:
        raise BenchmarkRefused(
            f"this plan costs CA${total:.2f} against a ceiling of "
            f"CA${BENCHMARK_CEILING_CAD:.2f}. Trimming samples to fit would measure a "
            f"different thing from the one this reports")

    return {
        "models": rows,
        "trials": [{"trial": t.key, "requirement": t.requirement, "tests": t.tests}
                   for t in TRIALS],
        "samples_per_trial": SAMPLES_PER_TRIAL,
        "images_per_model": per_model,
        "images_total": judged,
        "render_cad": render_cad,
        "judging_cad": judge_cad,
        "total_cad": total,
        "ceiling_cad": BENCHMARK_CEILING_CAD,
        "headroom_cad": round(BENCHMARK_CEILING_CAD - total, 4),
        "why_three_samples": (
            f"one render is a sample of a distribution. A benchmark that took one would be "
            f"measuring luck and reporting it as capability. {SAMPLES_PER_TRIAL} gives each "
            f"dimension twenty-five observations per model; the budget is better spent on "
            f"repetition than left unspent, and better left unspent than spent past the "
            f"point where more samples change the answer"),
        **_credential_state(keep, env),
    }


def _credential_state(keep, env: dict | None = None) -> dict:
    """Which of the eligible candidates could actually be rendered right now.

    `runnable` was a literal `False` with a sentence beside it explaining that no account
    existed. It was true when it was written. It would have gone on saying so after the
    accounts were created, which is the defect this build keeps finding in a new costume: a
    fact recorded once, surviving the world changing.
    """
    from . import images

    have = set(images.available(env))
    ready = [c.key for c in keep if c.key in have]
    missing = [c.key for c in keep if c.key not in have]
    plan_ = images.credential_plan(env)
    return {
        "runnable": bool(ready),
        "complete": not missing,
        "credentialled": ready,
        "awaiting_credential": missing,
        "blocked_on": ("" if not missing else
                       f"credentials for {missing}. "
                       + "; ".join(f"{a['name']} ({a['minutes']} min"
                                   + (", card needed)" if a["needs_card"] else ")")
                                   + f" unlocks {a['unlocks']}"
                                   for a in plan_["actions"])),
        "credential_plan": plan_,
        "a_partial_run_is_not_a_choice": (
            "a benchmark missing a candidate can report what it measured and must not lock "
            "a provider. The owner's rule is that the cheap candidate is not chosen because "
            "it is cheap, and a run where only the cheap candidate had a key would do "
            "exactly that while looking like a measurement"),
    }


def score_prompt(dimensions: tuple[Dimension, ...] = RUBRIC) -> str:
    """The judge's question. It never learns which model rendered what.

    The identity dimension is asked of two pictures rather than one, and the prompt has to
    say so: a judge shown a reference and a regeneration, told it is looking at "one product
    image", answers about whichever it looked at last.
    """
    pair = any(d.key == IDENTITY_DIMENSION.key for d in dimensions)
    preamble = (
        "You are shown TWO images from a crochet pattern shop. The FIRST is the approved "
        "reference photograph of the shop's model. The SECOND is a new photograph that is "
        "supposed to show the same woman. Judge the SECOND image, using the FIRST only to "
        "decide whether it is the same person."
        if pair else
        "You are judging one product image for a crochet pattern shop.")
    return (
        preamble + " Score each dimension "
        f"from {SCORE_MIN} (fails completely) to {SCORE_MAX} (could be published as it is). "
        "Reply with a single JSON object mapping each key to an integer, plus a key "
        "`notes` mapping any score below 2 to one short phrase. Nothing else.\n\n"
        + "\n".join(f"- {d.key}: {d.question}" for d in dimensions))


def parse_scores(text: str, dimensions: tuple[Dimension, ...] = RUBRIC) -> dict:
    """Read one judgement, refusing anything that is not a score on every dimension."""
    import json

    body = (text or "").strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise BenchmarkRefused(f"the judge did not answer with JSON: {body[:120]!r}") from exc
    if not isinstance(parsed, dict):
        raise BenchmarkRefused(f"expected one object, got {type(parsed).__name__}")

    parsed.pop("notes", None)
    keys = {d.key for d in dimensions}
    unknown = sorted(k for k in parsed if k not in keys)
    if unknown:
        raise BenchmarkRefused(f"{unknown} are not rubric dimensions: {sorted(keys)}")
    missing = sorted(keys - set(parsed))
    if missing:
        raise BenchmarkRefused(
            f"{missing} were not scored. A partial judgement averages into a total as "
            f"though the model had done well on what nobody asked about")

    out: dict[str, int] = {}
    for key, value in parsed.items():
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise BenchmarkRefused(f"{key}={value!r} is not a score") from exc
        if not SCORE_MIN <= number <= SCORE_MAX:
            raise BenchmarkRefused(
                f"{key}={number} is outside {SCORE_MIN}-{SCORE_MAX}")
        out[key] = number
    return out


@dataclass
class Result:
    """Every judged render for one model. Scores only; no image is stored."""

    model: str
    scores: list[dict] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    latencies_ms: list[float] = field(default_factory=list)
    gallery_consistency: int | None = None
    cad_spent: float = 0.0

    def mean(self, key: str) -> float | None:
        values = [s[key] for s in self.scores if key in s]
        return round(sum(values) / len(values), 3) if values else None

    def overall(self) -> float | None:
        means = [self.mean(d.key) for d in RUBRIC]
        present = [m for m in means if m is not None]
        return round(sum(present) / len(present), 3) if present else None

    def repeatability(self) -> float | None:
        """How consistent this model is with itself, on its own scale.

        Measured rather than judged. A model that is sometimes excellent and sometimes poor
        is worse to ship with than one that is consistently good: a catalogue goes out weekly
        and nobody re-rolls the bad frame. Reported as 1 minus the spread, so it reads in the
        same direction as every other number here -- higher is better.
        """
        import statistics

        per_sample = []
        for score in self.scores:
            values = [v for k, v in score.items() if k in {d.key for d in RUBRIC}]
            if values:
                per_sample.append(sum(values) / len(values))
        if len(per_sample) < 2:
            return None
        spread = statistics.pstdev(per_sample)
        return round(max(0.0, 1.0 - spread / (SCORE_MAX or 1)), 3)

    def latency_median(self) -> float | None:
        import statistics

        values = [float(v) for v in self.latencies_ms if v]
        return round(statistics.median(values), 1) if values else None


CANDIDATE_ACTION = "image.benchmark_candidate"

# Bumped when the *method* changes rather than the rubric, which invalidates every stored
# score. v2, 2026-09-21: the anti-drift trial is now actually given a reference image, and
# the judge is shown both pictures. Under v1 it was given neither -- the prompt said "the
# same woman as the reference image" with no reference supplied, and the judge was asked
# whether two people matched while looking at one photograph. The identity floor was
# unpassable by construction, which is exactly what the first live run reported: CA$6.40
# spent and no candidate cleared both floors. A check that cannot pass is not a check.
METHOD_VERSION = "v2-reference-conditioned"

# Which trial produces the face every later trial is conditioned on. Named rather than
# positional: reordering TRIALS must not silently change what the identity lock locks to.
CANONICAL_TRIAL = "model_identity"

# How many permanent failures in a row mean the candidate rather than the brief.
PERMANENT_FAILURES_BEFORE_STOPPING = 3


def rubric_fingerprint(candidate: Candidate) -> str:
    """What a stored result was measured under, so a stale one is never reused.

    A measurement is only comparable to another taken the same way. If the rubric gains a
    dimension, the trials change, the sample count moves or a candidate's resolution is
    corrected, every stored score was produced by a different experiment and reusing it
    would be averaging two questions.
    """
    import hashlib

    material = "|".join([
        METHOD_VERSION,
        candidate.key, candidate.resolution, f"{candidate.usd_per_image}",
        ",".join(d.key for d in RUBRIC), IDENTITY_DIMENSION.key, GALLERY_DIMENSION.key,
        ",".join(t.key for t in TRIALS), str(SAMPLES_PER_TRIAL), str(SCORE_MAX),
    ])
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def expected_samples() -> int:
    return len(TRIALS) * SAMPLES_PER_TRIAL


def _store(db, result: Result, candidate: Candidate) -> None:
    """Record a measurement, but only a complete one.

    The first live run was interrupted by a deploy after sixteen of thirty samples. Those
    sixteen were stored, and the next run reused them as though the candidate had been
    measured -- so one model was ranked on sixteen samples against another's thirty. That is
    the same fault `teardown.audits` refuses by name: scoring part of a schedule and
    reporting the mean lets the run that looked at less outrank the run that looked at all
    of it.
    """
    from ..agents.registry import Registry

    if len(result.scores) < expected_samples():
        Registry(db).audit("creative_director", CANDIDATE_ACTION + "_partial", detail={
            "model": result.model, "scored": len(result.scores),
            "expected": expected_samples(),
            "why": ("a partial measurement is not stored, because a reused partial is a "
                    "candidate ranked on fewer samples than the one it is compared with")})
        return

    Registry(db).audit("creative_director", CANDIDATE_ACTION, detail={
        "model": result.model, "fingerprint": rubric_fingerprint(candidate),
        "scores": result.scores, "failures": result.failures[:10],
        "latencies_ms": result.latencies_ms,
        "gallery_consistency": result.gallery_consistency,
        "cad_spent": result.cad_spent,
    })


def stored_result(db, candidate: Candidate) -> Result | None:
    """A previous measurement of this candidate under this exact rubric, if there is one."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    want = rubric_fingerprint(candidate)
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == CANDIDATE_ACTION)
                             .order_by(desc(AuditLog.id)).limit(50)):
            detail = row.detail or {}
            if detail.get("model") != candidate.key or detail.get("fingerprint") != want:
                continue
            if not detail.get("scores"):
                continue
            return Result(model=candidate.key, scores=list(detail["scores"]),
                          failures=list(detail.get("failures") or []),
                          latencies_ms=list(detail.get("latencies_ms") or []),
                          gallery_consistency=detail.get("gallery_consistency"),
                          cad_spent=float(detail.get("cad_spent") or 0.0))
    return None


def decide(results: list[Result], *, unmeasured: list[dict] | None = None) -> dict:
    """Name a winner from measured scores, or refuse to name one.

    Two refusals worth having. A result set with no scores names nobody, rather than falling
    back to the cheapest -- which is the outcome the owner explicitly ruled out. And a model
    below the fabric floor is out regardless of its total, because a generator that cannot
    render crochet convincingly is not a candidate for a crochet shop at any price.
    """
    scored = [r for r in results if r.overall() is not None]
    if not scored:
        return {"decided": False,
                "why": ("nothing was measured, so nothing is chosen. Falling back to the "
                        "cheapest candidate is the decision the owner ruled out, and it is "
                        "what a benchmark with no results quietly becomes"),
                "results": [{"model": r.model, "failures": r.failures} for r in results]}

    rows = []
    for r in scored:
        fabric = [r.mean(key) for key in FABRIC_DIMENSIONS]
        fabric_mean = round(sum(f for f in fabric if f is not None)
                            / max(len([f for f in fabric if f is not None]), 1), 3)
        rows.append({
            "model": r.model, "overall": r.overall(), "fabric": fabric_mean,
            "by_dimension": {d.key: r.mean(d.key) for d in RUBRIC},
            "identity_match": r.mean(IDENTITY_DIMENSION.key),
            "cad_per_image": BY_KEY[r.model].cad_per_image if r.model in BY_KEY else None,
            "judged_images": len(r.scores), "failures": len(r.failures),
            "repeatability": r.repeatability(),
            "gallery_consistency": r.gallery_consistency,
            "latency_ms_median": r.latency_median(),
            "meets_fabric_floor": fabric_mean >= FABRIC_FLOOR,
            "meets_identity_floor": (r.mean(IDENTITY_DIMENSION.key) is None
                                     or r.mean(IDENTITY_DIMENSION.key) >= IDENTITY_FLOOR),
        })

    qualified = [row for row in rows
                 if row["meets_fabric_floor"] and row["meets_identity_floor"]]
    if not qualified:
        return {"decided": False, "results": rows,
                "why": (f"no candidate cleared both floors -- fabric at {FABRIC_FLOOR} and "
                        f"identity at {IDENTITY_FLOOR}. A generator that cannot render "
                        f"crochet convincingly is not a candidate for a crochet shop at any "
                        f"price, and one whose face does not survive a regeneration produces "
                        f"a catalogue that drifts into somebody else by February")}

    qualified.sort(key=lambda row: (-row["overall"], row["cad_per_image"] or 0.0))
    best = qualified[0]
    contenders = [row for row in qualified
                  if best["overall"] - row["overall"] <= DECIDING_MARGIN]
    if len(contenders) > 1:
        # Inside the margin, repeatability decides before cost does. Both are tie-breaks and
        # only one of them is about quality: a model that is sometimes excellent and
        # sometimes poor is worse to ship with than one that is consistently good, because a
        # catalogue goes out weekly and nobody re-rolls the bad frame. Cost is the last
        # thing consulted, which is the policy stated as a sort key.
        contenders.sort(key=lambda row: (-(row["repeatability"] or 0.0),
                                         row["cad_per_image"] or 0.0, -row["overall"]))
        winner = contenders[0]
        beaten = [c["model"] for c in contenders[1:]]
        decided_on = ("repeatability"
                      if any((winner["repeatability"] or 0) != (c["repeatability"] or 0)
                             for c in contenders[1:]) else "cost")
        why = (f"{len(contenders)} candidates finished within {DECIDING_MARGIN} of each "
               f"other, which is inside what {SAMPLES_PER_TRIAL} samples can separate. "
               f"{decided_on} broke the tie against {beaten}, and only then -- "
               f"repeatability is consulted before cost because one of them is about "
               f"quality")
    else:
        winner = best
        why = (f"{winner['model']} scored {winner['overall']} against "
               f"{qualified[1]['overall'] if len(qualified) > 1 else 'nothing else'}, a "
               f"margin wider than {DECIDING_MARGIN}. Quality decided and cost did not")

    # A candidate nobody could render is not a candidate that lost. While one is missing
    # this names a leader and refuses to lock, because the owner's rule -- do not settle on
    # a provider because it is inexpensive -- is broken exactly as thoroughly by a run in
    # which the dearer candidates had no key as by a decision made from a price list.
    absent = list(unmeasured or [])
    return {"decided": True, "winner": winner["model"], "why": why,
            "locked": not absent,
            "provisional": bool(absent),
            "unmeasured": absent,
            "why_not_locked": ("" if not absent else
                               f"{[a['model'] for a in absent]} went unmeasured for want of "
                               f"a credential. A leader chosen over candidates nobody could "
                               f"render is a shortlist of one wearing a result's clothes"),
            "results": rows, "qualified": [row["model"] for row in qualified],
            "fabric_floor": FABRIC_FLOOR, "identity_floor": IDENTITY_FLOOR,
            "deciding_margin": DECIDING_MARGIN,
            "measured_not_judged": dict(MEASURED_NOT_JUDGED),
            "how_ties_break": ("repeatability, then cost. Quality decides the ranking and "
                               "the first tie-break is still a quality property; cost is "
                               "the last thing consulted")}


def run(db, *, generator=None, judge=None, env: dict | None = None,
        reuse: bool = True) -> dict:
    """Render, judge blind, and report. Refuses to start without a way to render.

    The judge never learns which model made an image. A judge told the brand grades the
    brand, and this one is choosing between brands.
    """
    from . import images

    if generator is None and not images.configured(env):
        return {"ran": False,
                "reason": ("no image provider is configured, so nothing can be rendered and "
                           "nothing will be scored. A benchmark that produced numbers from "
                           "published specifications would be a literature review with a "
                           "score column"),
                "plan": plan(), "eligible": eligible()}

    spent = 0.0
    results: list[Result] = []
    unmeasured: list[dict] = []
    reused: list[dict] = []
    have = set(images.available(env))
    for candidate in [c for c in CANDIDATES if c.can_hold_an_identity]:
        # A candidate with no credential is unmeasured, not beaten. Rendering it through
        # whichever provider the environment happened to name -- which is what a single
        # shared key silently did -- would have scored one model five times under five
        # names and crowned the cheapest of the five identical rows.
        # A candidate already measured under this exact rubric is not re-rendered. The
        # benchmark exists to be run more than once -- a provider's credential arrives
        # weeks after another's -- and re-paying for thirty renders of a model whose
        # scores are already on file buys no information. The fingerprint is what makes
        # this safe: change the rubric, the trials, the sample count or a candidate's
        # resolution and nothing stored matches, so everything is measured again.
        if reuse and generator is None:
            previous = stored_result(db, candidate)
            if previous is not None:
                results.append(previous)
                reused.append({"model": candidate.key,
                               "judged_images": len(previous.scores),
                               "cad_spent_then": previous.cad_spent})
                continue
        # Two images to prove the provider will condition on a reference, before thirty are
        # spent finding out it will not. Reference conditioning is the one part of each
        # dialect an ordinary render never exercises, it was wrong in a different way for
        # each provider, and the only thing that noticed was the sixth trial of a
        # thirty-sample run -- about CA$21 across four runs without completing a single
        # schedule. A capability nothing checks until it is expensive to check is one that
        # gets checked expensively.
        if generator is None and candidate.key in have:
            if not images.reference_proven(db, candidate.key):
                proof = images.reference_probe(db, candidate.key, env=env)
                spent += float(proof.get("cad") or 0.0)
                if not proof.get("ok"):
                    unmeasured.append({
                        "model": candidate.key,
                        "why": (f"reference conditioning does not work for this provider, "
                                f"so the identity trials cannot run and the schedule cannot "
                                f"complete: {proof.get('why', '')[:200]}")})
                    continue
        if generator is None and candidate.key not in have:
            unmeasured.append({
                "model": candidate.key,
                "why": f"no credential. Set {images.key_var(images.BY_KEY[candidate.key].account)}"
                       if candidate.key in images.BY_KEY else "no credential and no provider entry"})
            continue
        result = Result(model=candidate.key)
        rendered_urls: list[str] = []
        stopped: dict | None = None
        # The canonical face this candidate produced, kept so the anti-drift trial can be
        # conditioned on it. #200 is explicit that an identity lock is reference
        # conditioning rather than a better prompt, so a drift test run without the
        # reference is not a weak test -- it is a different test, of whether the model can
        # invent the same stranger twice from a description.
        reference: str = ""
        consecutive = 0
        for trial in TRIALS:
            if stopped:
                break
            for sample in range(SAMPLES_PER_TRIAL):
                if spent >= BENCHMARK_CEILING_CAD:
                    result.failures.append({"trial": trial.key, "why": "benchmark ceiling"})
                    continue
                try:
                    refs = [reference] if (trial.needs_reference and reference) else None
                    if trial.needs_reference and not reference:
                        result.failures.append({
                            "trial": trial.key, "sample": sample,
                            "why": ("no canonical render to condition on, so the drift test "
                                    "would be asking the model to invent the same stranger "
                                    "twice. Unrun, not failed")})
                        continue
                    size = f"{candidate.resolution}x{candidate.resolution}"
                    # The injected generator gets the reference too. A test double that
                    # is handed less than the real call is a double that cannot catch the
                    # real call dropping something -- which is exactly the bug this trial
                    # had for a day.
                    rendered = (generator(trial.prompt, env=env, size=size,
                                          reference_urls=refs)
                                if generator else
                                images.generate(trial.prompt, env=env,
                                                provider_key=candidate.key,
                                                reference_urls=refs, size=size))
                    spent += float(rendered.get("cad") or candidate.cad_per_image)
                    dimensions = ((IDENTITY_DIMENSION,) if trial.needs_reference
                                  else RUBRIC)
                    result.latencies_ms.append(float(rendered.get("latency_ms") or 0.0))
                    # Whatever the judge can be handed: a URL when the provider gives one,
                    # a path on this disk when it returns the bytes inline. Google never
                    # returns a URL, so reading only `url` would have treated every
                    # successful Google render as an answer with no picture in it.
                    ref = rendered.get("image_ref") or rendered.get("url") or ""
                    if ref:
                        rendered_urls.append(ref)
                        if trial.key == CANONICAL_TRIAL and not reference:
                            reference = ref
                    # The drift question is "is this the same person", which needs both
                    # pictures. Asking it of one was asking whether a stranger matched a
                    # photograph nobody had shown the judge.
                    shown = ([reference, ref] if (trial.needs_reference and reference)
                             else [ref])
                    answer = (judge or _judge)(db, shown, dimensions)
                    result.scores.append(parse_scores(answer, dimensions))
                except images.QuotaUnavailable as exc:
                    # Not this trial's failure: the account cannot render at all. Recording
                    # it thirty times would fill the failure list with one fact and leave a
                    # candidate looking like it had been measured and lost.
                    stopped = {"model": candidate.key, "why": str(exc)[:300]}
                    break
                except (PermanentError, TransientError, BenchmarkRefused) as exc:
                    result.failures.append({"trial": trial.key, "sample": sample,
                                            "why": str(exc)[:200]})
                    # A content refusal can be about one brief, so a single permanent error
                    # does not condemn a candidate. Three in a row is the account, the
                    # credential or the endpoint -- the shape of the Google project denied
                    # access on 2026-09-21, which would otherwise make thirty identical
                    # failing calls every time this cadence fires.
                    consecutive = consecutive + 1 if isinstance(exc, PermanentError) else 0
                    if consecutive >= PERMANENT_FAILURES_BEFORE_STOPPING:
                        stopped = {"model": candidate.key,
                                   "why": (f"{consecutive} consecutive permanent failures, "
                                           f"which is the account rather than the brief: "
                                           f"{str(exc)[:200]}")}
                        break
                else:
                    consecutive = 0
        # One judgement per model about the *set*: gallery consistency cannot be a per-image
        # score, because six images each individually fine can still read as six unrelated
        # stock photographs rather than one shop's gallery.
        if result.scores and rendered_urls:
            try:
                answer = (judge or _judge)(db, [rendered_urls[0]], (GALLERY_DIMENSION,))
                result.gallery_consistency = parse_scores(
                    answer, (GALLERY_DIMENSION,))[GALLERY_DIMENSION.key]
            except (PermanentError, TransientError, BenchmarkRefused) as exc:
                result.failures.append({"trial": "gallery_consistency",
                                        "why": str(exc)[:200]})
        result.cad_spent = round(spent, 4)
        complete = len(result.scores) >= expected_samples()
        if result.scores and generator is None:
            _store(db, result, candidate)
        if result.scores and not complete:
            # An incomplete schedule is not a measurement, and the rule has to hold for the
            # decision as well as for storage or the two disagree. It did disagree, live:
            # gpt-image-2 was named winner on a schedule too short to store, so the run that
            # crowned it could not remember doing so. `teardown.audits` already refuses this
            # by name -- scoring part of a schedule lets the run that looked at less
            # outrank the run that looked at all of it.
            unmeasured.append({
                "model": candidate.key,
                "why": (f"{len(result.scores)} of {expected_samples()} samples scored. An "
                        f"incomplete schedule is not a measurement"),
                "failures": result.failures[:3]})
            continue
        if not result.scores:
            # Nothing scored, so nothing was measured -- whether the account could not pay,
            # the credential was rejected or every render failed. A candidate with an empty
            # score list sitting in `results` is a candidate that looks considered and was
            # not, and the only thing standing between that and a winner is `decide`
            # happening to filter it out.
            unmeasured.append(stopped or {
                "model": candidate.key,
                "why": (result.failures[0]["why"] if result.failures
                        else "no render succeeded and no reason was recorded")})
            continue
        results.append(result)

    return {"ran": True, "spent_cad": round(spent, 4),
            "ceiling_cad": BENCHMARK_CEILING_CAD,
            "decision": decide(results, unmeasured=unmeasured),
            "unmeasured": unmeasured,
            "reused": reused,
            "reused_everything": bool(reused) and len(reused) == len(
                [c for c in CANDIDATES if c.can_hold_an_identity]),
            "reuse_rule": ("a candidate already measured under this exact rubric is not "
                           "re-rendered; change the rubric, the trials, the sample count or "
                           "a resolution and every stored score stops matching"),
            "blind": ("the judge was never told which model rendered which image")}


def _judge(db, images_shown, dimensions: tuple[Dimension, ...]) -> str:
    from ..finance import spend_report
    from . import anthropic as gw

    provider = gw.provider_for(JUDGE_TASK)
    estimate = gw.check_budget(
        db, model=provider.model,
        input_tokens=len(score_prompt(dimensions)) // 4
                     + gw.IMAGE_TOKENS_ESTIMATE * max(
                         1, len([images_shown] if isinstance(images_shown, str)
                                else images_shown)),
        max_tokens=JUDGE_MAX_TOKENS)["estimate_cad"]
    shown = [images_shown] if isinstance(images_shown, str) else list(images_shown)
    response = provider.see("", score_prompt(dimensions), shown,
                            max_tokens=JUDGE_MAX_TOKENS)
    spend_report.record(
        db, agent="creative_director",
        amount_cad=round(response.input_tokens * provider.cost_per_1k_input_cad / 1000
                         + response.output_tokens * provider.cost_per_1k_output_cad / 1000,
                         8),
        estimated_cad=estimate, purpose=JUDGE_TASK, provider="anthropic",
        model=provider.model, department="creative",
        tokens_in=response.input_tokens, tokens_out=response.output_tokens,
        detail={"price_basis": "assumed"})
    return response.text


def state(db=None) -> dict:
    """The benchmark's design, its cost and its honest status."""
    try:
        planned = plan()
        refused = ""
    except BenchmarkRefused as exc:
        planned, refused = None, str(exc)
    return {
        "requirement": "owner decision 2026-09-20: measure before locking a provider",
        "eligible": eligible(),
        "plan": planned,
        "plan_refused": refused,
        "rubric": [{"dimension": d.key, "requirement": d.requirement,
                    "question": d.question} for d in RUBRIC]
                  + [{"dimension": IDENTITY_DIMENSION.key,
                      "requirement": IDENTITY_DIMENSION.requirement,
                      "question": IDENTITY_DIMENSION.question}],
        "fabric_floor": FABRIC_FLOOR,
        "deciding_margin": DECIDING_MARGIN,
        "how_cost_is_used": (
            "quality decides unless the quality difference is inside what three samples can "
            "separate, and then cost breaks the tie. Expressed as a score margin rather than "
            "a dollar rule, because the dollars here are small enough that any dollar rule "
            "would dominate"),
        "prompts_are_original": (
            "every trial describes an original Brambleloop subject. Benchmarking on a "
            "competitor's product would be commissioning a copy to see how good the copier "
            "is"),
        **_measured_state(db),
    }


def spent_to_date(db) -> float:
    """Every dollar this benchmark has cost across all its runs.

    `BENCHMARK_CEILING_CAD` was being applied per run, so four runs could each stay inside a
    budget the owner approved once. They did: about CA$21 spent across four runs that
    completed no schedule at all, every one of them lost to a defect in the benchmark rather
    than to a candidate. A ceiling that resets is a ceiling that is not one.
    """
    from sqlalchemy import select

    from ..core.models import AuditLog

    if db is None:
        return 0.0
    total = 0.0
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action.in_(
                ("image.benchmark", CANDIDATE_ACTION, images_reference_action())))):
            total += float((row.detail or {}).get("spent_cad")
                           or (row.detail or {}).get("cad_spent")
                           or (row.detail or {}).get("cad") or 0.0)
    return round(total, 4)


def images_reference_action() -> str:
    from . import images

    return images.REFERENCE_PROBE_ACTION


def last_run(db) -> dict | None:
    """The most recent benchmark job's own record of what it did."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    if db is None:
        return None
    with db.session() as s:
        rows = list(s.scalars(
            select(AuditLog).where(AuditLog.action.in_(
                ("image.benchmark", "image.benchmark_blocked", "image.benchmark_capped")))
            .order_by(desc(AuditLog.id)).limit(1)))
    return dict(rows[0].detail or {}) if rows else None


def _measured_state(db) -> dict:
    """Which candidates have actually been scored, read from the rows rather than asserted.

    `measured` was a literal `False` with a sentence beside it saying no provider account
    existed. That was true when it was written. Two accounts now render and the sentence
    would have gone on denying it -- the same defect as `plan()["runnable"]`, in the same
    module, three days apart, which is how thoroughly a written-down fact resists the world
    changing.
    """
    keep = [c for c in CANDIDATES if c.can_hold_an_identity]
    if db is None:
        return {"measured": None,
                "why_not_measured": "no database was supplied, so nothing was read",
                "measured_candidates": [], "last_run": None}

    rows = {c.key: stored_result(db, c) for c in keep}
    scored = [k for k, r in rows.items() if r is not None]
    outstanding = [c.key for c in keep if c.key not in scored]
    return {
        "results": [{
            "model": k,
            "overall": r.overall(),
            "fabric": round(sum(v for v in (r.mean(f) for f in FABRIC_DIMENSIONS)
                                if v is not None)
                            / max(len([1 for f in FABRIC_DIMENSIONS
                                       if r.mean(f) is not None]), 1), 3),
            "identity_match": r.mean(IDENTITY_DIMENSION.key),
            "by_dimension": {d.key: r.mean(d.key) for d in RUBRIC},
            "judged_images": len(r.scores),
            "repeatability": r.repeatability(),
            "latency_ms_median": r.latency_median(),
            "cad_spent": r.cad_spent,
        } for k, r in rows.items() if r is not None],
        "method_version": METHOD_VERSION,
        "samples_expected": expected_samples(),
        "spent_to_date_cad": spent_to_date(db),
        "approved_budget_cad": BENCHMARK_CEILING_CAD,
        "budget_note": ("cumulative across every run, because a ceiling applied per run is "
                        "a ceiling four runs can each stay inside"),
        "measured": bool(scored),
        "complete": not outstanding,
        "measured_candidates": scored,
        "awaiting_measurement": outstanding,
        "last_run": last_run(db),
        "why_not_measured": (
            "" if not outstanding else
            f"{outstanding} have no scores on file under the current rubric. A candidate "
            f"nobody could render is unmeasured rather than beaten, and no winner is locked "
            f"while one remains"),
    }
