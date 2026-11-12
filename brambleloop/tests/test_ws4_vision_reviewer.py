"""WS4 §3.3 check 11: independent vision review with the reviewer's identity (M6 increment 9).

The stored frames' review and the exported-frame review must both hold, and every reviewed
frame must name its reviewer (provider and model) in the review entry for exactly those
bytes, from a provider AND a model family other than the frame's generator. A review that
names no reviewer reads UNKNOWN; a reviewer from the generator's own family reads FAIL.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, ListingAsset  # noqa: E402
from brambleloop.ops import standing_boundary as SB  # noqa: E402
from brambleloop.ops import standing_issuer as SI  # noqa: E402
from brambleloop.runtime.release import FRAME_REVIEW_ACTION  # noqa: E402
from brambleloop.visual.image_records import ImageCandidate  # noqa: E402

SLUG, VERSION = "vision-coaster", "1.0.0"
REVIEWER = {"provider": "anthropic", "model": "claude-vision-x"}
SHA_RENDER, SHA_AI = "a" * 64, "b" * 64


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/v.sqlite", scratch=True)
    db.create_all()
    return db


def _frames(db, *, ai=False, candidate=True, gen=("bfl", "flux-pro-1.1")):
    with db.session() as s:
        s.add(ListingAsset(product_slug=SLUG, version=VERSION, position=1,
                           asset_class="DIGITAL_TWIN_RENDER", role="hero", sha256=SHA_RENDER,
                           claims={}, approved=True))
        if ai:
            cid = None
            if candidate:
                c = ImageCandidate(sha256=SHA_AI, method="generated",
                                   provenance_kind="ai_generated_lifestyle", slug=SLUG,
                                   provider=gen[0], model=gen[1])
                s.add(c)
                s.flush()
                cid = c.id
            s.add(ListingAsset(product_slug=SLUG, version=VERSION, position=2,
                               asset_class="AI_LIFESTYLE_CONCEPT", role="collection",
                               sha256=SHA_AI, claims={"candidate_id": cid}, approved=True))


def _review(db, *, reviewer=REVIEWER, ai=False, verdict="clear", bind=True, drop=()):
    frames = {"1": {"verdict": verdict, "reviewer": dict(reviewer) if reviewer else None,
                    "sha256": SHA_RENDER if bind else "c" * 64}}
    shas = {"1": SHA_RENDER}
    if ai:
        frames["2"] = {"verdict": verdict, "reviewer": dict(reviewer) if reviewer else None,
                       "sha256": SHA_AI}
        shas["2"] = SHA_AI
    for pos in drop:
        frames[pos].pop("reviewer", None)
    with db.session() as s:
        s.add(AuditLog(actor="publishing", action=FRAME_REVIEW_ACTION,
                       artifact=f"{SLUG}@{VERSION}",
                       detail={"frames": frames, "frame_shas": shas}))


def _check(db):
    return SI._independent_vision_review(db, SLUG, VERSION)


def test_deterministic_frames_reviewed_by_a_named_reviewer_pass():
    db = _db()
    _frames(db)
    _review(db)
    assert _check(db) == {"state": SB.PASS, "value": True, "why": None}


def test_no_frame_review_on_record_fails():
    db = _db()
    _frames(db)
    out = _check(db)
    assert out["state"] == SB.FAIL and "frame review" in out["why"], out


def test_a_frame_not_cleared_fails():
    db = _db()
    _frames(db)
    _review(db, verdict="blocked")
    assert _check(db)["state"] == SB.FAIL


def test_a_review_with_no_reviewer_identity_is_unknown():
    db = _db()
    _frames(db)
    _review(db, reviewer=None)
    out = _check(db)
    assert out["state"] == SB.UNKNOWN and "no reviewer identity" in out["why"], out
    db = _db()
    _frames(db)
    _review(db, reviewer={"provider": "anthropic", "model": ""})
    assert _check(db)["state"] == SB.UNKNOWN


def test_a_reviewer_not_bound_to_the_reviewed_bytes_is_unknown():
    db = _db()
    _frames(db)
    _review(db, bind=False)
    out = _check(db)
    assert out["state"] == SB.UNKNOWN and "not bound" in out["why"], out


def test_an_ai_frame_reviewed_outside_its_generators_family_passes():
    db = _db()
    _frames(db, ai=True)
    _review(db, ai=True)
    assert _check(db)["state"] == SB.PASS


def test_a_reviewer_sharing_the_generators_provider_or_model_family_fails():
    for reviewer, needle in (({"provider": "bfl", "model": "claude-vision-x"}, "provider bfl"),
                             ({"provider": "other", "model": "flux-dev"}, "model family flux"),
                             ({"provider": "BFL", "model": "black-forest-labs/flux-pro-2"},
                              "provider BFL and model family flux")):
        db = _db()
        _frames(db, ai=True)
        _review(db, ai=True, reviewer=reviewer)
        out = _check(db)
        assert out["state"] == SB.FAIL and needle in out["why"], (reviewer, out)


def test_an_ai_frame_without_a_generator_record_is_unknown():
    db = _db()
    _frames(db, ai=True, candidate=False)
    _review(db, ai=True)
    out = _check(db)
    assert out["state"] == SB.UNKNOWN and "no generator record" in out["why"], out


def test_the_exported_frame_review_is_read_when_it_applies():
    from brambleloop.visual import exported_review

    db = _db()
    _frames(db)
    _review(db)
    # Its own state refuses: the check fails whatever the stored-frame review says.
    with patch.object(exported_review, "review_state",
                      return_value={"applies": True, "reviewed": False, "why": "not filed"}):
        out = _check(db)
    assert out["state"] == SB.FAIL and "exported-frame review" in out["why"], out
    # It holds, but its entries name no reviewer: UNKNOWN.
    with db.session() as s:
        s.add(AuditLog(actor="quality_director", action=exported_review.ACTION,
                       artifact=f"{SLUG}@{VERSION}",
                       detail={"frames": {"1": {"job": "DESIRE", "sha256": SHA_RENDER,
                                                "verdict": "clear"}},
                               "frame_shas": {"1": SHA_RENDER}}))
    with patch.object(exported_review, "review_state",
                      return_value={"applies": True, "reviewed": True}):
        out = _check(db)
        assert out["state"] == SB.UNKNOWN and exported_review.ACTION in out["why"], out
        with db.session() as s:
            s.add(AuditLog(actor="quality_director", action=exported_review.ACTION,
                           artifact=f"{SLUG}@{VERSION}",
                           detail={"frames": {"1": {"job": "DESIRE", "sha256": SHA_RENDER,
                                                    "verdict": "clear",
                                                    "reviewer": dict(REVIEWER)}},
                                   "frame_shas": {"1": SHA_RENDER}}))
        assert _check(db)["state"] == SB.PASS


def test_model_family():
    assert SI.model_family("claude-sonnet-5-5") == "claude"
    assert SI.model_family("black-forest-labs/flux-pro-1.1") == "flux"
    assert SI.model_family("FLUX.1-dev") == "flux"
    assert SI.model_family("gpt-image-1") == "gpt"
    assert SI.model_family("") is None and SI.model_family(None) is None


def test_the_describers_record_the_reviewer_provider_and_model():
    """Both blind-description calls return the provider's name and model, which the frame
    reviews file per frame beside the reviewed bytes."""
    from brambleloop.core.resilience import PermanentError
    from brambleloop.visual import inspect as inspection

    class _Provider:
        name, model = "anthropic", "claude-vision-x"
        cost_per_1k_input_cad = cost_per_1k_output_cad = 0.0

        def see(self, *_a, **_k):
            raise PermanentError("offline fixture")

    got = inspection.describe_image("/nonexistent.png", provider=_Provider())
    assert got["provider"] == "anthropic" and got["model"] == "claude-vision-x", got
    import inspect as pyinspect

    from brambleloop.runtime import release
    from brambleloop.visual import exported_review

    src = pyinspect.getsource(release._review_frames)
    assert '"reviewer": {"provider": got.get("provider")' in src
    assert '"sha256": (shas or {}).get(frame.position)' in src
    assert '"reviewer": {"provider": got.get("provider")' in pyinspect.getsource(
        exported_review.review)


def test_the_issuer_reads_check_11_for_real():
    db = _db()
    _frames(db)
    _review(db)
    with patch.object(SI, "_independent_vision_review",
                      side_effect=RuntimeError("x")):
        facts = SI.read_facts(db, SLUG, VERSION, "r", {}, shadow=True)
    assert facts["independent_vision_review"]["state"] == SB.UNKNOWN
    facts = SI.read_facts(db, SLUG, VERSION, "r", {}, shadow=True)
    assert facts["independent_vision_review"]["state"] == SB.PASS, facts[
        "independent_vision_review"]
    assert SI.NOT_BUILT_YET == {}


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
