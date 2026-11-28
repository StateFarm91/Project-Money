"""ENG-CANDIDATE-VIEWER: the readback views of generated image candidates and galleries.

OFFLINE TEST -- NOT PRODUCTION EVIDENCE.

* `/api/readback/candidates`, `/api/readback/candidates/{id}/image` and
  `/api/readback/galleries` are readback routes: closed (503) without a configured token,
  401 with no token, a wrong token or the operator token; 200 with the readback token;
* every non-GET method is refused and the database is unchanged by any request;
* content: candidate metadata (verdicts with codes, fidelity and identity readings, receipt
  with verbatim prompt, ordered reference hashes and roles, aspect/resolution/seed, cost),
  pagination, filters; the image bytes byte-for-byte with the right content type, from disk
  and from the durable row; gallery frames;
* no secret: paid-call tokens, credential-named keys, the owner's identity and any
  configured secret value never appear in any response.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_eng_candidate_viewer.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit

import contextlib
import hashlib
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="cand_view_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cv.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI", "BFL")):
        os.environ.pop(_k)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main, security  # noqa: E402
from brambleloop.core import opsauth, readbackauth  # noqa: E402
from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.core.models import DurableArtifact  # noqa: E402
from brambleloop.visual.image_records import (  # noqa: E402
    ImageCandidate, ImageProductionRun, ensure_tables)

# Built at run time so no credential-shaped literal sits in the repository.
OPS_TOKEN = "op" * 20
READBACK_TOKEN = "rb-" + "c5" * 20
PROVIDER_SECRET = "bfl-" + "zq" * 16          # a configured provider key
PAID_TOKEN = "paid-" + "x3" * 12
OWNER = "owner-identity@example.invalid"
CANDS = "/api/readback/candidates"
GALS = "/api/readback/galleries"
RUN = "cozy-cowl@1.0.0@r1"


def _png(colour) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 48), colour).save(buf, "PNG")
    return buf.getvalue()


def _jpeg(colour) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 40), colour).save(buf, "JPEG")
    return buf.getvalue()


@contextlib.contextmanager
def _env(**kw):
    saved = {k: os.environ.get(k) for k in kw}
    try:
        for k, v in kw.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _auth_env(**extra):
    return _env(**{readbackauth.TOKEN_VAR: READBACK_TOKEN, opsauth.TOKEN_VAR: OPS_TOKEN,
                   "BFL_API_KEY": PROVIDER_SECRET, **extra})


def _bearer(t):
    return {"Authorization": f"Bearer {t}"}


_C: dict = {}


def _seed():
    db = main.db
    ensure_tables(db)
    store = ArtifactStore()
    png, jpg, kept = _png((200, 30, 30)), _jpeg((20, 200, 20)), _png((10, 10, 220))
    sha_png = store.put("t/anchor", png, "image/png").sha256
    sha_jpg = store.put("t/lifestyle", jpg, "image/jpeg").sha256
    sha_kept = store.put("t/kept", kept, "image/png", db=db, keep="test durable").sha256
    # Only the durable row remains: the disk copy is gone (container restart).
    p = Path(os.environ["BRAMBLELOOP_ARTIFACT_DIR"]) / sha_kept[:2] / sha_kept
    if p.exists():
        p.unlink()
    ref_a, ref_b = "a" * 64, "b" * 64
    with db.session() as s:
        base = dict(run_key=RUN, method="autonomous", provenance_kind="ai_generated_autonomous",
                    slug="cozy-cowl", version="1.0.0", release="r1", listing="cozy-cowl",
                    provider="bfl-flux3", model="flux-3-image")
        a = ImageCandidate(
            sha256=sha_png, role="anchor", stage="anchor", attempt=1,
            prompt=f"A cowl on a table. Key {PROVIDER_SECRET} must never show.",
            prompt_sha256="p" * 64, prompt_version="pv-7",
            references=[{"sha256": ref_a, "kind": "pattern_derived"},
                        {"sha256": ref_b, "kind": "laura_canonical"}],
            laura_present=False, cost_cad=0.11, cost_basis="BFL credits", width=64, height=48,
            checks={"quality": {"status": "PASS", "why": "ok"},
                    "product_truth": {"status": "FAIL", "why": "colour",
                                      "codes": ["FID-COLOUR"],
                                      "fidelity": {"score": 0.41, "band": "low"}},
                    "identity": {"status": "NA", "why": "no Laura"},
                    "_paid_call": {"token": PAID_TOKEN},
                    "_identity_evidence": {
                        "request": {"aspect_ratio": "4:3", "resolution": "1MP",
                                    "api_key": PROVIDER_SECRET},
                        "references": [{"position": 0, "sha256": ref_a},
                                       {"position": 1, "sha256": ref_b}]},
                    "_route": {"route": "flux", "supplied_by": "owner"}},
            technical_status="FAIL", outcome="rejected",
            failure_categories=["product_fidelity"], submitted_by=OWNER, **base)
        b = ImageCandidate(
            sha256=sha_jpg, role="lifestyle", stage="lifestyle", attempt=2,
            prompt="Laura wears the cowl.", laura_present=True, outfit_id="outfit-3",
            checks={"identity": {"status": "PASS", "why": "face match",
                                 "face": {"verdict": "PASS", "distance": 0.21}},
                    "body_proportions": {"status": "PASS", "why": "ok"},
                    "_identity_evidence": {"seed": 12345}},
            technical_status="PASS", outcome="accepted", publishable=True,
            cost_cad=0.12, **base)
        c = ImageCandidate(sha256=sha_kept, role="detail", stage="detail", attempt=1,
                           prompt="detail", checks={}, technical_status="UNKNOWN",
                           outcome="unverified", **base)
        d = ImageCandidate(sha256="f" * 64, role="detail", stage="detail", attempt=2,
                           prompt="bytes lost", checks={}, outcome="unverified", **base)
        s.add_all([a, b, c, d])
        s.flush()
        ids = {"anchor": a.id, "lifestyle": b.id, "kept": c.id, "lost": d.id}
        s.add(ImageProductionRun(
            run_key=RUN, slug="cozy-cowl", version="1.0.0", release="r1", listing="cozy-cowl",
            stage="gallery", status="ready_for_owner_review",
            card={"roles": [
                {"position": 1, "role": "anchor", "status": "rejected", "source": "generated",
                 "candidate": {"candidate_id": a.id, "sha256": sha_png,
                               "technical_status": "FAIL"}},
                {"position": 2, "role": "lifestyle", "status": "accepted",
                 "source": "generated",
                 "candidate": {"candidate_id": b.id, "sha256": sha_jpg,
                               "technical_status": "PASS"}},
                {"position": 3, "role": "pattern_page", "status": "missing",
                 "source": "pdf"}],
                "_paid_call": {"token": PAID_TOKEN}},
            owner_decision={"visual": {"by": OWNER}}))
    return ids, {"png": png, "jpg": jpg, "kept": kept}


def _client():
    if "c" not in _C:
        main.db.create_all()
        Registry(main.db).seed_defaults()
        _C["ids"], _C["bytes"] = _seed()
        _C["c"] = TestClient(main.app, raise_server_exceptions=False,
                             base_url="https://testserver")
    return _C["c"]


def _urls():
    _client()
    ids = _C["ids"]
    return [CANDS, f"{CANDS}/{ids['anchor']}/image", GALS]


def _fingerprint():
    with main.db.session() as s:
        return (s.scalar(select(func.count()).select_from(ImageCandidate)),
                s.scalar(select(func.count()).select_from(ImageProductionRun)),
                s.scalar(select(func.count()).select_from(DurableArtifact)),
                [(r.outcome, r.technical_status) for r in s.scalars(select(ImageCandidate))])


def _disk_files():
    root = Path(os.environ["BRAMBLELOOP_ARTIFACT_DIR"])
    return sorted(str(p) for p in root.rglob("*") if p.is_file())


def test_routes_are_readback_routes():
    paths = {getattr(r, "path", None) for r in main.app.routes}
    for u in (CANDS, "/api/readback/candidates/{candidate_id}/image", GALS):
        assert u in security.READBACK_ROUTES, u
        assert u not in getattr(security, "PUBLIC_GET_ROUTES", ()), u
        assert u in paths, u


def test_closed_without_a_configured_token():
    c = _client()
    with _env(**{readbackauth.TOKEN_VAR: None, opsauth.TOKEN_VAR: OPS_TOKEN}):
        for u in _urls():
            assert c.get(u).status_code == 503, u
            assert c.get(u, headers=_bearer(READBACK_TOKEN)).status_code == 503, u


def test_no_token_wrong_token_and_operator_token_refused():
    c = _client()
    with _auth_env():
        for u in _urls():
            for h in ({}, _bearer(READBACK_TOKEN[:-1]), _bearer("x" * 40), _bearer(OPS_TOKEN),
                      {"Authorization": READBACK_TOKEN + "x"}):
                r = c.get(u, headers=h)
                assert r.status_code in (401, 403), (u, h.keys(), r.status_code)
                assert READBACK_TOKEN not in r.text and OPS_TOKEN not in r.text
            assert c.get(u, headers=_bearer(READBACK_TOKEN)).status_code == 200, u


def test_read_only():
    c = _client()
    before, files = _fingerprint(), _disk_files()
    with _auth_env():
        for u in _urls():
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                for h in ({}, _bearer(READBACK_TOKEN), _bearer(OPS_TOKEN)):
                    r = c.request(method, u, headers=h, json={"outcome": "accepted"})
                    assert r.status_code in (401, 403, 405), (method, u, r.status_code)
        ids = _C["ids"]
        for _ in range(2):
            for u in _urls() + [f"{CANDS}/{ids['kept']}/image"]:
                assert c.get(u, headers=_bearer(READBACK_TOKEN)).status_code == 200
    assert _fingerprint() == before
    # A durable-row read never writes the bytes back to disk.
    assert _disk_files() == files


def test_candidate_content():
    c = _client()
    ids = _C["ids"]
    with _auth_env():
        body = c.get(CANDS, headers=_bearer(READBACK_TOKEN)).json()
    assert body["count"] == 4 and body["next_before_id"] is None
    by = {x["candidate_id"]: x for x in body["candidates"]}
    assert [x["candidate_id"] for x in body["candidates"]] == sorted(by, reverse=True)
    a = by[ids["anchor"]]
    for k in ("candidate_id", "sha256", "run_key", "slug", "version", "role", "method",
              "attempt", "outcome", "gates", "fidelity", "laura_identity", "receipt",
              "created_at"):
        assert k in a, k
    assert a["run_key"] == RUN and a["role"] == "anchor" and a["outcome"] == "rejected"
    assert a["gates"]["product_truth"] == {"status": "FAIL", "why": "colour",
                                           "codes": ["FID-COLOUR"]}
    assert a["fidelity"]["product_truth"]["fidelity"]["score"] == 0.41
    assert a["failure_categories"] == ["product_fidelity"]
    rc = a["receipt"]
    assert rc["model"] == "flux-3-image" and rc["cost_cad"] == 0.11
    assert rc["prompt"].startswith("A cowl on a table. Key [redacted] must never show.")
    assert [(r["position"], r["sha256"], r["role"]) for r in rc["references"]] == [
        (0, "a" * 64, "pattern_derived"), (1, "b" * 64, "laura_canonical")]
    assert rc["aspect_ratio"] == "4:3" and rc["resolution"] == "1MP" and rc["seed"] is None
    assert rc["not_recorded"] == ["seed"]
    assert a["image_url"] == f"/api/readback/candidates/{ids['anchor']}/image"
    b = by[ids["lifestyle"]]
    assert b["laura_identity"]["laura_present"] is True
    assert b["laura_identity"]["identity"]["face"]["distance"] == 0.21
    assert b["receipt"]["seed"] == 12345


def test_candidate_filters_and_pagination():
    c = _client()
    ids = _C["ids"]
    with _auth_env():
        h = _bearer(READBACK_TOKEN)
        r = c.get(CANDS, params={"role": "detail"}, headers=h).json()
        assert {x["candidate_id"] for x in r["candidates"]} == {ids["kept"], ids["lost"]}
        assert c.get(CANDS, params={"run_key": "nope"}, headers=h).json()["count"] == 0
        p1 = c.get(CANDS, params={"limit": 3}, headers=h).json()
        assert p1["count"] == 3 and p1["next_before_id"] is not None
        p2 = c.get(CANDS, params={"limit": 3, "before_id": p1["next_before_id"]},
                   headers=h).json()
        assert p2["count"] == 1 and p2["next_before_id"] is None
        seen = [x["candidate_id"] for x in p1["candidates"] + p2["candidates"]]
        assert len(set(seen)) == 4
        big = c.get(CANDS, params={"limit": 10_000}, headers=h).json()
        assert big["limit"] == 50


def test_image_bytes_and_content_type():
    c = _client()
    ids, raw = _C["ids"], _C["bytes"]
    with _auth_env():
        h = _bearer(READBACK_TOKEN)
        r = c.get(f"{CANDS}/{ids['anchor']}/image", headers=h)
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
        assert r.content == raw["png"]
        assert r.headers["x-content-sha256"] == hashlib.sha256(raw["png"]).hexdigest()
        r = c.get(f"{CANDS}/{ids['lifestyle']}/image", headers=h)
        assert r.headers["content-type"] == "image/jpeg" and r.content == raw["jpg"]
        r = c.get(f"{CANDS}/{ids['kept']}/image", headers=h)    # from the durable row
        assert r.status_code == 200 and r.content == raw["kept"]
        assert c.get(f"{CANDS}/{ids['lost']}/image", headers=h).status_code == 404
        assert c.get(f"{CANDS}/999999/image", headers=h).status_code == 404
        t = c.get(f"{CANDS}/{ids['anchor']}/image", params={"max_px": 32}, headers=h)
        assert t.status_code == 200 and t.headers["content-type"] == "image/jpeg"
        from PIL import Image

        assert max(Image.open(io.BytesIO(t.content)).size) <= 32


def test_galleries_content():
    c = _client()
    ids = _C["ids"]
    with _auth_env():
        body = c.get(GALS, headers=_bearer(READBACK_TOKEN)).json()
    assert body["count"] == 1
    g = body["galleries"][0]
    assert g["run_key"] == RUN and g["status"] == "ready_for_owner_review"
    assert [(f["role"], f["candidate_id"], f["status"]) for f in g["frames"]] == [
        ("anchor", ids["anchor"], "rejected"), ("lifestyle", ids["lifestyle"], "accepted"),
        ("pattern_page", None, "missing")]
    assert g["frames"][0]["image_url"].endswith(f"/{ids['anchor']}/image")


def test_no_secret_in_any_response():
    c = _client()
    with _auth_env():
        h = _bearer(READBACK_TOKEN)
        texts = [c.get(u, headers=h).text for u in (CANDS, GALS, CANDS + "?limit=1")]
    for t in texts:
        for needle in (READBACK_TOKEN, OPS_TOKEN, PROVIDER_SECRET, PAID_TOKEN, OWNER,
                       "_paid_call", "api_key", "submitted_by", "supplied_by"):
            assert needle not in t, needle


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
