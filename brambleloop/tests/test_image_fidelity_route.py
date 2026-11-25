"""IMAGE-FIDELITY-ROUTE (19i25): the product frame's fidelity judge asks the vision route the
owner activated, and a frame parked on an UNKNOWN fidelity verdict is re-judged once.

Production 19i24 (afe3df8fe, evidence 2026-11-25T05Z): two gallery runs blocked with
`fidelity_gate:product_truth`, both hexagon-coaster-set@1.2.1 (`blocked_releases` lists it
twice). Not `:exhausted`, so neither is the "FAIL after N attempts" block: it is the
`fidelity_gate` UNKNOWN branch, "product fidelity cannot be verified". No coaster check is in
`fidelity_rejections` (only basket:* checks FAILed), so every check of the coaster frames was
PASS or UNKNOWN. The UNKNOWN is `craft_texture`:

* `fidelity.craft_texture` asks `fidelity.GatewayVisionJudge`, which answers only while the
  `image_vision` gate is open, and that gate opens on Anthropic vision alone
  (`gateway.anthropic.vision_usable`).
* Production has `openai-vision:vision` activated and Anthropic vision not
  (`paid_call_dedupe.activations`, `concept_judge.route_now: "openai"`, and the admission gate
  waited on `image_vision` three times in 24 h).
* So every product frame's craft reading was "the vision judge (image_vision) is unfunded;
  nothing was called": UNKNOWN, and a deterministically clean coaster frame parked. The
  basket frames FAILed deterministically first, which is why only the coasters show this.

ASSET-VISION (19i3) fixed the same defect for asset inspection (`vision_route.choose`). The
fidelity judge now uses that rule. It is a false rejection: wrong transport, not a wrong
product. The comparison (`compare_craft`) and every deterministic check are unchanged, and no
usable route still reads UNKNOWN.

The parked runs had no retry path (not a FAIL, not a capability gate, not a provider answer).
The hourly sweep now restarts such a run once per fidelity-judge version, only while a vision
route is usable, at `fidelity_gate` with `reverify`: the stored frame is judged again, nothing
is generated, and every cap binds.

Every provider answer here is a TEST FIXTURE. There is no network.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_image_fidelity_route.py
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
_TMP = tempfile.mkdtemp(prefix="fid_route_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("BRAMBLELOOP_IMAGE_KEY_OPENAI", None)


def _no_network(*_a, **_k):
    raise OSError("network refused by the fidelity-route harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

import _paid_activation as paid  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.gateway import openai_chat  # noqa: E402
from brambleloop.gateway import paid_provider_gate as G  # noqa: E402
from brambleloop.gateway import providers as gw  # noqa: E402
from brambleloop.visual import candidate_gates as CG  # noqa: E402
from brambleloop.visual import fidelity as F  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402
from brambleloop.visual import vision_route as VR  # noqa: E402
from brambleloop.visual.image_records import (ImageCandidate, ImageProductionRun,  # noqa: E402
                                              ensure_tables)

COASTERS = "hexagon-coaster-set"
# FIXTURE: what the craft question's answer looks like for the synthetic coaster flat lay
# (`test_w4_fidelity.flat_lay`, the same reading as its PASSING_JUDGE). Not a model answer.
CRAFT_OK = {"craft": "crochet", "ribbing_visible": "false",
            "border_or_edging_visible": "false", "edge_placement": "none",
            "all_edges_visible": "true", "cable_style": "none",
            "fabric_visible_clearly": "true"}
UNKNOWN_REASON = ("product fidelity cannot be verified: the fidelity verifier (visual.fidelity) "
                  "reads UNKNOWN on ['craft_texture'] (vision judge). Unknown: "
                  "['product_truth']")


class _Transport:
    """FIXTURE transport for `OpenAIProvider._post`: never a network call. Counts requests."""

    def __init__(self, reading=None, *, status: int = 200):
        self.reading, self.status, self.calls = reading or CRAFT_OK, status, 0

    def __call__(self, provider, body, headers, timeout):
        self.calls += 1
        if self.status != 200:
            return self.status, '{"error": {"message": "fixture provider error"}}'
        return 200, json.dumps({
            "id": f"fixture-{self.calls}", "model": provider.model,
            "choices": [{"message": {"content": json.dumps(self.reading)},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 60}})


class _Patched:
    def __init__(self, transport):
        self.transport = transport

    def __enter__(self):
        self.saved_post = openai_chat.OpenAIProvider._post
        openai_chat.OpenAIProvider._post = lambda s, body, headers, timeout: self.transport(
            s, body, headers, timeout)
        return self

    def __exit__(self, *exc):
        openai_chat.OpenAIProvider._post = self.saved_post


_N = [0]


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/fr{_N[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    ensure_tables(db)
    return db


def _production_vision(db):
    """Production 19i24: openai-vision activated by the owner, Anthropic vision not."""
    paid.activate(db, G.OPENAI_VISION, G.VISION, daily=2.0, monthly=10.0, per_gallery=1.0)
    os.environ["BRAMBLELOOP_IMAGE_KEY_OPENAI"] = "fixture-key-not-a-secret"
    assert not gw.vision_usable(db), "Anthropic vision stays closed, as in production"


def _no_vision():
    os.environ.pop("BRAMBLELOOP_IMAGE_KEY_OPENAI", None)


_LAY: dict = {}


def _coasters():
    """The certified coaster CIR and a clean synthetic flat lay of it (test_w4_fidelity)."""
    if not _LAY:
        import test_w4_fidelity as W

        cir = W._cir(COASTERS)
        _LAY.update(cir=cir, good=W.flat_lay(cir), short=W.flat_lay(cir, drop=1))
    return _LAY


def _non_pass(v):
    return [(c["check"], c["status"], c["why"][:90]) for c in v["checks"]
            if c["status"] != "PASS"]


# ---- 1. the check that failed, reproduced --------------------------------------------------

def test_1_production_state_leaves_a_clean_coaster_frame_unknown_on_craft_texture_only():
    """Before the fix: the verifier's judge was `GatewayVisionJudge` (image_vision only). With
    openai-vision activated and Anthropic not, a clean coaster frame passes every
    deterministic check and is UNKNOWN on craft_texture alone -- the 19i24 block."""
    db = _db()
    _production_vision(db)
    lay = _coasters()
    t = _Transport()
    with _Patched(t):
        v = F.verify_anchor(lay["good"], lay["cir"], judge=F.GatewayVisionJudge(db))
    assert t.calls == 0, "the image_vision-only judge never asks the activated route"
    assert v["status"] == "UNKNOWN" and v["failed"] == [], _non_pass(v)
    assert v["unknown"] == ["craft_texture"], _non_pass(v)
    craft = [c for c in v["checks"] if c["check"] == "craft_texture"][0]
    assert craft.get("needs") == "vision judge" and "unfunded" in craft["why"], craft
    deterministic = [c for c in v["checks"] if c["check"] != "craft_texture"]
    assert deterministic and all(c["status"] == "PASS" for c in deterministic), _non_pass(v)


def test_2_the_routed_judge_asks_the_activated_openai_route_and_the_frame_passes():
    db = _db()
    _production_vision(db)
    lay = _coasters()
    judge = F.RoutedVisionJudge(db)
    assert judge.gate_open() and F.vision_route_usable(db)
    t = _Transport()
    with _Patched(t):
        v = F.verify_anchor(lay["good"], lay["cir"], judge=judge)
    assert t.calls == 1, t.calls
    assert v["status"] == "PASS" and v["codes"] == [], _non_pass(v)
    craft = [c for c in v["checks"] if c["check"] == "craft_texture"][0]
    assert craft["judge"] == "image_vision_openai", craft


def test_3_product_truth_uses_the_routed_judge_and_the_adapters_keep_theirs():
    """RealJudges: Product Truth asks the routed judge unless the caller named one; the
    identity/anatomy/realism adapters keep `GatewayVisionJudge` (Laura's checks untouched)."""
    db = _db()
    j = CG.RealJudges(db, second_vision=None, embedder=None)
    assert isinstance(j._fidelity_judge(), F.RoutedVisionJudge)
    assert type(j._vision_judge()) is F.GatewayVisionJudge
    named = object()
    j2 = CG.RealJudges(db, vision=named, second_vision=None, embedder=None)
    assert j2._fidelity_judge() is named and j2._vision_judge() is named


# ---- 2. still strict -------------------------------------------------------------------------

def test_4_no_usable_route_sends_nothing_and_stays_unknown():
    db = _db()
    _no_vision()
    lay = _coasters()
    judge = F.RoutedVisionJudge(db)
    assert not judge.gate_open() and not F.vision_route_usable(db)
    t = _Transport()
    with _Patched(t):
        v = F.verify_anchor(lay["good"], lay["cir"], judge=judge)
    assert t.calls == 0 and v["status"] == "UNKNOWN", (t.calls, _non_pass(v))
    assert v["unknown"] == ["craft_texture"] and VR.NO_JUDGE_WHY[:40] in str(v["checks"])


def test_5_a_wrong_product_still_fails_through_the_routed_judge():
    db = _db()
    _production_vision(db)
    lay = _coasters()
    with _Patched(_Transport()):
        short = F.verify_anchor(lay["short"], lay["cir"], judge=F.RoutedVisionJudge(db))
    assert short["status"] == "FAIL" and "WRONG_PIECE_COUNT" in short["codes"], short["codes"]
    db2 = _db()
    _production_vision(db2)
    with _Patched(_Transport({**CRAFT_OK, "craft": "knitting"})):
        knit = F.verify_anchor(lay["good"], lay["cir"], judge=F.RoutedVisionJudge(db2))
    assert knit["status"] == "FAIL" and "WRONG_CRAFT_TEXTURE" in knit["codes"], knit["codes"]
    db3 = _db()
    _production_vision(db3)
    with _Patched(_Transport({**CRAFT_OK, "border_or_edging_visible": "unclear"})):
        unclear = F.verify_anchor(lay["good"], lay["cir"], judge=F.RoutedVisionJudge(db3))
    assert unclear["status"] == "UNKNOWN", _non_pass(unclear)


def test_6_the_same_bytes_are_asked_once_and_a_failed_ask_is_not_resent():
    db = _db()
    _production_vision(db)
    lay = _coasters()
    t = _Transport()
    with _Patched(t):
        a = F.verify_anchor(lay["good"], lay["cir"], judge=F.RoutedVisionJudge(db))
        b = F.verify_anchor(lay["good"], lay["cir"], judge=F.RoutedVisionJudge(db))
    assert t.calls == 1 and a["status"] == b["status"] == "PASS", (t.calls, _non_pass(b))
    db2 = _db()
    _production_vision(db2)
    bad = _Transport(status=500)
    with _Patched(bad):
        x = F.verify_anchor(lay["good"], lay["cir"], judge=F.RoutedVisionJudge(db2))
        n = bad.calls
        y = F.verify_anchor(lay["good"], lay["cir"], judge=F.RoutedVisionJudge(db2))
    assert x["status"] == y["status"] == "UNKNOWN" and bad.calls == n >= 1, (n, bad.calls)


# ---- 3. the parked runs are re-judged once ---------------------------------------------------

def _blocked(db, slug=COASTERS, *, reason=UNKNOWN_REASON, anchor_status="UNKNOWN",
             extra_fail=False, restarts=0, calls=1, spent=0.07, ns=""):
    key = IP.run_key(slug, "1.2.1", f"{slug}-83b5db1f2cb4", ns=ns,
                     route=IP.SP.FLUX_ROUTE)
    stages = {}
    if restarts:
        stages[IP.RESTART_KEY] = {"epoch": restarts, "history": [
            {"epoch": i + 1, "by": "owner:test", "reason": "earlier restart"}
            for i in range(restarts)]}
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug=slug, version="1.2.1",
                                 release=f"{slug}-83b5db1f2cb4", listing=slug,
                                 stage="fidelity_gate", status="blocked",
                                 blocked_reason=reason, stages=stages,
                                 generation_calls=calls, spent_cad=spent,
                                 attempts_exhausted=False))
        s.add(_cand(key, slug, 1, anchor_status))
        if extra_fail:
            s.add(_cand(key, slug, 2, "FAIL"))
    return key


def _cand(key, slug, attempt, status):
    return ImageCandidate(sha256=f"{attempt:064x}", run_key=key, method="autonomous",
                          provenance_kind="ai_generated_autonomous", slug=slug,
                          version="1.2.1", release=f"{slug}-83b5db1f2cb4", listing=slug,
                          role=IP.ANCHOR_ROLE, stage="product_generation", attempt=attempt,
                          checks={"product_truth": {"status": status}},
                          technical_status=status,
                          outcome={"FAIL": "rejected"}.get(status, "unverified"))


def _follow(calls):
    def follow(inputs, key, *, session=None):
        calls.append((inputs, key))
        return object()
    return follow


def _row(db, key):
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        return {"status": r.status, "calls": r.generation_calls, "spent": r.spent_cad,
                "reason": r.blocked_reason, "stage": r.stage, "stages": dict(r.stages or {})}


def _reblock(db, key):
    with db.session() as s:
        r = s.scalar(select(ImageProductionRun).where(ImageProductionRun.run_key == key))
        r.status, r.blocked_reason, r.stage = "blocked", UNKNOWN_REASON, "fidelity_gate"


def _due(db):
    with db.session() as s:
        return IP.redrive_due(s, None)


def test_7_before_the_fix_nothing_restarts_an_unknown_fidelity_block():
    """The parked shape: `restartable` would allow a reverify, but the only sweep branch that
    looked at `fidelity_gate` (the method redrive) needs a FAIL, so it returned silently.
    The fidelity redrive is that missing path; with it disabled the run stays parked."""
    db = _db()
    key = _blocked(db)
    can = IP.restartable(db, key)
    assert can["restartable"] and can["resume_at"] == "fidelity_gate" and can["reverify"], can
    saved = IP._fidelity_redrive_candidate
    IP._fidelity_redrive_candidate = lambda *_a, **_k: False
    try:
        calls = []
        out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    finally:
        IP._fidelity_redrive_candidate = saved
    assert calls == [] and _row(db, key)["status"] == "blocked", out
    assert key not in str(out), "the old sweep did not even report the parked run"


def test_8_no_vision_route_waits_and_is_judged_once_a_day():
    db = _db()
    _no_vision()
    key = _blocked(db)
    assert _due(db)["kind"] == "fidelity_unknown" and _due(db)["run_key"] == key
    calls = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert calls == [] and [w["run_key"] for w in out["waiting"]] == [key], out
    row = _row(db, key)
    assert row["status"] == "blocked" and row["reason"] == UNKNOWN_REASON, row
    rec = row["stages"][IP.FIDELITY_REDRIVE_KEY]
    assert rec["judge_version"] == F.FIDELITY_JUDGE_VERSION and rec["day"], rec
    assert _due(db) is None, "a refusal for today stops the probe lifting the backoff"


def test_9_with_a_usable_route_the_frame_is_rejudged_once_without_generating():
    db = _db()
    _production_vision(db)
    key = _blocked(db, calls=1, spent=0.07)
    assert _due(db)["kind"] == "fidelity_unknown"
    calls = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert [r["run_key"] for r in out["restarted"]] == [key], out
    assert len(calls) == 1, calls
    inputs, job_key = calls[0]
    assert inputs["stage"] == "fidelity_gate" and inputs["reverify"] is True, inputs
    assert inputs.get("route") == IP.SP.FLUX_ROUTE and job_key.endswith(":e1"), (inputs, job_key)
    row = _row(db, key)
    assert row["status"] != "blocked" and row["stage"] == "fidelity_gate", row
    assert row["calls"] == 1 and abs(row["spent"] - 0.07) < 1e-9, "no cap is reset"
    hist = row["stages"][IP.RESTART_KEY]["history"][-1]
    assert hist["by"] == IP.FIDELITY_REDRIVE_BY and hist["reverify"] is True, hist
    assert hist["judge_version"] == F.FIDELITY_JUDGE_VERSION, hist
    assert IP._attempts(db, key, IP.ANCHOR_ROLE) == 1, "a re-judgement adds no attempt"
    # the same version never re-drives it again
    _reblock(db, key)
    assert _due(db) is None
    out2 = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert len(calls) == 1 and out2["restarted"] == [], out2
    assert any("already re-driven" in r["why"] for r in out2["refused"]), out2


def test_10_a_failed_role_experiment_or_spent_restart_cap_is_not_redriven_here():
    db = _db()
    _production_vision(db)
    # the anchor's best candidate FAILed: a re-judgement is not this redrive's decision
    failed = _blocked(db, "basket-with-fail", anchor_status="FAIL")
    experiment = _blocked(db, "coaster-experiment", ns="xp1")
    assert "#" in experiment
    capped = _blocked(db, "coaster-capped", restarts=IP.MAX_RESTARTS)
    other = _blocked(db, "coaster-other", reason="product fidelity FAIL after 3 attempts: x",
                     anchor_status="FAIL")
    assert not IP._fidelity_redrive_candidate(db, experiment, UNKNOWN_REASON)
    assert not IP.fidelity_unknown_block("product fidelity FAIL after 3 attempts: x")
    calls = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    for r in out["restarted"]:
        assert r["run_key"] in (failed, other), out     # only ever by the method redrive
    restarted = {r["run_key"] for r in out["restarted"]}
    assert not restarted & {experiment, capped}, out
    for key in (experiment, capped):
        assert _row(db, key)["status"] == "blocked"
    hist = (_row(db, failed)["stages"].get(IP.RESTART_KEY) or {}).get("history") or []
    assert not any(h.get("by") == IP.FIDELITY_REDRIVE_BY for h in hist), hist
    failed_rec = _row(db, failed)["stages"].get(IP.FIDELITY_REDRIVE_KEY) or {}
    assert "FAILed" in failed_rec.get("why", "") and failed_rec.get("day") is None, failed_rec
    # the FAILed run is left to the method redrive: it still sees it (pre-method failure)
    assert failed in (out["method_redrives"]["eligible"] or []), out["method_redrives"]
    hist = (_row(db, other)["stages"].get(IP.RESTART_KEY) or {}).get("history") or []
    assert not any(h.get("by") == IP.FIDELITY_REDRIVE_BY for h in hist), hist
    capped_rec = _row(db, capped)["stages"].get(IP.FIDELITY_REDRIVE_KEY) or {}
    assert capped_rec.get("day") is None and "cap" in capped_rec.get("why", ""), capped_rec


def test_11_the_readback_names_the_unknown_check_and_the_due_kind():
    from brambleloop.ops import production_evidence as PE

    acc = {"frames": 0, "by_check": {}, "needs_vision_judge": 0}
    PE._count_fidelity_unknown(acc, {"product_truth": {"fidelity": {
        "status": "UNKNOWN", "checks": [
            {"check": "craft_texture", "status": "UNKNOWN", "needs": "vision judge"},
            {"check": "piece_count", "status": "PASS"},
            {"check": "Free Text Here!", "status": "UNKNOWN"}]}}})
    PE._count_fidelity_unknown(acc, {"product_truth": {"fidelity": {"status": "FAIL",
                                                                     "checks": []}}})
    PE._count_fidelity_unknown(acc, None)
    assert acc == {"frames": 1, "by_check": {"craft_texture": 1, "other": 1},
                   "needs_vision_judge": 1}, acc
    db = _db()
    _no_vision()
    _blocked(db)
    assert PE._redrive_due_kind(db) == "fidelity_unknown"


if __name__ == "__main__":
    failed = 0
    tests = [v for k, v in sorted(globals().items(), key=lambda kv: (
        int(kv[0].split("_")[1]) if kv[0].startswith("test_") else 0, kv[0]))
        if k.startswith("test_") and callable(v)]
    for fn in tests:
        try:
            fn()
            print(f"OK   {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            traceback.print_exc()
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
