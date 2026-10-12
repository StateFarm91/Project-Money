"""W3 lane F integrator wiring: listing-outcome intake (K3), brand fonts (A), SEO w3 in the
Command Center (G), Laura memory principal only from the verified owner session (E).

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_laura_cc_wiring.py
"""
from __future__ import annotations

import w3_laura_cc_harness as H  # noqa: E402

DB = H.DB
BAD_CSV = "not,a,stats\nexport,at,all\n"


def test_listing_outcomes_operator_route():
    anon = H.client()
    r = anon.post("/api/listing-outcomes?period_start=2026-09-01&period_end=2026-09-30",
                  content=BAD_CSV)
    assert r.status_code == 401, r.text
    r = anon.post("/api/listing-outcomes?period_start=2026-09-01&period_end=2026-09-30",
                  content=BAD_CSV, headers={"Authorization": "Bearer " + H.OPS})
    assert r.status_code == 400 and r.json()["error"], r.text


def test_listing_outcomes_owner_route_needs_session_csrf_and_refuses_bad_exports():
    anon = H.client()
    path = "/api/cc/listing-outcomes?period_start=2026-09-01&period_end=2026-09-30"
    assert anon.post(path, content=BAD_CSV).status_code == 401
    c, csrf = H.session()
    r = c.post(path, content=BAD_CSV, headers={"Content-Type": "text/csv"})
    assert r.status_code == 403 and r.json()["code"] == "CSRF", r.text
    r = c.post(path, content=BAD_CSV, headers={**H.fresh(csrf), "Content-Type": "text/csv"})
    assert r.status_code == 400 and r.json()["code"] == "REFUSED", r.text
    # A period that has not finished is refused by the producer's own rule, verbatim.
    r = c.post("/api/cc/listing-outcomes?period_start=2026-10-01&period_end=2099-01-01",
               content=BAD_CSV, headers={**H.fresh(csrf), "Content-Type": "text/csv"})
    assert r.status_code == 400, r.text


def test_brand_fonts_served_allow_listed():
    from brambleloop.brand import identity_system

    css = identity_system.font_face_css("/brand/")
    files = [seg.split("')")[0] for seg in css.split("url('/brand/")[1:]]
    assert files, css
    c = H.client()
    for f in files:
        r = c.get(f"/brand/{f}")
        assert r.status_code == 200 and r.headers["content-type"] == "font/woff", (f, r.status_code)
        assert r.content[:4] == b"wOFF", f
        assert "font-src 'self'" in r.headers.get("content-security-policy", ""), r.headers
    for bad in ("../identity_system.py", "..%2Fidentity_system.py", "nope.woff"):
        assert c.get(f"/brand/fonts/{bad}").status_code == 404, bad


def test_store_tab_surfaces_seo_w3():
    c, _csrf = H.session()
    store = c.get("/api/cc/store").json()
    sec = store["sections"]["seo_w3"]
    assert sec["status"] in ("OK", "DEGRADED", "UNKNOWN"), sec
    if sec["status"] != "UNKNOWN":
        assert {i["part"] for i in sec["items"]} & {"constraints", "strategy"}, sec
    else:
        assert sec["reason"], sec


def test_memory_principal_only_from_verified_session():
    from brambleloop.laura.agency import evidence

    c, _csrf = H.session()
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    ok = evidence.memory(DB, sid, None, tiers=("canonical",))
    assert ok["status"] in ("OK", "UNKNOWN"), ok
    forged = evidence.memory(DB, "not-a-real-session", None, tiers=("canonical",))
    assert forged["status"] == "UNKNOWN" and not forged["facts"], forged
    none = evidence.memory(DB, "", None, tiers=("canonical",))
    assert none["status"] == "UNKNOWN" and not none["facts"], none


if __name__ == "__main__":
    H.run(globals())
