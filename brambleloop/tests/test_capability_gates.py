"""The day one gate turned out to be two, and what a capability has to prove.

`browser_vision` named "rendered-page and image evidence" and held twenty-eight
requirements. Half of them needed a cloud browser nobody had bought. The other half needed a
model to look at a picture -- and the model had been credentialed since 2026-09-19, with the
gallery URLs arriving from the sanctioned Etsy endpoint the whole time. Nobody had written
the call, which is not a capability anybody had to buy, and while both lived under one name
the two were indistinguishable.

The tests here are mostly about the second failure rather than the first: a gate that can be
opened by typing, and a capability that reports itself available on the strength of a
response that carried nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.build2 import executor as E  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing  # noqa: E402
from brambleloop.gateway import anthropic as GW  # noqa: E402
from brambleloop.gateway.model_gateway import ModelResponse  # noqa: E402
from brambleloop.intel import browser, vision  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


class _Seeing:
    """A provider whose eyes are scripted. Records what it was asked."""

    name = "anthropic"
    model = GW.VISION_PROBE_MODEL
    cost_per_1k_input_cad = 0.0
    cost_per_1k_output_cad = 0.0

    def __init__(self, answers):
        self.answers = list(answers)
        self.seen: list[list[str]] = []

    @staticmethod
    def key() -> str:
        return "a-key"

    def see(self, system, prompt, image_urls, *, max_tokens):
        self.seen.append(list(image_urls))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return ModelResponse(text=answer, provider=self.name, model=self.model,
                             input_tokens=900, output_tokens=40, latency_ms=10.0)


def _audited(db, *, urls=("https://i.etsystatic.com/a.jpg",), ref="1") -> None:
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key="mjs_off_the_hook_designs", listing_ref=ref,
                               title="t", pod="hats", audit_state="audited",
                               detail={"image_urls": list(urls)}))


# ---- a gate nobody can open by typing --------------------------------------


def test_no_gate_in_the_table_opens_on_an_environment_variable_alone():
    """The property the split was for, stated over the whole table rather than two keys.

    `browser_vision` read BRAMBLELOOP_BROWSER_URL. A worker URL that is set, misconfigured,
    unreachable or answered with a bot-protection challenge are four states and one string,
    and twenty-eight requirements sat behind that string. Two env-gates remain and both are
    honest about what they mean: an archive URL exists only once a bucket does, and a shop
    name exists only once a shop does. Neither claims a capability that could fail.
    """
    db = _db()
    env_openable = []
    for gate in E.GATES:
        if not gate.requirement_ids:
            continue
        fabricated = {"BRAMBLELOOP_BROWSER_URL": "https://worker.invalid",
                      "BRAMBLELOOP_IMAGE_KEY": "k",
                      "ANTHROPIC_API_KEY": "k", "ETSY_API_KEY": "k",
                      "ETSY_SHARED_SECRET": "k", "BRAMBLELOOP_ARCHIVE_URL": "s3://x",
                      "ETSY_SHOP_NAME": "x"}
        if gate.open(db, fabricated) and not gate.open(db, {}):
            env_openable.append(gate.key)
    assert env_openable == [], (
        f"{env_openable} would open on typed strings while holding requirements. A "
        f"capability that can be claimed is a capability that will be")


def test_the_split_gates_hold_what_they_say_they_hold():
    """Photograph judgement and rendered pages are different purchases."""
    image_gate = E.GATE_BY_KEY["image_vision"]
    page_gate = E.GATE_BY_KEY["rendered_pages"]

    assert not set(image_gate.requirement_ids) & set(page_gate.requirement_ids)
    # #209 and #304 are the gallery-analysis pair and must not need a browser.
    assert 209 in image_gate.requirement_ids
    assert 304 in image_gate.requirement_ids
    # Marketplace Insights and the SERP laboratory have no sanctioned endpoint.
    assert 1 in page_gate.requirement_ids
    assert 15 in page_gate.requirement_ids
    assert "no endpoint" in page_gate.what


# ---- the browser probe ------------------------------------------------------


def test_an_unconfigured_browser_is_a_gate_and_not_an_outage():
    db = _db()
    record = browser.probe(db, env={})
    assert record["ok"] is False
    assert "no BRAMBLELOOP_BROWSER_URL" in record["reason"]
    assert browser.usable(db) is False
    assert browser.configured({}) is False


def test_a_configured_browser_is_not_a_usable_one():
    """The whole reason this is a probe. Set is not reachable, and reachable is not allowed."""
    db = _db()
    assert browser.configured({"BRAMBLELOOP_BROWSER_URL": "https://worker.invalid"}) is True
    state = browser.state(db, env={"BRAMBLELOOP_BROWSER_URL": "https://worker.invalid"})
    assert state["endpoint_configured"] is True
    assert state["usable"] is False
    assert "four states and one environment variable" in state["why_a_probe"]


def test_a_short_body_is_a_challenge_page_rather_than_a_page():
    """An empty body, a bot challenge and an error document all arrive with HTTP 200."""
    db = _db()
    original = browser.fetch
    try:
        browser.fetch = lambda url, **kw: {
            "url": url, "final_url": url, "status": 200, "bytes": 40, "text": "x" * 40,
            "latency_ms": 5.0}
        record = browser.probe(db, env={"BRAMBLELOOP_BROWSER_URL": "https://worker.test"})
    finally:
        browser.fetch = original
    assert record["ok"] is False
    assert "challenge page" in record["reason"]
    assert browser.usable(db) is False


def test_a_real_page_opens_the_gate_and_nothing_else_does():
    db = _db()
    original = browser.fetch
    try:
        browser.fetch = lambda url, **kw: {
            "url": url, "final_url": url, "status": 200,
            "bytes": browser.MIN_PROBE_BYTES + 1, "text": "x" * (browser.MIN_PROBE_BYTES + 1),
            "latency_ms": 5.0}
        record = browser.probe(db, env={"BRAMBLELOOP_BROWSER_URL": "https://worker.test"})
    finally:
        browser.fetch = original
    assert record["ok"] is True
    assert browser.usable(db) is True
    assert E.GATE_BY_KEY["rendered_pages"].open(db, {}) is True


def test_the_worker_is_told_to_respect_robots_and_identify_itself():
    """A crawler that hides what it is has decided in advance it will not be welcome."""
    assert "Brambleloop" in browser.USER_AGENT
    assert browser.MIN_SECONDS_BETWEEN_FETCHES >= 1.0
    state = browser.state(_db(), env={})
    assert state["politeness"]["robots_txt"].startswith("respected")


# ---- the vision probe -------------------------------------------------------


def test_a_vision_probe_with_no_image_refuses_rather_than_passing():
    """A vision call with no picture is a text call that thinks it looked at something."""
    db = _db()
    record = GW.vision_probe(db, provider=_Seeing(["photograph"]))
    assert record["ok"] is False
    assert "no image to look at" in record["reason"]
    assert GW.vision_usable(db) is False


def test_a_two_hundred_carrying_an_apology_is_not_a_capability():
    """The shape a broken vision path actually takes: a successful call, no picture seen."""
    db = _db()
    _audited(db)
    record = GW.vision_probe(db, provider=_Seeing(["none"]))
    assert record["ok"] is False
    assert "carrying an apology" in record["reason"]
    assert GW.vision_usable(db) is False
    assert E.GATE_BY_KEY["image_vision"].open(db, {}) is False


def test_a_judged_image_opens_the_vision_gate():
    db = _db()
    _audited(db)
    record = GW.vision_probe(db, provider=_Seeing(["Photograph"]))
    assert record["ok"] is True
    assert record["image_url"] == "https://i.etsystatic.com/a.jpg"
    assert E.GATE_BY_KEY["image_vision"].open(db, {}) is True


def test_the_probe_looks_at_an_observed_image_rather_than_a_constant():
    """A probe against a hardcoded picture proves the provider works, not that this does."""
    db = _db()
    _audited(db, urls=("https://i.etsystatic.com/real.jpg",))
    seeing = _Seeing(["photograph"])
    GW.vision_probe(db, provider=seeing)
    assert seeing.seen == [["https://i.etsystatic.com/real.jpg"]]


# ---- judging the backlog ----------------------------------------------------


def test_an_answer_outside_the_vocabulary_is_refused_rather_than_filtered():
    """A parser that drops unknown keys turns a wrong answer into a thin observation."""
    raised = None
    try:
        vision.parse_observation('{"vibe": "lovely", "shot_type": "flat_lay"}')
    except vision.AnalysisRefused as exc:
        raised = exc
    assert raised is not None and "not gallery observation fields" in str(raised)


def test_prose_instead_of_json_is_refused():
    raised = None
    try:
        vision.parse_observation("It is a lovely photograph of a blanket.")
    except vision.AnalysisRefused as exc:
        raised = exc
    assert raised is not None and "did not answer with JSON" in str(raised)


def test_the_question_never_asks_what_the_product_depicts():
    """The containment rule, at the place the model is actually asked.

    A decomposition that keeps the expression is a copy with extra steps (#214, B-473), and
    the cheapest place for that to go wrong is the prompt.
    """
    assert "Never describe, name or transcribe the depicted design" in vision.ANALYSIS_SYSTEM
    assert "never reproduce text from the image" in vision.ANALYSIS_SYSTEM
    for field in vision.OBSERVATION_FIELDS:
        assert field in vision.analysis_prompt()


def test_a_run_that_judged_nothing_says_so_instead_of_looking_empty():
    """A drain loop whose failure mode is an empty result looks like an empty backlog."""
    from brambleloop.core.resilience import TransientError

    db = _db()
    _audited(db, urls=("https://i.etsystatic.com/a.jpg", "https://i.etsystatic.com/b.jpg"))
    result = vision.analyse(db, "mjs_off_the_hook_designs",
                            provider=_Seeing([TransientError("worker said no"),
                                              TransientError("again")]),
                            env={"ANTHROPIC_API_KEY": "k"})
    assert result["judged"] == 0
    assert result["attempted"] == 2
    assert len(result["failures"]) == 2
    assert "failure rather than a quiet success" in result["note"]


def test_one_image_per_call_because_a_batch_answers_about_the_set():
    db = _db()
    _audited(db, urls=("https://i.etsystatic.com/a.jpg", "https://i.etsystatic.com/b.jpg"))
    seeing = _Seeing(['{"shot_type": "flat_lay"}', '{"shot_type": "in_use"}'])
    result = vision.analyse(db, "mjs_off_the_hook_designs", provider=seeing,
                            env={"ANTHROPIC_API_KEY": "k"})
    assert result["judged"] == 2
    assert all(len(call) == 1 for call in seeing.seen), seeing.seen


def test_a_model_answering_the_wrong_question_is_counted_as_a_failure():
    """Not stored, and not silently skipped: named, so a bad prompt is visible."""
    db = _db()
    _audited(db, urls=("https://i.etsystatic.com/a.jpg",))
    result = vision.analyse(db, "mjs_off_the_hook_designs",
                            provider=_Seeing(['{"vibe": "lovely"}']),
                            env={"ANTHROPIC_API_KEY": "k"})
    assert result["judged"] == 0
    assert "not gallery observation fields" in result["failures"][0]["why"]


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
