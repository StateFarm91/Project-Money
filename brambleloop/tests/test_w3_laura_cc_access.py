"""W3 lane F: only the authenticated owner reaches Laura; existing protections all apply.

* anonymous requests, and the operator bearer credential without an owner session, are
  refused on every `/api/cc/laura/*` route (default-deny via `security.operator_gate`);
* an owner session still needs CSRF, a fresh nonce and same-origin for every POST; a replayed
  nonce is refused; a revoked session is refused;
* the portrait is served only to the owner, no-store, labelled internal / not
  publication-approved; the PWA view carries the same label;
* `/cc/store-preview?variant=` passes through (owner session required).

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_laura_cc_access.py
"""
from __future__ import annotations

import time
import uuid

import w3_laura_cc_harness as H  # noqa: E402

from brambleloop.app import security  # noqa: E402
from brambleloop.app.command_center import STATIC_DIR  # noqa: E402

GETS = ("/api/cc/laura", "/api/cc/laura/conversation", "/api/cc/laura/portrait")
POSTS = (("/api/cc/laura/ask", {"question": "What genuinely needs me?"}),
         ("/api/cc/laura/follow-on", {"turn_id": 1, "proposal_key": "x", "confirm": True}))


def test_anonymous_and_operator_token_cannot_reach_laura():
    anon = H.client()
    bearer = {"Authorization": "Bearer " + H.OPS}
    assert GETS and POSTS
    for path in GETS:
        assert security.owner_session_route(path), path
        for headers in ({}, bearer):
            r = anon.get(path, headers=headers)
            assert r.status_code == 401, (path, headers.keys(), r.status_code, r.text[:200])
            assert r.json()["code"] == "NOT_AUTHENTICATED"
    for path, body in POSTS:
        for headers in ({}, bearer):
            r = anon.post(path, json=body, headers={**headers, "X-CC-Nonce": uuid.uuid4().hex,
                                                    "X-CC-Timestamp": str(int(time.time()))})
            assert r.status_code == 401, (path, r.status_code, r.text[:200])
    from brambleloop.laura.agency.models import LauraTurn, ensure_tables

    ensure_tables(H.DB)
    with H.DB.session() as s:
        assert s.query(LauraTurn).count() == 0     # nothing was answered or recorded


def test_owner_posts_need_csrf_nonce_and_same_origin():
    c, csrf = H.session()
    path, body = POSTS[0]
    r = c.post(path, json=body)                                   # no CSRF / nonce
    assert r.status_code == 403 and r.json()["code"] == "CSRF", r.text
    r = c.post(path, json=body, headers={**H.fresh(csrf), "X-CSRF-Token": "wrong"})
    assert r.status_code == 403, r.text
    r = c.post(path, json=body, headers={**H.fresh(csrf), "Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["code"] == "CSRF", r.text
    hdr = H.fresh(csrf)
    assert c.post(path, json=body, headers=hdr).status_code == 200
    r = c.post(path, json=body, headers=hdr)                      # replayed nonce
    assert r.status_code in (400, 409) and r.json()["code"] in ("STALE_REQUEST", "REPLAY"), r.text
    stale = {**H.fresh(csrf), "X-CC-Timestamp": str(int(time.time()) - 3600)}
    assert c.post(path, json=body, headers=stale).status_code == 400


def test_revoked_session_is_refused():
    c, csrf = H.session()
    assert c.get("/api/cc/laura").status_code == 200
    assert H.post(c, csrf, "/api/cc/auth/logout", {}).status_code == 200
    assert c.get("/api/cc/laura").status_code == 401
    assert H.post(c, csrf, "/api/cc/laura/ask", {"question": "hi"}).status_code == 401


def test_portrait_is_owner_only_and_labelled_internal():
    c, _csrf = H.session()
    r = c.get("/api/cc/laura/portrait")
    assert r.status_code == 200, r.text[:200]
    assert r.headers["content-type"] == "image/jpeg" and r.content[:2] == b"\xff\xd8"
    assert r.headers["cache-control"] == "no-store"
    assert "not publication-approved" in r.headers["x-laura-image-status"]
    assert r.headers["x-laura-identity"] == "laura-v15-a42aeac7"
    # The portrait is not in the public static shell; the shell only references the API.
    assert not [p for p in STATIC_DIR.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg")]
    view = (STATIC_DIR / "js" / "views" / "laura.js").read_text()
    assert "Internal — canonical reference, not publication-approved" in view
    assert "/api/cc/laura" not in view or "portrait_path" in view


def test_store_preview_variant_passthrough_is_owner_gated():
    anon = H.client()
    r = anon.get("/cc/store-preview?variant=brand_face")
    assert r.status_code == 401, r.status_code
    c, _csrf = H.session()
    r = c.get("/cc/store-preview?variant=brand_face&viewport=mobile")
    assert r.status_code == 200, r.text[:300]
    assert "not publication-approved" in r.text or "not\npublication-approved" in r.text
    std = c.get("/cc/store-preview?viewport=mobile")
    assert std.status_code == 200
    assert r.text != std.text                   # the variant actually reached the renderer
    bogus = c.get("/cc/store-preview?variant=%3Cscript%3E")
    assert bogus.status_code == 200 and "<script>" not in bogus.text


if __name__ == "__main__":
    H.run(globals())
