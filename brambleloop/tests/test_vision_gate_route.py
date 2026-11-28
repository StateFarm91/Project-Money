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


# ---- the second vendor: Anthropic vision opens on its own activation and probe --------------

class _Resp:
    def __init__(self, text, model):
        self.text, self.model, self.input_tokens, self.output_tokens = text, model, 900, 60


class _AnthropicFixture:
    """FIXTURE provider standing in for `AnthropicProvider` on the asset_inspection route: the
    real model name and prices (so the reservation is the real one), no network."""

    def __init__(self):
        real = gw.provider_for("asset_inspection")
        self.model = real.model
        self.cost_per_1k_input_cad = real.cost_per_1k_input_cad
        self.cost_per_1k_output_cad = real.cost_per_1k_output_cad
        self.name, self.calls = "anthropic", 0

    def see(self, system, prompt, image_urls, *, max_tokens):
        import json

        self.calls += 1
        return _Resp(json.dumps({"face": "matches"}), self.model)


def _probe_row(db, *, ok=True, hours_ago=1.0, activation_id=None, key_fp=None):
    from datetime import datetime, timedelta, timezone

    from brambleloop.core.models import AuditLog
    from brambleloop.gateway import anthropic as A

    at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=A.VISION_PROBE_ACTION,
                       artifact=A.VISION_PROBE_MODEL,
                       detail={"at": at.isoformat(), "model": A.VISION_PROBE_MODEL, "ok": ok,
                               "reason": "", "answer": "photograph", "cost_cad": 0.0004,
                               "activation_id": activation_id,
                               "key_fp": key_fp if key_fp is not None else A.key_fingerprint()}))


def _anthropic_vision(db):
    """The owner's activation of Anthropic vision (test fixture of the step-up path) and a
    successful vision probe made under it."""
    import _paid_activation as paid

    rows = paid.activate(db, G.ANTHROPIC_VISION, G.VISION, daily=2.0, monthly=10.0,
                         per_gallery=1.0)
    _probe_row(db, activation_id=rows[0]["id"] if isinstance(rows[0], dict) and
               "id" in rows[0] else rows[0].get("activation", {}).get("id"))
    return rows


def test_with_both_vendors_usable_identity_gets_two_independent_readings():
    db = R._db()
    R._production_vision(db)                          # openai-vision activated + key
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-fixture-not-a-key"
    try:
        _anthropic_vision(db)
        assert gw.vision_usable(db), "Anthropic vision: activation + probe in force"
        fake = _AnthropicFixture()
        saved = gw.provider_for
        gw.provider_for = lambda task: fake if task == "asset_inspection" else saved(task)
        try:
            first = CG.RealJudges(db, second_vision=None, embedder=None)._vision_judge()
            assert first._route()[0] == "anthropic"
            second = _second(db)
            assert second.gate_open()
            with R._Patched(R._Transport({"face": "matches"})):
                readings = VJ.person_readings([first, second], b"\x89PNG-fixture",
                                              {f: b"ref" for f in VJ.REF_ORDER})
        finally:
            gw.provider_for = saved
        assert len(readings) == 2 and all(r["answered"] for r in readings), readings
        ids = [r["judge"] for r in readings]
        assert ids[0].startswith("image_vision:") and ids[1].startswith("image_vision_openai")
        assert fake.calls == 1
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)


def test_without_its_activation_anthropic_never_opens_even_with_a_key_and_a_probe_row():
    db = R._db()
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-fixture-not-a-key"
    try:
        _probe_row(db, activation_id=None)            # a successful row, no activation
        assert not gw.vision_usable(db)
        first = CG.RealJudges(db, second_vision=None, embedder=None)._vision_judge()
        assert not first.gate_open()
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)


def test_the_capability_probe_job_runs_the_vision_probe_with_reuse():
    from brambleloop.gateway import anthropic as A

    src = (ROOT / "src/brambleloop/runtime/release.py").read_text()
    assert '"image_vision": gw.vision_probe_if_due(ctx.db, job_id=ctx.job.id)' in src
    from brambleloop.runtime import worker

    cad = [c for c in worker.__dict__.get("CADENCES", ()) if "ops.capability_probes" in c] \
        or [l for l in (ROOT / "src/brambleloop/runtime/worker.py").read_text().splitlines()
            if '"ops.capability_probes", 6 * 60 * 60' in l]
    assert cad, "ops.capability_probes runs every six hours"
    db = R._db()
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-fixture-not-a-key"
    asked = []
    real = A.vision_probe
    A.vision_probe = lambda db_, **kw: asked.append(kw) or {"ok": False, "reason": "fixture"}
    try:
        # no activation: the real probe is asked and (in production) refuses, sends nothing
        assert A.vision_probe_if_due(db)["ok"] is False and len(asked) == 1
        # activation + a success under it, 1 h old: reused, CA$0, the gate stays open
        _anthropic_vision(db)
        got = A.vision_probe_if_due(db)
        assert got["ok"] and got["reused"] and got["cost_cad"] == 0.0, got
        assert len(asked) == 1 and gw.vision_usable(db)
        # a success older than the reuse window is asked again
        db2 = R._db()
        import _paid_activation as paid

        rows = paid.activate(db2, G.ANTHROPIC_VISION, G.VISION)
        aid = rows[0]["id"]
        _probe_row(db2, hours_ago=25, activation_id=aid)
        A.vision_probe_if_due(db2)
        assert len(asked) == 2
        # a success made with another key is asked again
        _probe_row(db2, hours_ago=1, key_fp="00000000", activation_id=aid)
        A.vision_probe_if_due(db2)
        assert len(asked) == 3
        assert rows
    finally:
        A.vision_probe = real
        os.environ.pop("ANTHROPIC_API_KEY", None)


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
