"""W4-PRODFIX independent review fixes (INDEPENDENT_SECREVIEW_PRODFIX.md).

F1 (HIGH): a sentinel retry reused the first attempt's stage token, so its stage enqueue hit
the refused attempt's key and nothing was rebuilt. End to end on the real chain (the
review's repro, on the `test_cert_rebuild_chain` harness): the first attempt is refused
downstream, the retry produces a new stage job and bound completion evidence.
F2: only a paid answer that does not parse is given up at once; a refusal to record keeps
its counted retries. F3: the waiver names the one systemic signature. F8: a policy review is
bound to the snapshot the owner was shown.
"""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_cert_rebuild_chain as rc  # noqa: E402 - the real chain harness
from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (ArtefactProvenance, BenchmarkListing, Incident,  # noqa: E402
                                     Job, JobStatus, PolicySnapshot, Product, utcnow)
from brambleloop.gates import platform_policy  # noqa: E402
from brambleloop.intel import vision  # noqa: E402
from brambleloop.publish import release_gates  # noqa: E402


def _cancel_pending(db):
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.status == JobStatus.PENDING)):
            j.status = JobStatus.CANCELLED


def test_a_retry_after_a_refused_attempt_actually_rebuilds_end_to_end():
    st = rc.chain()
    db, slug = st["db"], st["slug"]
    target = rc._rows(db, slug, "marketing_asset")[0][0]
    with db.session() as s:
        row = s.scalar(select(ArtefactProvenance).where(
            ArtefactProvenance.artefact_class == "marketing_asset",
            ArtefactProvenance.artefact_key == target))
        inputs = dict(row.inputs)
        new = inputs[f"cir:{slug}"]
        inputs[f"cir:{slug}"] = "0" * 16
        row.inputs = inputs
    node = f"marketing_asset:{target}"
    payload = {"product_slug": slug, "artefacts": [node], "reason": "sentinel",
               "fingerprints": {f"cir:{slug}": {"old": "0" * 16, "new": new}}}
    first = rc._run(db, "listing", "chain.rebuild", payload, "rebuild:product:orig")
    assert first.status == JobStatus.DONE and first.outputs["stage_job"], first.outputs
    _cancel_pending(db)                         # the deadlock: downstream refused everything
    retry_key = "rebuild:product:orig:retry:2026-10-27"
    retry = rc._run(db, "listing", "chain.rebuild",
                    {**payload, "retry_of_key": "rebuild:product:orig", "retry": retry_key},
                    retry_key)
    out = retry.outputs
    assert out["stage_job"] and out["stage_job"] != first.outputs["stage_job"], out
    with db.session() as s:
        assert s.get(Job, out["stage_job"]).job_type == "pricing.position"
        verify = s.scalar(select(Job).where(
            Job.idempotency_key == f"rebuild-verify:{slug}:{retry.id}:1"))
        verify_id = verify.id
    rc._drain(db, "retry-drain")
    with db.session() as s:
        s.get(Job, verify_id).run_after = utcnow()
    rc._drain(db, "retry-verify")
    done = [d for a, d in rc._audits(db, "chain.rebuild_completed", node)
            if d.get("bound", {}).get("stage_job") == out["stage_job"]]
    assert done and done[-1]["bound"]["bound"] is True, rc._audits(db, "chain.rebuild_completed")
    assert done[-1]["evidence"]["inputs"][f"cir:{slug}"] == new
    # within one retry the token is stable: the same retry asked again enqueues no new stage
    again = rc._run(db, "listing", "chain.rebuild",
                    {**payload, "retry_of_key": "rebuild:product:orig", "retry": retry_key},
                    retry_key + ":rerun")
    assert again.outputs.get("stage_job") is None, again.outputs


# --- F3: only the publication halt's own signature is waived ------------------------------

def test_a_systemic_halt_with_another_signature_is_never_waived():
    db = Database("sqlite://", scratch=True)
    db.create_all()
    with db.session() as s:
        for sl in ("a", "b", "c"):
            s.add(Product(slug=sl, title=sl))
            s.add(Incident(severity="P1", product_slug=sl, halts_publication=True,
                           signature=f"stale-artefact:marketing_asset:{sl}:pin:1"))
        s.add(Incident(severity="P0", halts_publication=True,
                       signature="systemic-halt:publication"))
    own = {"stale-artefact:marketing_asset:a:pin:1"}
    assert release_gates._halting_other_than_staleness(db, "a", own) == []
    with db.session() as s:
        s.add(Incident(severity="P0", halts_publication=True, signature="systemic-halt:other"))
    assert release_gates._halting_other_than_staleness(db, "a", own) == ["systemic-halt:other"]


# --- F2: give up at once only when the paid answer does not parse --------------------------

class _P:
    model = "claude-sonnet-5"
    cost_per_1k_input_cad = cost_per_1k_output_cad = 0.0

    def __init__(self, text):
        self.text = text

    def see(self, system, prompt, images, *, max_tokens, json_schema=None):
        from brambleloop.gateway.model_gateway import ModelResponse

        return ModelResponse(text=self.text, provider="fx", model=self.model,
                             input_tokens=10, output_tokens=5, latency_ms=1)


def _vdb():
    db = Database("sqlite://", scratch=True)
    db.create_all()
    Registry(db).seed_defaults()
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key="k", listing_ref="L1", audit_state="audited",
                               detail={"image_urls": ["https://fixture.invalid/1.jpg"]}))
    return db


def _tried(db):
    with db.session() as s:
        return dict(s.scalar(select(BenchmarkListing)).detail.get("gallery_ranks_failed") or {})


def test_an_unparseable_paid_answer_gives_up_and_a_record_refusal_keeps_its_retries():
    db = _vdb()
    vision.analyse(db, "k", limit=1, provider=_P("not json at all"))
    assert _tried(db) == {"1": vision.FAILED_ATTEMPTS} and vision.pending(db, "k") == []
    db = _vdb()

    def refuse(*_a, **_k):
        raise vision.AnalysisRefused("no model provider is configured")

    with patch.object(vision, "record", refuse):
        vision.analyse(db, "k", limit=1, provider=_P('{"shot_type": "flat_lay"}'))
    assert _tried(db) == {"1": 1} and len(vision.pending(db, "k")) == 1


# --- F8: the review is bound to the snapshot that was shown --------------------------------

def test_a_policy_review_bound_to_an_older_snapshot_is_refused():
    db = Database("sqlite://", scratch=True)
    db.create_all()
    with db.session() as s:
        a = PolicySnapshot(source="listing_image_rules", digest="a" * 64,
                           material_change=True, affects=["publishing"])
        s.add(a)
        s.flush()
        shown = a.id
        s.add(PolicySnapshot(source="listing_image_rules", digest="b" * 64,
                             material_change=True, affects=["publishing"]))
    try:
        platform_policy.review_change(db, "listing_image_rules", reviewed_by="o",
                                      tested="t", snapshot_id=shown)
        raise AssertionError("a review of text nobody was shown was recorded")
    except platform_policy.PolicyRefused as exc:
        assert "newer change" in str(exc)
    assert platform_policy.unreviewed_changes(db)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
