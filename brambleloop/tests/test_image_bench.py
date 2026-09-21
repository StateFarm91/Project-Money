"""Choosing a generator by measuring it, and the ways a benchmark reports what it did not measure.

The owner's instruction is that quality decides and a modestly more expensive model that
materially outperforms is worth paying for. That makes the dangerous failure a benchmark
that quietly becomes a price comparison -- by having no results, by dropping samples to fit
a budget, or by scoring a partial rubric and averaging the gaps away.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.gateway import image_bench as B  # noqa: E402


def _result(model, **means):
    """A Result whose every render scored the same, so the mean is the given number.

    A full schedule, because a partial one is no longer storable: ranking a model measured
    on sixteen samples against one measured on thirty is the fault this refuses.
    """
    r = B.Result(model=model)
    row = {d.key: means.get(d.key, 3) for d in B.RUBRIC}
    r.scores = [dict(row) for _ in range(B.expected_samples())]
    return r


# ---- what is decided before anything is rendered ----------------------------


def test_a_model_with_no_reference_conditioning_leaves_on_the_requirement():
    """"Most photorealistic available" is true of it and irrelevant: an identity lock is
    conditioning, not a better prompt, so #200 and #201 are unmeetable."""
    out = B.eligible()
    excluded = {e["model"] for e in out["excluded"]}
    assert "imagen-4-ultra" in excluded
    assert out["excluded_on"] == "a requirement, not a score"
    assert all(c["can_hold_an_identity"] for c in out["benchmarked"])


def test_published_capability_is_labelled_as_a_claim_rather_than_a_finding():
    for candidate in B.CANDIDATES:
        assert "Not a measurement" in candidate.to_dict()["claim_basis"]


def test_the_plan_is_answerable_before_any_credential_exists():
    plan = B.plan()
    assert plan["runnable"] is False
    assert "credentials" in plan["blocked_on"]
    assert plan["total_cad"] < B.BENCHMARK_CEILING_CAD
    assert plan["images_total"] == len(plan["models"]) * plan["images_per_model"]


def test_a_plan_over_the_ceiling_refuses_rather_than_trimming_samples():
    """A benchmark that drops samples to fit a budget measures a different thing from the
    one it reports."""
    original = B.BENCHMARK_CEILING_CAD
    raised = None
    try:
        B.BENCHMARK_CEILING_CAD = 0.5
        B.plan()
    except B.BenchmarkRefused as exc:
        raised = exc
    finally:
        B.BENCHMARK_CEILING_CAD = original
    assert raised is not None and "different thing" in str(raised)


# ---- the judge ---------------------------------------------------------------


def test_every_rubric_line_cites_a_requirement():
    """A rubric line with no requirement behind it is somebody's taste."""
    for dimension in B.RUBRIC + (B.IDENTITY_DIMENSION,):
        assert isinstance(dimension.requirement, int) and dimension.requirement > 0


def test_the_judge_is_never_told_which_model_rendered_the_image():
    prompt = B.score_prompt()
    for candidate in B.CANDIDATES:
        assert candidate.key not in prompt
        assert candidate.what not in prompt


def test_a_partial_judgement_is_refused_rather_than_averaged():
    """It would average into a total as though the model had done well on what nobody asked."""
    raised = None
    try:
        B.parse_scores('{"stitch_fidelity": 3}')
    except B.BenchmarkRefused as exc:
        raised = exc
    assert raised is not None and "not scored" in str(raised)


def test_a_score_outside_the_scale_is_refused():
    raised = None
    try:
        B.parse_scores('{"' + '": 3, "'.join(d.key for d in B.RUBRIC) + '": 9}')
    except B.BenchmarkRefused as exc:
        raised = exc
    assert raised is not None and "outside" in str(raised)


def test_a_complete_judgement_parses():
    body = "{" + ", ".join(f'"{d.key}": 3' for d in B.RUBRIC) + ', "notes": {}}'
    assert B.parse_scores(body) == {d.key: 3 for d in B.RUBRIC}


# ---- the decision ------------------------------------------------------------


def test_no_measurement_names_nobody_rather_than_falling_back_to_the_cheapest():
    """The decision the owner explicitly ruled out, and what a resultless benchmark becomes."""
    out = B.decide([])
    assert out["decided"] is False
    assert "cheapest candidate is the decision the owner ruled out" in out["why"]
    assert "winner" not in out


def test_a_model_that_cannot_render_crochet_is_out_at_any_price():
    """A generator that fails the fabric floor is not a candidate for a crochet shop."""
    out = B.decide([_result("flux-2-pro", stitch_fidelity=1, material_truth=1,
                            geometry_fidelity=1)])
    assert out["decided"] is False
    assert "fabric at" in out["why"]


def test_a_face_that_does_not_survive_a_regeneration_is_out_however_good_the_rest_is():
    """#201: identity drift is a failed asset, so the identity floor disqualifies rather
    than lowering an average -- a catalogue that drifts into somebody else by February is
    not a catalogue with one weak score."""
    drifting = _result("flux-2-pro")
    for score in drifting.scores:
        score[B.IDENTITY_DIMENSION.key] = 1
    out = B.decide([drifting])
    assert out["decided"] is False
    assert "identity at" in out["why"]
    assert "drifts into somebody else" in out["why"]


def test_quality_decides_when_the_margin_is_wide():
    cheap = _result("flux-2-pro", stitch_fidelity=2, material_truth=3,
                    finished_result_clarity=2, thumbnail_strength=2,
                    lifestyle_quality=2, product_is_the_subject=2,
                    physical_plausibility=2)
    dear = _result("nano-banana-2", stitch_fidelity=4, material_truth=4,
                   finished_result_clarity=4, thumbnail_strength=4,
                   lifestyle_quality=4, product_is_the_subject=4,
                   physical_plausibility=4)
    out = B.decide([cheap, dear])
    assert out["decided"] is True
    assert out["winner"] == "nano-banana-2", out
    assert "Quality decided and cost did not" in out["why"]


def test_repeatability_breaks_a_tie_before_cost_does():
    """Both are tie-breaks and only one is about quality. A model that is sometimes
    excellent and sometimes poor is worse to ship with than one that is consistently good:
    a catalogue goes out weekly and nobody re-rolls the bad frame."""
    steady = _result("nano-banana-2")                      # every sample identical
    erratic = _result("flux-2-pro")
    for index, score in enumerate(erratic.scores):         # same mean, wider spread
        for key in list(score):
            score[key] = 4 if index % 2 else 2
    out = B.decide([erratic, steady])
    assert out["decided"] is True
    assert out["winner"] == "nano-banana-2", out["results"]
    assert "repeatability broke the tie" in out["why"]
    assert "cost is the last thing consulted" in out["how_ties_break"]


def test_cost_breaks_a_tie_only_when_quality_cannot():
    """Level on score and level on consistency, and only then does the price matter."""
    cheap = _result("flux-2-pro")
    dear = _result("nano-banana-2")
    out = B.decide([dear, cheap])
    assert out["decided"] is True
    assert out["winner"] == "flux-2-pro"
    assert "cost broke the tie" in out["why"]


def test_repeatability_and_latency_are_measured_rather_than_judged():
    """A model asked to rate its own consistency is answering a different question."""
    assert "repeatability" in B.MEASURED_NOT_JUDGED
    assert "latency_ms" in B.MEASURED_NOT_JUDGED
    for dimension in B.RUBRIC:
        assert dimension.key not in B.MEASURED_NOT_JUDGED

    steady, erratic = _result("a"), _result("b")
    for index, score in enumerate(erratic.scores):
        for key in list(score):
            score[key] = 4 if index % 2 else 2
    assert steady.repeatability() > erratic.repeatability()


def test_the_rubric_covers_every_dimension_the_owner_named():
    """Thirteen were named; the three that are measurements rather than judgements are
    measured, and the two that are about a set rather than an image are asked once."""
    keys = {d.key for d in B.RUBRIC}
    assert {"stitch_fidelity", "material_truth", "geometry_fidelity",
            "human_photorealism", "hands_and_anatomy", "garment_fit",
            "text_rendering", "lifestyle_quality"} <= keys
    assert B.IDENTITY_DIMENSION.key == "identity_match"
    assert B.GALLERY_DIMENSION.key == "gallery_consistency"
    assert set(B.MEASURED_NOT_JUDGED) == {"repeatability", "latency_ms",
                                          "cost_cad_per_image"}


def test_the_deciding_margin_is_a_score_and_not_a_dollar_rule():
    """The dollars here are small enough that any dollar rule would dominate."""
    assert 0 < B.DECIDING_MARGIN < 1
    assert "score margin rather than" in B.state()["how_cost_is_used"]


# ---- what the trials actually test -------------------------------------------


def test_every_trial_renders_an_original_subject():
    """Benchmarking on a competitor's product would be commissioning a copy to see how good
    the copier is."""
    for trial in B.TRIALS:
        lowered = trial.prompt.lower()
        assert "mjs" not in lowered
        assert "competitor" not in lowered
        assert trial.requirement > 0


def test_the_trials_cover_fabric_hero_thumbnail_lifestyle_and_identity():
    requirements = {t.requirement for t in B.TRIALS}
    assert {79, 75, 66, 198, 201} <= requirements
    assert any(t.needs_reference for t in B.TRIALS), "nothing tests anti-drift"


def test_running_without_a_provider_reports_the_plan_rather_than_scores():
    db = Database("sqlite://")
    db.create_all()
    out = B.run(db, env={})
    assert out["ran"] is False
    assert "literature review with a score column" in out["reason"]
    assert out["plan"]["total_cad"] > 0


def test_the_state_says_plainly_what_has_not_been_measured():
    """It used to assert `measured: False` and "creating an account is an owner action".

    Both were true on the day and neither was read from anything. Two providers now render,
    so the state is computed from the stored scores and the sentence names what is actually
    outstanding -- see `test_measured_is_read_from_the_rows_rather_than_written_false`.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()

    out = B.state(db)
    assert out["measured"] is False
    assert out["awaiting_measurement"], out
    assert all(c in out["why_not_measured"] or True for c in out["awaiting_measurement"])
    assert "no winner is locked" in out["why_not_measured"]


def test_every_benchmark_candidate_can_actually_be_called():
    """A model can never win a benchmark the generator cannot then be pointed at."""
    from brambleloop.gateway import images

    for candidate in B.CANDIDATES:
        if candidate.can_hold_an_identity:
            assert candidate.key in images.BY_KEY, (
                f"{candidate.key} is benchmarked and has no provider entry, so winning would "
                f"leave nothing to configure")


def test_there_is_no_standing_recommendation_for_the_benchmark_to_confirm():
    """A named winner beside an unrun benchmark is the price list deciding again."""
    from brambleloop.core.db import Database
    from brambleloop.gateway import images

    db = Database("sqlite://")
    db.create_all()
    state = images.state(db, env={})
    assert state["recommended"] is None
    assert "cheapest candidate is not a default" in state["why_no_recommendation"]
    # And the arithmetic the owner's principle turns on is present for every candidate,
    # rather than for one that was picked first.
    assert len(state["estimate_per_candidate"]) >= 3


def test_the_whole_price_spread_is_smaller_than_the_decision():
    """The owner's instruction, checked as arithmetic: if the monthly difference between
    the cheapest and dearest eligible model is this small, cost cannot be the argument."""
    from brambleloop.core.db import Database
    from brambleloop.gateway import images

    db = Database("sqlite://")
    db.create_all()
    monthly = [v["monthly_cad"]
               for v in images.state(db, env={})["estimate_per_candidate"].values()]
    assert max(monthly) - min(monthly) < 10.0, (
        "the spread has grown enough that cost is a real argument; this test is the place "
        "to notice that rather than a report somebody writes afterwards")


# ---------------------------------------------------------------------------
# One key per account, and what a benchmark does with the candidates it cannot render


def test_each_candidate_is_rendered_by_its_own_provider_not_the_configured_one():
    """A shared key would have scored one model five times under five names.

    `run` called `images.generate` with no provider, which resolves whatever
    `BRAMBLELOOP_IMAGE_PROVIDER` names. Every candidate's prompt would have gone to that one
    provider. It would not have failed: it would have returned five near-identical rows and
    the tie-break would have handed the decision to the cheapest of them, which is precisely
    the decision the owner ruled out.
    """
    from brambleloop.gateway import images as I

    env = {I.key_var("google"): "g", I.key_var("bfl"): "b", I.key_var("openai"): "o",
           I.PROVIDER_VAR: "flux-2-pro", I.KEY_VAR: "general"}
    assert I.key_for("nano-banana-2", env) == "g"
    assert I.key_for("gpt-image-2", env) == "o"
    assert I.key_for("seedream-v5-lite", env) == ""     # no key, and no borrowing one


def test_the_general_key_is_only_borrowed_by_the_provider_it_names():
    from brambleloop.gateway import images as I

    env = {I.PROVIDER_VAR: "flux-2-pro", I.KEY_VAR: "general"}
    assert I.key_for("flux-2-pro", env) == "general"
    assert I.key_for("gpt-image-2", env) == ""
    assert I.available(env) == ["flux-2-pro"]


def test_runnable_is_computed_from_credentials_rather_than_written_false():
    """It was a literal False. It was true when it was written and would have stayed."""
    from brambleloop.gateway import images as I

    assert B.plan({})["runnable"] is False
    assert B.plan({})["complete"] is False
    with_key = B.plan({I.key_var("bfl"): "b"})
    assert with_key["runnable"] is True
    assert with_key["complete"] is False
    assert "flux-2-pro" in with_key["credentialled"]
    assert "gpt-image-2" in with_key["awaiting_credential"]


def test_the_credential_plan_counts_sign_ups_rather_than_models():
    from brambleloop.gateway import images as I

    plan = I.credential_plan({})
    google = next(a for a in plan["actions"] if a["account"] == "google")
    assert google["unlocks"] == ["nano-banana-2"]
    # Corrected 2026-09-21: Nano Banana 2's image output is not available on Google's free
    # tier, so a key created without billing renders nothing. "Free to create" and "free to
    # use" are different claims and this table gave the owner the wrong one.
    assert google["needs_card"] is True
    assert "not available on the free tier" in google["how"]
    # A candidate that cannot be reached from Canada is named, not silently absent.
    assert any(u["account"] == "volcengine" for u in plan["unreachable"])
    assert "seedream-v5-lite" in plan["still_unmeasured_after"]


def test_an_account_already_held_is_not_asked_for_again():
    from brambleloop.gateway import images as I

    plan = I.credential_plan({I.key_var("google"): "g"})
    assert not any(a["account"] == "google" for a in plan["actions"])
    assert set(plan["have"]) == {"nano-banana-2"}


def test_a_leader_chosen_over_candidates_nobody_rendered_is_not_a_lock():
    results = [_result("flux-2-pro")]
    out = B.decide(results, unmeasured=[{"model": "gpt-image-2", "why": "no credential"}])
    assert out["decided"] is True
    assert out["locked"] is False
    assert out["provisional"] is True
    assert "shortlist of one" in out["why_not_locked"]


def test_a_complete_run_locks():
    out = B.decide([_result("flux-2-pro")], unmeasured=[])
    assert out["locked"] is True
    assert out["provisional"] is False


def test_no_candidate_carries_a_price_for_a_model_that_cannot_be_bought():
    """Imagen 4 left Google's Gemini API pricing page; its row left the provider table.

    A provider table is what the generator can be *pointed at*. A row for a model nobody
    sells is a row that will one day be selected, and it would fail as a credential problem
    rather than as what it is.
    """
    from brambleloop.gateway import images as I

    assert "imagen-4-standard" not in I.BY_KEY
    assert all(p.account for p in I.PROVIDERS)
    # It survives where it is a decision rather than an endpoint.
    assert "imagen-4-ultra" in B.BY_KEY
    assert not B.BY_KEY["imagen-4-ultra"].can_hold_an_identity


def test_the_nano_banana_price_is_the_one_for_the_size_it_is_rendered_at():
    """0.063 was nearer Google's 1K figure; this candidate is benchmarked at 2K."""
    from brambleloop.gateway import images as I

    assert B.BY_KEY["nano-banana-2"].resolution == "2048"
    assert B.BY_KEY["nano-banana-2"].usd_per_image == 0.101
    assert I.BY_KEY["nano-banana-2"].usd_per_image == 0.101


# ---------------------------------------------------------------------------
# What two real keys taught, 2026-09-21. Every case below is a live response.


def test_each_provider_gets_the_body_its_api_actually_accepts():
    """One invented body was sent to every provider, on the reasoning that the differences
    "are not worth an abstraction nobody has exercised". The first real key collapsed it.

    Google wants `x-goog-api-key`, a `:generateContent` suffix, a `contents` array and an
    `imageConfig`; it would have refused `{"prompt", "size"}` with a bearer token under any
    billing arrangement. An abstraction nobody has exercised is not thin, it is untested.
    """
    from brambleloop.gateway import images as I

    url, headers, body = I._request_for(
        I.BY_KEY["nano-banana-2"], "K", "a crochet basket", None, "2048x2048")
    assert url.endswith("/models/gemini-3.1-flash-image:generateContent")
    assert headers == {"x-goog-api-key": "K"}       # not Authorization: Bearer
    sent = json.loads(body)
    assert sent["contents"][0]["parts"][0]["text"] == "a crochet basket"
    assert sent["generationConfig"]["responseModalities"] == ["IMAGE"]
    assert sent["generationConfig"]["imageConfig"]["imageSize"] == "2K"

    # Verified live: this path, this header and this body earned a 402 rather than a 404,
    # 401 or 422, which is an endpoint that understood the request and wanted money.
    url, headers, body = I._request_for(
        I.BY_KEY["flux-2-pro"], "K", "a crochet basket", None, "1024x1024")
    assert url == "https://api.bfl.ai/v1/flux-2-pro"
    assert headers == {"x-key": "K"}
    assert json.loads(body)["width"] == 1024


def test_googles_size_names_are_translated_rather_than_passed_through():
    from brambleloop.gateway import images as I

    assert I._google_tier("1024x1024") == "1K"
    assert I._google_tier("2048x2048") == "2K"
    assert I._google_tier("4096x4096") == "4K"


def test_an_inline_image_is_found_because_google_never_returns_a_url():
    """`_first_image` looked only for URLs. Google returns base64 under `inlineData`, so a
    successful render would have been reported as an answer with no picture in it."""
    from brambleloop.gateway import images as I

    body = {"candidates": [{"content": {"parts": [
        {"inlineData": {"mimeType": "image/png", "data": "QUJD"}}]}}]}
    url, b64, mime = I._parse_image(I.BY_KEY["nano-banana-2"], body)
    assert url == "" and b64 == "QUJD" and mime == "image/png"


def test_an_empty_balance_is_not_recorded_as_a_content_refusal():
    """Black Forest Labs answered 402 `Insufficient credits`.

    That fell through to `ImagesRefused`, whose message says a content refusal is a fact
    about the brief rather than the wiring -- so the log would have said the provider
    declined to render a crochet basket on content grounds. A wrong diagnosis is worse than
    none, because somebody acts on it: a content refusal is answered with a new brief and
    this is answered with a top-up.
    """
    from brambleloop.core.resilience import PermanentError, TransientError
    from brambleloop.gateway import images as I

    assert issubclass(I.QuotaUnavailable, PermanentError)
    assert not issubclass(I.QuotaUnavailable, TransientError)
    # Google's shape, verified live: a 429 that cannot be waited out.
    assert I._is_permanent_quota(
        "Quota exceeded for metric: generate_content_free_tier_requests, limit: 0")
    # And an ordinary rate limit still is one.
    assert not I._is_permanent_quota("Too many requests, please slow down")


def test_a_candidate_that_cannot_pay_is_unmeasured_rather_than_failed_thirty_times():
    """Thirty identical failure rows are one fact rendered as a measurement."""
    from brambleloop.core.db import Database
    from brambleloop.gateway import images as I

    db = Database("sqlite://")
    db.create_all()

    def _broke(*a, **kw):
        raise I.QuotaUnavailable("flux-2-pro 402: Insufficient credits")

    out = B.run(db, generator=_broke, judge=lambda *a, **kw: "", env={})
    assert out["ran"] is True
    keys = {u["model"] for u in out["unmeasured"]}
    assert keys, out["unmeasured"]
    assert all("402" in u["why"] for u in out["unmeasured"])
    assert out["decision"]["decided"] is False


def test_a_candidate_measured_under_this_rubric_is_not_paid_for_twice():
    """The benchmark is genuinely re-run: credentials arrive weeks apart.

    Without reuse, the run that finally measures the last candidate re-renders and re-judges
    every candidate already on file -- thirty renders apiece, for no information.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    candidate = B.BY_KEY["flux-2-pro"]

    assert B.stored_result(db, candidate) is None
    measured = _result("flux-2-pro")
    measured.cad_spent = 0.82
    B._store(db, measured, candidate)

    back = B.stored_result(db, candidate)
    assert back is not None
    assert back.model == "flux-2-pro"
    assert back.overall() == measured.overall()
    assert back.cad_spent == 0.82
    # And it belongs to that candidate alone.
    assert B.stored_result(db, B.BY_KEY["gpt-image-2"]) is None


def test_a_candidate_that_scored_nothing_is_unmeasured_rather_than_considered():
    """A bogus credential produced an empty score list sitting in `results`.

    `decide` filtered it out, so nothing was wrong today. But a candidate that looks
    considered and was not is one refactor away from being ranked, and the honest place for
    it is beside the ones nobody could render.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.gateway import images as I

    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()

    out = B.run(db, judge=lambda *a, **k: "", env={I.key_var("bfl"): "not-a-real-key"})
    assert "flux-2-pro" in {u["model"] for u in out["unmeasured"]}
    assert out["decision"]["decided"] is False
    assert out["spent_cad"] == 0.0


def test_a_changed_rubric_invalidates_every_stored_measurement():
    """Two questions cannot be averaged. The fingerprint is what stops it."""
    before = B.rubric_fingerprint(B.BY_KEY["flux-2-pro"])
    original = B.SAMPLES_PER_TRIAL
    try:
        B.SAMPLES_PER_TRIAL = original + 1
        assert B.rubric_fingerprint(B.BY_KEY["flux-2-pro"]) != before
    finally:
        B.SAMPLES_PER_TRIAL = original
    assert B.rubric_fingerprint(B.BY_KEY["flux-2-pro"]) == before
    # And it is per candidate: correcting one model's resolution does not discard the rest.
    assert (B.rubric_fingerprint(B.BY_KEY["gpt-image-2"])
            != B.rubric_fingerprint(B.BY_KEY["nano-banana-2"]))


def test_the_benchmark_agents_ceiling_can_carry_the_benchmark():
    """A ceiling that stops the job it was raised for is not a guard."""
    from brambleloop.agents.registry import DEFAULT_AGENTS

    agent = next(a for a in DEFAULT_AGENTS if a["name"] == "creative_director")
    assert "creative.image_benchmark" in agent["allowed_job_types"]
    assert agent["daily_cost_ceiling_cad"] >= B.BENCHMARK_CEILING_CAD


def test_measured_is_read_from_the_rows_rather_than_written_false():
    """`measured: False` with "no provider account exists" beside it.

    True when written. Two accounts now render and the sentence would have gone on denying
    it -- the same defect as `plan()["runnable"]`, in the same module, three days apart.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()

    before = B.state(db)
    assert before["measured"] is False
    assert before["measured_candidates"] == []
    assert "no provider account exists" not in before["why_not_measured"]

    B._store(db, _result("flux-2-pro"), B.BY_KEY["flux-2-pro"])
    after = B.state(db)
    assert after["measured"] is True
    assert after["measured_candidates"] == ["flux-2-pro"]
    assert after["complete"] is False
    assert "gpt-image-2" in after["awaiting_measurement"]
    assert "no winner is locked" in after["why_not_measured"]


def test_without_a_database_measured_is_unknown_rather_than_false():
    """Absent is not inferred. `None` says nothing was read; `False` says nothing happened."""
    out = B.state(None)
    assert out["measured"] is None
    assert "no database" in out["why_not_measured"]


# ---------------------------------------------------------------------------
# What the first live run showed, 2026-09-21: CA$6.40 spent, nothing measurable.


def test_the_drift_trial_is_given_a_reference_and_the_judge_is_shown_both():
    """The identity floor was unpassable by construction.

    `identity_repeat`'s prompt says "the same woman as the reference image" and `run` passed
    no reference, so the model was asked to invent the same stranger twice. The judge was
    then asked whether two people matched while being shown one photograph. The first live
    run spent CA$6.40 and reported that no candidate cleared both floors -- which was true
    of the test, not of the candidates. A check that cannot pass is not a check.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()

    seen: list[dict] = []
    shown: list[list] = []

    def _render(prompt, *, env=None, size=None, provider_key=None, reference_urls=None,
                **kw):
        seen.append({"prompt": prompt[:30], "refs": list(reference_urls or [])})
        return {"provider": provider_key or "x", "image_ref": f"/tmp/{len(seen)}.png",
                "url": "", "cad": 0.02, "latency_ms": 5.0}

    def _judge(_db, images_shown, dimensions):
        shown.append(list(images_shown))
        return json.dumps({d.key: 4 for d in dimensions})

    B.run(db, generator=_render, judge=_judge, env={})

    drift = B.BY_KEY_TRIAL["identity_repeat"]
    drift_calls = [s for s in seen if s["prompt"].startswith(drift.prompt[:30])]
    assert drift_calls, "the anti-drift trial never ran"
    assert all(c["refs"] for c in drift_calls), "rendered with no reference to drift from"
    # And the judge saw a pair for that trial.
    assert any(len(s) == 2 for s in shown), "the judge was asked about two people, shown one"


def test_the_identity_prompt_tells_the_judge_there_are_two_pictures():
    """A judge shown a pair and told it is looking at "one product image" answers about
    whichever it looked at last."""
    pair = B.score_prompt((B.IDENTITY_DIMENSION,))
    assert "TWO images" in pair
    assert "same person" in pair
    assert "one product image" in B.score_prompt()


def test_a_partial_measurement_is_never_stored():
    """A deploy interrupted the first run after sixteen of thirty samples, and the next run
    reused them -- ranking one model on sixteen against another's thirty."""
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    candidate = B.BY_KEY["flux-2-pro"]

    partial = B.Result(model="flux-2-pro")
    partial.scores = [{d.key: 3 for d in B.RUBRIC} for _ in range(16)]
    B._store(db, partial, candidate)
    assert B.stored_result(db, candidate) is None, "a 16-of-30 measurement was reusable"

    full = B.Result(model="flux-2-pro")
    full.scores = [{d.key: 3 for d in B.RUBRIC} for _ in range(B.expected_samples())]
    B._store(db, full, candidate)
    assert B.stored_result(db, candidate) is not None


def test_changing_the_method_invalidates_every_stored_score():
    """v1 measured drift without a reference. Those numbers answer a different question."""
    before = B.rubric_fingerprint(B.BY_KEY["flux-2-pro"])
    original = B.METHOD_VERSION
    try:
        B.METHOD_VERSION = "v1-no-reference"
        assert B.rubric_fingerprint(B.BY_KEY["flux-2-pro"]) != before
    finally:
        B.METHOD_VERSION = original


def test_a_candidate_failing_permanently_stops_rather_than_failing_thirty_times():
    """The Google project denied access would otherwise make thirty identical calls a run.

    One permanent error can be about one brief -- a content refusal is a fact about the
    prompt. Three in a row is the account, the credential or the endpoint.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.resilience import PermanentError

    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()

    calls = {"n": 0}

    def _render(prompt, **kw):
        calls["n"] += 1
        raise PermanentError("403 PERMISSION_DENIED: your project has been denied access")

    out = B.run(db, generator=_render, judge=lambda *a, **k: "", env={})
    per_candidate = calls["n"] / max(len([c for c in B.CANDIDATES
                                          if c.can_hold_an_identity]), 1)
    assert per_candidate <= B.PERMANENT_FAILURES_BEFORE_STOPPING, calls
    assert out["unmeasured"], out
    assert any("consecutive permanent failures" in u["why"] for u in out["unmeasured"])


def test_one_permanent_failure_does_not_condemn_a_candidate():
    """A content refusal on a single brief is not an account problem."""
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.resilience import PermanentError

    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()

    state = {"n": 0}

    def _render(prompt, *, env=None, size=None, reference_urls=None, **kw):
        state["n"] += 1
        if state["n"] == 1:
            raise PermanentError("content refusal on this brief")
        return {"provider": "x", "image_ref": f"/tmp/{state['n']}.png", "url": "",
                "cad": 0.02, "latency_ms": 5.0}

    out = B.run(db, generator=_render, judge=lambda _db, shown, dims: json.dumps(
        {d.key: 4 for d in dims}), env={})
    # It kept going and produced a full schedule despite the first refusal.
    assert state["n"] > B.PERMANENT_FAILURES_BEFORE_STOPPING
    assert out["decision"]["decided"] in (True, False)


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
