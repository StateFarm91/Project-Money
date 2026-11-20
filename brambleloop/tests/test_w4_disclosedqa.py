"""W4-DISCLOSEDQA: #61 Visual Semantic QA on the frames a disclosed listing actually uploads.

A Launch-0 listing uploads its listing-set certificate's disclosed set and verified gallery
supplements (`etsy_ops.certified_images`), not the `ListingAsset` frames `assets.build`
stores. Before this change only the stored frames were semantically reviewed. Now:
* `visual.exported_review.review` describes every exported frame's exact upload bytes blind,
  against the claim registered for its job. The first image also needs the product family
  and the 230 px grid reading. An unregistered job is UNCLAIMED and blocks;
* `review_state` counts the review only while it covers exactly the certified frames, all
  clear;
* `_listing_parity` (store.publish) and `publication_authority` both read it. This only
  tightens: a release with no disclosed set is unaffected.
Stub providers only: no network, no spend.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_disclosedqa.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_disclosedqa_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.pop("ANTHROPIC_API_KEY", None)


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-DISCLOSEDQA harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import desc, func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Listing, Phase  # noqa: E402
from brambleloop.publish import disclosed_listing, release_gates  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402
from brambleloop.visual import exported_review as X  # noqa: E402

SLUG = "hexagon-coaster-set"


def _description(**over):
    base = {"object_shown": "four hexagon coasters", "object_count": 4,
            "finished_or_in_progress": "finished", "human_present": False,
            "text_present": True, "chart_or_diagram": False,
            "dominant_colours": "cream, wine", "clarity": "clear",
            "third_party_marks": "none"}
    base.update(over)
    return base


class _Provider:
    model = "claude-sonnet-5"
    cost_per_1k_input_cad = 0.003 * 1.37
    cost_per_1k_output_cad = 0.015 * 1.37

    def __init__(self, description=None):
        self.description = description or _description()
        self.calls = 0

    def see(self, system, prompt, images, max_tokens=0):
        self.calls += 1
        payload = json.dumps(self.description)

        class R:
            text = payload
            input_tokens = 1200
            output_tokens = 90
        return R()


_C: dict = {}


def _certified():
    """A coaster release whose disclosed set + supplements hold a valid listing-set certificate."""
    if "db" not in _C:
        db = Database(f"sqlite:///{_TMP}/qa.sqlite")
        db.create_all()
        Registry(db).seed_defaults()
        cir = pipeline._engineered_cir(SLUG)
        JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                             idempotency_key="cert", priority=0)
        Worker(db, "c", phase=Phase.SHADOW, job_types=["gate.certify"]).run_once()
        JobQueue(db).enqueue("publishing", "assets.build",
                             {"slug": SLUG, "version": cir.version, "release": "",
                              "rebuild": "disclosed"}, idempotency_key="d", priority=0)
        Worker(db, "b", phase=Phase.SHADOW, job_types=["assets.build"]).run_once()
        with db.session() as s:
            s.add(Listing(product_slug=SLUG, version=cir.version, title=cir.title,
                          description="A crochet pattern.\n\n" + disclosed_listing.COPY_DISCLOSURE,
                          price_cad=4.0, state="draft"))
        v = release_gates.listing_set(db, slug=SLUG, version=cir.version, issue=True)
        assert (v.get("certificate") or {}).get("valid"), v.get("reasons")
        _C["db"], _C["cir"] = db, cir
    return _C["db"], _C["cir"]


def test_a_disclosed_release_needs_the_review_and_starts_unreviewed():
    db, cir = _certified()
    assert X.applies(db, SLUG, cir.version) is True
    state = X.review_state(db, SLUG, cir.version)
    assert state["applies"] and state["reviewed"] is False and "never" in state["why"]
    p = _Provider()
    out = X.review(db, SLUG, cir.version, provider=p, gate_open=False)
    assert out["reviewed"] is False and p.calls == 0


def test_every_job_the_certificate_exports_has_a_registered_claim():
    from brambleloop.runtime.etsy_ops import certified_frames

    db, cir = _certified()
    jobs = [f.get("job") for f in certified_frames(db, SLUG, cir.version)["frames"]]
    assert jobs and all(j in X.JOB_CLAIMS for j in jobs), jobs


def test_a_clear_blind_review_of_the_exact_exported_bytes_opens_the_gate():
    db, cir = _certified()
    p = _Provider()
    out = X.review(db, SLUG, cir.version, provider=p, gate_open=True)
    assert out["reviewed"] is True, out["not_clear"]
    n = len(out["frames"])
    assert n >= 4 and p.calls == n + 1          # every frame + the hero's grid reading
    assert out["frames"]["1"]["job"] == "DESIRE" and out["frames"]["1"]["grid"]["verdict"] == "clear"
    state = X.review_state(db, SLUG, cir.version)
    assert state["reviewed"] is True, state


def test_a_review_of_other_bytes_does_not_count():
    db, cir = _certified()
    X.review(db, SLUG, cir.version, provider=_Provider(), gate_open=True)
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == X.ACTION)
                       .order_by(desc(AuditLog.id)).limit(1))
        detail = dict(row.detail)
        detail["frame_shas"] = {**detail["frame_shas"], "1": "0" * 64}
        row.detail = detail
    state = X.review_state(db, SLUG, cir.version)
    assert state["reviewed"] is False and "not of the frames" in state["why"]


def test_a_hero_that_shows_something_else_blocks():
    db, cir = _certified()
    out = X.review(db, SLUG, cir.version,
                   provider=_Provider(_description(object_shown="a striped rug")),
                   gate_open=True, fresh=True)
    assert out["reviewed"] is False and out["frames"]["1"]["verdict"] == "blocked"
    assert X.review_state(db, SLUG, cir.version)["reviewed"] is False


def test_a_text_frame_with_no_text_blocks_and_an_unregistered_job_is_unclaimed():
    db, cir = _certified()
    # INTEG7 (S-1): same bytes, a different judgement simulated, so a fresh review is asked
    # for explicitly; without `fresh` the filed review of these frames is reused.
    out = X.review(db, SLUG, cir.version,
                   provider=_Provider(_description(text_present=False)), gate_open=True,
                   fresh=True)
    bad = {f["job"] for f in out["frames"].values() if f["verdict"] == "blocked"}
    assert "MATERIALS" in bad, out["frames"]
    saved = dict(X.JOB_CLAIMS)
    X.JOB_CLAIMS.pop("MATERIALS")
    try:
        out = X.review(db, SLUG, cir.version, provider=_Provider(), gate_open=True,
                       fresh=True)                 # the claims changed: judge again
    finally:
        X.JOB_CLAIMS.clear()
        X.JOB_CLAIMS.update(saved)
    assert any(f["verdict"] == "unclaimed" for f in out["frames"].values())
    assert X.review_state(db, SLUG, cir.version)["reviewed"] is False


def test_s1_a_retry_over_unchanged_frames_makes_no_second_paid_review():
    """INTEG7 (review S-1): the daily rebuild retry re-drives listing.seo over the same frames.
    The filed review covers exactly those frames, so it is reused and no vision call is paid."""
    db, cir = _certified()
    first = _Provider()
    a = X.review(db, SLUG, cir.version, provider=first, gate_open=True, fresh=True)
    assert first.calls == len(a["frames"]) + 1 and a["reviewed"] is True
    with db.session() as s:
        filed = s.scalar(select(func.count()).select_from(AuditLog)
                         .where(AuditLog.action == X.ACTION))
    for _ in range(2):                              # two more daily retries
        again = _Provider()
        b = X.review(db, SLUG, cir.version, provider=again, gate_open=True)
        assert again.calls == 0, again.calls        # zero paid vision calls
        assert b["reused"] is True and b["reviewed"] is True
        assert b["frame_shas"] == a["frame_shas"]
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(AuditLog)
                        .where(AuditLog.action == X.ACTION)) == filed   # nothing re-filed
    assert X.review_state(db, SLUG, cir.version)["reviewed"] is True


def test_s1_changed_or_undescribed_frames_are_reviewed_again():
    db, cir = _certified()
    X.review(db, SLUG, cir.version, provider=_Provider(), gate_open=True, fresh=True)
    with db.session() as s:                        # the frame set changed: a new image at 1
        row = s.scalar(select(AuditLog).where(AuditLog.action == X.ACTION)
                       .order_by(desc(AuditLog.id)).limit(1))
        d = dict(row.detail)
        d["frame_shas"] = {**d["frame_shas"], "1": "0" * 64}
        b = {**d["basis"], "frames": {**d["basis"]["frames"]}}       # the filed review is of
        b["frames"]["1"] = {**b["frames"]["1"], "sha256": "0" * 64}   # other bytes at 1
        d["basis"] = b
        row.detail = d
    p = _Provider()
    X.review(db, SLUG, cir.version, provider=p, gate_open=True)
    assert p.calls > 0                              # other bytes: judged again
    with db.session() as s:                        # a frame whose description failed
        row = s.scalar(select(AuditLog).where(AuditLog.action == X.ACTION)
                       .order_by(desc(AuditLog.id)).limit(1))
        d = dict(row.detail)
        fr = {k: dict(v) for k, v in d["frames"].items()}
        fr["1"]["verdict"] = "unreviewed"
        d["frames"] = fr
        row.detail = d
    q = _Provider()
    X.review(db, SLUG, cir.version, provider=q, gate_open=True)
    assert q.calls > 0                              # no paid answer yet: asked again


def test_m1_a_relabelled_job_or_a_changed_claim_is_judged_again_never_reused():
    """Review M1 (dbb4ebf): the reuse key is the whole basis (bytes, certified job, the claim it
    is judged against, the describer), not position -> sha256 alone."""
    from brambleloop.runtime import etsy_ops

    db, cir = _certified()
    X.review(db, SLUG, cir.version, provider=_Provider(), gate_open=True, fresh=True)
    same = _Provider()
    assert X.review(db, SLUG, cir.version, provider=same, gate_open=True)["reused"] is True
    assert same.calls == 0
    # 1. The same bytes re-certified for another job: judged again, and an unclaimed job blocks.
    real_imgs, real_frames = etsy_ops.certified_images, etsy_ops.certified_frames

    def relabel(order):
        out = [dict(r) for r in order]
        out[2]["job"] = "NO_SUCH_JOB"
        return out

    etsy_ops.certified_images = lambda db, slug, version, **k: {
        **real_imgs(db, slug, version, **k),
        "order": relabel(real_imgs(db, slug, version, **k)["order"])}
    etsy_ops.certified_frames = lambda db, slug, version, **k: {
        **real_frames(db, slug, version, **k),
        "frames": relabel(real_frames(db, slug, version, **k)["frames"])}
    try:
        p = _Provider()
        out = X.review(db, SLUG, cir.version, provider=p, gate_open=True)
        assert not out.get("reused") and p.calls > 0
        assert out["reviewed"] is False and "unclaimed" in out["not_clear"].values()
        again = _Provider()                          # an unclaimed job is never reused
        out2 = X.review(db, SLUG, cir.version, provider=again, gate_open=True)
        assert not out2.get("reused") and again.calls > 0
        assert X.review_state(db, SLUG, cir.version)["reviewed"] is False
    finally:
        etsy_ops.certified_images, etsy_ops.certified_frames = real_imgs, real_frames
    # 2. A claim changed by a deploy: judged again without anyone passing fresh=True.
    X.review(db, SLUG, cir.version, provider=_Provider(), gate_open=True, fresh=True)
    saved = dict(X.JOB_CLAIMS)
    job = next(iter(X.JOB_CLAIMS))
    X.JOB_CLAIMS[job] = {**X.JOB_CLAIMS[job], "stricter": True}
    try:
        p = _Provider()
        assert not X.review(db, SLUG, cir.version, provider=p, gate_open=True).get("reused")
        assert p.calls > 0
    finally:
        X.JOB_CLAIMS.clear()
        X.JOB_CLAIMS.update(saved)


def test_l1_a_failed_grid_reading_is_asked_again_not_reused():
    db, cir = _certified()
    X.review(db, SLUG, cir.version, provider=_Provider(), gate_open=True, fresh=True)
    with db.session() as s:                         # the hero's grid call had failed
        row = s.scalar(select(AuditLog).where(AuditLog.action == X.ACTION)
                       .order_by(desc(AuditLog.id)).limit(1))
        d = dict(row.detail)
        fr = {k: dict(v) for k, v in d["frames"].items()}
        hero = next(k for k, v in fr.items() if v.get("grid"))
        fr[hero]["grid"] = {**fr[hero]["grid"], "described": False, "verdict": "unjudged"}
        fr[hero]["verdict"] = "unjudged"
        d["frames"] = fr
        row.detail = d
    p = _Provider()
    assert not X.review(db, SLUG, cir.version, provider=p, gate_open=True).get("reused")
    assert p.calls > 0


def test_the_publish_read_includes_the_exported_review():
    from brambleloop.ops import publication_authority as PA

    db, cir = _certified()
    got = PA._parity(db, SLUG, cir.version)
    assert "exported_frame_review" in got and got["exported_frame_review"]["applies"] is True


def test_a_release_with_no_certified_disclosed_set_is_unaffected():
    db = Database("sqlite://")
    db.create_all()
    assert X.applies(db, SLUG, "1.2.0") is False
    assert X.review_state(db, SLUG, "1.2.0") == {
        "applies": False, "reviewed": True,
        "why": X.review_state(db, SLUG, "1.2.0")["why"]}


if __name__ == "__main__":
    import time

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, test in tests:
        started = time.time()
        try:
            test()
            print("OK  ", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(bool(failures))
