"""KEYS-19i4: provider credentials are read where Railway holds them, and the readback says why.

Production (19i3, 2026-11-22T01:58Z): the concept judge's openai route was chosen but
`openai_key_present` read false -- the code read only OPENAI_API_KEY, while Railway holds the
OpenAI account's key as BRAMBLELOOP_IMAGE_KEY_OPENAI. Every FLUX decline read "auth" with
nothing saying which part refused. These tests pin: the OpenAI key fallback (presence only,
never a value), the FLUX request shape (x-key on submit and poll, api.bfl.ai, no auth header
on the result download), the decline detail codes, and the credential reading in the readback.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_keys_19i4.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

FIXTURE = "fixture-key-not-a-secret"


def _db():
    import tempfile

    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='keys19i4-')}/t.sqlite")
    db.create_all()
    return db


def test_openai_key_falls_back_to_the_accounts_image_variable():
    from brambleloop.gateway import openai_chat as O

    assert O.api_key({}) == "" and not O.key_present({})
    assert O.api_key({"BRAMBLELOOP_IMAGE_KEY_OPENAI": FIXTURE}) == FIXTURE
    # OPENAI_API_KEY, when present, wins
    assert O.api_key({"OPENAI_API_KEY": "a", "BRAMBLELOOP_IMAGE_KEY_OPENAI": "b"}) == "a"
    assert O.api_key({"OPENAI_API_KEY": "  ", "BRAMBLELOOP_IMAGE_KEY_OPENAI": " b "}) == "b"
    saved = {v: os.environ.pop(v, None) for v in ("OPENAI_API_KEY",
                                                  "BRAMBLELOOP_IMAGE_KEY_OPENAI")}
    try:
        os.environ["BRAMBLELOOP_IMAGE_KEY_OPENAI"] = FIXTURE
        assert O.OpenAIProvider.key() == FIXTURE
        from brambleloop.gateway import model_gateway

        assert "openai" in model_gateway.available_providers()
    finally:
        for v, val in saved.items():
            os.environ.pop(v, None)
            if val is not None:
                os.environ[v] = val


def test_no_openai_key_means_the_judge_route_is_not_usable():
    import _paid_activation as paid

    from brambleloop.creative import concept_judge as CJ
    from brambleloop.gateway import paid_provider_gate as G

    db = _db()
    paid.activate(db, G.OPENAI_VISION, G.VISION, daily=2.0, monthly=10.0, per_gallery=1.0)
    saved = {v: os.environ.pop(v, None) for v in ("OPENAI_API_KEY",
                                                  "BRAMBLELOOP_IMAGE_KEY_OPENAI")}
    try:
        assert not CJ.openai_vision_usable(db), "no credential: nothing could be judged"
        os.environ["BRAMBLELOOP_IMAGE_KEY_OPENAI"] = FIXTURE
        assert CJ.openai_vision_usable(db), "activated, never used, credential present"
    finally:
        for v, val in saved.items():
            os.environ.pop(v, None)
            if val is not None:
                os.environ[v] = val


def test_flux3_request_shape_is_pinned():
    from brambleloop.gateway import images as I

    p = I.BY_KEY["flux-3-image"]
    url, headers, body = I._request_for(p, FIXTURE, "a crochet basket", [], "1024x1024")
    assert url == "https://api.us.bfl.ai/v1/flux-3-image", url
    assert headers == {"x-key": FIXTURE}, "BFL auth is the x-key header, nothing else"
    assert "authorization" not in {k.lower() for k in headers}
    assert json.loads(body)["prompt"] == "a crochet basket"
    assert I.key_var(p.account) == "BRAMBLELOOP_IMAGE_KEY_BFL"
    assert I.key_for("flux-3-image", {"BRAMBLELOOP_IMAGE_KEY_BFL": f" {FIXTURE} "}) == FIXTURE


def test_flux3_poll_carries_x_key_and_the_download_carries_no_auth():
    import inspect

    from brambleloop.gateway import images as I

    poll_src = inspect.getsource(I.poll_render)
    assert 'headers = {"x-key": key_for(provider.key, e)}' in poll_src
    assert "_get(payload[\"op_ref\"], headers" in poll_src
    # the presigned result link is fetched with no header at all
    src = inspect.getsource(I)
    assert "urllib.request.urlopen(image_url, timeout=timeout)" in src


def test_decline_detail_codes():
    from brambleloop.ops import production_evidence as PE

    e = 'ImagesRefused: flux-3-image 403: {"detail":"Not authenticated - Invalid Authentication"}'
    assert PE._decline_http(e) == "403" and PE._decline_detail(e) == "not_authenticated"
    assert PE._decline_detail('flux-3-image 422: {"detail":"Invalid API key format"}') \
        == "key_format"
    assert PE._decline_detail("flux-3-image 403: you do not have access to this model") \
        == "no_model_access"
    assert PE._decline_http("TransientError: unreachable") == "none"
    assert PE._decline_detail("something else") == "other"


def test_credential_health_in_the_readback_has_no_key_and_no_text():
    from brambleloop.core.models import AuditLog
    from brambleloop.gateway import credentials as C
    from brambleloop.ops import production_evidence as PE

    db = _db()
    out = PE.paid_calls(db, now=datetime.now(timezone.utc))
    assert out["credential_health"]["bfl"] == {"status": "UNREAD"}, out["credential_health"]
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=C.ACTION, artifact="bfl",
                       detail={"status": "REJECTED", "http_status": 403,
                               "why": "secret-ish provider words", "rotation_marker": "ab12"}))
    out = PE.paid_calls(db, now=datetime.now(timezone.utc))
    h = out["credential_health"]["bfl"]
    assert h["status"] == "REJECTED" and h["http_status"] == 403 and h["at"], h
    blob = json.dumps(out["credential_health"])
    assert "secret-ish" not in blob and "ab12" not in blob, blob


def test_boot_reads_credentials_once_per_deploy():
    src = (ROOT / "src/brambleloop/app/main.py").read_text()
    assert '("provider_credentials", "orchestrator",\n                                "ops.provider_credentials")' in src


if __name__ == "__main__":
    fails = passed = 0
    for name, t in sorted(globals().items()):
        if name.startswith("test_") and callable(t):
            try:
                t()
                passed += 1
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{passed} passed, {fails} failed")
    sys.exit(1 if fails else 0)
