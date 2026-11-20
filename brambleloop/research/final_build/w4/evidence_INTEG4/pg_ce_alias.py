"""W-VISNEXT: owner-only controlled visual experiments in production.

Exercised through the real `/api/cc/*` routes with a real owner session and step-up, the real
durable queue and worker handler, and `gateway.images.generate` on a MOCK BFL transport. No
network, no spend, no real key: the "key" is a stand-in string the test then hunts for
everywhere it must never appear.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_controlled_experiments.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import io
import json
import logging
import os
import shutil
import socket
import sys
import tempfile
import time
import uuid
from datetime import timedelta
from pathlib import Path

ROOT = Path('/home/user/Project-Money/.claude/worktrees/W4-FC6b25eb0/brambleloop')
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
_TMP = tempfile.mkdtemp(prefix="w4_ctrl_exp_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = "postgresql+psycopg2://bl@127.0.0.1:55432/exptest"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI",
                      "BRAMBLELOOP_IMAGE_KEY")):
        os.environ.pop(_k)
SECRET = "bfl-sk-STANDIN-" + uuid.uuid4().hex          # a stand-in, hunted for afterwards
os.environ["BRAMBLELOOP_IMAGE_KEY_BFL"] = SECRET


def _no_network(*_a, **_k):
    raise OSError("network refused by the controlled-experiment harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

LOG = io.StringIO()
_h = logging.StreamHandler(LOG)
_h.setLevel(logging.DEBUG)
logging.getLogger().addHandler(_h)
logging.getLogger().setLevel(logging.DEBUG)

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.app.command_center.models import OwnerSession  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import AuditLog, Job  # noqa: E402
from brambleloop.core.resilience import TransientError  # noqa: E402
from brambleloop.experiments import controlled as C  # noqa: E402
from brambleloop.gateway import images as I  # noqa: E402
from brambleloop.visual import experiment as XP  # noqa: E402

import test_w4_fluxapi as FA  # noqa: E402

OPS = "q" * 40
PASS = "owner passphrase for the experiment harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db
EXP = "exp-2026-10-20-wrap-7ref"


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (36, 74, 58)).save(buf, format="PNG")
    return buf.getvalue()


class Transport(FA.Transport):
    """Mock BFL that serves a real PNG."""

    def urlopen(self, url, timeout=None):
        self.fetches += 1

        class _R(io.BytesIO):
            headers = {"content-type": "image/png"}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return _R(_png())


def session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def fresh(csrf):
    return {"X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
            "X-CC-Timestamp": str(int(time.time()))}


def post(c, csrf, path, body=None):
    return c.post(path, json=body or {}, headers=fresh(csrf))


def stepup(c, csrf):
    assert post(c, csrf, "/api/cc/auth/step-up", {"passphrase": PASS}).status_code == 200


def expire_stepup(c):
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    with DB.session() as s:
        s.scalar(select(OwnerSession).where(OwnerSession.public_id == sid)).stepup_until = (
            auth._now() - timedelta(seconds=1))


def drain():
    from brambleloop.runtime import release  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import Worker

    w = Worker(DB, "exp-test", job_types=[C.JOB_TYPE])
    n = 0
    while w.run_once():
        n += 1
    return n


def _fresh_definition_dir():
    """A private copy of the definitions so drift tests never touch the committed files."""
    d = Path(tempfile.mkdtemp(prefix="defs-")) / "definitions"
    shutil.copytree(C.DEFINITIONS_DIR, d)
    return d


# ---- definitions ------------------------------------------------------------------------------

def test_the_definition_is_frozen_and_verifies():
    assert EXP in C.definition_ids()
    loaded = C.load(EXP)
    d = loaded["definition"]
    v = C.verify(loaded)
    assert v["ok"], v["problems"]
    assert [r["sha256"][:8] for r in v["references"]] == [
        "a42aeac7", "afe6191f", "f32bac68", "3f737a08", "10d013b8", "3638b3a5", "bc88ed04"]
    assert d["prompt"]["sha256"].startswith("99f0f1a8")
    assert d["generation_cap_cad"] == 5.0 and d["vision_cap_cad"] == 1.0
    assert d["max_retries"] == 1 and d["model"] == "flux-3-image" and d["size"] == "2048x2048"
    assert d["owner_authorization"]["required"] is True
    frozen = ROOT / "research/final_build/w4/flux_live_test_2026-10-20/prompt.txt"
    assert v["prompt"] == frozen.read_text()                      # the frozen plan's prompt


# ---- auth and step-up ---------------------------------------------------------------------

def test_auth_and_step_up_are_required():
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert anon.get("/api/cc/experiments").status_code == 401
    assert anon.post(f"/api/cc/experiments/{EXP}/run", json={}).status_code in (401, 403)
    ops_only = anon.post(f"/api/cc/experiments/{EXP}/authorize", json={},
                         headers={"Authorization": f"Bearer {OPS}"})
    assert ops_only.status_code in (401, 403), ops_only.text      # no ops-token route
    c, csrf = session()
    assert c.get("/api/cc/experiments").status_code == 200
    expire_stepup(c)
    r = post(c, csrf, f"/api/cc/experiments/{EXP}/authorize")
    assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
    r = post(c, csrf, f"/api/cc/experiments/{EXP}/run")
    assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
    try:
        C.authorize(DB, EXP, by="owner", stepped_up=False)
        raise AssertionError("authorized without step-up")
    except C.ControlledRefused:
        pass


def test_caps_cannot_exceed_the_definition():
    c, csrf = session()
    stepup(c, csrf)
    r = post(c, csrf, f"/api/cc/experiments/{EXP}/authorize", {"generation_cap_cad": 5.01})
    assert r.status_code == 400 and "definition's cap" in r.text
    r = post(c, csrf, f"/api/cc/experiments/{EXP}/authorize", {"vision_cap_cad": 1.5})
    assert r.status_code == 400


# ---- the run ------------------------------------------------------------------------------

def _authorize(gen=None, vis=None):
    return C.authorize(DB, EXP, by="owner:test", stepped_up=True, generation_cap_cad=gen,
                       vision_cap_cad=vis)


def _settle_active():
    with DB.session() as s:
        for r in s.scalars(select(C.ControlledRun).where(C.ControlledRun.status.in_(C.ACTIVE))):
            r.status = "failed"


def test_full_run_through_the_routes_and_the_worker_and_no_key_anywhere():
    _settle_active()
    c, csrf = session()
    stepup(c, csrf)
    r = post(c, csrf, f"/api/cc/experiments/{EXP}/authorize")
    assert r.status_code == 200, r.text
    auth_id = r.json()["auth_id"]
    r = post(c, csrf, f"/api/cc/experiments/{EXP}/run")
    assert r.status_code == 200, r.text
    first = r.json()
    dup = post(c, csrf, f"/api/cc/experiments/{EXP}/run").json()
    assert dup["duplicate"] is True and dup["job_id"] == first["job_id"]   # idempotent
    assert first["idempotency_key"].startswith(f"exp:{EXP}:")
    t = Transport()
    with t:
        assert drain() >= 1
    assert len(t.posts) == 1                                            # one FLUX call
    sent = t.posts[0]
    assert any(SECRET in str(v) for v in sent["headers"].values())      # the key was used
    run = C.get_run(DB, first["run_id"])
    assert run["status"] == "completed", run
    assert run["image_sha256"] and run["generation_spent_cad"] > 0
    assert [x["position"] for x in run["references"]] == list(range(1, 8))
    v = run["verification"]
    assert v["summary"] in ("UNKNOWN", "FAIL") and "identity" in v["unknown"]   # gate closed
    # durable bytes
    from brambleloop.core.models import DurableArtifact
    with DB.session() as s:
        assert s.get(DurableArtifact, run["image_sha256"]) is not None
    # card rendering and the image route
    card = c.get(f"/api/cc/experiments/runs/{first['run_id']}/card")
    assert card.status_code == 200
    cj = card.json()
    assert cj["banner"] == XP.LABEL and cj["experiment"] is True
    assert cj["authorization"]["auth_id"] == auth_id
    assert len(cj["references_in_order"]) == 7
    assert cj["costs"]["generation_cap_cad"] == 5.0 and cj["costs"]["vision_cap_cad"] == 1.0
    assert cj["decisions"]["publication_authorization"]["state"] == "not_available"
    assert cj["frames"][0]["image_url"].endswith("/image")
    img = c.get(cj["frames"][0]["image_url"])
    assert img.status_code == 200 and img.content.startswith(b"\x89PNG")
    assert "EXPERIMENT" in img.headers["X-Image-Status"]
    # the key appears nowhere it must not
    blobs = [card.text, c.get("/api/cc/experiments").text, LOG.getvalue()]
    with DB.session() as s:
        for j in s.scalars(select(Job)):
            blobs.append(json.dumps(j.inputs, default=str))
            blobs.append(json.dumps(j.outputs, default=str))
            blobs.append(str(getattr(j, "error", "") or ""))
        for a in s.scalars(select(AuditLog)):
            blobs.append(json.dumps(a.detail, default=str))
        for rr in s.scalars(select(C.ControlledRun)):
            blobs.append(json.dumps(C._run_view(rr), default=str))
    assert len(blobs) > 5
    assert not [b for b in blobs if SECRET in b], "a key value leaked"
    # a new submit after completion is a new run under a new key
    nxt = post(c, csrf, f"/api/cc/experiments/{EXP}/run").json()
    assert nxt["duplicate"] is False and nxt["n"] == first["n"] + 1
    _settle_active()


def test_publication_is_refused_everywhere_for_the_experiment():
    runs = [r for r in C.runs(DB, EXP) if r["image_sha256"]]
    assert runs, "the previous test leaves a completed run"
    sha = runs[0]["image_sha256"]
    for action in ("store.publish", "Etsy payload", "listing image export", "listing approval"):
        try:
            XP.refuse_if_experiment(DB, "reading-nook-cable-wrap", "0.1.0", action=action)
            raise AssertionError(f"{action} was not refused")
        except XP.ExperimentRefused as exc:
            assert XP.LABEL in str(exc)
    try:
        XP.refuse_if_experiment(DB, "reading-nook-cable-wrap", None, action="image export")
        raise AssertionError("slug-level export was not refused")
    except XP.ExperimentRefused:
        pass
    from brambleloop.visual import gallery_persist as GP

    try:
        GP.write_frames(DB, "cloudline-baby-blanket", "1.2.0",
                        [{"position": 2, "role": "lifestyle", "candidate_id": 1, "sha256": sha}],
                        run_key="x")
        raise AssertionError("an experiment image became a listing asset")
    except XP.ExperimentRefused:
        pass
    assert XP.is_experiment_image(DB, sha) and not XP.is_experiment_image(DB, "0" * 64)
    # the existing publication paths call the guard first (source-level pin)
    import inspect

    from brambleloop.ops import activation_authority, publication_authority
    from brambleloop.publish import disclosed_listing
    from brambleloop.runtime import etsy_ops, pipeline
    from brambleloop.visual import image_production

    for mod in (activation_authority, publication_authority, disclosed_listing, etsy_ops,
                pipeline, image_production, GP):
        assert "refuse_if_experiment" in inspect.getsource(mod), mod.__name__
    assert "refuse_if_experiment_image" in inspect.getsource(image_production.approve)


def test_fingerprint_and_prompt_drift_are_refused_before_any_spend():
    _settle_active()
    saved = C.DEFINITIONS_DIR
    for what in ("reference", "prompt"):
        d = _fresh_definition_dir()
        try:
            C.DEFINITIONS_DIR = d
            _authorize()
            out = C.submit(DB, EXP, by="owner:test", stepped_up=True,
                           enqueue=lambda i, k: None)
            target = (d / EXP / "refs" / "ref5_cable_stitch_structure.png" if what ==
                      "reference" else d / EXP / "prompt.txt")
            target.write_bytes(target.read_bytes() + b" ")
            t = Transport()
            with t:
                got = C.run_job(DB, {"run_id": out["run_id"],
                                     "definition_sha256": C.load(EXP)["sha256"]})
            assert got.get("refused") and "drift" in got["why"], (what, got)
            assert t.posts == [] and C.get_run(DB, out["run_id"])["status"] == "refused"
            assert C.get_run(DB, out["run_id"])["generation_spent_cad"] == 0.0
        finally:
            C.DEFINITIONS_DIR = saved
    # a definition edited after submission is refused too
    d = _fresh_definition_dir()
    try:
        C.DEFINITIONS_DIR = d
        _authorize()
        out = C.submit(DB, EXP, by="owner:test", stepped_up=True, enqueue=lambda i, k: None)
        f = d / EXP / "definition.json"
        f.write_text(f.read_text().replace('"max_retries": 1', '"max_retries": 3'))
        got = C.run_job(DB, {"run_id": out["run_id"], "definition_sha256": out[
            "idempotency_key"].split(":")[2]})
        assert got.get("refused") and "changed" in got["why"], got
    finally:
        C.DEFINITIONS_DIR = saved
    _authorize()                      # restore a live authorization for the committed files


def test_generation_cap_is_enforced_before_the_call():
    _settle_active()
    _authorize(gen=0.10)              # under one 2k render (about CA$0.14)
    out = C.submit(DB, EXP, by="owner:test", stepped_up=True, enqueue=lambda i, k: None)
    t = Transport()
    with t:
        got = C.run_job(DB, {"run_id": out["run_id"],
                             "definition_sha256": C.load(EXP)["sha256"]})
    run = C.get_run(DB, out["run_id"])
    assert t.posts == [] and run["status"] == "failed" and run["generation_spent_cad"] == 0.0
    assert "generation cap" in json.dumps(run["attempt_log"])
    _authorize()


def test_vision_cap_is_enforced_and_unknown_never_passes():
    class Inner:
        provider = type("P", (), {"model": "claude-sonnet-5"})()
        n = 0

        def read(self, prompt, images, **kw):
            Inner.n += 1
            return {"answered": True, "reading": {"x": 1}, "cost_cad": 0.04}

    from brambleloop.gateway import anthropic as gw

    est = gw.estimate_cad("claude-sonnet-5", input_tokens=gw.IMAGE_TOKENS_ESTIMATE + 100,
                          output_tokens=300)
    capped = C.CappedVision(Inner(), cap_cad=est * 1.5)
    a = capped.read("p" * 400, [b"x"])
    b = capped.read("p" * 400, [b"x"])
    assert a["answered"] and not b["answered"] and "vision cap" in b["why"] and Inner.n == 1
    zero = C.CappedVision(Inner(), cap_cad=0.0)
    assert not zero.read("p", [b"x"])["answered"] and Inner.n == 1


def test_one_retry_only_and_only_on_a_transient_error():
    _settle_active()
    _authorize()
    calls = []
    saved = I.generate

    def flaky(*a, **k):
        calls.append(1)
        raise TransientError("provider 503")

    try:
        I.generate = flaky
        out = C.submit(DB, EXP, by="owner:test", stepped_up=True, enqueue=lambda i, k: None)
        C.run_job(DB, {"run_id": out["run_id"], "definition_sha256": C.load(EXP)["sha256"]})
        assert len(calls) == 2                                       # 1 + max_retries (1)
        run = C.get_run(DB, out["run_id"])
        assert run["status"] == "failed" and run["attempts"] == 2
        calls.clear()

        def broken(*a, **k):
            calls.append(1)
            raise ValueError("bad request")

        I.generate = broken
        out = C.submit(DB, EXP, by="owner:test", stepped_up=True, enqueue=lambda i, k: None)
        C.run_job(DB, {"run_id": out["run_id"], "definition_sha256": C.load(EXP)["sha256"]})
        assert len(calls) == 1                                       # never re-rolled
    finally:
        I.generate = saved
    _settle_active()


def test_the_images_view_renders_the_experiment_card():
    view = (ROOT / "src/brambleloop/app/command_center/static/js/views/images.js").read_text()
    for needle in ("Controlled experiments", "References sent, in order", "Authorize",
                   "Unknown (never treated as pass)", "Provider receipt", "vision CA$"):
        assert needle in view, needle
    from brambleloop.app.command_center.api import make_router

    paths = {r.path for r in make_router(None).routes}
    assert {"/api/cc/experiments", "/api/cc/experiments/{definition_id}/authorize",
            "/api/cc/experiments/{definition_id}/run",
            "/api/cc/experiments/runs/{run_id}/card",
            "/api/cc/experiments/runs/{run_id}/image"} <= paths


if __name__ == "__main__":
    fails = passes = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn) and fn.__module__ == __name__:
            try:
                fn()
                passes += 1
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{passes} passed, {fails} failed")
    sys.exit(1 if fails else 0)
