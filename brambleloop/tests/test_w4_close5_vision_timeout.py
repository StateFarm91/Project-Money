"""W4-CLOSE5: the `intel.gallery_analysis` read timeouts on b931d17 (#195 clean-run blocker).

Production b931d17 (deployed 2026-10-20T03:48Z) dead-lettered `intel.gallery_analysis` three
times: 9 of 9 attempts between 04:02Z and 08:06Z failed with "TimeoutError: The read operation
timed out" (research/final_build/w4/evidence_CLOSE5/gallery_timeout_b931d17.json). On the build
before it (0417f35) the same cadence judged 4 images per run. The difference is REL2 B5
(da658123), which asked for structured output with a schema of 24 properties, every one of
them optional. Every vision call waited on the 60-second socket read timeout sized for text.

The fix, asserted here:
  1. A vision call gets its own documented, bounded read timeout,
     `gateway.anthropic.VISION_TIMEOUT_SECONDS`. Text calls keep 60 s. The timeout is asserted
     on the real `_send` path (urlopen's own `timeout=` argument), not on a stub.
  2. The observation schema has no optional property. Every field is required, and
     "unjudgeable" is the empty string, which the parser drops as it dropped an omitted key.
  3. One `analyse` run never starts a call that could end past `ANALYSIS_RUN_SECONDS`, and that
     is under the worker's lease-renewal cap. The images it leaves are still pending.
  4. Unchanged: a timed-out paid call is still UNCERTAIN. The paid-call guard never resends a
     call whose billing is unknown, and the failure is not reclassified in /api/verify.

Local, deterministic; urlopen is replaced, nothing reaches the network, nothing is spent.
Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close5_vision_timeout.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.intel import vision  # noqa: E402

_OK = {"content": [{"type": "text", "text": "{}"}], "model": "claude-sonnet-5",
       "usage": {"input_tokens": 1, "output_tokens": 1}, "stop_reason": "end_turn"}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _provider():
    p = gw.AnthropicProvider(model="claude-sonnet-5")
    p.key = staticmethod(lambda: "test-key")  # type: ignore[method-assign]
    return p


def _urlopen_timeouts(call):
    seen = []

    def fake(request, timeout=None):
        seen.append(timeout)
        return _Resp(json.dumps(_OK).encode())

    # Delta review N-9: keyed requests open through `venice.no_redirect_opener()` (no
    # redirect follows); the fake stands in for that opener's `open` as well as urlopen.
    with patch("urllib.request.urlopen", fake), \
            patch("brambleloop.gateway.venice.no_redirect_opener", lambda: _Opener(fake)):
        call()
    return seen


class _Opener:
    def __init__(self, fn):
        self.open = fn


def test_a_vision_call_waits_longer_than_a_text_call_on_the_real_transport():
    assert gw.VISION_TIMEOUT_SECONDS > gw.AnthropicProvider.timeout_seconds == 60.0
    p = _provider()
    seen = _urlopen_timeouts(lambda: p.see(
        "sys", "prompt", ["https://fixture.invalid/a.jpg"], max_tokens=50,
        json_schema=vision.observation_schema()))
    assert seen == [gw.VISION_TIMEOUT_SECONDS], seen
    seen = _urlopen_timeouts(lambda: p.complete("sys", "hi", max_tokens=5))
    assert seen == [60.0], "text calls keep their own timeout"
    # bounded: tighter than the SDKs' 10-minute default, and a caller's longer setting wins
    assert 60 < gw.VISION_TIMEOUT_SECONDS <= 300
    slow = _provider()
    slow.timeout_seconds = 400.0
    assert _urlopen_timeouts(lambda: slow.see(
        "s", "p", ["https://fixture.invalid/a.jpg"], max_tokens=5)) == [400.0]


def test_a_timeout_is_still_uncertain_and_never_resent():
    """The guard is unchanged: a read timeout leaves billing unknown, so it is UNCERTAIN."""
    from brambleloop.gateway import paid_calls

    assert gw._classify_failure(TimeoutError("The read operation timed out")) == \
        paid_calls.UNCERTAIN
    p = _provider()

    def times_out(request, timeout=None):
        raise TimeoutError("The read operation timed out")

    with patch("urllib.request.urlopen", times_out), \
            patch("brambleloop.gateway.venice.no_redirect_opener",
                  lambda: _Opener(times_out)):
        try:
            p.see("s", "p", ["https://fixture.invalid/a.jpg"], max_tokens=5)
            raise AssertionError("a timed-out call was reported as an answer")
        except TimeoutError:
            pass                                   # surfaces as itself; nothing hides it


def test_the_observation_schema_has_no_optional_property():
    schema = vision.observation_schema()
    optional = set(schema["properties"]) - set(schema.get("required") or ())
    assert optional == set(), ("an all-optional object is a grammar over every subset of its "
                               f"properties -- the shape that timed out: {sorted(optional)}")
    assert schema["required"] == list(vision.OBSERVATION_FIELDS)
    assert schema["additionalProperties"] is False
    assert "" in schema["properties"]["shot_type"]["enum"]
    # "unjudgeable" still means "not in the observation"
    blank = {f: "" for f in vision.OBSERVATION_FIELDS}
    assert vision.parse_observation(json.dumps({**blank, "shot_type": "flat_lay"})) == \
        {"shot_type": "flat_lay"}
    try:
        vision.parse_observation(json.dumps(blank))
        raise AssertionError("an all-blank answer was stored as an observation")
    except vision.AnalysisRefused:
        pass
    prompt = vision.analysis_prompt()
    assert "empty string" in prompt and "all optional" not in prompt, prompt


def test_a_run_never_starts_a_call_that_could_outlast_its_budget():
    from brambleloop.core.db import Database
    from brambleloop.runtime import worker

    assert gw.VISION_TIMEOUT_SECONDS < vision.ANALYSIS_RUN_SECONDS < worker.MAX_HANDLER_SECONDS
    db = Database("sqlite://", scratch=True)
    db.create_all()
    items = [vision.PendingAnalysis("w4-bench", f"l{i}", f"https://fixture.invalid/{i}.jpg", 1)
             for i in range(3)]
    calls = []

    class _P:
        model = "claude-sonnet-5"
        cost_per_1k_input_cad = cost_per_1k_output_cad = 0.0

        def see(self, system, prompt, images, *, max_tokens, json_schema=None):
            calls.append(images[0])
            raise gw.TransientError("fixture: provider unavailable")

    now = [0.0]
    with patch.object(vision, "pending", lambda *a, **k: list(items)), \
            patch.object(vision, "_mark_failed", lambda db, item: None):
        # budget exhausted before the first call: nothing is sent, the backlog stays
        now[0] = 0.0
        ticks = iter([0.0, vision.ANALYSIS_RUN_SECONDS - gw.VISION_TIMEOUT_SECONDS + 1])
        out = vision.analyse(db, "w4-bench", limit=3, provider=_P(),
                             clock=lambda: next(ticks))
        assert calls == [] and out["stopped_by"] == "run_time_budget", out
        # positive control: with time left, every image is attempted
        out = vision.analyse(db, "w4-bench", limit=3, provider=_P(), clock=lambda: 0.0)
    assert len(calls) == 3 and out["stopped_by"] == "", out


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 4, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
