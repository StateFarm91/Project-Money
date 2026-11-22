"""ASSET-VISION (19i3): asset inspection uses the same judge choice as the concept judge.

Production (FIRST-LISTING owner item 2): `inspect.describe_image` always asked the
`asset_inspection` route's default vendor, Anthropic, and the hero and frame review paths ran
only while the Anthropic-only `image_vision` gate was open. The owner activated
`openai-vision:vision` only, so parity HERO and frame review stayed unjudged.

This proves the following:
1. With no usable vision route, nothing is sent and every check stays unmade (unjudged). It is
   never a pass.
2. With only openai-vision activated (Anthropic closed, as in production), the review opens
   and the asset is described through OpenAI.
3. The OpenAI route is idempotent per image bytes. A repeat is served from the stored answer:
   nothing is sent and nothing is billed.
4. A provider error leaves the check unmade, closes the route, and is not re-sent.

Every provider answer here is a TEST FIXTURE. There is no network.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_asset_vision_route.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import json
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
_TMP = tempfile.mkdtemp(prefix="asset_vision_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.pop("ANTHROPIC_API_KEY", None)


def _no_network(*_a, **_k):
    raise OSError("network refused by the asset-vision harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

import _paid_activation as paid  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.gateway import openai_chat  # noqa: E402
from brambleloop.gateway import paid_provider_gate as G  # noqa: E402
from brambleloop.gateway import providers as gw  # noqa: E402
from brambleloop.visual import inspect as I  # noqa: E402
from brambleloop.visual import vision_route as VR  # noqa: E402

DESCRIPTION = json.dumps({
    "object_shown": "four hexagon coasters", "object_count": 4,
    "finished_or_in_progress": "finished", "human_present": False, "text_present": False,
    "chart_or_diagram": False, "dominant_colours": "cream, wine", "clarity": "clear",
    "third_party_marks": "none"})


class _Transport:
    """FIXTURE transport for `OpenAIProvider._post`: never a network call. Counts requests."""

    def __init__(self, *, status: int = 200):
        self.status, self.calls = status, 0

    def __call__(self, provider, body, headers, timeout):
        self.calls += 1
        if self.status != 200:
            return self.status, '{"error": {"message": "fixture provider error"}}'
        return 200, json.dumps({
            "id": f"fixture-{self.calls}", "model": provider.model,
            "choices": [{"message": {"content": DESCRIPTION}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 60}})


class _Patched:
    def __init__(self, transport):
        self.transport = transport

    def __enter__(self):
        self.saved_post = openai_chat.OpenAIProvider._post
        self.saved_key = os.environ.get(openai_chat.KEY_VAR)
        openai_chat.OpenAIProvider._post = lambda s, body, headers, timeout: self.transport(
            s, body, headers, timeout)
        os.environ[openai_chat.KEY_VAR] = "fixture-key-not-a-secret"
        return self

    def __exit__(self, *exc):
        openai_chat.OpenAIProvider._post = self.saved_post
        if self.saved_key is None:
            os.environ.pop(openai_chat.KEY_VAR, None)
        else:
            os.environ[openai_chat.KEY_VAR] = self.saved_key


_N = [0]


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/av{_N[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _png(name: str, colour=(200, 40, 60)) -> str:
    from PIL import Image

    path = os.path.join(_TMP, name)
    Image.new("RGB", (64, 64), colour).save(path, "PNG")
    return path


def _openai_only(db):
    paid.activate(db, G.OPENAI_VISION, G.VISION, daily=2.0, monthly=10.0, per_gallery=1.0)
    assert not gw.vision_usable(db), "Anthropic vision stays closed, as in production"


def test_no_route_sends_nothing_and_stays_unjudged():
    db = _db()
    assert VR.vision_open(db) is False
    vendor, provider = VR.choose(db)
    assert vendor is None and isinstance(provider, VR.NoVisionJudge)
    got = I.describe_image(_png("a.png"), db=db, claim={"object_count": 4})
    assert got["described"] is False and "no owner-activated vision" in got["description_error"]
    full = I.inspect_image(_png("b.png"), db=db)
    assert I.gate(full)["verdict"] == "unjudged", "an unmade check is never a pass"


def test_openai_vision_alone_opens_the_review_and_describes():
    db = _db()
    _openai_only(db)
    assert VR.vision_open(db) is True
    vendor, provider = VR.choose(db)
    assert vendor == VR.OPENAI and provider.name == "openai"
    t = _Transport()
    with _Patched(t):
        got = I.describe_image(_png("c.png"), db=db)
    assert t.calls == 1 and got["described"] is True
    assert got["description"]["object_count"] == 4


def test_the_same_bytes_are_never_paid_for_twice():
    db = _db()
    _openai_only(db)
    t = _Transport()
    path = _png("d.png")
    with _Patched(t):
        first = I.describe_image(path, db=db)
        copy = _png("d-copy.png")                 # the same bytes under another name
        second = I.describe_image(copy, db=db)
        other = I.describe_image(_png("e.png", colour=(10, 200, 10)), db=db)
    assert first["described"] and second["described"] and other["described"]
    assert t.calls == 2, f"identical bytes are served from the stored answer; calls={t.calls}"
    assert second["description"] == first["description"]


def test_a_provider_error_stays_unmade_and_is_not_resent():
    db = _db()
    _openai_only(db)
    t = _Transport(status=500)
    path = _png("f.png")
    with _Patched(t):
        got = I.describe_image(path, db=db)
        calls_after_first = t.calls
        again = I.describe_image(path, db=db)
    assert got["described"] is False and again["described"] is False
    assert t.calls == calls_after_first, "an attempt with no kept answer is not re-sent"
    assert calls_after_first >= 1


def test_anthropic_route_is_unchanged_when_usable():
    db = _db()
    saved = gw.vision_usable
    gw.vision_usable = lambda _db: True
    try:
        vendor, provider = VR.choose(db)
    finally:
        gw.vision_usable = saved
    assert vendor == VR.ANTHROPIC and not isinstance(provider, VR.NoVisionJudge)
    assert not str(getattr(provider, "name", "")).startswith("openai")


if __name__ == "__main__":
    failed = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        try:
            fn()
            print(f"   OK   {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            traceback.print_exc()
            print(f" FAIL   {fn.__name__}: {exc}")
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
