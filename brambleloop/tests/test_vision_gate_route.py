"""VISION-GATE-ROUTE (19i35): Laura's identity and the other blind adapters ask the vision route
actually in use.

Production 19i34, candidate 68 (manual_method/1 coaster lifestyle, 15:05Z): identity UNKNOWN,
both judges "the vision judge (image_vision) is unfunded; nothing was called":
`image_vision` and `image_vision_openai:gpt-4.1-2025-04-14`. Yet openai-vision:vision was
activated and in use (concept judge route_now "openai"). Cause:

* the adapters' first judge was `fidelity.GatewayVisionJudge`, whose `gate_open` reads the
  `image_vision` gate = `gateway.anthropic.vision_usable` (Anthropic activation + Anthropic
  vision probe), closed in production;
* the OpenAI second judge (`vision_judges._openai_second_judge`) subclassed it and inherited the
  same Anthropic-only gate, so it never reached OpenAI either.

Fix: the adapters ask `fidelity.RoutedVisionJudge` (Anthropic when its gate is open, else the
owner-activated openai-vision route, `vision_route.choose`), and the OpenAI judge opens on
OpenAI's own evidence (`concept_judge.openai_vision_usable`: activation in force and its latest
settled call not failing). Two readings through the same vendor are one reading, so identity
still needs two vendors to pass. No route activated: closed, nothing sent. No cap changed.

Every provider answer is a TEST FIXTURE; there is no network.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_vision_gate_route.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_image_fidelity_route as R  # noqa: E402  (its sandbox, no-network and fixtures)

from brambleloop.gateway import paid_provider_gate as G  # noqa: E402
from brambleloop.gateway import providers as gw  # noqa: E402
from brambleloop.visual import candidate_gates as CG  # noqa: E402
from brambleloop.visual import fidelity as F  # noqa: E402
from brambleloop.visual import vision_judges as VJ  # noqa: E402

ANATOMY_OK = {"hands_visible": "false", "extra_or_missing_fingers": "false",
              "malformed_limbs": "false", "face_visible": "true"}


def _second(db):
    os.environ["OPENAI_API_KEY"] = "sk-fixture-not-a-key"
    try:
        return VJ._openai_second_judge(db)
    finally:
        os.environ.pop("OPENAI_API_KEY", None)


def test_openai_activated_and_usable_opens_both_judges_and_an_answer_comes_back():
    db = R._db()
    R._production_vision(db)                  # openai-vision activated, Anthropic not
    j = CG.RealJudges(db, second_vision=None, embedder=None)
    first = j._vision_judge()
    assert isinstance(first, F.RoutedVisionJudge) and first.gate_open()
    t = R._Transport({"craft": "crochet"})
    with R._Patched(t):
        got = VJ.ask(first, "anatomy", "describe", [b"\x89PNG-fixture"])
    assert t.calls == 1 and got["answered"], got
    assert got["judge"].startswith("image_vision_openai"), got
    second = _second(db)
    assert second is not None and second.gate_open()
    t2 = R._Transport({"craft": "crochet"})
    with R._Patched(t2):
        # another frame: an identical request is never bought twice (paid-call store)
        got2 = VJ.ask(second, "anatomy", "describe", [b"\x89PNG-fixture-2"])
    assert t2.calls == 1 and got2["answered"], got2
    assert got2["judge"] == f"image_vision_openai:{VJ.SECOND_JUDGE_MODEL}", got2


def test_two_readings_through_one_vendor_are_one_reading():
    db = R._db()
    R._production_vision(db)
    first = CG.RealJudges(db, second_vision=None, embedder=None)._vision_judge()
    second = _second(db)
    with R._Patched(R._Transport({"face": "x"})):
        readings = VJ.person_readings([first, second], b"\x89PNG-fixture",
                                      {f: b"ref" for f in VJ.REF_ORDER})
    assert len(readings) == 1, readings          # identity cannot pass on one vendor


def test_no_activation_keeps_every_judge_closed_and_sends_nothing():
    db = R._db()
    R._no_vision()
    first = CG.RealJudges(db, second_vision=None, embedder=None)._vision_judge()
    assert not first.gate_open()
    second = _second(db)                      # a key alone never opens it
    assert second is not None and not second.gate_open()
    t = R._Transport()
    with R._Patched(t):
        a = VJ.ask(first, "anatomy", "describe", [b"\x89PNG-fixture"])
        b = VJ.ask(second, "anatomy", "describe", [b"\x89PNG-fixture"])
    assert t.calls == 0 and not a["answered"] and not b["answered"], (a, b)


def test_a_key_without_activation_never_opens_the_openai_judge():
    db = R._db()
    os.environ["BRAMBLELOOP_IMAGE_KEY_OPENAI"] = "fixture-key-not-a-secret"
    try:
        assert not _second(db).gate_open()
        assert not CG.RealJudges(db, second_vision=None, embedder=None)._vision_judge() \
            .gate_open()
    finally:
        R._no_vision()


def test_anthropic_open_behaves_as_before():
    db = R._db()
    saved = gw.vision_usable
    gw.vision_usable = lambda _db: True       # FIXTURE: Anthropic activation + probe in force
    try:
        first = CG.RealJudges(db, second_vision=None, embedder=None)._vision_judge()
        vendor, provider = first._route()
        assert vendor == "anthropic" and first.gate_open()
        assert provider.model == gw.provider_for("asset_inspection").model
        # the OpenAI judge does not open on Anthropic's evidence
        assert not _second(db).gate_open()
    finally:
        gw.vision_usable = saved


def test_caps_are_unchanged():
    assert G.GALLERY_CAD_CAP == 6.00 and G.GALLERY_IMAGE_CAP == 60


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn) and fn.__module__ == __name__:
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                import traceback

                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
