"""One seasonal cycle, end to end, with every step's evidence rather than its assertion.

Requirement 300, and the requirement calls itself release-blocking. It asks Build 2 to
*demonstrate* a full cycle: observe a benchmark signal, classify what that market is made of,
choose an upcoming event, compute the customer's lead time and the launch date, generate
several original responses, select and engineer one, certify it, create assets this company
owns, prepare search, and **show that the scheduler launched early enough for a customer to
make the thing before the event**.

The last clause is the one that makes it an acceptance test rather than a checklist. A
seasonal product that goes live two weeks before Christmas is not late by a little; it is a
product nobody can finish, and every step before it was wasted. So the cycle ends on an
arithmetic comparison -- launch date plus the maker's own time against the event date -- and
that comparison is the verdict.

Three rules keep the demonstration honest.

**A step reports evidence, not success.** Each one returns what it actually produced -- a
count, a date, a certificate's verdict -- so a step that ran and achieved nothing is visible
as such rather than as a tick.

**A gated step is named, never simulated.** Image generation and paid search are owner
capabilities this company does not have. Filling them with placeholders would produce a green
cycle that proves nothing, which is the failure mode the funnel's five stages are arranged
against one level up. They report `gated`, with the capability that would open them.

**The cycle's verdict is the weakest ungated step.** Not an average and not a count of green
ticks: one broken link in a backward-chained schedule breaks the schedule, and an average is
how that gets hidden.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

RAN, GATED, FAILED = "ran", "gated", "failed"

# Every link the requirement names, in the order it names them. A cycle that stopped early
# has steps that are *absent*, and absent is not gated: the first version of this reported
# `complete: true` for a run with no model provider, which had invented nothing, engineered
# nothing and certified nothing. A missing step is not a passing one.
EXPECTED_STEPS: tuple[str, ...] = (
    "observe", "classify", "choose_event", "launch_date", "generate",
    "engineer", "certify", "assets", "search")


@dataclass
class Step:
    """One link in the cycle: what it is for, what it produced, and what it waits on."""

    key: str
    what: str
    state: str = FAILED
    evidence: dict = field(default_factory=dict)
    gated_on: str = ""
    why: str = ""

    def to_dict(self) -> dict:
        return {"step": self.key, "what": self.what, "state": self.state,
                "evidence": self.evidence, "gated_on": self.gated_on, "why": self.why}


class CycleRefused(ValueError):
    """A cycle that cannot be demonstrated, said out loud rather than reported as partial."""


def run(db, *, today: date | None = None, gateway=None,
        benchmark_key: str = "", asset_maker=None) -> dict:
    """Run one simulated seasonal cycle and report what each link actually produced.

    `asset_maker` is how the assets link gets closed, and only a job ever passes one. The
    cycle authors and certifies its concept in memory and never files it in the catalogue
    -- correctly, because #300 asks for a *simulated* cycle and filing a product on every
    page view would inflate the catalogue that #292 exists to protect. But the daily
    photography job looks products up by slug, so it can never reach this one, which left
    the assets link unreachable for the very product the chain produced.

    So the maker takes the CIR in hand rather than a slug. `run` stays free when nobody
    passes one -- this endpoint is a GET, and a GET that spends money spends it every time
    a test sweep walks the routes.
    """
    from ..creative.audit import catalogue_concepts
    from ..creative.prospecting import (NoArenasContradictsEvidence, arenas, choose,
                                        slots)
    from ..intel import benchmarks

    today = today or date.today()
    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    steps: list[Step] = []

    def add(key: str, what: str) -> Step:
        step = Step(key=key, what=what)
        steps.append(step)
        return step

    # 1. Observe a benchmark market signal ------------------------------------
    observe = add("observe", "a benchmark market signal somebody actually recorded")
    from sqlalchemy import func, select

    from ..core.models import BenchmarkListing

    with db.session() as s:
        observed = s.scalar(select(func.count(BenchmarkListing.id)).where(
            BenchmarkListing.benchmark_key == benchmark_key)) or 0
    if observed:
        observe.state = RAN
        observe.evidence = {"listings_observed": observed, "benchmark": benchmark_key}
    else:
        observe.why = ("no listing has been observed in the benchmark catalogue, so there "
                       "is no market signal to start a cycle from")
        return _verdict(steps, today, None, None)

    # 2. Classify what that market is made of ---------------------------------
    classify = add("classify", "the generic product characteristics of that market")
    try:
        found = arenas(db, today=today)
    except NoArenasContradictsEvidence as e:
        classify.why = str(e)[:300]
        return _verdict(steps, today, None, None)
    if not found:
        classify.why = ("the benchmark is observed but no arena is both proven and unserved, "
                        "so there is nothing this catalogue does not already answer")
        return _verdict(steps, today, None, None)
    classify.state = RAN
    classify.evidence = {"proven_and_unserved_arenas": len(found),
                         "pods": sorted({a.pod for a in found})}

    # 3. Choose an upcoming event ---------------------------------------------
    chosen = add("choose_event", "an upcoming event with runway left")
    arena = choose(found, cycle=0, today=today)
    chosen.state = RAN
    chosen.evidence = {"event": arena.event, "pod": arena.pod,
                       "days_away": arena.days_away,
                       "benchmark_listings": arena.benchmark_listings}

    # 4. Lead time and launch date --------------------------------------------
    schedule = add("launch_date", "the customer's lead time, chained backwards to a date")
    catalogue = catalogue_concepts()
    plan = slots(arena, catalogue=catalogue, today=today)
    if not plan["slot_objects"]:
        schedule.why = ("no form in this arena can still be made in time, which is a "
                        "statement about the calendar rather than about the catalogue")
        return _verdict(steps, today, arena, None)
    slot = plan["slot_objects"][0]
    launch = _launch_for(arena, slot, today=today)
    schedule.state = RAN
    schedule.evidence = {
        "make_lane": slot.make_lane,
        "make_hours": launch.make_hours,
        "effective_make_days": launch.effective_make_days,
        "latest_effective_launch": launch.latest_effective_launch.isoformat(),
        "preferred_launch": launch.preferred_launch.isoformat(),
        "work_must_start_by": launch.work_must_start_by.isoformat(),
    }

    # 5. Generate several original responses -----------------------------------
    generate = add("generate", "several original seasonal responses, not one")
    if gateway is None:
        generate.state = GATED
        generate.gated_on = "model_provider"
        generate.why = ("generating a field needs the model provider. A placeholder concept "
                        "would make this cycle green and prove nothing")
        return _verdict(steps, today, arena, launch)

    from ..creative.prospecting import propose

    candidates, refused = propose(slot, gateway=gateway, count=6)
    if len(candidates) < 2:
        generate.why = (f"{len(candidates)} concept(s) parsed from the generator, and 'several "
                        f"original responses' is not one. Refusals: {refused[:2]}")
        return _verdict(steps, today, arena, launch)
    generate.state = RAN
    generate.evidence = {"proposed": len(candidates), "refused": len(refused),
                         "forms": sorted({c.concept.form for c in candidates})}

    # 6. Select and engineer one ----------------------------------------------
    engineer = add("engineer", "one selected concept, authored as a checkable pattern")
    from ..creative.prototype import PrototypeRefused, author

    cir = None
    for candidate in candidates:
        try:
            cir = author(candidate.concept)
        except PrototypeRefused:
            continue
        break
    if cir is None:
        engineer.why = ("no proposed concept has a form with a finished size on file, so "
                        "none of them can be engineered yet. That is the geometry backlog")
        return _verdict(steps, today, arena, launch)
    engineer.state = RAN
    engineer.evidence = {"slug": cir.slug, "construction": cir.construction,
                         "gauge_sts_per_10cm": cir.gauge.stitches_per_10cm}

    # 7. Certify it ------------------------------------------------------------
    certified = add("certify", "the full release chain, run rather than asserted")
    from ..gates.certificate import certify

    certificate = certify(cir)
    certified.state = RAN if certificate.granted else FAILED
    certified.evidence = {"granted": certificate.granted,
                          "stages_run": list(certificate.stages_run),
                          "blocking": certificate.blocking_reasons[:3]}
    if not certificate.granted:
        certified.why = ("the release chain refused this pattern, which is the chain working. "
                         "A cycle that certified it anyway would be demonstrating nothing")
        return _verdict(steps, today, arena, launch)

    # 8. Assets this company owns ----------------------------------------------
    assets = add("assets", "publishable visual assets Brambleloop made itself")
    from ..gateway import images as _images
    from ..publish import owned_photography

    # For *this cycle's* product, not for whichever product was photographed last.
    #
    # `last_asset(db)` returns the most recent owned asset on file, and the cycle was
    # handing that straight into step 8 as its own evidence. On 2026-09-22 the run
    # engineered `hats-hat-0` and the assets step reported `cloudline-baby-blanket`: a
    # launch-blocking end-to-end acceptance test evidencing a different product than the
    # one its own chain produced, and reporting that product's motif failure as this
    # cycle's. Both halves are wrong -- the chain is broken, and the failure is
    # misattributed, so a pass would have been meaningless and the fail was about
    # something else.
    from ..publish import listing_asset

    owned = listing_asset.last(db, slug=cir.slug)
    # A maker was handed in, so this run is allowed to produce the thing it reports on --
    # for the CIR in hand rather than by slug, which is the whole reason the daily job
    # cannot cover a cycle-internal product. Only a job passes one; the endpoint does not,
    # and a GET that spends money spends it every time a sweep walks the routes.
    declined: dict = {}
    if owned is None and asset_maker is not None and _images.usable(db):
        declined = asset_maker(cir) or {}
        from ..publish import listing_asset

    owned = listing_asset.last(db, slug=cir.slug)
    if not _images.usable(db):
        assets.state = GATED
        assets.gated_on = "image_generation"
        assets.why = ("chart and schematic assets render from the certified CIR today; "
                      "a styled image of the finished object needs the image-generation "
                      "capability, and no successful generation is on file. Rendering a "
                      "placeholder and calling it a product photograph is the one thing "
                      "the asset-truth gate exists to refuse")
    elif owned is None:
        # Read rather than rendered: a report that generated an image every time somebody
        # opened an endpoint would spend money to answer a question about the past.
        #
        # Two reasons there is no asset, and they are not the same finding. The daily job
        # photographs *catalogue* products, and this cycle authors its concept in memory
        # and certifies it without filing it -- so for a cycle-internal product the job
        # can never reach it, and reporting that as "waiting for the daily job" would be a
        # gate that cannot open. Saying which one it is, is the difference between a queue
        # entry somebody can act on and a permanent blocker wearing one.
        from ..products.builder import for_slug

        in_catalogue = for_slug(cir.slug) is not None
        assets.evidence = {"slug": cir.slug, "in_catalogue": in_catalogue,
                           "other_products_have_assets": bool(listing_asset.last(db))}
        waiting = str(declined.get("waiting_on") or "") if declined else ""
        if declined and not declined.get("made"):
            # The maker ran and refused, and its reason outranks every guess below it.
            #
            # Without this the step would report "never filed in the catalogue" for a
            # product the maker declined for an entirely different reason -- and the
            # reason it declines most often is the live one: the cycle's arena is `hats`,
            # a hat is not a product-first form, and a model-bearing frame is blocked
            # while the canonical identity is built and unapproved. Reporting a gate on
            # the owner's decision as a filing problem would send the next session after
            # the catalogue and leave the actual blocker unmentioned.
            # A wait is a gate only when the thing waited on is outside this build.
            #
            # This mapped any named `waiting_on` to GATED, and a GATED link does not stop
            # `complete` -- so within minutes of the canonical identity being frozen, #300
            # reported `complete: true` with `assets_state: gated` and no asset ever made.
            # The refusal it was gating on was `model_bearing_render_path`, which is work
            # nobody has done rather than a capability nobody has granted. Calling our own
            # unfinished work a gate is how a launch-blocking acceptance test passes
            # without doing the thing it tests.
            #
            # Unrecognised waits fail rather than gate, so a new refusal reason added
            # somewhere else cannot quietly buy itself a pass.
            external = waiting in EXTERNAL_WAITS
            assets.state = GATED if external else FAILED
            assets.gated_on = waiting if external else ""
            assets.evidence["form"] = declined.get("form") or owned_photography.form_of(cir)
            assets.why = declined.get("why", "the asset maker declined without a reason")
        elif in_catalogue:
            assets.state = GATED
            assets.gated_on = "owned_photography_job"
            assets.why = (f"image generation is proven and no owned asset has been "
                          f"rendered for {cir.slug} yet. `assets.owned_photography` runs "
                          f"daily and makes one per release; this step reports what "
                          f"exists for this cycle's own product rather than making it, "
                          f"and rather than borrowing another product's photograph to "
                          f"look complete")
        else:
            assets.state = FAILED
            assets.gated_on = ""
            assets.why = (f"{cir.slug} was engineered and certified inside this cycle and "
                          f"never filed in the catalogue, and the photography job "
                          f"photographs catalogue products -- so no asset can ever be "
                          f"made for it. This link is structurally unreachable for a "
                          f"cycle-internal product rather than merely waiting. Filing "
                          f"the product would fix it and would inflate the catalogue on "
                          f"every page view, which is what #292 exists to refuse, so the "
                          f"fix is an `asset_maker`: a job runs this cycle and renders "
                          f"for the CIR in hand. Reported as a failure rather than as "
                          f"gated because a gate that cannot open is not a gate, and "
                          f"because the previous behaviour -- handing in whichever "
                          f"product was photographed last -- made this look complete")
    elif owned.get("verdict") == "clear" and not owned.get("motif_verified"):
        # Rendered, every asset-truth check passed, and the fabric is not the pattern's
        # fabric -- or could not be seen well enough to tell. Both block a customer-facing
        # asset; the difference is that one needs a different render and the other needs a
        # closer frame, and the record says which.
        assets.state = FAILED
        assets.gated_on = ""
        assets.evidence = {
            "slug": owned.get("slug"), "form": owned.get("form"),
            "image": (owned.get("image") or {}).get("url"),
            "verdict": owned.get("verdict"),
            "motif_claimed": owned.get("motif_claimed"),
            "motif_verdict": (owned.get("motif") or {}).get("verdict"),
            "disclosed_as_illustration": owned.get("disclosed_as_illustration"),
            "charts_and_schematics": "rendered deterministically from the certified CIR"}
        assets.why = owned.get("motif_why", "")
    elif owned.get("usable_as_listing_asset"):
        assets.state = RAN
        assets.evidence = {
            "slug": owned.get("slug"), "form": owned.get("form"),
            "image": (owned.get("image") or {}).get("url"),
            "verdict": owned.get("verdict"),
            "disclosed_as_illustration": owned.get("disclosed_as_illustration"),
            "disclosure": owned.get("disclosure"),
            "charts_and_schematics": "rendered deterministically from the certified CIR"}
    else:
        assets.state = FAILED
        assets.evidence = {"slug": owned.get("slug"), "verdict": owned.get("verdict")}
        assets.why = (f"an owned asset was rendered and did not clear the asset-truth "
                      f"gate: {owned.get('why', '')[:160]}. An asset that failed its "
                      f"checks is not an asset")

    # 9. Search and ads ---------------------------------------------------------
    search = add("search", "search coverage prepared, and paid media named as gated")
    from ..commerce.intent import arena_language

    language = arena_language(db, pod=arena.pod, benchmark_key=benchmark_key)
    if language.get("measurable"):
        search.state = RAN
        search.evidence = {"observed_terms": sum(
            len(rows) for rows in (language.get("by_facet") or {}).values()),
            "paid_media": "gated on ad_authority"}
    else:
        search.state = GATED
        search.gated_on = "benchmark_observation"
        search.why = language.get("reason", "")

    return _verdict(steps, today, arena, launch)


def _launch_for(arena, slot, *, today: date):
    """Chain the customer's own make time backwards from the event."""
    from .leadtime import DEFAULT, compile_launch

    hours = {"QUICK": 3.0, "SHORT": 8.0, "MEDIUM": 20.0, "LONG": 45.0,
             "FLAGSHIP": 90.0}.get(slot.make_lane, 20.0)
    return compile_launch(arena.event, today + timedelta(days=arena.days_away),
                          make_hours=hours, assumptions=DEFAULT)


# Things a refusal may wait on that are genuinely outside this build, and are therefore
# gates rather than unfinished work. A gated link does not stop the cycle reporting
# complete, which is why membership here has to be earned: money nobody has added and
# authority nobody has granted are gates; a render path nobody has written is not.
#
# Deliberately a closed set with a failing default. An unrecognised wait is treated as
# unfinished work, so a refusal reason invented elsewhere cannot buy itself a pass by
# naming something plausible.
EXTERNAL_WAITS: frozenset[str] = frozenset({
    "model_provider_balance",     # the provider's account is empty; only the owner adds to it
    "canonical_model",            # the owner has not approved an identity
    "ad_authority",               # no approved advertising budget
    "image_generation",           # no image provider has demonstrated a render
    "owned_photography_job",      # the daily job has not reached this product yet
})


def _verdict(steps: list[Step], today: date, arena, launch) -> dict:
    """The cycle's answer: the weakest ungated link, and whether a buyer could finish in time.

    A count of green steps would let nine working links hide one broken one, and a backward
    chained schedule is exactly the structure where that matters -- the whole point of the
    chain is that every link has to hold.
    """
    ran = [s for s in steps if s.state == RAN]
    gated = [s for s in steps if s.state == GATED]
    failed = [s for s in steps if s.state == FAILED]

    in_time = None
    timing = {}
    if launch is not None and arena is not None:
        event_date = today + timedelta(days=arena.days_away)
        # The earliest this product can actually go live is today, not the date the backward
        # chain would have preferred. Measuring from a preferred date that has already passed
        # is how a cycle reports "launched early enough" about a window it missed -- the
        # first run of this reported `complete: true` on a launch date twenty days gone.
        missed = launch.preferred_launch < today
        effective_launch = max(launch.preferred_launch, today)
        finishes = effective_launch + timedelta(
            days=launch.effective_make_days + launch.assumptions.completion_buffer_days)
        in_time = finishes <= event_date
        timing = {
            "event_date": event_date.isoformat(),
            "preferred_launch": launch.preferred_launch.isoformat(),
            "earliest_possible_launch": effective_launch.isoformat(),
            "preferred_window_already_passed": missed,
            "a_buyer_starting_then_finishes": finishes.isoformat(),
            "days_to_spare": (event_date - finishes).days,
            "why": (
                f"the backward chain wanted this live on "
                f"{launch.preferred_launch.isoformat()}, which has passed. Measured from "
                f"today instead, because a date that has gone cannot be launched on and a "
                f"cycle measuring from one is reporting about a window it missed"
                if missed else
                "measured from the launch date the backward chain chose, which is still "
                "ahead"),
        }

    reached = {s.key for s in steps}
    missing = [key for key in EXPECTED_STEPS if key not in reached]
    complete = not failed and not missing and in_time is True
    return {
        "today": today.isoformat(),
        "steps": [s.to_dict() for s in steps],
        "ran": [s.key for s in ran],
        "gated": {s.key: s.gated_on for s in gated},
        "failed": [s.key for s in failed],
        "customer_can_finish_in_time": in_time,
        "timing": timing,
        "complete": complete,
        "did_not_reach": missing,
        # A gate that stopped the run outranks the steps it stopped: those are consequences,
        # and the gate is the thing somebody can act on.
        "weakest_link": (failed[0].key if failed else
                         gated[0].key if gated and missing else
                         missing[0] if missing else
                         "timing" if in_time is False else
                         gated[0].key if gated else ""),
        "note": (
            "A cycle is complete when every link the requirement names was reached, every "
            "ungated one produced evidence, *and* a customer starting on the chosen launch "
            "date would finish before the event. A step the run never got to is absent "
            "rather than gated, and absent is not passing. The last condition is the one "
            "that makes this an acceptance test: a seasonal product that "
            "goes live two weeks before Christmas is not slightly late, it is a product "
            "nobody can finish, and every step before it was wasted (#300)."),
    }
