"""What a strong competitor photograph teaches a designer, and what it may never hand over.

Requirements 116 and 278. #116 asks that studying a high-performing product decompose *why*
it works into non-copying primitives. #278 asks that competitor listing photography be a
first-class product input rather than a curiosity: silhouette, proportions, neckline, sleeve
treatment, stripe and blocking logic, colour architecture, styling and seasonal cues.

Those two read as one dangerous sentence and are two safe ones, and the distinction is the
whole module.

**Construction is learnable; depiction is not.** A crew neckline is a construction fact, like
a gauge or a join -- nobody owns the crew neck, and a company that could not observe one
could not make a cardigan. A gnome with a striped hat is a design somebody drew. The
vocabularies below contain necklines and contain nothing that could hold a subject, and
`rights.check_free_of` is reused rather than reimplemented, for the reason #214 gives: two
containment checks drift, and the one that drifts is the one called less often.

**Density is not the motif.** `motif_density` is how much of the surface carries pattern --
sparse, scattered, allover. It is deliberately a *quantity*, because the field that describes
a motif is the field that reproduces it, and a vocabulary with a slot for "what the motif is"
will eventually have one filled in.

**A primitive is a brief, not an instruction.** What this produces goes to concept generation
as constraints to design within -- this silhouette family, this density, this palette role --
and the tournament that follows makes something original inside them. Handing a designer a
competitor's photograph and a list of its properties, with nothing in between, is the
pipeline #227 refuses: a year of defensible choices ending in a shop that looks like a copy
of a shop.
"""
from __future__ import annotations

import json

from ..core.resilience import PermanentError, TransientError
from ..culture import rights

# #278's vocabulary: what a garment or object photograph shows about how it was built. Every
# entry is a construction decision a maker could arrive at independently.
CONSTRUCTION_FIELDS: tuple[str, ...] = (
    "silhouette_class", "proportion", "neckline", "sleeve_treatment", "edge_finish",
    "colour_blocking", "colour_architecture", "styling_context", "seasonal_cue",
)

# #116's vocabulary: the abstract commercial primitives a concept brief is written in.
PRIMITIVES: tuple[str, ...] = (
    "silhouette", "motif_density", "dimensionality", "palette_role", "prop_context",
    "function", "emotional_tone", "construction_novelty",
)

# Closed answer sets where an open one would let a subject in. `motif_density` is the one
# that matters: a quantity, never a description of the motif.
MOTIF_DENSITY: tuple[str, ...] = ("none", "sparse", "scattered", "allover", "structural")
DIMENSIONALITY: tuple[str, ...] = ("flat", "low_relief", "sculptural", "three_dimensional")

# Words that name what a product depicts rather than how it is built. Reused from #214's
# decomposition rules rather than restated, so the two cannot disagree about what a copy is.
from ..intel.mechanisms import DEPICTION_WORDS  # noqa: E402

READ_SYSTEM = (
    "You are a crochet designer reading a competitor's product photograph for construction "
    "evidence. Report only how the object is built and presented. Never name, describe or "
    "identify what the product depicts -- no characters, animals, plants, motifs, subjects "
    "or scenes -- and never transcribe text from the image. If a field does not apply to "
    "this kind of object, omit it."
)

READ_MAX_TOKENS = 700
# The declared task, routed rather than hardcoded. This named the cheap model directly, which
# put the evidence a concept brief is written from on the tier meant for classification --
# and a misread neckline does not announce itself, it becomes a design constraint nobody
# questions afterwards.
TASK = "construction_reading"

# Below this, a primitive set is one listing's habits rather than a market's pattern. The
# same threshold #215 uses for a mechanism becoming a standard, and for the same reason: a
# second independent example is what separates a pattern from one seller's preference.
MIN_LISTINGS_FOR_A_BRIEF = 2


class ReferenceRefused(ValueError):
    """A reading that carries expression rather than construction."""


def read_prompt() -> str:
    return (
        "Reply with a single JSON object and nothing else. Optional keys:\n"
        + "\n".join(f"- {f}" for f in CONSTRUCTION_FIELDS)
        + "\n\nEach value is one short phrase describing construction or presentation. "
          "Omit any key that does not apply. Do not include any key not listed.")


def check_free_of_depiction(values) -> None:
    """Refuse a reading that names what the product depicts.

    The same check `intel.mechanisms` makes, on the same word list, through the same
    function. A second implementation would drift, and the one that drifts is the one on the
    competitor path -- where being wrong is a rights problem rather than an aesthetic one.
    """
    text = " ".join(str(v) for v in values)
    tokens = [rights.ProtectedToken(word, rights.WORK_TITLE, source="depiction vocabulary")
              for word in DEPICTION_WORDS]
    try:
        rights.check_free_of(text, tokens)
    except rights.RightsRefused as exc:
        raise ReferenceRefused(
            f"this reading names what the product depicts rather than how it is built: "
            f"{exc}. A decomposition that keeps the subject is a copy with extra steps") from exc


def parse_reading(text: str) -> dict:
    body = (text or "").strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise ReferenceRefused(f"the model did not answer with JSON: {body[:120]!r}") from exc
    if not isinstance(parsed, dict):
        raise ReferenceRefused(f"expected one object, got {type(parsed).__name__}")

    unknown = sorted(k for k in parsed if k not in CONSTRUCTION_FIELDS)
    if unknown:
        raise ReferenceRefused(
            f"{unknown} are not construction fields. The vocabulary is closed because an "
            f"open one is where a subject arrives: {sorted(CONSTRUCTION_FIELDS)}")
    reading = {k: str(v).strip() for k, v in parsed.items() if str(v).strip()}
    if not reading:
        raise ReferenceRefused("an empty reading is not evidence about anything")
    check_free_of_depiction(reading.values())
    return reading


def read_listing(image_ref: str, *, db=None, provider=None) -> dict:
    """One construction reading of one competitor image (#278)."""
    from ..gateway import anthropic as gw

    provider = provider or gw.provider_for(TASK)
    estimate = 0.0
    reservation = None
    if db is not None:
        # `agent` is what makes `creative_director`'s daily ceiling bind on this path, and the
        # reservation is what stops two of these in two processes both finding room in the
        # same month. Both were absent until 2026-09-25.
        budget = gw.check_budget(
            db, model=provider.model,
            input_tokens=len(read_prompt()) // 4 + gw.IMAGE_TOKENS_ESTIMATE,
            max_tokens=READ_MAX_TOKENS, agent="creative_director", purpose=TASK)
        estimate = budget["estimate_cad"]
        reservation = budget["reservation_id"]
    try:
        response = provider.see(READ_SYSTEM, read_prompt(), [image_ref],
                                max_tokens=READ_MAX_TOKENS)
    except BaseException:
        # Released on the way out, including on a refusal: a reservation a failed call never
        # gives back holds budget nobody is spending until it expires.
        if db is not None:
            gw.release_reservation(db, reservation)
        raise
    if db is not None:
        from ..finance import spend_report

        cost = round(response.input_tokens * provider.cost_per_1k_input_cad / 1000
                     + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
        gw.release_reservation(db, reservation, actual_cad=cost)
        spend_report.record(
            db, agent="creative_director", amount_cad=cost,
            estimated_cad=estimate, purpose=TASK, provider="anthropic",
            model=provider.model, department="creative",
            tokens_in=response.input_tokens, tokens_out=response.output_tokens,
            detail={"price_basis": "assumed"})
    return parse_reading(response.text)


def density_of(observations: list[dict], readings: list[dict]) -> str:
    """Motif density as a quantity, from what was observed rather than from the subject."""
    blocking = " ".join(str(r.get("colour_blocking") or "") for r in readings).lower()
    texture = " ".join(str(o.get("detail_coverage") or "") for o in observations).lower()
    joined = f"{blocking} {texture}"
    for word, value in (("allover", "allover"), ("repeat", "allover"),
                        ("scatter", "scattered"), ("motif", "scattered"),
                        ("stripe", "structural"), ("block", "structural"),
                        ("plain", "none"), ("solid", "none")):
        if word in joined:
            return value
    return "sparse" if joined.strip() else "none"


def primitives(observations: list[dict], readings: list[dict]) -> dict:
    """The #116 primitives, assembled from evidence already gathered.

    Nothing here asks a new question of a model. Both inputs are readings that already exist
    -- the gallery observations from #209 and the construction readings from #278 -- because
    a third question about the same picture is a third bill for an answer already bought,
    and because every extra question is another place a subject could enter.
    """
    def first(source, *fields):
        for item in source:
            for field in fields:
                value = str(item.get(field) or "").strip()
                if value:
                    return value
        return ""

    out = {
        "silhouette": first(readings, "silhouette_class", "proportion"),
        "motif_density": density_of(observations, readings),
        "dimensionality": first(readings, "edge_finish") and "low_relief" or "flat",
        "palette_role": first(observations, "palette_role"),
        "prop_context": first(observations, "setting", "model_product_relationship"),
        "function": first(readings, "styling_context"),
        "emotional_tone": first(observations, "emotional_merchandising"),
        "construction_novelty": first(readings, "sleeve_treatment", "neckline",
                                      "colour_architecture"),
    }
    present = {k: v for k, v in out.items() if v}
    check_free_of_depiction(present.values())
    return {
        "primitives": present,
        "absent": sorted(k for k in PRIMITIVES if k not in present),
        "why_absent": ("a primitive nobody could read from the evidence is left out rather "
                       "than filled with a neutral value, which would keep the brief's shape "
                       "and lose its meaning"),
    }


def brief(db, pod: str, *, benchmark_key: str = "") -> dict:
    """What the observed evidence in one department says a concept must live inside (#116).

    Refused below two listings. One listing's primitives are one seller's habits, and a brief
    written from them is an instruction to make that product again -- which is exactly the
    aggregation failure #227 names, arriving through the design system rather than through a
    decision anybody made.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from ..intel import benchmarks, vision

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        refs = [r.listing_ref for r in s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key,
            BenchmarkListing.pod == pod))]

    observations: list[dict] = []
    readings: list[dict] = []
    with_evidence = 0
    for ref in refs:
        got = vision.observations_for(db, ref, benchmark_key=benchmark_key)
        if not got:
            continue
        with_evidence += 1
        observations.extend(got)
        stored = _stored_readings(db, ref, benchmark_key)
        readings.extend(stored)

    if with_evidence < MIN_LISTINGS_FOR_A_BRIEF:
        return {
            "pod": pod, "listings_with_evidence": with_evidence, "usable": False,
            "reason": (f"{with_evidence} listings in this department have judged images, "
                       f"under {MIN_LISTINGS_FOR_A_BRIEF}. One listing's primitives are one "
                       f"seller's habits, and a brief written from them is an instruction to "
                       f"make that product again"),
        }

    derived = primitives(observations, readings)
    return {
        "pod": pod, "listings_with_evidence": with_evidence, "usable": True,
        **derived,
        "is_a_brief_not_an_instruction": (
            "these are constraints to design within -- this silhouette family, this density, "
            "this palette role -- and the tournament that follows makes something original "
            "inside them. A designer handed a competitor's photograph and its properties, "
            "with nothing in between, is the pipeline #227 refuses"),
        "carries_no_expression": (
            "the vocabularies here have nowhere to put a subject, motif density is a "
            "quantity rather than a description, and every value passes the same containment "
            "check #214 applies to mechanisms"),
    }


def _stored_readings(db, listing_ref: str, benchmark_key: str) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import BenchmarkObservation

    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkObservation).where(
            BenchmarkObservation.benchmark_key == benchmark_key,
            BenchmarkObservation.listing_ref == listing_ref,
            BenchmarkObservation.kind == "construction_reading")))
    return [(r.detail or {}).get("reading") or {} for r in rows]


def record_reading(db, listing_ref: str, reading: dict, *, benchmark_key: str = "",
                   image_key: str = "", env: dict | None = None) -> int:
    """Store one construction reading as dated benchmark evidence."""
    from ..intel import benchmarks, mission

    check_free_of_depiction(reading.values())
    got = mission.record(
        db, benchmark_key=benchmark_key or benchmarks.MJS_KEY,
        kind="construction_reading", listing_ref=listing_ref,
        detail={"reading": reading, "image": image_key}, env=env)
    return got.observation_id


def state() -> dict:
    """What may be learned from a competitor's photograph, and what may never be."""
    return {
        "requirements": [116, 278],
        "construction_fields": list(CONSTRUCTION_FIELDS),
        "primitives": list(PRIMITIVES),
        "motif_density_values": list(MOTIF_DENSITY),
        "minimum_listings_for_a_brief": MIN_LISTINGS_FOR_A_BRIEF,
        "learnable": ("how an object is built and presented. A crew neckline is a "
                      "construction fact like a gauge or a join; nobody owns it, and a "
                      "company that could not observe one could not make a cardigan"),
        "never": ("what the product depicts. The field that describes a motif is the field "
                  "that reproduces it, so `motif_density` is a quantity and there is no slot "
                  "for what the motif is"),
        "containment": ("culture.rights.check_free_of over intel.mechanisms.DEPICTION_WORDS "
                        "-- the same check on the same list through the same function, "
                        "because two implementations drift and the one that drifts is the "
                        "one on the competitor path"),
    }
