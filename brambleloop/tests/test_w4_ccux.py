"""W4-CCUX: Command Center on a phone -- the /cc redirect, decide-first, long pages, navigation.

* `/cc` -> `/cc/` used Starlette's trailing-slash redirect, which builds an absolute URL from the
  scheme the app sees. Behind Railway's TLS edge that is `http`, so the owner's phone went
  https -> http://host/cc/ -> https. The redirect is now a relative `Location: /cc/` (308),
  resolved by the browser against the URL it actually used: scheme-correct behind any proxy,
  and nothing is taken from a client-supplied Host or X-Forwarded-* header.
* The browser behaviour (decide-first ranking with cost/consequence, collapsible long pages,
  More hints/badges, breadcrumb) is proven in tests/fixtures/cc_mock/check.mjs (run by
  tests/test_v11_pwa_browser.py); this file pins the static wiring so it cannot silently drop.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_ccux.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_ccux_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"

STATIC = ROOT / "src" / "brambleloop" / "app" / "command_center" / "static"
CHECK = ROOT / "tests" / "fixtures" / "cc_mock" / "check.mjs"


def _client(base: str):
    from fastapi.testclient import TestClient

    from brambleloop.app import main

    return TestClient(main.app, base_url=base, raise_server_exceptions=False)


def test_cc_redirect_is_relative_and_never_downgrades_to_http():
    # The app sees plain http (TLS ends at the edge) but the browser used https.
    c = _client("http://app.internal:8080")
    for headers in ({}, {"x-forwarded-proto": "https", "host": "brambleloop.example"},
                    {"x-forwarded-proto": "http"}):
        r = c.get("/cc", headers=headers, follow_redirects=False)
        assert r.status_code == 308, (headers, r.status_code)
        loc = r.headers["location"]
        assert loc == "/cc/", (headers, loc)
        assert "http" not in loc and "//" not in loc, loc
        assert r.headers.get("cache-control") == "no-store"


def test_cc_redirect_keeps_the_query_and_cannot_be_steered():
    c = _client("http://app.internal:8080")
    r = c.get("/cc?from=pwa&x=1", follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == "/cc/?from=pwa&x=1", r.headers
    # A hostile Host / forwarded host never reaches the Location.
    r = c.get("/cc", headers={"host": "evil.example", "x-forwarded-host": "evil.example"},
              follow_redirects=False)
    assert r.headers["location"] == "/cc/", r.headers["location"]
    r = c.head("/cc", follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == "/cc/"
    # Only GET/HEAD redirect; other methods are refused, not bounced to an absolute http URL.
    r = c.post("/cc", follow_redirects=False)
    assert r.status_code == 405 and "location" not in r.headers, (r.status_code, r.headers)


def test_cc_redirect_lands_on_the_shell_with_the_same_scheme():
    c = _client("https://brambleloop.example")
    r = c.get("/cc")
    assert r.status_code == 200 and str(r.url) == "https://brambleloop.example/cc/", r.url
    assert "Brambleloop Command Center" in r.text
    assert "script-src 'self';" in r.headers["content-security-policy"]


def test_trailing_slash_shell_and_api_gate_unchanged():
    c = _client("https://testserver")
    assert c.get("/cc/", follow_redirects=False).status_code == 200
    # No session: refused (401, or 503 while the harness has no ops token configured).
    assert c.get("/api/cc/home").status_code in (401, 503)
    assert c.get("/cc/store-preview", follow_redirects=False).status_code in (401, 503)


def test_new_modules_are_in_the_offline_shell_and_storage_free():
    sw = (STATIC / "sw.js").read_text(encoding="utf-8")
    for rel in ("js/sections.js", "js/views/_decisions.js"):
        assert f'"{rel}"' in sw, rel
    for rel in ("js/sections.js", "js/views/_decisions.js"):
        text = (STATIC / rel).read_text(encoding="utf-8")
        assert not re.search(r"localStorage|sessionStorage|indexedDB|innerHTML", text), rel


def test_app_wires_sections_breadcrumb_and_badges():
    app = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
    assert "enhanceLongPage(node, def.id)" in app
    assert "moreCrumb(def)" in app and "repaintBadges(root)" in app
    routes = (STATIC / "js" / "routes.js").read_text(encoding="utf-8")
    more = [ln for ln in routes.splitlines() if re.search(r'\{ id: "', ln) and "primary: true" not in ln]
    assert more and all("hint:" in ln for ln in more), more


def test_decide_first_ranks_and_never_writes_zero_for_unknown():
    src = (STATIC / "js" / "views" / "_decisions.js").read_text(encoding="utf-8")
    assert "UNKNOWN_TEXT" in src and "?? 0" not in src and "|| 0" not in src
    for view in ("approvals.js", "home.js"):
        text = (STATIC / "js" / "views" / view).read_text(encoding="utf-8")
        assert "rankDecisions(" in text and "decideFirstCard(" in text, view


def test_browser_check_covers_every_ccux_change():
    text = CHECK.read_text(encoding="utf-8")
    for name in ("ccux approvals: Decide first leads", "ccux ranking:", "ccux home: Decide first",
                 "ccux learn: Collapse all", "ccux learn: folding keeps every link",
                 "ccux approvals: folding keeps evidence links", "ccux more: every More item",
                 "ccux more: menu shows the same notifications badge",
                 "ccux nav: More sections show", "ccux nav: desktop uses the sidebar"):
        assert name in text, name


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
            print(f"OK   {t.__name__} {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {str(exc)[:500]}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
