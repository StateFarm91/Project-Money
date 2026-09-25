"""Image-level observation: the work the API cannot do, queued for when it can.

Requirements 209, 304. The sanctioned Etsy API gives every gallery image's URL and Etsy's own
per-image colour statistics, which answers palette questions outright. What it cannot answer is
whether the shot works: shot type, composition, product visibility, how the model relates to
the product, how the scale is communicated, whether it reads at thumbnail size.

That needs a model with eyes, and the owner approved one. The key is not set
yet, so this builds the queue rather than the excuse: every audited gallery becomes pending
analysis work with a stable identity, and the moment the credential exists the backlog drains
in cost order. Nothing here invents an observation in the meantime.

The vocabulary is closed for the same reason the pods' mechanism list is: an open field accepts
"nice photo", and a competitive intelligence system whose evidence is "nice photo" has learned
nothing it can act on.
"""
from __future__ import annotations

from dataclasses import dataclass

# What a gallery observation is allowed to conclude (#209). Each is something a different
# Brambleloop decision depends on.
OBSERVATION_FIELDS: tuple[str, ...] = (
    "shot_type", "composition", "product_visibility", "model_product_relationship",
    "setting", "scale_communication", "detail_coverage", "infographic_use", "typography",
    "palette_role", "thumbnail_readability", "emotional_merchandising",
)

SHOT_TYPES: tuple[str, ...] = (
    "hero_product_only", "hero_styled", "full_fit", "three_quarter", "detail_macro",
    "flat_lay", "in_use", "scale_reference", "infographic", "process", "packaging",
)

# How many times one image may fail before the queue stops offering it.
#
# A failing image is never marked judged, so without this it returns on every run forever,
# taking a slot and a little money with it: the live runs have carried `failures: 1` in
# every batch since the drain began. Three, then it is counted as given up on and named,
# because an image the provider refuses four times is not an image one more attempt fixes.
FAILED_ATTEMPTS = 3

PENDING = "pending"
ANALYSED = "analysed"
BLOCKED = "blocked"


class AnalysisRefused(ValueError):
    """An observation that is not one of the things a gallery observation may conclude."""


@dataclass(frozen=True)
class PendingAnalysis:
    benchmark_key: str
    listing_ref: str
    image_url: str
    rank: int

    @property
    def key(self) -> str:
        """Stable identity, so the same image is never paid for twice."""
        return f"{self.benchmark_key}:{self.listing_ref}:{self.rank}"

    def to_dict(self) -> dict:
        return {"benchmark": self.benchmark_key, "listing_ref": self.listing_ref,
                "rank": self.rank, "image_url": self.image_url, "key": self.key}


def pending(db, benchmark_key: str, *, limit: int = 200) -> list[PendingAnalysis]:
    """Gallery images that have been inventoried and not yet judged.

    Ordered by listing recency so a release run is analysed before an eighteen-month-old
    listing, which is the order the commercial value arrives in.
    """
    from sqlalchemy import desc, select

    from ..core.models import BenchmarkListing

    with db.session() as s:
        rows = list(s.scalars(
            select(BenchmarkListing)
            .where(BenchmarkListing.benchmark_key == benchmark_key,
                   BenchmarkListing.audit_state == "audited")
            .order_by(desc(BenchmarkListing.last_seen))))

    out: list[PendingAnalysis] = []
    for row in rows:
        detail = row.detail or {}
        if detail.get("gallery_analysed"):
            continue
        # Per image, not per listing. Marking only whole listings would re-offer every
        # image of a listing whose last image failed, and a run that stops at its batch
        # limit part-way through a gallery leaves the rest behind for good.
        done = set(detail.get("gallery_ranks_judged") or [])
        tried = detail.get("gallery_ranks_failed") or {}
        for rank, url in enumerate(detail.get("image_urls") or [], start=1):
            if (url and rank not in done
                    and int(tried.get(str(rank), 0)) < FAILED_ATTEMPTS):
                out.append(PendingAnalysis(benchmark_key, row.listing_ref, url, rank))
            if len(out) >= limit:
                return out
    return out


def pending_count(db, benchmark_key: str) -> dict:
    """How many images are genuinely unjudged, and how many have failed repeatedly.

    Counted over the whole catalogue rather than over a page of it. `analyse` reported
    `remaining` as `len(pending(..., limit=limit * 20))`, which saturates at five hundred:
    with 438 listings carrying several images each the true backlog is thousands, so the
    figure read 500 whether the queue was draining or not. That is the same defect as the
    subtraction it replaced -- a progress number that cannot show progress -- and it would
    have hidden whether B-647's fix worked for weeks.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing

    unjudged = judged = stuck = 0
    with db.session() as s:
        for row in s.scalars(select(BenchmarkListing).where(
                BenchmarkListing.benchmark_key == benchmark_key,
                BenchmarkListing.audit_state == "audited")):
            detail = row.detail or {}
            urls = [u for u in (detail.get("image_urls") or []) if u]
            done = set(detail.get("gallery_ranks_judged") or [])
            tried = detail.get("gallery_ranks_failed") or {}
            judged += len(done)
            for rank in range(1, len(urls) + 1):
                if rank in done:
                    continue
                if int(tried.get(str(rank), 0)) >= FAILED_ATTEMPTS:
                    stuck += 1
                else:
                    unjudged += 1
    return {"unjudged": unjudged, "judged": judged, "given_up_on": stuck}


def check_observation(observation: dict) -> None:
    """Refuse an observation that is not about anything actionable."""
    unknown = [k for k in observation if k not in OBSERVATION_FIELDS]
    if unknown:
        raise AnalysisRefused(
            f"{sorted(unknown)} are not gallery observation fields. The vocabulary is closed "
            f"because an open one accepts 'nice photo', and intelligence whose evidence is "
            f"'nice photo' has taught the company nothing it can act on")
    shot = observation.get("shot_type")
    if shot is not None and shot not in SHOT_TYPES:
        raise AnalysisRefused(f"{shot!r} is not a shot type: {sorted(SHOT_TYPES)}")
    if not observation:
        raise AnalysisRefused("an empty observation is not an observation")


def plan(db, benchmark_key: str, env: dict[str, str] | None = None) -> dict:
    """What image work is outstanding, what it would cost, and whether it can run.

    Reports the backlog whether or not the capability exists, because "how much would this
    cost once the key is set" is exactly the question the owner will ask tomorrow, and it is
    answerable today.
    """
    from ..gateway import routing
    from ..launch import access

    queue = pending(db, benchmark_key)
    per_call = routing.estimate_cad("gallery_observation")
    capable = access.available("model_provider", env)
    budget = routing.budget(db)

    affordable = int(budget.remaining_cad / per_call) if per_call else 0
    return {
        "state": PENDING if capable else BLOCKED,
        "pending_images": len(queue),
        "estimated_cad_per_image": per_call,
        "estimated_cad_total": round(len(queue) * per_call, 4),
        "affordable_this_month": affordable,
        "capability_available": capable,
        "next": [p.to_dict() for p in queue[:10]],
        "note": ("Ready to run: the backlog drains in listing-recency order, newest first, "
                 "because that is the order commercial value arrives in."
                 if capable else
                 "No model provider is configured, so no image has been judged and none has "
                 "been guessed at. The backlog is real work waiting, not a gap being "
                 "papered over (#224)."),
    }


def record(db, analysis: PendingAnalysis, observation: dict,
           *, env: dict[str, str] | None = None) -> int:
    """Store one judged image, and never store one nobody judged."""
    from ..launch import access
    from . import mission

    if not access.available("model_provider", env):
        raise AnalysisRefused(
            "no model provider is configured, so this observation was not produced by looking "
            "at the image. Recording it would be the silent downgrade #224 forbids")
    check_observation(observation)

    got = mission.record(
        db, benchmark_key=analysis.benchmark_key, kind="gallery_image_observation",
        listing_ref=analysis.listing_ref,
        detail={"image": analysis.to_dict(), "observation": observation},
        env=env)
    _mark_judged(db, analysis)
    return got.observation_id


def _mark_failed(db, analysis: PendingAnalysis) -> None:
    """Count one failed attempt against this image, so it is not retried forever.

    A failing image is never marked judged, so before this it came back on every run --
    the live batches carried `failures: 1` every time, taking a slot and a little money
    with it indefinitely. After `FAILED_ATTEMPTS` the queue stops offering it and
    `pending_count` reports it as given up on rather than as outstanding work, because a
    backlog that includes what nobody will retry is not a backlog anybody can clear.
    """
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from ..core.models import BenchmarkListing

    with db.session() as s:
        row = s.scalar(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == analysis.benchmark_key,
            BenchmarkListing.listing_ref == analysis.listing_ref))
        if row is None:
            return
        detail = dict(row.detail or {})
        tried = dict(detail.get("gallery_ranks_failed") or {})
        tried[str(analysis.rank)] = int(tried.get(str(analysis.rank), 0)) + 1
        detail["gallery_ranks_failed"] = tried
        row.detail = detail
        flag_modified(row, "detail")


def _mark_judged(db, analysis: PendingAnalysis) -> None:
    """Record that this image has been judged, so nobody pays to judge it twice.

    `gallery_analysed` was read in `pending` and written nowhere. The backlog therefore
    never shrank: every two-hourly run took the same twenty-five images off the same newest
    listings, judged them, paid for them and left them pending -- about CA$8.50 a day,
    indefinitely, for no new evidence. It looked like progress from the outside because
    `judged: 25` is what a draining queue also reports.
    """
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from ..core.models import BenchmarkListing

    with db.session() as s:
        row = s.scalar(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == analysis.benchmark_key,
            BenchmarkListing.listing_ref == analysis.listing_ref))
        if row is None:
            return
        detail = dict(row.detail or {})
        done = sorted({*(detail.get("gallery_ranks_judged") or []), analysis.rank})
        detail["gallery_ranks_judged"] = done
        urls = [u for u in (detail.get("image_urls") or []) if u]
        tried = detail.get("gallery_ranks_failed") or {}
        settled = {r for r in range(1, len(urls) + 1)
                   if r in done or int(tried.get(str(r), 0)) >= FAILED_ATTEMPTS}
        # Analysed when every image this listing offers is settled -- judged, or given up
        # on after its attempts. Counted rather than assumed from the last one, because a
        # batch limit can land mid-gallery, and an image nobody will retry must not hold a
        # whole gallery open for ever.
        if urls and len(settled) >= len(urls):
            detail["gallery_analysed"] = True
        row.detail = detail
        flag_modified(row, "detail")


# ---------------------------------------------------------------------------
# Actually looking (#209, #304, #303, #61, #79)
#
# Added 2026-09-20. Until then this module built the backlog and said, correctly, that
# nothing had judged an image -- and the note beside it said the reason was that no model
# provider was configured. That stopped being true on 2026-09-19, when the provider was
# credentialed and a real call succeeded. Nobody had written the call, which is a different
# thing from nobody being able to make it, and the two were indistinguishable from the
# outside for a day. The parked-on-a-capability story survived the capability arriving.


# What the model is asked, and the shape the answer must come back in. The vocabulary is
# closed on both sides: a question with an open answer produces "nice photo", and a closed
# question with an open parser produces "nice photo" one layer down.
ANALYSIS_SYSTEM = (
    "You are looking at one product photograph from a competitor's marketplace listing, as "
    "commercial evidence. Describe only how the photograph works as merchandising. Never "
    "describe, name or transcribe the depicted design, motif, character or subject, and "
    "never reproduce text from the image. If a field cannot be judged from this image, omit "
    "it rather than guessing."
)

# The declared task this analysis routes through. Named once so the tier, the token budget
# and the ledger's `purpose` cannot disagree about what is being paid for.
TASK = "gallery_observation"
ANALYSIS_MAX_TOKENS = 1200

# Whose permission this spends under. Named once for the same reason `TASK` is: the ceiling
# check, the ledger row and the cadence that sizes the batch all have to be talking about the
# same agent, and a name written three times is a name that will disagree with itself.
AGENT = "market_radar"


def per_image_estimate_cad(model: str | None = None) -> float:
    """What one gallery image is expected to cost, on the arithmetic the ceiling uses.

    The same estimator, the same padding, the same image-token figure as the `check_budget`
    call in `analyse` below -- because this number is what the cadence's batch size is derived
    from, and a batch sized on one estimate against a guard enforced on another is two numbers
    disagreeing about the same money, which is the defect this whole change is about.

    Deliberately the padded estimate rather than the measured mean. The measured mean this
    month is about CA$0.034 an image and the padded estimate is about CA$0.062; sizing on the
    mean would plan a batch the second half of which the guard refuses. This build has already
    been wrong about the image-token figure twice, both times optimistically -- see
    `gateway.anthropic.IMAGE_TOKENS_ESTIMATE`, which carries the story.
    """
    from ..gateway import anthropic as gw
    from ..gateway import routing

    if model is None:
        _, tier = routing.route(TASK)
        model = tier.model
    return gw.estimate_cad(model,
                           input_tokens=len(analysis_prompt()) // 4
                                        + gw.IMAGE_TOKENS_ESTIMATE,
                           output_tokens=ANALYSIS_MAX_TOKENS)


def analysis_prompt() -> str:
    """The question, built from the closed vocabulary so the two cannot drift apart."""
    return (
        "Reply with a single JSON object and nothing else. Permitted keys, all optional:\n"
        + "\n".join(f"- {field}" for field in OBSERVATION_FIELDS)
        + f"\n\n`shot_type`, when present, must be exactly one of: "
        + ", ".join(SHOT_TYPES)
        + "\n\nEvery other value is one short phrase. Omit any key you cannot judge."
    )


def parse_observation(text: str) -> dict:
    """Read the model's answer, and refuse anything that is not an observation.

    Refusing here rather than storing and filtering later is the point: `record()` already
    guards the vocabulary, and a parser that quietly drops unknown keys would turn a model
    that answered the wrong question into a thin observation nobody could distinguish from
    a hard image.
    """
    import json

    body = (text or "").strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise AnalysisRefused(
            f"the model did not answer with JSON: {body[:120]!r}. An answer that has to be "
            f"guessed at is the observation this module refuses") from exc
    if not isinstance(parsed, dict):
        raise AnalysisRefused(f"expected one object, got {type(parsed).__name__}")

    observation = {k: v for k, v in parsed.items() if v not in (None, "", [], {})}
    check_observation(observation)
    return observation


def analyse(db, benchmark_key: str, *, limit: int = 10,
            provider=None, env: dict[str, str] | None = None,
            job_id: int | None = None) -> dict:
    """Judge up to `limit` pending gallery images, one call each, and record what was seen.

    One image per call rather than a batch. A batch is cheaper per image and makes a single
    refusal lose every observation in it, and -- worse -- invites the model to answer about
    the set, which is how a per-image field quietly becomes an impression of a gallery.

    Every failure is counted and named. A run that judged nothing returns `judged: 0` with
    the reasons, because a drain loop whose failure mode is an empty result looks identical
    to an empty backlog.
    """
    from ..core.resilience import PermanentError, TransientError
    from ..gateway import anthropic as gw

    # The declared tier for this task, not a hardcoded cheap model. This called
    # `VISION_PROBE_MODEL` -- the probe's model, chosen because a probe should be the
    # smallest possible real call -- which quietly routed the owner's second-highest
    # spending priority through the cheapest tier while `routing.TASKS` declared `standard`.
    # A probe's model is not an analysis model, and the two sharing a constant is how the
    # substitution happened without anybody choosing it.
    provider = provider or gw.provider_for(TASK)
    queue = pending(db, benchmark_key, limit=limit)

    judged, failures, spent = 0, [], 0.0
    reserved, tokens_in, tokens_out = 0.0, 0, 0
    stopped_by = ""
    for item in queue:
        estimate = 0.0
        held = None
        try:
            # `uncommitted_cad` is this run's own spend, which is not in the ledger yet:
            # this loop bills once, at the end, so without it every image after the first
            # was checked against the month as it stood before the run began. The larger of
            # what the run has actually cost and what it reserved, because the reservation
            # is deliberately pessimistic and a ceiling check should not become optimistic
            # by taking the smaller of two numbers.
            #
            # `agent` is new on 2026-09-25 and is the reason a run can now stop part-way:
            # `market_radar` may spend CA$4.00 a day, that ceiling was checked by nothing on
            # this path, and the handler sizes the batch to fit it. A batch that still runs
            # out is a batch the day's other cadences have eaten into, which is exactly when
            # a permission should bite.
            reservation = gw.check_budget(
                db, model=provider.model,
                input_tokens=len(analysis_prompt()) // 4 + gw.IMAGE_TOKENS_ESTIMATE,
                max_tokens=ANALYSIS_MAX_TOKENS,
                uncommitted_cad=max(spent, reserved),
                agent=AGENT, purpose=TASK, job_id=job_id)
            estimate = reservation["estimate_cad"]
            held = reservation["reservation_id"]
            response = provider.see(ANALYSIS_SYSTEM, analysis_prompt(), [item.image_url],
                                    max_tokens=ANALYSIS_MAX_TOKENS)
        except gw.AgentCeilingExceeded as exc:
            # This agent is finished for today. The month may well have room, so this is
            # reported as a stop with a named ceiling rather than as a failure -- the images
            # are still pending and the next run takes them.
            gw.release_reservation(db, held)
            stopped_by = "agent_daily_ceiling"
            failures.append({"key": item.key, "why": f"agent ceiling: {exc}"})
            break
        except gw.BudgetExceeded as exc:
            # The ceiling is not a per-image failure; it ends the run. Continuing would
            # attempt the same refusal once per remaining image.
            gw.release_reservation(db, held)
            stopped_by = "monthly_model_ceiling"
            failures.append({"key": item.key, "why": f"budget: {exc}"})
            break
        except (PermanentError, TransientError) as exc:
            gw.release_reservation(db, held)
            failures.append({"key": item.key, "why": str(exc)[:200]})
            _mark_failed(db, item)
            continue

        cost = round(
            response.input_tokens * provider.cost_per_1k_input_cad / 1000
            + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
        # Released as soon as the call has answered, with what it actually cost. Holding it
        # until the end of the run would make this loop block itself: twenty-five images
        # reserving pessimistically and releasing nothing is a run that refuses its own
        # later images against money it had already spent and counted once.
        gw.release_reservation(db, held, actual_cad=cost)
        spent += cost
        reserved += estimate
        tokens_in += response.input_tokens
        tokens_out += response.output_tokens
        try:
            observation = parse_observation(response.text)
            record(db, item, observation, env=env)
        except AnalysisRefused as exc:
            failures.append({"key": item.key, "why": str(exc)[:200]})
            _mark_failed(db, item)
            continue
        judged += 1

    _bill(db, spent, judged, job_id, provider=provider, reserved=reserved,
          tokens_in=tokens_in, tokens_out=tokens_out)
    backlog = pending_count(db, benchmark_key)
    return {
        "benchmark": benchmark_key,
        "model": provider.model,
        "tier": TASK,
        "judged": judged,
        "reserved_cad": round(reserved, 8),
        "attempted": len(queue),
        # Counted after the run, with nothing subtracted. This read the backlog and then
        # took this run's `judged` off it -- which made the number fall by twenty-five
        # every time while the backlog itself stood still, so a queue that was not
        # draining reported as one that was.
        # Counted over the whole catalogue, not over a page of it, and not saturating.
        **{"remaining": backlog["unjudged"], "backlog": backlog},
        "failures": failures,
        "stopped_by": stopped_by,
        "cost_cad": round(spent, 8),
        "note": ("nothing was judged and the backlog is not empty, which is a failure rather "
                 "than a quiet success -- the reasons are above"
                 if queue and not judged else
                 "an image judged is an image looked at; nothing here infers an observation "
                 "from a title"),
    }


def _bill(db, spent: float, judged: int, job_id: int | None, *, provider,
          reserved: float = 0.0, tokens_in: int = 0, tokens_out: int = 0) -> None:
    """One ledger row for the run, with every dimension the spend policy reports by."""
    if spent <= 0:
        return
    from ..finance import spend_report

    spend_report.record(
        db, agent=AGENT, amount_cad=round(spent, 8),
        estimated_cad=round(reserved, 8), purpose=TASK, provider="anthropic",
        model=provider.model, department="intel", job_id=job_id,
        tokens_in=tokens_in, tokens_out=tokens_out,
        detail={"images_judged": judged, "price_basis": "assumed"})


# ---------------------------------------------------------------------------
# What the judged images are for (#303, #210, #211, #116, #278)
#
# Judging images and *using* them are different pieces of work, and the second is where the
# containment rule is easiest to lose: a summary that carried the depicted subject forward
# would be a copy assembled one field at a time, however carefully each field was gathered.
# So everything below is derived from the closed observation vocabulary, which has nowhere to
# put a motif, and nothing reads a listing title.


# The two columns `intel.market_map` calls vision attributes. Each is derived from the
# observation fields rather than asked for separately: a second question about the same
# picture is a second bill for an answer already bought.
SILHOUETTE_FROM = ("shot_type", "product_visibility", "scale_communication")
MECHANISM_FROM = ("composition", "setting", "model_product_relationship",
                  "infographic_use", "typography", "emotional_merchandising")

# Below this many judged images for a listing, the derived columns are absent rather than
# thin. One image is one photographer's decision about one frame, and a silhouette read from
# it would be a fact about the hero shot presented as a fact about the product.
MIN_IMAGES_FOR_ATTRIBUTES = 2


def observations_for(db, listing_ref: str, *, benchmark_key: str = "") -> list[dict]:
    """Every recorded judgement about this listing's gallery."""
    from sqlalchemy import select

    from ..core.models import BenchmarkObservation
    from . import benchmarks

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkObservation).where(
            BenchmarkObservation.benchmark_key == benchmark_key,
            BenchmarkObservation.listing_ref == listing_ref,
            BenchmarkObservation.kind == "gallery_image_observation")))
    return [(r.detail or {}).get("observation") or {} for r in rows]


def derive(observations: list[dict]) -> dict:
    """The two map columns, or nothing, from what was actually seen.

    Absent rather than partial. A column computed from one image looks the same in the map as
    one computed from twelve, and the map's whole job is that a cell somebody points at in a
    planning meeting means what it appears to mean.
    """
    if len(observations) < MIN_IMAGES_FOR_ATTRIBUTES:
        return {}

    def gather(fields):
        seen: list[str] = []
        for observation in observations:
            for field in fields:
                value = str(observation.get(field) or "").strip()
                if value and value not in seen:
                    seen.append(value)
        return seen

    silhouette = gather(SILHOUETTE_FROM)
    mechanism = gather(MECHANISM_FROM)
    out = {}
    if silhouette:
        out["silhouette"] = {"from_images": len(observations), "reads": silhouette}
    if mechanism:
        out["merchandising_mechanism"] = {"from_images": len(observations),
                                          "reads": mechanism}
    return out


def attributes_for(db, listing_ref: str, *, benchmark_key: str = "") -> dict:
    """The vision columns for one listing, derived from judged images or absent."""
    return derive(observations_for(db, listing_ref, benchmark_key=benchmark_key))


def coverage(db, *, benchmark_key: str = "") -> dict:
    """How much of the catalogue has been looked at, and how much is still queued.

    Reported as a fraction with both numbers, because "vision is available" and "vision has
    been applied" are different claims and the first is the one a dashboard shows.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing, BenchmarkObservation
    from ..gateway.anthropic import vision_usable
    from . import benchmarks

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        audited = len(list(s.scalars(select(BenchmarkListing.listing_ref).where(
            BenchmarkListing.benchmark_key == benchmark_key,
            BenchmarkListing.audit_state == "audited"))))
        judged = {r for (r,) in s.execute(select(BenchmarkObservation.listing_ref).where(
            BenchmarkObservation.benchmark_key == benchmark_key,
            BenchmarkObservation.kind == "gallery_image_observation").distinct())}

    return {
        "capability_proven": vision_usable(db),
        "listings_audited": audited,
        "listings_with_a_judged_image": len(judged),
        "share": round(len(judged) / audited, 4) if audited else 0.0,
        "pending_images": len(pending(db, benchmark_key, limit=5000)),
        "note": ("the capability being proven and the catalogue being looked at are "
                 "different claims, and a dashboard that reports the first is reporting the "
                 "one that is easy"),
    }


def by_pod(db, *, benchmark_key: str = "") -> dict:
    """Image evidence gathered per specialist pod (#210), and per-pod honesty about gaps.

    This is what each pod's opportunity map is built from. A pod with no judged images gets
    an empty map that says so, rather than an empty map that looks like a department with
    nothing going on in it.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from . import benchmarks

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        rows = [(r.listing_ref, r.pod) for r in s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key))]

    out: dict[str, dict] = {}
    for ref, pod in rows:
        bucket = out.setdefault(pod or "unclassified",
                                {"listings": 0, "judged": 0, "reads": []})
        bucket["listings"] += 1
        observations = observations_for(db, ref, benchmark_key=benchmark_key)
        if observations:
            bucket["judged"] += 1
            derived = derive(observations)
            for value in derived.values():
                for read in value["reads"]:
                    if read not in bucket["reads"]:
                        bucket["reads"].append(read)

    for pod, bucket in out.items():
        bucket["share"] = round(bucket["judged"] / bucket["listings"], 4)
        bucket["state"] = (
            "empty because nothing in this department has been judged yet"
            if not bucket["judged"] else
            f"{bucket['judged']} of {bucket['listings']} listings judged")
    return out
