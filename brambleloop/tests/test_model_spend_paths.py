"""Every model-spend call site in `src/`, measured against the set that checks the ceiling.

The question `research/RELIABILITY_AUDIT.md` and `research/RELIABILITY_WAVE2.md` could both
see and neither could answer: **is there a path left that reaches a provider without passing
through `gateway.anthropic.check_budget`?** Wave 2 closed the six it knew about by name and
said so; naming six is not the same claim as "there are no others", and the difference is the
whole reason a seventh could be added without anybody noticing.

So it is measured rather than asserted. This file parses every module under `src/`, finds
every call that reaches a model provider, and compares that set against the set whose
enclosing function calls `check_budget`. The residue is written down here, per site, with its
owner and the reason it is still open -- the shape `ops.retention.KNOWN_READ_ACTIONS` uses,
for the same reason: the danger is not today's list, it is tomorrow's addition.

**What this instrument can and cannot see.** It reads the source, so it measures the *code*
and not a run. A call reached through a callback the scanner cannot follow would be missed,
and a `check_budget` in the enclosing function is counted as guarding every provider call in
it, which is true of every call site in this repository today and would stop being true of a
function that checked once and called twice on different estimates. Both limits are stated
here rather than left for a reader to discover, because a check that overstates its reach is
how requirement 40's consistency check came to compare a decision with itself.

Written by the Visual/Reliability department, 2026-09-25, alongside closing the five Visual
holes wave 2 left because the files were not its to edit.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

SRC = ROOT / "src"

# The methods on a model provider that cost money. `AnthropicProvider` has exactly these two
# public call methods (`complete` for text, `see` for vision); `_read` is their shared
# response reader and `key` reads an environment variable.
PROVIDER_METHODS = ("see", "complete")

# Receivers that share a method name with a provider and are not one. Explicit, and checked
# below for staleness, because a silent exclusion list is a bypass with a tidy name.
NOT_A_MODEL_PROVIDER: dict[str, str] = {
    "self.queue": "`queue.durable.JobQueue.complete` marks a job done. It spends nothing.",
}

# Model-spend call sites that reach a provider with no `check_budget` in their enclosing
# function, each with the owner who can close it and why it is still open.
#
# Exact equality below, in both directions. A new entry means somebody added a spend path
# with no ceiling check. A missing entry means somebody closed one -- good news, and the
# entry should be deleted in the same commit, because a list of open holes that still names a
# closed one stops being read.
KNOWN_UNGUARDED: dict[tuple[str, str], str] = {
    ("brambleloop/gateway/model_gateway.py", "complete_json"): (
        "Owner: the gateway. It bills through `agents.registry.record_cost`, which checks "
        "the agent's daily ceiling *after* the provider has answered and checks the "
        "authorised month not at all. A post-hoc check is a measurement, not a control, and "
        "the cross-process reservation never touches this path. Closing it means calling "
        "`check_budget(agent=..., purpose=...)` before `breaker.call` and releasing in the "
        "`_record` path; the estimate is already available as "
        "`prompt.max_output_tokens` and the rendered user text."),
    ("brambleloop/publish/motif_fidelity.py", "check"): (
        "Owner: Publishing (`publish/**`). One vision call per customer-facing asset, "
        "billed nowhere and checked nowhere -- it does not even write a `spend_report` row, "
        "so this call site is invisible to the monthly total as well as unguarded by it. "
        "Closing it means the same six lines as `creative/reference.py::read_listing`, with "
        "two image allowances in the estimate because it shows the render and the chart."),
}

# Image *generation* call sites. None of them passes through `check_budget` and none of them
# can today, which is a different finding from the two above and is kept separate so that it
# cannot be read as the same one.
#
# `check_budget` prices a call with `estimate_cad(model, input_tokens, output_tokens)` from
# `PRICES_USD_PER_MTOK`, which is a per-token table. An image render is priced per image
# (`gateway.images.ImageProvider.cad_per_image`) and its provider keys -- `gpt-image-2`,
# `flux-2-pro`, `nano-banana-2` -- are not in that table at all, so `check_budget` on one
# raises "has no price on file" rather than checking anything. The mechanism has to learn a
# per-image estimate before any of these can pass through it; inventing a second ceiling
# mechanism for images is the one thing the owner's rule forbids.
#
# Pinned so that the set cannot grow silently while that is true.
KNOWN_IMAGE_GENERATION: dict[tuple[str, str], str] = {
    ("brambleloop/gateway/image_bench.py", "_run_inside"): "the benchmark's own renders",
    ("brambleloop/gateway/images.py", "reference_probe"): "two renders, four times a day",
    ("brambleloop/gateway/images.py", "probe"): "one render per capability probe",
    ("brambleloop/publish/model_photography.py", "make"): "one render per model frame",
    ("brambleloop/publish/owned_photography.py", "make"): "one render per owned frame",
    ("brambleloop/visual/portrait_repair.py", "propose"): "one render per repair proposal",
    ("brambleloop/visual/reference_pack.py", "_render"): "one render per pack frame",
    ("brambleloop/visual/tournament.py", "generate_candidates"): "one render per candidate",
    ("brambleloop/visual/tournament.py", "stress_test"): "one render per stress scene",
}

_IMAGE_GENERATORS = ("images.generate", "generate", "generator or generate")


def _calls_check_budget(fn: ast.AST) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("check_budget"):
            return True
    return False


def scan_source(source: str, rel: str) -> dict:
    """Provider calls and image renders in one module, each with its enclosing function.

    `guarded` is true when `check_budget` is called anywhere inside the nearest enclosing
    function or one containing it. `visual/inspect.py` needs the containing case: its guard
    and its two provider calls all sit in the nested `_call`, and a scanner that only looked
    at the outermost function would report it unguarded and be wrong.
    """
    tree = ast.parse(source, filename=rel)
    provider_calls: list[dict] = []
    image_calls: list[dict] = []

    def visit(node: ast.AST, stack: list) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            stack = stack + [node]
        if isinstance(node, ast.Call):
            func = node.func
            where = stack[-1].name if stack else "<module>"
            if isinstance(func, ast.Attribute) and func.attr in PROVIDER_METHODS:
                receiver = ast.unparse(func.value)
                if receiver not in NOT_A_MODEL_PROVIDER:
                    provider_calls.append({
                        "file": rel, "line": node.lineno, "function": where,
                        "call": f"{receiver}.{func.attr}",
                        "guarded": any(_calls_check_budget(f) for f in stack)})
            name = ast.unparse(func)
            if name in _IMAGE_GENERATORS and (
                    name == "images.generate" or rel == "brambleloop/gateway/images.py"):
                image_calls.append({"file": rel, "line": node.lineno, "function": where,
                                    "call": name})
        for child in ast.iter_child_nodes(node):
            visit(child, stack)

    visit(tree, [])
    return {"provider_calls": provider_calls, "image_calls": image_calls}


def scan_tree(root: Path = SRC) -> dict:
    provider_calls: list[dict] = []
    image_calls: list[dict] = []
    for base, _dirs, files in os.walk(root):
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = Path(base) / name
            rel = str(path.relative_to(root))
            found = scan_source(path.read_text(), rel)
            provider_calls += found["provider_calls"]
            image_calls += found["image_calls"]
    return {"provider_calls": provider_calls, "image_calls": image_calls}


def _sites(rows: list[dict]) -> set[tuple[str, str]]:
    return {(r["file"], r["function"]) for r in rows}


# ---------------------------------------------------------------------------
# The measurement


def test_the_scan_finds_the_provider_calls_that_are_actually_there():
    """A scanner that finds nothing passes every other test in this file.

    So the instrument is checked before it is believed: the six call sites wave 2 says it
    fixed, plus the five Visual ones this session fixed, must all be present and all be
    guarded. If a rename makes one of them invisible to the scan, this fails rather than the
    scan quietly reporting a clean tree.
    """
    found = scan_tree()
    sites = _sites(found["provider_calls"])
    for site in (
            ("brambleloop/intel/vision.py", "analyse"),
            ("brambleloop/culture/classify.py", "classify"),
            ("brambleloop/creative/reference.py", "read_listing"),
            ("brambleloop/gateway/image_bench.py", "_judge"),
            ("brambleloop/gateway/anthropic.py", "probe"),
            ("brambleloop/gateway/anthropic.py", "vision_probe"),
            ("brambleloop/visual/inspect.py", "_call"),
            ("brambleloop/visual/model_registry.py", "observe"),
            ("brambleloop/visual/model_registry.py", "compare_identity"),
            ("brambleloop/visual/model_registry.py", "compare_hair"),
            ("brambleloop/visual/photoreal.py", "judge"),
            ("brambleloop/visual/bible.py", "judge"),
            ("brambleloop/visual/tournament.py", "_judge"),
    ):
        assert site in sites, f"the scan no longer sees {site}; the instrument is broken"
    assert len(found["provider_calls"]) >= 13


def test_no_model_spend_path_reaches_a_provider_without_the_ceiling_check():
    """The answer the audit could not give, measured rather than asserted.

    Exact equality with `KNOWN_UNGUARDED`, both directions. Read the failure message: a new
    name is a hole somebody opened, a missing name is one somebody closed.
    """
    found = scan_tree()
    unguarded = {(r["file"], r["function"]) for r in found["provider_calls"]
                 if not r["guarded"]}
    added = sorted(unguarded - set(KNOWN_UNGUARDED))
    closed = sorted(set(KNOWN_UNGUARDED) - unguarded)
    assert not added, (
        f"these reach a model provider with no check_budget in the enclosing function: "
        f"{added}. Every model-spend path reserves, checks and releases through "
        f"`gateway.anthropic.check_budget` and `release_reservation`. There is no second "
        f"mechanism and no path gets an exemption")
    assert not closed, (
        f"{closed} no longer reaches a provider unguarded -- good news. Delete the entry "
        f"from KNOWN_UNGUARDED in the same commit: a list of open holes that names a closed "
        f"one stops being read")


def test_every_visual_spend_path_passes_its_agent_and_releases_its_reservation():
    """The five holes wave 2 named and left for Visual, closed through the one mechanism.

    Measured on the source of each function rather than on a run, because what is being
    asserted is that the code cannot spend without doing this -- not that one particular
    call happened to. `agent=` is what makes a daily permission bind; `release_reservation`
    is what stops a padded estimate being held for its full TTL after the bill is known.
    """
    import inspect as _inspect

    from brambleloop.visual import bible, inspect as visual_inspect
    from brambleloop.visual import model_registry, photoreal, tournament

    for module, name in (
            (visual_inspect, "inspect_image"),
            (model_registry, "observe"),
            (model_registry, "compare_identity"),
            (model_registry, "compare_hair"),
            (photoreal, "judge"),
            (bible, "judge"),
            (tournament, "_judge"),
    ):
        source = _inspect.getsource(getattr(module, name))
        assert "check_budget(" in source, f"{module.__name__}.{name} checks no ceiling"
        assert "agent=" in source, (
            f"{module.__name__}.{name} calls check_budget without an agent, so its daily "
            f"permission binds on nothing -- the state visual/inspect.py:246 was left in")
        assert "purpose=" in source, f"{module.__name__}.{name} reserves with no purpose"
        assert "release_reservation(" in source, (
            f"{module.__name__}.{name} takes a reservation and never gives it back, so it "
            f"holds budget nobody is spending for the reservation's full TTL")


def test_the_scan_catches_a_spend_path_added_without_a_ceiling_check():
    """The injected defect. Without this, the scan above could be vacuously green.

    A module that reaches a provider and checks nothing is exactly what a future session
    adds when it copies an older call site, and it is what this file exists to refuse.
    """
    defective = (
        "def judge_a_picture(db, provider, image):\n"
        "    from ..finance import spend_report\n"
        "    response = provider.see('sys', 'prompt', [image], max_tokens=500)\n"
        "    spend_report.record(db, agent='creative_director', amount_cad=0.01)\n"
        "    return response.text\n")
    found = scan_source(defective, "brambleloop/visual/invented.py")
    rows = found["provider_calls"]
    assert len(rows) == 1, rows
    assert rows[0]["guarded"] is False
    assert ("brambleloop/visual/invented.py", "judge_a_picture") not in KNOWN_UNGUARDED

    guarded = defective.replace(
        "    response = provider.see(",
        "    gw.check_budget(db, model=provider.model, input_tokens=1, max_tokens=500,\n"
        "                    agent='creative_director', purpose='x')\n"
        "    response = provider.see(")
    assert scan_source(guarded, "x.py")["provider_calls"][0]["guarded"] is True


def test_the_scan_sees_a_guard_in_a_nested_function():
    """`visual/inspect.py` puts both the guard and the call in a nested helper.

    Pinned separately because a scanner that only looked at the outermost function would
    call that file unguarded, and the natural fix for a false positive is to widen the
    exclusion list -- which is how an instrument stops measuring.
    """
    source = (
        "def outer(db, provider, image):\n"
        "    def _call(prompt):\n"
        "        gw.check_budget(db, model=provider.model, input_tokens=1, max_tokens=2,\n"
        "                        agent='quality_director', purpose='t')\n"
        "        return provider.see('s', prompt, [image], max_tokens=2)\n"
        "    return _call('a'), _call('b')\n")
    rows = scan_source(source, "x.py")["provider_calls"]
    assert len(rows) == 1
    assert rows[0]["guarded"] is True
    assert rows[0]["function"] == "_call"


def test_the_exclusion_list_is_not_a_bypass():
    """Every excluded receiver must still exist in `src/`, and it must not be a provider.

    An exclusion list nobody prunes is where a real spend path goes to hide. `self.queue`
    earns its place by being `queue.durable.JobQueue.complete`, which marks a job done.
    """
    import brambleloop.queue.durable as durable

    assert hasattr(durable.JobQueue, "complete")
    assert not hasattr(durable.JobQueue, "see")

    text = "\n".join(p.read_text() for p in SRC.rglob("*.py"))
    for receiver, reason in NOT_A_MODEL_PROVIDER.items():
        assert f"{receiver}.complete(" in text or f"{receiver}.see(" in text, (
            f"{receiver!r} is excluded from the spend scan and no longer appears in src/. "
            f"Delete the entry rather than leaving a hole shaped like it. Reason on file: "
            f"{reason}")


def test_image_generation_is_outside_this_mechanism_and_the_set_is_pinned():
    """A separate finding, kept separate, and unable to grow quietly.

    `check_budget` prices per token. An image render is priced per image and its provider
    keys are not in `PRICES_USD_PER_MTOK` at all, so routing one through `check_budget`
    today raises "has no price on file" instead of checking anything. That is a gap in the
    mechanism, not a licence for a second one -- so the sites are enumerated and pinned
    until the mechanism can price them.
    """
    from brambleloop.gateway import anthropic as gw
    from brambleloop.gateway import images

    for key in ("gpt-image-2", "flux-2-pro", "nano-banana-2"):
        assert key in images.BY_KEY
        assert key not in gw.PRICES_USD_PER_MTOK, (
            f"{key} now has a per-token price, so the reason these call sites cannot pass "
            f"through check_budget may no longer hold. Re-read the finding before editing "
            f"this test")

    found = scan_tree()
    sites = _sites(found["image_calls"])
    added = sorted(sites - set(KNOWN_IMAGE_GENERATION))
    removed = sorted(set(KNOWN_IMAGE_GENERATION) - sites)
    assert not added, (
        f"{added} render images and no ceiling mechanism reaches them. Adding one is a "
        f"decision about spend, not a refactor: record it here with its owner")
    assert not removed, (
        f"{removed} no longer renders an image. Delete the entry so the list stays the "
        f"list of what is actually open")


class _Provider:
    """A model that answers and counts how often it was reached.

    The count is the point. A guard that refuses *after* the provider has answered has not
    refused anything -- the money has already left -- so what these two tests assert is that
    the provider was never called at all.
    """

    model = "claude-sonnet-5"
    cost_per_1k_input_cad = 0.003 * 1.37
    cost_per_1k_output_cad = 0.015 * 1.37

    def __init__(self, payload: str = '{"no_person": true}'):
        self.payload = payload
        self.calls = 0

    def see(self, system, prompt, images, max_tokens=0):
        self.calls += 1
        payload = self.payload

        class R:
            text = payload
            input_tokens = 1200
            output_tokens = 90
        return R()


def _seeded_db():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def test_a_visual_call_is_refused_before_the_provider_when_the_permission_is_spent():
    """The behaviour change, on a real Visual path, end to end.

    `quality_director` may spend CA$1.00 a day (`agents.registry.DEFAULT_AGENTS`).
    `model_registry.observe` is one of the three calls that were checked by nothing before
    2026-09-25. With the day's permission spent it now returns an error and **does not reach
    the provider** -- and `drift_check` reads that error as maximum drift, so a dimension
    unmeasured because the budget ran out is unmeasured rather than matching.
    """
    from datetime import datetime, timezone

    from brambleloop.core.models import CostEntry
    from brambleloop.visual import model_registry

    db = _seeded_db()
    with db.session() as session:
        session.add(CostEntry(agent="quality_director", amount_cad=0.999, kind="llm",
                              purpose="asset_inspection",
                              at=datetime.now(timezone.utc)))
    provider = _Provider()
    out = model_registry.observe(db, "frame.png", provider=provider)
    assert provider.calls == 0, "the ceiling was checked after the money had already left"
    assert "quality_director" in out["error"]
    assert "may spend CA$1.00 a day" in out["error"]
    assert "Refused before the call" in out["error"]
    # `observe` truncates its error to 200 characters, which cuts the refusal off before the
    # sentence saying the work resumes at the next UTC day and how to raise the ceiling.
    # Recorded rather than widened: the truncation is pre-existing, it applies to provider
    # failures too, and changing it is a decision about every error this function returns.
    assert len(out["error"]) == 200


def test_a_visual_call_gives_its_reservation_back_with_the_bill():
    """What `visual/inspect.py:246` did not do, on every Visual path, proved on the rows.

    Wave 2 said an unreleased reservation is not a leak that lasts -- it expires -- but it
    holds budget nobody is spending for up to five minutes, and `inspect_image` makes two
    calls in a row, so the second was checked against a month carrying the first one's dead
    claim. Nothing is outstanding after the call, the row survives beside the bill it became
    (which is the reconciliation the owner's spend-accounting instruction asked for), and the
    actual is the real cost rather than the padded estimate.
    """
    from brambleloop.core.models import SpendReservation
    from brambleloop.finance import reservations
    from brambleloop.visual import model_registry

    db = _seeded_db()
    provider = _Provider()
    out = model_registry.observe(db, "frame.png", provider=provider)
    assert provider.calls == 1 and out == {"no_person": True}

    assert reservations.outstanding(db)["cad"] == 0.0
    with db.session() as session:
        rows = list(session.scalars(__import__(
            "sqlalchemy").select(SpendReservation)))
        assert len(rows) == 1
        row = rows[0]
        assert row.released_at is not None, "the reservation was left to expire"
        assert row.agent == "quality_director"
        assert row.purpose == "asset_inspection"
        assert 0 < row.actual_cad < row.amount_cad, (
            f"actual {row.actual_cad} against a padded estimate {row.amount_cad}: the "
            f"release did not carry the bill")


def test_a_ceiling_refusal_ends_the_tournament_instead_of_scoring_the_field_on_it():
    """A defect this session's own change would otherwise have introduced.

    `BudgetExceeded` is a `PermanentError`, and `generate_candidates` already caught
    `PermanentError` per candidate and continued. So adding a ceiling check to `_judge`
    without this would have recorded the refusal as *this candidate screened badly* and gone
    on to render the next one -- paying for an image, on a path no ceiling check reaches, to
    ask a question the budget had already refused, once per remaining seed note. Four seed
    notes, one render.
    """
    from brambleloop.gateway import anthropic as gw
    from brambleloop.visual import tournament

    db = _seeded_db()
    renders: list[str] = []

    def generator(prompt, **kw):
        renders.append(prompt)
        return {"image_ref": f"ref{len(renders)}", "cad": 0.05, "provider": "fake"}

    def judge(_db, _ref):
        raise gw.AgentCeilingExceeded("agent 'creative_director' may spend CA$28.00 a day")

    out = tournament.generate_candidates(db, count=4, generator=generator, judge=judge)
    assert len(renders) == 1, f"the field kept rendering after the ceiling refused: {renders}"
    assert out["stopped_by"] == "agent_daily_ceiling"
    assert out["field_complete"] is False
    assert out["generated"] == 0 and len(out["failures"]) == 1


def test_a_ceiling_refusal_does_not_read_as_a_finalist_who_drifted():
    """The other half, and the one with a one-way door behind it.

    `model_registry.compare_identity` returns an error dict rather than raising, and
    `identity.drift_check` reads a dict with no dimensions in it as maximum drift -- correct
    for a judge that failed, wrong for a judge nobody was allowed to ask. Unhandled, a spent
    permission would disqualify a finalist on a run that decides whether she becomes the
    brand's permanent identity. `stopped_by` says which, and the floor for a run with no
    judged scene is `unverifiable`, not `fail`.
    """
    from brambleloop.visual import identity, tournament

    db = _seeded_db()

    def reference_observer(_db, _ref):
        return {d: "described" for d in identity.DRIFT_DIMENSIONS}

    def observer(_db, _reference, _candidate):
        return {"error": "agent 'quality_director' may spend CA$1.00 a day",
                "ceiling": "agent_daily_ceiling"}

    renders: list[str] = []

    def generator(prompt, **kw):
        renders.append(prompt)
        return {"image_ref": f"scene{len(renders)}", "cad": 0.05, "provider": "fake"}

    out = tournament.stress_test(
        db, {"key": "cand-00", "image_ref": "ref", "provider": "fake"},
        generator=generator, observer=observer, reference_observer=reference_observer)
    assert out["usable"] is True
    assert out["stopped_by"] == "agent_daily_ceiling"
    assert len(renders) == 1, "the stress test kept rendering scenes after the refusal"
    assert out["scenes_rendered"] == 0
    assert out["scenes"][0]["image_made_but_not_judged"] is True
    assert out["face_floor"] == "unverifiable" and out["morphology_floor"] == "unverifiable"


def test_a_spender_with_no_agent_row_still_gets_no_invented_ceiling():
    """`photoreal.judge` bills `publishing`, which is not a registered agent.

    Wave 2's rule, re-checked from the path that now depends on it: a name the registry has
    never heard of gets no daily permission rather than a made-up one. Enforcing a number
    nobody authorised would be worse than the gap, and `spend_report.per_agent_today`
    already reports these under `spenders_with_no_agent_row`.
    """
    from brambleloop.core.db import Database
    from brambleloop.gateway import anthropic as gw
    from brambleloop.visual import photoreal

    db = Database("sqlite://")
    db.create_all()
    assert gw.agent_daily_ceiling(db, photoreal.AGENT) is None
    assert gw.agent_daily_ceiling(db, "") is None


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
