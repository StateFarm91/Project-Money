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

# The owner's benchmark budget, in code rather than in a message. A measurement that can
# overrun is a measurement somebody stops trusting.
BENCHMARK_CEILING_CAD = 25.0

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
    Candidate("nano-banana-2", "Google Gemini 3.1 Flash Image (Nano Banana 2)", 0.063, 5,
              "fine-grained fabric and material texture at up to 4K; feature consistency "
              "maintained across up to five characters", resolution="2048"),
    Candidate("imagen-4-ultra", "Google Imagen 4 Ultra", 0.054, 0,
              "the most photorealistic output available; skin, fabric, lighting and "
              "reflections hardest to distinguish from a photograph"),
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
)

# The identity dimension is scored differently: against a reference rather than on its own,
# so it is kept out of the rubric above and asked separately.
IDENTITY_DIMENSION = Dimension(
    "identity_match", 201,
    "Is this the same person as the reference: same facial geometry, hair, eye colour and "
    "apparent age, with no drift in style?")

SCORE_MIN, SCORE_MAX = 0, 4

# A model that cannot render crochet fabric convincingly is not a candidate at any price,
# whatever it does with lighting. Below this mean on the two fabric dimensions it is out.
FABRIC_FLOOR = 2.5

# How much a cost difference is allowed to matter. The owner's instruction, in arithmetic:
# quality decides unless the quality difference is inside the noise, and then cost breaks the
# tie. Expressed as a score margin rather than as a dollar rule, because the dollars here are
# small enough that any dollar rule would dominate.
DECIDING_MARGIN = 0.25


class BenchmarkRefused(ValueError):
    """A benchmark that would report something it did not measure."""


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


def plan() -> dict:
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
    judge_cad = round(judged * 0.004, 4)
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
        "runnable": False,
        "blocked_on": ("credentials. No provider account exists, and creating one needs a "
                       "payment method and identity this build may not supply"),
    }


def score_prompt(dimensions: tuple[Dimension, ...] = RUBRIC) -> str:
    """The judge's question. It never learns which model rendered what."""
    return (
        "You are judging one product image for a crochet pattern shop. Score each dimension "
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
    cad_spent: float = 0.0

    def mean(self, key: str) -> float | None:
        values = [s[key] for s in self.scores if key in s]
        return round(sum(values) / len(values), 3) if values else None

    def overall(self) -> float | None:
        means = [self.mean(d.key) for d in RUBRIC]
        present = [m for m in means if m is not None]
        return round(sum(present) / len(present), 3) if present else None


def decide(results: list[Result]) -> dict:
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
        fabric = [r.mean("stitch_fidelity"), r.mean("material_truth")]
        fabric_mean = round(sum(f for f in fabric if f is not None)
                            / max(len([f for f in fabric if f is not None]), 1), 3)
        rows.append({
            "model": r.model, "overall": r.overall(), "fabric": fabric_mean,
            "by_dimension": {d.key: r.mean(d.key) for d in RUBRIC},
            "identity_match": r.mean(IDENTITY_DIMENSION.key),
            "cad_per_image": BY_KEY[r.model].cad_per_image if r.model in BY_KEY else None,
            "judged_images": len(r.scores), "failures": len(r.failures),
            "meets_fabric_floor": fabric_mean >= FABRIC_FLOOR,
        })

    qualified = [row for row in rows if row["meets_fabric_floor"]]
    if not qualified:
        return {"decided": False, "results": rows,
                "why": (f"no candidate reached the fabric floor of {FABRIC_FLOOR}. A "
                        f"generator that cannot render crochet convincingly is not a "
                        f"candidate for a crochet shop at any price")}

    qualified.sort(key=lambda row: (-row["overall"], row["cad_per_image"] or 0.0))
    best = qualified[0]
    contenders = [row for row in qualified
                  if best["overall"] - row["overall"] <= DECIDING_MARGIN]
    if len(contenders) > 1:
        contenders.sort(key=lambda row: (row["cad_per_image"] or 0.0, -row["overall"]))
        winner = contenders[0]
        why = (f"{len(contenders)} candidates finished within {DECIDING_MARGIN} of each "
               f"other, which is inside what {SAMPLES_PER_TRIAL} samples can separate. "
               f"Cost broke the tie, and only then")
    else:
        winner = best
        why = (f"{winner['model']} scored {winner['overall']} against "
               f"{qualified[1]['overall'] if len(qualified) > 1 else 'nothing else'}, a "
               f"margin wider than {DECIDING_MARGIN}. Quality decided and cost did not")

    return {"decided": True, "winner": winner["model"], "why": why,
            "results": rows, "qualified": [row["model"] for row in qualified],
            "fabric_floor": FABRIC_FLOOR, "deciding_margin": DECIDING_MARGIN}


def run(db, *, generator=None, judge=None, env: dict | None = None) -> dict:
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
    for candidate in [c for c in CANDIDATES if c.can_hold_an_identity]:
        result = Result(model=candidate.key)
        for trial in TRIALS:
            for sample in range(SAMPLES_PER_TRIAL):
                if spent >= BENCHMARK_CEILING_CAD:
                    result.failures.append({"trial": trial.key, "why": "benchmark ceiling"})
                    continue
                try:
                    rendered = (generator or images.generate)(
                        trial.prompt, env=env, size=f"{candidate.resolution}x"
                                                    f"{candidate.resolution}")
                    spent += float(rendered.get("cad") or candidate.cad_per_image)
                    dimensions = ((IDENTITY_DIMENSION,) if trial.needs_reference
                                  else RUBRIC)
                    answer = (judge or _judge)(db, rendered["url"], dimensions)
                    result.scores.append(parse_scores(answer, dimensions))
                except (PermanentError, TransientError, BenchmarkRefused) as exc:
                    result.failures.append({"trial": trial.key, "sample": sample,
                                            "why": str(exc)[:200]})
        result.cad_spent = round(spent, 4)
        results.append(result)

    return {"ran": True, "spent_cad": round(spent, 4),
            "ceiling_cad": BENCHMARK_CEILING_CAD,
            "decision": decide(results),
            "blind": ("the judge was never told which model rendered which image")}


def _judge(db, image_url: str, dimensions: tuple[Dimension, ...]) -> str:
    from . import anthropic as gw

    provider = gw.AnthropicProvider(model=gw.VISION_PROBE_MODEL)
    gw.check_budget(db, model=provider.model,
                    input_tokens=len(score_prompt(dimensions)) // 4
                    + gw.IMAGE_TOKENS_ESTIMATE, max_tokens=400)
    return provider.see("", score_prompt(dimensions), [image_url], max_tokens=400).text


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
        "measured": False,
        "why_not_measured": (
            "no provider account exists. Creating one needs a payment method and an identity "
            "this build may not supply, so the measurement is an owner action and the "
            "benchmark is built and waiting"),
    }
