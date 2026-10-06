"""Wave 3, lane K12: model-photography residuals F-212 F-213 F-219 F-677 F-732 F-877.

No network, no provider call, no spend: the provider HTTP call is replaced by a recording
stand-in, judges and embeddings are fakes, and the one image rendered is the deterministic
disclosed render. Nothing here touches Laura's canonical assets or approves any image.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w3_k12_")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.gateway import images as I  # noqa: E402
from brambleloop.visual import canonical, identity  # noqa: E402
from brambleloop.visual import final_image_gate as F  # noqa: E402
from brambleloop.visual import identity_gate as IG  # noqa: E402
from brambleloop.visual import spend_plan as SP  # noqa: E402
from brambleloop.visual.rnd import loop as L  # noqa: E402
from brambleloop.visual.rnd import status as S  # noqa: E402

_N = [0]
FAKE_EMBEDDER = "k12-test-fake-embedder"


def fresh_db() -> Database:
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/k12_{_N[0]}.sqlite")
    db.create_all()
    return db


def _ref(name: str, data: bytes) -> str:
    p = Path(_TMP) / name
    p.write_bytes(data)
    return str(p)


# ----------------------------------------------------------------------------- fixtures

def canonical_receipt(**over) -> dict:
    """A receipt naming her three current reference hashes, all transmitted."""
    refs = [{"reference": k, "sha256": v, "bytes": 1000, "transmitted": True}
            for k, v in canonical.CURRENT_REFERENCE_HASHES.items()]
    r = {"version": I.CONDITIONING_RECEIPT_VERSION, "provider": "nano-banana-2",
         "dialect": "google", "requested": 3, "transmitted": 3, "references": refs,
         "proven": True}
    r.update(over)
    return r


ALL_MATCH = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}


def laura_evidence(*, judges=None, biometric=True, **over) -> dict:
    ev = {"conditioning": canonical_receipt(),
          "judges": judges if judges is not None else [
              {"judge": "vision-a", "scored": dict(ALL_MATCH)},
              {"judge": "vision-b", "scored": dict(ALL_MATCH)}],
          "biometric": ({"embedder": FAKE_EMBEDDER, "reference": [1.0, 0.0, 0.2],
                         "frame": [0.99, 0.01, 0.2]} if biometric else None)}
    ev.update(over)
    return ev


class FakeEmbedder:
    """Registers a qualified embedder for the test only, then removes it."""

    def __enter__(self):
        IG.QUALIFIED_EMBEDDERS[FAKE_EMBEDDER] = {"match_at": 0.95, "refuse_below": 0.7}
        return self

    def __exit__(self, *exc):
        IG.QUALIFIED_EMBEDDERS.pop(FAKE_EMBEDDER, None)


_RENDER: dict = {}


def verified_source(root: str):
    """A disclosed render stored by sha, as a frame record the structural floor accepts."""
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.products import launch0
    from brambleloop.visual import disclosed_render as D

    if "f" not in _RENDER:
        _RENDER["f"] = D.render(launch0.cir_for("hexagon_coasters"), "hero")
    f = _RENDER["f"]
    sha = ArtifactStore(root).put("src.png", f.png, "image/png").sha256
    rec = {"kind": "disclosed_render", "generated": False, "made": True,
           "role": f.manifest["role"], "slug": f.manifest["slug"],
           "version": f.manifest["version"], "image": {"sha256": sha},
           "disclosed_render": dict(f.manifest, image_sha256=sha), "artifact_dir": root}
    return rec, f.png


def presented(png: bytes, *, touch_product: bool = False) -> bytes:
    """A 'presentation' of the render: the background repainted, optionally a product pixel."""
    from PIL import Image

    from brambleloop.visual import render_contract as K

    img = Image.open(io.BytesIO(png)).convert("RGB")
    bg = tuple(K.BACKGROUND)
    px = img.load()
    w, h = img.size
    product_at = None
    for y in range(h):
        for x in range(w):
            if px[x, y] == bg:
                px[x, y] = (240, 236, 228)
            elif product_at is None:
                product_at = (x, y)
    if touch_product and product_at:
        r, g, b = px[product_at]
        px[product_at] = ((r + 9) % 256, g, b)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def product_evidence(**over) -> dict:
    root = tempfile.mkdtemp(dir=_TMP)
    frame, png = verified_source(root)
    out = presented(png)
    ev = {"source_frame": frame, "image_png": out,
          "image_sha256": hashlib.sha256(out).hexdigest()}
    ev.update(over)
    return ev


# ----------------------------------------------------------------------------- F-212

class RecordingPost:
    """Replaces the HTTP POST: records the body, answers with a tiny inline image."""

    def __init__(self):
        self.bodies: list[bytes] = []

    def __enter__(self):
        self._orig = I._post

        def post(url, headers, payload, *, label, timeout):
            self.bodies.append(payload)
            png = base64.standard_b64encode(b"\x89PNG-fake").decode()
            return {"candidates": [{"content": {"parts": [
                {"inlineData": {"mimeType": "image/png", "data": png}}]}}]}
        I._post = post
        return self

    def __exit__(self, *exc):
        I._post = self._orig


def test_f212_receipt_proves_reference_bytes_are_in_the_request_body():
    face = _ref("face.png", b"\x89PNG face-bytes " + os.urandom(64))
    body = _ref("body.png", b"\x89PNG body-bytes " + os.urandom(64))
    google = I.BY_KEY["nano-banana-2"]
    _, _, payload = I._request_for(google, "k", "p", [face, body], "1024x1024",
                                   benchmark_hashes=frozenset())
    r = I.conditioning_receipt(google, [face, body], payload)
    assert r["proven"] and r["transmitted"] == 2 and r["requested"] == 2, r
    assert r["references"][0]["sha256"] == hashlib.sha256(Path(face).read_bytes()).hexdigest()
    # BFL carries only the first reference: the second is not in the body, so not proven.
    bfl = I.BY_KEY["flux-2-pro"]
    _, _, payload = I._request_for(bfl, "k", "p", [face, body], "1024x1024",
                                   benchmark_hashes=frozenset())
    r = I.conditioning_receipt(bfl, [face, body], payload)
    assert not r["proven"] and r["transmitted"] == 1, r
    assert [x["transmitted"] for x in r["references"]] == [True, False]
    # OpenAI-shaped multipart carries the raw upload.
    gpt = I.BY_KEY["gpt-image-2"]
    _, _, payload = I._request_for(gpt, "k", "p", [face], "1024x1024",
                                   benchmark_hashes=frozenset())
    assert I.conditioning_receipt(gpt, [face], payload)["proven"]
    # A prompt that only *says* "same person as the reference" proves nothing.
    _, _, payload = I._request_for(google, "k", "the same woman as the reference", None,
                                   "1024x1024", benchmark_hashes=frozenset())
    r = I.conditioning_receipt(google, [], payload)
    assert r["requested"] == 0 and not r["proven"], r


def test_f212_generate_attaches_receipt_and_refuses_unprovable_conditioning():
    from brambleloop.agents.registry import Registry

    db = fresh_db()
    Registry(db).seed_defaults()
    face = _ref("face2.png", b"\x89PNG face " + os.urandom(32))
    env = {"BRAMBLELOOP_IMAGE_PROVIDER": "nano-banana-2", "BRAMBLELOOP_IMAGE_KEY": "stand-in"}
    with RecordingPost() as post, tempfile.TemporaryDirectory() as work:
        out = I.generate("p", env=env, reference_urls=[face], work_dir=work, db=db)
    assert out["conditioning"]["proven"], out["conditioning"]
    assert out["conditioning"]["request_sha256"] == hashlib.sha256(post.bodies[0]).hexdigest()
    # BFL asked to condition on two references would send one: refused before any request
    # is sent or any budget reserved.
    second = _ref("body2.png", b"\x89PNG body " + os.urandom(32))
    env = {"BRAMBLELOOP_IMAGE_PROVIDER": "flux-2-pro", "BRAMBLELOOP_IMAGE_KEY": "stand-in"}
    with RecordingPost() as post, tempfile.TemporaryDirectory() as work:
        try:
            I.generate("p", env=env, reference_urls=[face, second], work_dir=work, db=db)
        except I.ImagesRefused as exc:
            assert "F-212" in str(exc), exc
        else:
            raise AssertionError("unprovable conditioning was not refused")
        assert post.bodies == [], "a request was sent"
    from sqlalchemy import select

    from brambleloop.core.models import SpendReservation
    with db.session() as s:
        assert len(list(s.scalars(select(SpendReservation)))) == 1  # the first render only


def test_f212_reference_proven_needs_a_receipt():
    from brambleloop.agents.registry import Registry

    db = fresh_db()
    Registry(db).seed_defaults()
    Registry(db).audit("creative_director", I.REFERENCE_PROBE_ACTION,
                       detail={"provider": "flux-2-pro", "ok": True})
    assert I.reference_proven(db, "flux-2-pro") is False, "legacy probe without a receipt"
    Registry(db).audit("creative_director", I.REFERENCE_PROBE_ACTION,
                       detail={"provider": "flux-2-pro", "ok": True,
                               "conditioning": {"proven": True}})
    assert I.reference_proven(db, "flux-2-pro") is True


# ----------------------------------------------------------------------------- F-213

def test_f213_invalid_and_unmeasured_trials_are_never_a_score():
    now = datetime(2026, 10, 6, tzinfo=timezone.utc)
    cases = {
        "missing_reference_bytes": laura_evidence(conditioning={}),
        "unsupported_conditioning": laura_evidence(conditioning=canonical_receipt(proven=False)),
        "expired_reference": laura_evidence(references=[
            {"sha256": canonical.FACE_SHA256,
             "expires_at": (now - timedelta(minutes=1)).isoformat()}]),
        "reference_not_canonical": laura_evidence(conditioning=canonical_receipt(references=[
            {"reference": "x", "sha256": "b" * 64, "bytes": 10, "transmitted": True}])),
        "missing_judge_pair": laura_evidence(judges=[{"judge": "a", "scored": ALL_MATCH}]),
        "unmeasurable_morphology": laura_evidence(judges=[
            {"judge": "a", "scored": {**ALL_MATCH, "bust": identity.UNMEASURABLE}},
            {"judge": "b", "scored": ALL_MATCH}]),
    }
    assert cases
    for reason, ev in cases.items():
        v = IG.trial_validity(ev, now=now)
        assert v["validity"] in (IG.INVALID, IG.UNMEASURED), (reason, v)
        assert v["score"] is None and v["counts_against_provider"] is False, (reason, v)
        assert any(r.startswith(reason) for r in v["reasons"]), (reason, v["reasons"])
    # A superseded canon asset (forbidden as a fallback) is an expired reference.
    forbidden = sorted(canonical.forbidden_hashes())
    assert forbidden, "the canon manifest records superseded assets"
    ev = laura_evidence(conditioning=canonical_receipt(references=[
        *canonical_receipt()["references"],
        {"reference": "old", "sha256": forbidden[0], "bytes": 10, "transmitted": True}]))
    v = IG.trial_validity(ev, now=now)
    assert v["validity"] == IG.INVALID and any(r.startswith("expired_reference")
                                               for r in v["reasons"]), v
    ok = IG.trial_validity(laura_evidence(), now=now)
    assert ok["validity"] == IG.VALID and ok["counts_against_provider"] is True, ok


# ----------------------------------------------------------------------------- F-219 / F-732

def test_f219_borderline_enters_review_obvious_drift_is_refused():
    # Obvious drift (either judge) is auto-refused -- the existing rule, unchanged.
    drift = laura_evidence(judges=[{"judge": "a", "scored": {**ALL_MATCH, "face": identity.DRIFT}},
                                   {"judge": "b", "scored": ALL_MATCH}])
    g = IG.assess(drift)
    assert g["status"] == "FAIL" and g["band"] == IG.BAND_AUTO_REFUSE, g
    # Obscured anatomy: no drift, morphology unreadable -> review, never a pass.
    obscured = laura_evidence(judges=[
        {"judge": "a", "scored": {**ALL_MATCH, "bust": identity.UNMEASURABLE,
                                  "torso": identity.UNMEASURABLE}},
        {"judge": "b", "scored": ALL_MATCH}])
    g = IG.assess(obscured)
    assert g["status"] == "UNKNOWN" and g["band"] == IG.BAND_REVIEW and g["review_required"]
    # No qualified embedder in this build: even a clean pair goes to review (F-732).
    g = IG.assess(laura_evidence())
    assert IG.QUALIFIED_EMBEDDERS == {}, "no face-embedding model is qualified in the build"
    assert g["status"] == "UNKNOWN" and g["band"] == IG.BAND_REVIEW, g
    assert g["biometric"]["status"] == IG.UNMEASURED
    with FakeEmbedder():
        assert IG.assess(laura_evidence())["status"] == "PASS"
        similar = laura_evidence()
        similar["biometric"] = dict(similar["biometric"], frame=[0.1, 1.0, 0.0])
        g = IG.assess(similar)
        assert g["status"] == "FAIL" and "similar to Laura is NOT Laura" in g["why"], g
        borderline = laura_evidence()
        borderline["biometric"] = dict(borderline["biometric"], frame=[0.8, 0.45, 0.2])
        g = IG.assess(borderline)
        assert g["band"] == IG.BAND_REVIEW, g
    assert g["publication_approved"] is False


def test_f219_review_queue_through_the_rnd_door():
    db = fresh_db()
    obscured = laura_evidence(judges=[
        {"judge": "a", "scored": {**ALL_MATCH, "bust": identity.UNMEASURABLE}},
        {"judge": "b", "scored": ALL_MATCH}])
    good = {g: {"status": "PASS"} for g in L.P.GATES}
    out = L.record_judgement(db, "laura_on_model", subject="campaign:fit", gates=good,
                             identity_evidence=obscured, product_evidence=product_evidence(),
                             image_sha256="c" * 64, source="test:k12")
    assert not out["accepted"] and out["identity_review"], out
    again = L.record_judgement(db, "laura_on_model", subject="campaign:fit", gates=good,
                               identity_evidence=obscured, image_sha256="c" * 64,
                               source="test:k12")
    assert again["identity_review"] == out["identity_review"], "idempotent while open"
    q = IG.queue(db)
    assert len(q) == 1 and q[0]["band"] == IG.BAND_REVIEW, q
    summ = S.summary(db)
    assert summ["identity_review"]["open_listed"] == 1, summ["identity_review"]
    res = IG.resolve(db, q[0]["id"], decision="confirmed_same_person", reviewer="owner")
    assert res["publication_approved"] is False
    assert IG.queue(db) == [] and canonical.asset_status("c" * 64) != \
        canonical.PUBLICATION_APPROVED_STATUS
    for bad in ({"decision": "approve"}, {"decision": "not_laura", "reviewer": " "}):
        try:
            IG.resolve(db, q[0]["id"], **{"reviewer": "owner", **bad})
        except ValueError:
            pass
        else:
            raise AssertionError(bad)


# ----------------------------------------------------------------------------- F-677

def test_f677_final_image_gate_is_deterministic_and_the_proxy_can_only_fail():
    ev = product_evidence()
    g = F.evaluate(ev)
    assert g["status"] == "PASS", g
    assert set(g["attributes"]) == set(F.ATTRIBUTES) and all(
        v == "PASS" for v in g["attributes"].values())
    # One product pixel changed by the presentation stage: rejected, however it looks.
    root = tempfile.mkdtemp(dir=_TMP)
    frame, png = verified_source(root)
    touched = presented(png, touch_product=True)
    g = F.evaluate({"source_frame": frame, "image_png": touched,
                    "image_sha256": hashlib.sha256(touched).hexdigest()})
    assert g["status"] == "FAIL" and g["preservation"]["changed_pixels"] == 1, g
    # A vision 'match' alone is not evidence; a vision 'changed' rejects.
    assert F.evaluate({"vision": {a: "match" for a in F.ATTRIBUTES}})["status"] == "UNKNOWN"
    g = F.evaluate({**product_evidence(), "vision": {"neckline": "changed"}})
    assert g["status"] == "FAIL" and g["attributes"]["neckline"] == "FAIL", g
    # Bytes not bound to the judged sha.
    assert F.evaluate(dict(ev, image_sha256="d" * 64))["status"] == "FAIL"
    # A source whose manifest lies is not a verified source.
    lie = dict(ev["source_frame"], image={"sha256": "e" * 64})
    assert F.evaluate(dict(ev, source_frame=lie))["status"] in ("FAIL", "UNKNOWN")


def test_f677_and_f732_rnd_door_overrides_caller_pass():
    db = fresh_db()
    good = {g: {"status": "PASS"} for g in L.P.GATES}
    with FakeEmbedder():
        # Caller hands in PASS for product truth with no deterministic evidence: overridden.
        out = L.record_judgement(db, "laura_on_model", subject="campaign:hero", gates=good,
                                 identity_evidence=laura_evidence(), source="test:k12")
        assert not out["accepted"] and out["gates"]["product_truth"]["status"] == "UNKNOWN"
        out = L.record_judgement(db, "laura_on_model", subject="campaign:hero", gates=good,
                                 identity_evidence=laura_evidence(),
                                 product_evidence=product_evidence(), source="test:k12")
        assert out["accepted"], out["failures"]
    # Without the qualified embedder the same frame is held for review, never accepted.
    out = L.record_judgement(db, "laura_on_model", subject="campaign:hero2", gates=good,
                             identity_evidence=laura_evidence(),
                             product_evidence=product_evidence(), source="test:k12")
    assert not out["accepted"] and out["identity_review"], out


# ----------------------------------------------------------------------------- F-877

def test_f877_paid_experiments_carry_a_complete_plan():
    db = fresh_db()
    plan = L.plan_paid(db, "laura_on_model")
    assert plan["state"] == L.GATED_SPEND, plan
    p = plan["paid_plan"]
    assert SP.problems(p) == [], plan["plan_problems"]
    for k in SP.REQUIRED:
        assert p[k], k
    ran = L.execute_paid(db, plan["experiment"])
    assert ran["executed"] is False and ran["allowed"] is False and ran["paid_plan"] == p
    # An experiment row without a plan is refused on the plan, before the gate.
    from brambleloop.visual.rnd import models as M
    with M.session(db) as s:
        s.get(M.VisualExperiment, plan["experiment"]).result = {}
    ran = L.execute_paid(db, plan["experiment"])
    assert ran["executed"] is False and "F-877" in ran["why"], ran
    # Every missing field is named.
    for k in SP.REQUIRED:
        bad = dict(p, **{k: [] if "criteria" in k else (0 if k in ("call_count",
                                                                   "max_spend_cad") else "")})
        assert SP.problems(bad), k
    try:
        SP.guard(p, spent_cad=float(p["max_spend_cad"]), calls_made=0, next_cost_cad=0.01)
    except SP.PlanRefused:
        pass
    else:
        raise AssertionError("ceiling not enforced")
    try:
        SP.guard(p, spent_cad=0.0, calls_made=p["call_count"], next_cost_cad=0.0)
    except SP.PlanRefused:
        pass
    else:
        raise AssertionError("call count not enforced")
    assert S.summary(db)["spend"]["paid_plans_incomplete"] == [plan["experiment"]]


def test_f877_provider_trial_runs_under_its_plan():
    from brambleloop.visual import provider_trial as pt

    plan = pt.trial_plan("flux-2-pro")
    assert SP.problems(plan) == [] and plan["max_spend_cad"] == pt.CEILING_CAD, plan
    assert plan["call_count"] == (2 + 1) * len(pt.CASES)


if __name__ == "__main__":
    import time
    import traceback

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
            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:300])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    sys.exit(1 if failures else 0)
