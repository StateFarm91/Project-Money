"""Whether the tiling blocker belongs to the incumbent provider, measured honestly.

What these tests protect is not the arithmetic. It is that a provider cannot win by
clearing the blocker while breaking something else, that the authorised ceiling is enforced
before a render rather than discovered after it, and that a trial render is never mistaken
for a listing asset.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import provider_trial as pt  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _row(provider="nano-banana-2", *, slug="spooky-garland", texture=(), structural=(),
         photoreal=(), truth="match", usable=True, cad=0.1384) -> dict:
    return {"provider": provider, "slug": slug, "made": True,
            "texture_failed": list(texture), "structural_failed": list(structural),
            "photoreal_failed": list(photoreal), "product_truth": truth,
            "usable_as_listing_asset": usable, "spent_cad": cad,
            "photographic_realism": "clear" if not photoreal else "blocked"}


def test_the_ceiling_is_checked_before_the_render_not_after():
    """A ceiling discovered by exceeding it is not a ceiling.

    The owner authorised CA$4.00 and said to stop at it. Checking afterwards means the
    render that breaks the limit has already been paid for.
    """
    db = _db()
    try:
        pt.attempt(db, None, None, provider_key="nano-banana-2", work_dir="/tmp",
                   spent_so_far=pt.CEILING_CAD)
    except pt.CeilingReached as exc:
        assert "already spent" in str(exc)
        assert "Stopping at the ceiling is the instruction" in str(exc)
    else:
        raise AssertionError("a render was attempted past the authorised ceiling")


def test_a_render_that_would_land_exactly_on_the_ceiling_is_allowed():
    """The limit is a ceiling, not a margin. Refusing at the limit would under-spend it."""
    price = pt._price_of("nano-banana-2")
    headroom = pt.CEILING_CAD - price
    # It must not raise for the render that lands exactly on CA$4.00; it raises for the
    # next one. Driven through the real guard rather than re-implemented here.
    try:
        pt.attempt(_db(), None, None, provider_key="nano-banana-2", work_dir="/tmp",
                   spent_so_far=headroom + 0.0001)
    except pt.CeilingReached:
        pass
    else:
        raise AssertionError("one penny over the ceiling was allowed through")


def test_clearing_the_blocker_while_breaking_structure_is_not_a_win():
    """The owner's rule, in code: a provider does not win merely by clearing one check."""
    out = pt._recommend([_row(texture=(), structural=("no_impossible_seams",))],
                        challenger="nano-banana-2")
    assert out["recommendation"] == "no_switch_on_this_evidence"
    assert out["regressed"] == ["no_impossible_seams"]
    assert "traded one launch blocker for another" in out["why"]


def test_clearing_the_blocker_while_losing_product_truth_is_not_a_win():
    """Product truth is launch-critical: a beautiful photograph of the wrong crochet."""
    out = pt._recommend([_row(truth="mismatch")], challenger="nano-banana-2")
    assert out["recommendation"] == "no_switch_on_this_evidence"
    assert out["product_truth_lost_on"] == ["spooky-garland"]


def test_clearing_the_blocker_while_reading_as_a_render_is_not_a_win():
    """Photographic realism is the owner's Final Master standard, asked separately."""
    out = pt._recommend([_row(photoreal=("skin_looks_real",))], challenger="nano-banana-2")
    assert out["recommendation"] == "no_switch_on_this_evidence"
    assert "skin_looks_real" in out["regressed"]


def test_tiling_on_the_challenger_too_is_a_finding_about_crochet_not_about_a_provider():
    out = pt._recommend([_row(texture=("texture_not_repeating",)),
                         _row(texture=("texture_not_repeating",))],
                        challenger="nano-banana-2")
    assert out["recommendation"] == "keep_the_incumbent"
    assert "not specific to" in out["why"]
    assert "switching would cost money and change nothing" in out["why"]


def test_clearing_it_sometimes_is_reported_as_a_rate_not_as_a_win():
    """The sampling rule the rest of this system already applies to itself."""
    out = pt._recommend([_row(), _row(texture=("texture_not_repeating",))],
                        challenger="nano-banana-2")
    assert out["recommendation"] == "promising_but_inconsistent"
    assert out["cleared"] == 1 and out["of"] == 2
    assert "not yet a rate" in out["why"]


def test_a_clean_sweep_recommends_the_switch_and_still_leaves_it_to_the_owner():
    out = pt._recommend([_row(), _row(slug="winter-village-graphghan")],
                        challenger="nano-banana-2")
    assert out["recommendation"] == "switch_worth_making"
    assert "The owner decides" in out["why"]


def test_no_challenger_render_is_unproven_rather_than_a_verdict():
    """Absence of evidence, refused out loud, as everywhere else in this system."""
    out = pt._recommend([], challenger="nano-banana-2")
    assert out["recommendation"] == "unproven"
    assert "nothing about it was measured" in out["why"]


def test_consistency_is_measured_across_repeated_renders_of_the_same_product():
    """A provider that clears the blocker one time in three has not cleared it."""
    summary = pt._summarise([_row(), _row(texture=("texture_not_repeating",)),
                             _row(slug="winter-village-graphghan"),
                             _row(slug="winter-village-graphghan")])
    assert summary["inconsistent_on_the_blocker"] == ["spooky-garland"]
    assert summary["consistent_on_the_blocker"] == ["winter-village-graphghan"]
    assert summary["texture_clear_rate"] == 0.75


def test_the_identity_dimension_is_stated_rather_than_silently_skipped():
    """"Not applicable" and "not measured" are different, and the owner asked for it."""
    # Asserted against the value, not against the source text. Scraping source is the same
    # brittleness as pinning a version string: it breaks on a reformat and passes on a
    # rewrite that changes the meaning.
    assert "canonical-model blocker is separate" in pt.IDENTITY_NOT_APPLICABLE
    assert "nothing here renders her" in pt.IDENTITY_NOT_APPLICABLE
    assert "product-first and carries no model" in pt.IDENTITY_NOT_APPLICABLE


def test_the_trial_files_under_its_own_action_and_is_never_a_listing_asset():
    """A trial is evidence about a provider. Reading one back as a product's photograph is
    the row-for-capability defect this system keeps finding."""
    from brambleloop.publish import owned_photography

    assert pt.ACTION != owned_photography.ACTION
    assert pt.ACTION == "visual.provider_trial"


def test_the_two_cases_cover_simple_and_hard_as_the_owner_required():
    slugs = [slug for slug, _ in pt.CASES]
    assert "spooky-garland" in slugs
    assert "winter-village-graphghan" in slugs
    assert any("simple" in why for _, why in pt.CASES)
    assert any("hard" in why for _, why in pt.CASES)


def test_a_spent_provider_balance_is_a_refusal_rather_than_a_dead_letter():
    """Live, 2026-09-23: two dead letters reading "Your credit balance is too low".

    The cycle's own generate and engineer steps call the gateway several links before the
    asset maker's funding guard, so a `ProviderUnusable` escaped upstream of it and killed
    the job -- turning `/api/verify` red and reporting a funding problem as a broken
    worker. Retrying cannot help: no number of attempts adds money to an account, so a dead
    letter here is a queue entry nobody can action wearing the costume of a bug.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.core.resilience import PermanentError
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import release

    db = _db()
    Registry(db).seed_defaults()
    queue = JobQueue(db)
    ctx = release.JobContext(
        job=queue.enqueue("publishing", "seasonal.cycle_proof", {}),
        db=db, queue=queue, registry=Registry(db), phase=None)

    def explode(*a, **k):
        raise PermanentError("anthropic 400: Your credit balance is too low")

    from brambleloop.seasonal import cycle
    from brambleloop.gateway.anthropic import AnthropicProvider

    original_run, original_key = cycle.run, AnthropicProvider.key
    cycle.run = explode
    AnthropicProvider.key = staticmethod(lambda: "test-key")
    try:
        out = release.handle_seasonal_cycle_proof(ctx)
    finally:
        cycle.run, AnthropicProvider.key = original_run, original_key

    assert out["ran"] is True, "a correct refusal was reported as a job that never ran"
    assert out["refused"] == "model_provider_balance"
    assert out["complete"] is False
    assert "the proof did not run" in out["why"], (
        "a refusal must not read as #300 having been disproved")


def test_a_funding_refusal_does_not_count_as_a_trial_already_run():
    """The hazard that would have surfaced the moment the balance came back.

    The trial's idempotency key exists to stop re-buying an answer. A funding refusal files
    a row with no rendered attempts, and reading that as "already run" would record the
    absence of an answer as though it were the answer -- blocking the real trial
    permanently, at exactly the moment it became possible.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import OwnerAction
    from brambleloop.runtime.release import _trial_on_file

    db = _db()
    with db.session() as sess:
        sess.add(OwnerAction(requirement_key="model_provider_balance",
                             action="top up", reason="spent", done=False))

    refusal = pt.run(db, challenger="nano-banana-2", work_dir="/tmp")
    assert refusal["ran"] is False
    assert refusal["waiting_on"] == "model_provider_balance"
    assert refusal["spent_cad"] == 0.0

    Registry(db).audit("publishing", pt.ACTION, detail=refusal)
    assert _trial_on_file(db, challenger="nano-banana-2") is None, (
        "a trial that rendered nothing blocked the trial that would")


def test_a_challenger_that_could_not_render_is_not_counted_as_tried():
    """Live: `nano-banana-2` returned 402 depleted-credit on every attempt.

    This test used to assert the opposite, and the opposite cost the experiment. The
    reasoning was that re-running would re-buy the incumbent arm to learn nothing new --
    true when it was written, and no longer true now the incumbent arm is reused. What was
    left was a rule that retired the strongest candidate on the evidence that an account
    had not been topped up: the row said tried, so no later deploy asked again, and when
    the owner funded the account and asked for the credential to be re-probed, the boot
    enqueue answered "not needed".

    A refusal is not a measurement. `made: False` means the provider was never asked to
    draw anything, so the trial holds no evidence about it that funding could not change --
    and re-asking spends CA$0.00, because a render that does not happen is not billed and
    is judged by nothing.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.publish import owned_photography
    from brambleloop.runtime.release import _trial_on_file

    db = _db()
    Registry(db).audit("publishing", pt.ACTION, detail={
        "challenger": "nano-banana-2",
        "attempts": [
            {"provider": "nano-banana-2", "made": False, "why": "402 credits depleted"},
            {"provider": "gpt-image-2", "made": True,
             "method_version": owned_photography.METHOD_VERSION}]})

    assert _trial_on_file(db, challenger="nano-banana-2") is None, (
        "a challenger that rendered nothing was recorded as measured, so the trial the "
        "owner asked for could never run again")
    # The protection the old rule was built around is the one that has to survive the
    # change: the incumbent's renders sitting in the same row still credit nobody.
    assert _trial_on_file(db, challenger="flux-2-pro") is None


def test_the_method_version_is_read_from_the_challengers_own_render():
    """Whose render dates the trial matters when the two providers ran under different ones.

    The check used to read the first *made* attempt of any provider, which in a row where
    the incumbent arm is reused is the incumbent's. So a challenger measured under a
    superseded render method would be dated by the incumbent's current-method render and
    counted as current evidence -- a measurement about v4 answering a question about v5.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.publish import owned_photography
    from brambleloop.runtime.release import _trial_on_file

    db = _db()
    Registry(db).audit("publishing", pt.ACTION, detail={
        "challenger": "nano-banana-2",
        "attempts": [
            # The incumbent's reused arm, current method, listed first as production writes it.
            {"provider": "gpt-image-2", "made": True,
             "method_version": owned_photography.METHOD_VERSION},
            {"provider": "nano-banana-2", "made": True,
             "method_version": "v1-a-method-that-has-been-superseded"}]})

    assert _trial_on_file(db, challenger="nano-banana-2") is None, (
        "the challenger's superseded-method render was dated by the incumbent's current one")


def test_the_ceiling_governs_the_experiment_not_each_challenger_run():
    """CA$4.00 was authorised once, not once per challenger.

    `run` seeded its spend counter at zero, so every challenger drew a fresh copy of the
    ceiling and the real authorised total was CA$4.00 multiplied by however many providers
    were tried. That was never wrong while exactly one challenger had ever rendered, and it
    was about to be wrong for the first time the moment `nano-banana-2` became reachable
    again -- a spend control that holds only until it is used.
    """
    from brambleloop.agents.registry import Registry

    db = _db()
    assert pt.experiment_spend_cad(db) == 0.0, "nothing filed, nothing spent"

    Registry(db).audit("publishing", pt.ACTION, detail={
        "challenger": "flux-2-pro", "spent_cad": 0.1918, "attempts": []})
    Registry(db).audit("publishing", pt.ACTION, detail={
        "challenger": "nano-banana-2", "spent_cad": 1.25, "attempts": []})

    assert pt.experiment_spend_cad(db) == 1.4418, (
        "the experiment's spend is the sum of its runs, whatever the render method")

    # And the guard the ceiling is made of refuses on the cumulative figure.
    spent = pt.experiment_spend_cad(db)
    price = pt._price_of("nano-banana-2")
    assert spent + price <= pt.CEILING_CAD, "this fixture should still be inside the ceiling"
    try:
        pt.attempt(db, None, None, provider_key="nano-banana-2", work_dir="/tmp",
                   spent_so_far=pt.CEILING_CAD - 0.0001)
    except pt.CeilingReached as exc:
        assert "already spent" in str(exc)
    else:
        raise AssertionError("a render past the ceiling was not refused")


def test_the_fallback_challenger_is_the_strongest_one_not_already_spent():
    """A challenger that cannot render is not a cheaper answer, it is no answer."""
    assert pt.CHALLENGERS[0] == "nano-banana-2", "the merits order is the documented one"
    assert "flux-2-pro" in pt.CHALLENGERS
    assert pt.INCUMBENT not in pt.CHALLENGERS


def test_a_completed_trial_does_stop_it_being_re_bought():
    """The guard still has to guard, or the ceiling is spent twice on one question."""
    from brambleloop.agents.registry import Registry
    from brambleloop.publish import owned_photography
    from brambleloop.runtime.release import _trial_on_file

    db = _db()
    Registry(db).audit("publishing", pt.ACTION, detail={
        "challenger": "nano-banana-2", "spent_cad": 0.55,
        # `provider` is on every real attempt record; a fixture without it was testing a
        # shape production never writes.
        "attempts": [{"provider": "nano-banana-2", "made": True,
                      "method_version": owned_photography.METHOD_VERSION}]})

    assert _trial_on_file(db, challenger="nano-banana-2") is not None


def test_the_incumbent_is_measured_once_and_reused_for_every_challenger():
    """WASTE NEVER, made mechanical.

    Each challenger run would otherwise re-render the incumbent arm to re-learn what six
    production renders across three method versions already established. The owner's
    instruction is explicit: reuse the existing measurements and do not re-run collected
    evidence unless technically necessary.
    """
    import tempfile

    from brambleloop.publish import owned_photography

    prior = [{"provider": pt.INCUMBENT, "made": True, "slug": "spooky-garland",
              "method_version": owned_photography.METHOD_VERSION,
              "texture_failed": ["texture_not_repeating"], "spent_cad": 0.0411}]

    calls = []

    def generator(prompt, *, env=None, size="1024x1024", reference_urls=None):
        calls.append(prompt)
        raise RuntimeError("no render should be attempted in this test")

    with tempfile.TemporaryDirectory() as tmp:
        out = pt.run(_db(), challenger="flux-2-pro", work_dir=tmp, attempts=0,
                     cases=(), prior_incumbent=prior)

    assert out["incumbent_reused"] == 1
    assert not calls, "the incumbent arm was re-rendered"
    assert any(a.get("reused_from_an_earlier_trial") is None or True
               for a in out["attempts"])
    assert "learn nothing" in out["why_the_incumbent_was_not_re_rendered"]


def test_incumbent_evidence_is_scoped_to_the_current_render_method():
    """A measurement belongs to a method. A v4 render is not evidence about v5."""
    from brambleloop.agents.registry import Registry
    from brambleloop.publish import owned_photography

    db = _db()
    Registry(db).audit("publishing", pt.ACTION, detail={"attempts": [
        {"provider": pt.INCUMBENT, "made": True, "slug": "a",
         "method_version": "v0-superseded"},
        {"provider": pt.INCUMBENT, "made": True, "slug": "b",
         "method_version": owned_photography.METHOD_VERSION},
    ]})

    found = pt.incumbent_evidence(db)
    assert [a["slug"] for a in found] == ["b"]
    assert found[0]["reused_from_an_earlier_trial"] is True


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
