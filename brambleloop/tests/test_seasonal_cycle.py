"""#300: one seasonal cycle end to end, and the clause that makes it an acceptance test.

The requirement calls itself release-blocking and it ends on an arithmetic comparison --
*show that the scheduler launched early enough for a customer to make it before the event*.
A seasonal product that goes live two weeks before Christmas is not slightly late; it is a
product nobody can finish, and every step before it was wasted.

So these tests are mostly about the ways a cycle can look complete and prove nothing.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.seasonal import cycle  # noqa: E402
from test_prospecting import _WideGateway, _wide_db  # noqa: E402

TODAY = date(2026, 9, 20)


def test_the_cycle_runs_every_link_it_can_and_names_the_ones_it_cannot():
    out = cycle.run(_wide_db(), today=TODAY, gateway=_WideGateway())
    states = {s["step"]: s["state"] for s in out["steps"]}

    # Every link the requirement names is present, in order.
    assert [s["step"] for s in out["steps"]] == [
        "observe", "classify", "choose_event", "launch_date", "generate",
        "engineer", "certify", "assets", "search"], states

    for step in ("observe", "classify", "choose_event", "launch_date", "generate",
                 "engineer", "certify"):
        assert states[step] == cycle.RAN, (step, out["steps"])

    # And the release chain was run rather than asserted.
    certified = next(s for s in out["steps"] if s["step"] == "certify")
    assert certified["evidence"]["granted"] is True
    assert "reverse" in certified["evidence"]["stages_run"]


def test_a_gated_step_is_named_and_never_simulated():
    """A placeholder product photograph would make this cycle green and prove nothing.

    It is also the exact thing the asset-truth gate exists to refuse one level down, so
    faking it here would be the system disagreeing with itself in private.
    """
    out = cycle.run(_wide_db(), today=TODAY, gateway=_WideGateway())
    assert out["gated"].get("assets") == "image_generation", out["gated"]
    assets = next(s for s in out["steps"] if s["step"] == "assets")
    assert "placeholder" in assets["why"]


def test_with_no_generator_the_cycle_stops_and_says_which_capability():
    """Not a partial pass. A cycle that cannot invent anything has not demonstrated one."""
    out = cycle.run(_wide_db(), today=TODAY, gateway=None)
    assert out["gated"].get("generate") == "model_provider", out["gated"]
    assert out["complete"] is False
    # The gate that stopped the run, not the first step it stopped: those are consequences
    # and the gate is the thing somebody can act on.
    assert out["weakest_link"] == "generate", out["weakest_link"]
    # The steps after it are absent rather than passing, and absent is reported.
    reached = {s["step"] for s in out["steps"]}
    assert "certify" not in reached, reached
    assert "certify" in out["did_not_reach"], out["did_not_reach"]


def test_an_unobserved_benchmark_cannot_start_a_cycle():
    """The first link is somebody having looked. Nothing downstream can substitute."""
    db = Database("sqlite://")
    db.create_all()
    out = cycle.run(db, today=TODAY, gateway=_WideGateway())
    assert out["complete"] is False
    assert out["failed"] == ["observe"], out["failed"]
    assert "no market signal" in out["steps"][0]["why"]


def test_a_launch_date_that_has_passed_cannot_satisfy_launched_early_enough():
    """The first run of this reported `complete: true` on a launch date twenty days gone.

    The backward chain wanted the product live on 31 August; the cycle measured a buyer's
    finish date from that, found it comfortable, and called the window met. A date that has
    passed cannot be launched on, and measuring from one is reporting about a window the
    company missed.
    """
    out = cycle.run(_wide_db(), today=TODAY, gateway=_WideGateway())
    timing = out["timing"]
    assert timing["preferred_window_already_passed"] is True, timing
    assert timing["earliest_possible_launch"] == TODAY.isoformat()
    # The finish date is measured from a date that can actually be launched on.
    assert timing["a_buyer_starting_then_finishes"] > timing["earliest_possible_launch"]
    assert "cannot be launched on" in timing["why"]


def test_the_assets_step_evidences_this_cycles_product_and_never_another():
    """The chain was broken at step 8, in production, on a launch-blocking test.

    `last_asset(db)` returns the most recent owned asset on file, and the cycle handed that
    straight in as its own evidence. The 2026-09-22 run engineered `hats-hat-0` and the
    assets step reported `cloudline-baby-blanket` -- an end-to-end acceptance test
    evidencing a different product than the one its own chain produced, and reporting that
    product's motif failure as this cycle's. A pass would have been meaningless and the
    failure was about something else entirely.
    """
    from brambleloop.core.models import AuditLog
    from brambleloop.gateway import images
    from brambleloop.publish import owned_photography

    db = _wide_db()

    # An asset exists, for a product this cycle did not engineer.
    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action=owned_photography.ACTION,
                       detail={"made": True,
                               "method_version": owned_photography.METHOD_VERSION,
                               "slug": "some-other-product", "form": "blanket",
                               "verdict": "clear", "motif_verified": True,
                               "usable_as_listing_asset": True,
                               "image": {"url": "/api/model-tournament/image/deadbeef"}}))

    # Image generation proven, so the step gets past the capability gate and has to
    # decide on the asset itself -- which is where it was going wrong.
    was_usable = images.usable
    images.usable = lambda _db: True
    try:
        out = cycle.run(db, today=TODAY, gateway=_WideGateway())
    finally:
        images.usable = was_usable
    assets = next(s for s in out["steps"] if s["step"] == "assets")
    engineered = next(s for s in out["steps"] if s["step"] == "engineer")

    assert assets["state"] != cycle.RAN, \
        "another product's photograph was accepted as this cycle's asset"
    assert assets["evidence"].get("slug") == engineered["evidence"]["slug"]
    # And it says plainly that assets exist elsewhere, so the gap is legible rather than
    # looking like a capability that has never worked.
    assert assets["evidence"]["other_products_have_assets"] is True

    # Binding the step to this cycle's product exposed the structural gap underneath, and
    # it is reported as one rather than as a gate that will open: the cycle authors and
    # certifies its concept in memory and never files it, so the photography job -- which
    # photographs catalogue products -- can never reach it. A queue entry nobody can
    # action is a permanent blocker wearing one, so this is a failure with a named fix.
    assert assets["evidence"]["in_catalogue"] is False
    assert assets["state"] == cycle.FAILED
    assert assets["gated_on"] == ""
    assert "never filed in the catalogue" in assets["why"]
    assert "structurally unreachable" in assets["why"]

    # The other direction, or this is a wall rather than a check: an asset for the
    # cycle's own product does satisfy the step.
    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action=owned_photography.ACTION,
                       detail={"made": True,
                               "method_version": owned_photography.METHOD_VERSION,
                               "slug": engineered["evidence"]["slug"], "form": "hat",
                               "verdict": "clear", "motif_verified": True,
                               "usable_as_listing_asset": True,
                               "disclosed_as_illustration": True,
                               "image": {"url": "/api/model-tournament/image/feedface"}}))
    images.usable = lambda _db: True
    try:
        again = cycle.run(db, today=TODAY, gateway=_WideGateway())
    finally:
        images.usable = was_usable
    step = next(s for s in again["steps"] if s["step"] == "assets")
    assert step["state"] == cycle.RAN, step
    assert step["evidence"]["slug"] == engineered["evidence"]["slug"]


def test_an_asset_maker_closes_the_link_and_the_endpoint_never_gets_one():
    """The fix for the link #300 could not reach, and the reason it is a job.

    Filing the cycle's product would also fix it, and would inflate the catalogue on every
    page view -- the move #292 exists to refuse. So the maker takes the CIR in hand, which
    is the thing the daily slug-driven job cannot do, and only a job passes one: a GET that
    spends money spends it every time a test sweep walks the routes.
    """
    from brambleloop.core.models import AuditLog
    from brambleloop.gateway import images
    from brambleloop.publish import owned_photography

    db = _wide_db()
    made: list[str] = []

    def maker(cir):
        made.append(cir.slug)
        with db.session() as s:
            s.add(AuditLog(actor="publishing", action=owned_photography.ACTION,
                           detail={"made": True, "slug": cir.slug, "form": "hat",
                                   "method_version": owned_photography.METHOD_VERSION,
                                   "verdict": "clear", "motif_verified": True,
                                   "usable_as_listing_asset": True,
                                   "disclosed_as_illustration": True,
                                   "image": {"url": "/api/model-tournament/image/abc"}}))

    was_usable = images.usable
    images.usable = lambda _db: True
    try:
        # No maker: the link cannot close, and nothing was rendered.
        without = cycle.run(db, today=TODAY, gateway=_WideGateway())
        assert made == [], "the cycle rendered an image without being handed a maker"
        assert next(s for s in without["steps"]
                    if s["step"] == "assets")["state"] != cycle.RAN

        # With one: it closes, for the product the chain engineered.
        with_maker = cycle.run(db, today=TODAY, gateway=_WideGateway(), asset_maker=maker)
    finally:
        images.usable = was_usable

    engineered = next(s for s in with_maker["steps"]
                      if s["step"] == "engineer")["evidence"]["slug"]
    assert made == [engineered], (made, engineered)
    assets = next(s for s in with_maker["steps"] if s["step"] == "assets")
    assert assets["state"] == cycle.RAN, assets
    assert assets["evidence"]["slug"] == engineered


def test_the_proof_job_hands_the_cycle_a_gateway_and_refuses_when_it_cannot():
    """The first live run of this job proved nothing and reported success.

    `weakest_link: generate`, `assets_state: None` -- the handler asked the cycle for
    everything except the one input it needed, so the generate step gated on
    `model_provider` and the run stopped at step 5, four links short of the assets link
    the job exists to close. A proof that stops before the thing it proves is not a proof,
    and it cost a scheduled run to find out.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.gateway.anthropic import AnthropicProvider
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.release import JobContext, handle_seasonal_cycle_proof
    from brambleloop.seasonal import cycle as cycle_mod

    db = _wide_db()
    Registry(db).seed_defaults()
    queue = JobQueue(db)
    ctx = JobContext(job=queue.enqueue("publishing", "seasonal.cycle_proof", {}), db=db,
                     queue=queue, registry=Registry(db), phase=None)

    # No credential: it says so rather than running a cycle that cannot generate.
    was_key = AnthropicProvider.key
    AnthropicProvider.key = staticmethod(lambda: "")
    try:
        out = handle_seasonal_cycle_proof(ctx)
    finally:
        AnthropicProvider.key = was_key
    assert out["ran"] is False
    assert "four links" in out["reason"]

    # With one, the cycle is handed both a gateway and a maker -- captured rather than
    # run, because the point under test is what the handler passes.
    seen = {}

    def spy(_db, **kwargs):
        seen.update(kwargs)
        return {"steps": [], "complete": False, "weakest_link": "",
                "customer_can_finish_in_time": True}

    was_run = cycle_mod.run
    AnthropicProvider.key = staticmethod(lambda: "a-key")
    cycle_mod.run = spy
    try:
        handle_seasonal_cycle_proof(ctx)
    finally:
        cycle_mod.run = was_run
        AnthropicProvider.key = was_key
    assert seen.get("gateway") is not None, "the cycle was run without a model provider"
    assert callable(seen.get("asset_maker"))


def test_the_makers_own_refusal_outranks_the_structural_guess():
    """The live blocker, reported as itself rather than as a filing problem.

    The cycle's soonest proven arena is `hats`, a hat is not a product-first form, and a
    model-bearing frame is blocked while the canonical identity is built and unapproved.
    So the maker declines -- and without this the step would report "never filed in the
    catalogue", sending the next session after the catalogue while the actual blocker, an
    owner decision, went unmentioned. A reason the maker gives outranks every guess made
    on its behalf.
    """
    from brambleloop.gateway import images

    db = _wide_db()
    refusals: list[str] = []

    def refusing_maker(cir):
        refusals.append(cir.slug)
        return {"made": False, "slug": cir.slug, "form": "hat",
                "why": ("'hat' is a form whose listing needs the canonical model, and she "
                        "is built but not approved. A model-bearing frame is blocked "
                        "rather than faked")}

    was_usable = images.usable
    images.usable = lambda _db: True
    try:
        out = cycle.run(db, today=TODAY, gateway=_WideGateway(),
                        asset_maker=refusing_maker)
    finally:
        images.usable = was_usable

    assets = next(s for s in out["steps"] if s["step"] == "assets")
    assert refusals, "the maker was never asked"
    assert assets["state"] == cycle.FAILED
    assert "needs the canonical model" in assets["why"]
    assert "never filed in the catalogue" not in assets["why"]
    assert assets["evidence"]["form"] == "hat"

    # A refusal naming something genuinely outside this build is gated on it, because that
    # is somebody else's to grant and the cycle should not call it our failure.
    def waiting_maker(cir):
        return {"made": False, "slug": cir.slug,
                "why": "the model provider's balance is spent",
                "waiting_on": "model_provider_balance"}

    images.usable = lambda _db: True
    try:
        held = cycle.run(db, today=TODAY, gateway=_WideGateway(),
                         asset_maker=waiting_maker)
    finally:
        images.usable = was_usable
    step = next(s for s in held["steps"] if s["step"] == "assets")
    assert step["state"] == cycle.GATED
    assert step["gated_on"] == "model_provider_balance"


def test_our_own_unfinished_work_fails_the_cycle_instead_of_gating_it():
    """The defect this introduced and production showed within the hour.

    A GATED link does not stop `complete`. So when the assets refusal started naming
    `model_bearing_render_path` -- work nobody has written -- #300 reported
    `complete: true` with `assets_state: gated` and no asset ever made, minutes after the
    canonical identity was frozen. Calling our own unfinished work a gate is how a
    launch-blocking acceptance test passes without doing the thing it tests.

    Unrecognised waits fail rather than gate, so a refusal reason invented somewhere else
    cannot buy itself a pass by naming something plausible.
    """
    from brambleloop.gateway import images

    db = _wide_db()

    def ours(cir):
        return {"made": False, "slug": cir.slug, "form": "hat",
                "why": "she is approved and frozen; the render path is not built",
                "waiting_on": "model_bearing_render_path"}

    was_usable = images.usable
    images.usable = lambda _db: True
    try:
        out = cycle.run(db, today=TODAY, gateway=_WideGateway(), asset_maker=ours)
    finally:
        images.usable = was_usable

    step = next(s for s in out["steps"] if s["step"] == "assets")
    assert step["state"] == cycle.FAILED, step
    assert step["gated_on"] == ""
    assert out["complete"] is False, "an unbuilt render path let the cycle report complete"
    assert out["weakest_link"] == "assets"
    assert "model_bearing_render_path" not in cycle.EXTERNAL_WAITS

    # An invented reason must not gate either.
    def invented(cir):
        return {"made": False, "slug": cir.slug, "why": "reasons",
                "waiting_on": "something_plausible_sounding"}

    images.usable = lambda _db: True
    try:
        made_up = cycle.run(db, today=TODAY, gateway=_WideGateway(), asset_maker=invented)
    finally:
        images.usable = was_usable
    assert next(s for s in made_up["steps"]
                if s["step"] == "assets")["state"] == cycle.FAILED
    assert made_up["complete"] is False


def test_the_verdict_is_the_weakest_link_rather_than_a_count_of_green_ticks():
    """A backward-chained schedule is exactly where an average hides a broken link."""
    out = cycle.run(_wide_db(), today=TODAY, gateway=_WideGateway())
    assert out["weakest_link"], out
    if out["failed"]:
        assert out["complete"] is False
        assert out["weakest_link"] == out["failed"][0]
    elif out["customer_can_finish_in_time"] is False:
        assert out["complete"] is False
        assert out["weakest_link"] == "timing"


def test_a_buyer_who_cannot_finish_in_time_fails_the_cycle_however_green_the_rest():
    """The clause that makes this release-blocking, checked directly.

    Every other step can be perfect and the cycle still fails, because a product nobody can
    finish before the occasion is a product that should not have been made for it.
    """
    from types import SimpleNamespace

    # Every link present and green, so nothing but the arithmetic can decide this.
    steps = [cycle.Step(key=key, what="x", state=cycle.RAN)
             for key in cycle.EXPECTED_STEPS]
    arena = SimpleNamespace(event="Christmas", pod="hats", days_away=10)
    launch = SimpleNamespace(
        preferred_launch=TODAY, effective_make_days=30,
        assumptions=SimpleNamespace(completion_buffer_days=3))
    verdict = cycle._verdict(steps, TODAY, arena, launch)
    assert verdict["customer_can_finish_in_time"] is False, verdict["timing"]
    assert verdict["complete"] is False
    assert verdict["weakest_link"] == "timing", verdict
    assert verdict["timing"]["days_to_spare"] < 0


def test_a_cycle_that_completes_says_so_only_when_the_buyer_arithmetic_holds():
    out = cycle.run(_wide_db(), today=TODAY, gateway=_WideGateway())
    assert out["customer_can_finish_in_time"] is True, out["timing"]
    assert out["timing"]["days_to_spare"] >= 0
    assert out["complete"] is True, out["failed"]

    # And a cycle whose event is too close fails on the same arithmetic rather than on mood.
    late = cycle.run(_wide_db(), today=date(2026, 10, 30), gateway=_WideGateway())
    if late["customer_can_finish_in_time"] is False:
        assert late["complete"] is False


def test_the_deploy_re_ask_stops_asking_once_the_chain_closes():
    """A weekly cadence is right unattended and wrong right after the blocker changes.

    The canonical identity was frozen minutes after this week's run had already happened,
    so the next scheduled answer would have been seven days stale. A deploy re-asks -- and
    has to stop: a boot enqueue that fired forever would spend a cycle on every deploy to
    re-prove something already proved, which is the opposite failure and just as wasteful.
    """
    from brambleloop.core.models import AuditLog
    from brambleloop.runtime.release import cycle_proof_incomplete

    db = _wide_db()
    assert cycle_proof_incomplete(db) is True, "no run on file must re-ask"

    with db.session() as s:
        s.add(AuditLog(actor="publishing", action="seasonal.cycle_proof",
                       detail={"steps": [{"step": "assets", "state": "failed"}]}))
    assert cycle_proof_incomplete(db) is True, "an open assets link must re-ask"

    with db.session() as s:
        s.add(AuditLog(actor="publishing", action="seasonal.cycle_proof",
                       detail={"steps": [{"step": "assets", "state": "ran"}]}))
    assert cycle_proof_incomplete(db) is False, "a closed chain must stop asking"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
